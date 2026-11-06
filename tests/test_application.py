import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("GEMINI_API_KEY", "unit-test-key")

from fastapi import HTTPException

from app import auth, db
from app.agent import policies, runner
from app.api import routes
from app.api.schema import AdminDecisionRequest, ChatRequest, ResetRequest
from app.tools import orders, refunds


class DatabaseAndToolTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path_patch = patch.object(
            db, "DB_PATH", Path(self.temp_dir.name) / "test.db"
        )
        self.db_path_patch.start()
        with patch("builtins.print"):
            db.init_db()
        self.user_id = auth.create_user("test-user", "test-password")
        conn = db.get_db_connection()
        try:
            conn.execute(
                """
                INSERT INTO orders (order_id, user_id, item_name, price, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("ORD-001", self.user_id, "iPhone 18 Pro", 180000, "Delivered"),
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_init_db_creates_seed_orders_and_is_idempotent(self):
        with patch("builtins.print"):
            db.init_db()

        conn = db.get_db_connection()
        try:
            orders_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            refunds_count = conn.execute("SELECT COUNT(*) FROM refunds").fetchone()[0]
        finally:
            conn.close()

        self.assertEqual(orders_count, 1)
        self.assertEqual(refunds_count, 0)

    def test_search_database_returns_order_details_and_trims_id(self):
        result = orders.search_database(" ORD-001 ", self.user_id)

        self.assertEqual(
            result,
            {
                "order_id": "ORD-001",
                "item": "iPhone 18 Pro",
                "price": 180000,
                "status": "Delivered",
            },
        )

    def test_search_database_reports_missing_order(self):
        self.assertEqual(
            orders.search_database("UNKNOWN", self.user_id),
            "Order with id 'UNKNOWN' was not found",
        )

    def test_issue_refund_records_refunded_status(self):
        result = refunds.issue_refund("ORD-001", 25.0, self.user_id)

        self.assertEqual(
            result,
            "Success: Your refund of amount $25.0 is issued for ORD-001.",
        )
        conn = db.get_db_connection()
        try:
            row = conn.execute(
                "SELECT order_id, amount, status FROM refunds"
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(
            tuple(row),
            ("ORD-001", 25.0, "refunded"),
        )

    def test_issue_refund_does_not_record_missing_order(self):
        result = refunds.issue_refund("UNKNOWN", 25.0, self.user_id)

        self.assertEqual(result, "Error: Order UNKNOWN does not exist")
        conn = db.get_db_connection()
        try:
            count = conn.execute("SELECT COUNT(*) FROM refunds").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 0)

    def test_issue_refund_rolls_back_and_closes_connection_on_database_error(self):
        connection = MagicMock()
        connection.cursor.return_value.execute.side_effect = sqlite3.OperationalError(
            "database unavailable"
        )

        with patch.object(refunds, "get_db_connection", return_value=connection):
            result = refunds.issue_refund("ORD-001", 25.0, self.user_id)

        self.assertEqual(
            result,
            "Error: Unable to issue refund for ORD-001: database unavailable",
        )
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()

    def test_orders_and_refunds_are_scoped_to_the_owner(self):
        other_user_id = auth.create_user("other-user", "other-password")
        self.assertIn("not found", orders.search_database("ORD-001", other_user_id))
        self.assertIn(
            "does not exist",
            refunds.issue_refund("ORD-001", 25.0, other_user_id),
        )

    def test_refund_cannot_exceed_the_order_price(self):
        result = refunds.issue_refund("ORD-001", 180001.0, self.user_id)

        self.assertIn("must be between", result)


class RefundPolicyTests(unittest.TestCase):
    def test_amount_at_or_below_threshold_does_not_require_approval(self):
        self.assertFalse(policies.requires_refund_approval(0))
        self.assertFalse(policies.requires_refund_approval(50.0))

    def test_amount_above_threshold_requires_approval(self):
        self.assertTrue(policies.requires_refund_approval(50.01))


class AgentRunnerTests(unittest.TestCase):
    @staticmethod
    def response(function_calls=None, text=None):
        return SimpleNamespace(
            function_calls=function_calls or [],
            candidates=[SimpleNamespace(content=object())],
            text=text,
        )

    def test_run_agent_returns_text_response(self):
        with patch(
            "app.agent.runner.client.models.generate_content",
            return_value=self.response(text="How can I help?"),
        ):
            result = runner.run_gemini_agent("Hello", [], user_id=1)

        self.assertEqual(result, {"reply": "How can I help?", "pending_approval": None})

    def test_run_agent_requests_admin_approval_for_large_refund(self):
        function_call = SimpleNamespace(
            name="issue_refund",
            args={"order_id": "ORD-001", "amount": 75},
        )
        with (
            patch(
                "app.agent.runner.client.models.generate_content",
                return_value=self.response([function_call]),
            ),
            patch("app.agent.runner.issue_refund") as issue_refund,
        ):
            result = runner.run_gemini_agent("Refund my order", [], user_id=1)

        self.assertEqual(
            result,
            {
                "reply": "Your refund request was sent to an admin for review.",
                "pending_approval": {"order_id": "ORD-001", "amount": 75.0},
            },
        )
        issue_refund.assert_not_called()

    def test_run_agent_executes_small_refund_then_returns_final_reply(self):
        function_call = SimpleNamespace(
            name="issue_refund",
            args={"order_id": "ORD-001", "amount": 25},
        )
        responses = [
            self.response([function_call]),
            self.response(text="Refund issued."),
        ]
        with (
            patch(
                "app.agent.runner.client.models.generate_content",
                side_effect=responses,
            ),
            patch(
                "app.agent.runner.issue_refund",
                return_value="Refund recorded.",
            ) as issue_refund,
        ):
            result = runner.run_gemini_agent("Refund my order", [], user_id=1)

        self.assertEqual(result, {"reply": "Refund issued.", "pending_approval": None})
        issue_refund.assert_called_once_with(
            order_id="ORD-001", amount=25, user_id=1
        )

    def test_run_agent_reports_unknown_function_to_model(self):
        function_call = SimpleNamespace(name="not_registered", args={})
        responses = [
            self.response([function_call]),
            self.response(text="Done."),
        ]
        with patch(
            "app.agent.runner.client.models.generate_content",
            side_effect=responses,
        ) as generate_content:
            result = runner.run_gemini_agent("Do something", [], user_id=1)

        self.assertEqual(result, {"reply": "Done.", "pending_approval": None})
        self.assertEqual(generate_content.call_count, 2)

    def test_run_agent_stops_after_llm_iteration_limit(self):
        function_call = SimpleNamespace(
            name="issue_refund",
            args={"order_id": "ORD-001", "amount": 25},
        )
        with (
            patch("app.agent.runner.MAX_LLM_ITERATIONS", 2),
            patch(
                "app.agent.runner.client.models.generate_content",
                return_value=self.response([function_call]),
            ) as generate_content,
            patch(
                "app.agent.runner.issue_refund",
                return_value="Refund recorded.",
            ) as issue_refund,
        ):
            result = runner.run_gemini_agent("Refund my order", [], user_id=1)

        self.assertEqual(result["reply"], runner.ITERATION_LIMIT_REPLY)
        self.assertIsNone(result["pending_approval"])
        self.assertEqual(generate_content.call_count, 2)
        self.assertEqual(issue_refund.call_count, 2)

    def test_run_agent_stops_after_tool_iteration_limit(self):
        function_call = SimpleNamespace(
            name="issue_refund",
            args={"order_id": "ORD-001", "amount": 25},
        )
        with (
            patch("app.agent.runner.MAX_LLM_ITERATIONS", 5),
            patch("app.agent.runner.MAX_TOOL_ITERATIONS", 1),
            patch(
                "app.agent.runner.client.models.generate_content",
                return_value=self.response([function_call]),
            ) as generate_content,
            patch(
                "app.agent.runner.issue_refund",
                return_value="Refund recorded.",
            ) as issue_refund,
        ):
            result = runner.run_gemini_agent("Refund my order", [], user_id=1)

        self.assertEqual(result["reply"], runner.ITERATION_LIMIT_REPLY)
        self.assertIsNone(result["pending_approval"])
        self.assertEqual(generate_content.call_count, 2)
        issue_refund.assert_called_once_with(
            order_id="ORD-001", amount=25, user_id=1
        )

    def test_resolve_refund_issues_approved_refund(self):
        with (
            patch("app.agent.runner.issue_refund", return_value="Refund recorded.") as issue,
            patch(
                "app.agent.runner.client.models.generate_content",
                return_value=self.response(text="Refund approved."),
            ),
        ):
            result = runner.resolve_refund([], "ORD-001", 75.0, approved=True, user_id=1)

        self.assertEqual(result, {"reply": "Refund approved.", "pending_approval": None})
        issue.assert_called_once_with(order_id="ORD-001", amount=75.0, user_id=1)

    def test_resolve_refund_does_not_issue_rejected_refund(self):
        with (
            patch("app.agent.runner.issue_refund") as issue,
            patch(
                "app.agent.runner.client.models.generate_content",
                return_value=self.response(text="Request rejected."),
            ),
        ):
            result = runner.resolve_refund([], "ORD-001", 75.0, approved=False, user_id=1)

        self.assertEqual(result, {"reply": "Request rejected.", "pending_approval": None})
        issue.assert_not_called()


class ApiRouteTests(unittest.TestCase):
    def setUp(self):
        routes.active_sessions.clear()
        self.user = {"id": 1, "username": "test-user"}
        self.other_user = {"id": 2, "username": "other-user"}

    def tearDown(self):
        routes.active_sessions.clear()

    def test_chat_rejects_empty_message(self):
        with self.assertRaises(HTTPException) as raised:
            routes.chat(
                ChatRequest(session_id="session-1", message="  "), user=self.user
            )

        self.assertEqual(raised.exception.status_code, 400)

    def test_chat_creates_session_and_returns_agent_result(self):
        with patch(
            "app.api.routes.run_gemini_agent",
            return_value={"reply": "Hello!", "pending_approval": None},
        ) as run_agent:
            result = routes.chat(
                ChatRequest(session_id="session-1", message="  Hi  "),
                user=self.user,
            )

        self.assertEqual(
            result,
            {"reply": "Hello!", "pending_approval": None, "update_id": 1},
        )
        session = routes.active_sessions[self.user["id"]]
        run_agent.assert_called_once_with("Hi", session["contents"], self.user["id"])
        self.assertEqual(session["status"], "active")

    def test_chat_rejects_another_active_session(self):
        routes.active_sessions[self.user["id"]] = {"session_id": "session-1"}

        with self.assertRaises(HTTPException) as raised:
            routes.chat(
                ChatRequest(session_id="session-2", message="Hi"), user=self.user
            )

        self.assertEqual(raised.exception.status_code, 409)

    def test_chat_sessions_are_independent_per_user(self):
        with patch(
            "app.api.routes.run_gemini_agent",
            return_value={"reply": "Hello!", "pending_approval": None},
        ) as run_agent:
            routes.chat(ChatRequest(session_id="session-1", message="Hi"), self.user)
            routes.chat(
                ChatRequest(session_id="session-2", message="Hello"),
                self.other_user,
            )

        self.assertEqual(len(routes.active_sessions), 2)
        self.assertEqual(run_agent.call_args_list[0].args[2], self.user["id"])
        self.assertEqual(run_agent.call_args_list[1].args[2], self.other_user["id"])

    def test_chat_rejects_request_while_approval_is_pending(self):
        routes.active_sessions[self.user["id"]] = {
            "session_id": "session-1",
            "user_id": self.user["id"],
            "contents": [],
            "pending_approval": {"order_id": "ORD-001", "amount": 75.0},
            "status": "waiting_for_admin",
        }

        with self.assertRaises(HTTPException) as raised:
            routes.chat(
                ChatRequest(session_id="session-1", message="Another request"),
                user=self.user,
            )

        self.assertEqual(raised.exception.status_code, 409)

    def test_chat_returns_gateway_error_and_restores_active_status_on_failure(self):
        with self.assertLogs("app.api.routes", level="ERROR"):
            with (
                patch(
                    "app.api.routes.run_gemini_agent",
                    side_effect=RuntimeError("agent failed"),
                ),
                self.assertRaises(HTTPException) as raised,
            ):
                routes.chat(
                    ChatRequest(session_id="session-1", message="Hi"),
                    user=self.user,
                )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(
            routes.active_sessions[self.user["id"]]["status"], "active"
        )

    def test_chat_status_returns_idle_for_unknown_session(self):
        self.assertEqual(
            routes.chat_status("unknown", user=self.user),
            {
                "status": "idle",
                "reply": None,
                "pending_approval": None,
                "update_id": 0,
            },
        )

    def test_chat_status_returns_active_session_state(self):
        routes.active_sessions[self.user["id"]] = {
            "session_id": "session-1",
            "status": "active",
            "reply": "Hello",
            "pending_approval": None,
            "update_id": 3,
        }

        self.assertEqual(
            routes.chat_status("session-1", user=self.user),
            {
                "status": "active",
                "reply": "Hello",
                "pending_approval": None,
                "update_id": 3,
            },
        )

    def test_chat_status_does_not_expose_another_users_session(self):
        routes.active_sessions[self.other_user["id"]] = {
            "session_id": "other-session",
            "status": "active",
            "reply": "Private reply",
            "pending_approval": None,
            "update_id": 1,
        }

        self.assertEqual(
            routes.chat_status("other-session", user=self.user)["status"], "idle"
        )

    def test_admin_pending_returns_idle_without_session(self):
        self.assertEqual(
            routes.admin_pending(),
            {"session_id": None, "status": "idle", "pending_approval": None},
        )

    def test_admin_pending_returns_current_approval(self):
        pending = {"order_id": "ORD-001", "amount": 75.0}
        routes.active_sessions[self.user["id"]] = {
            "session_id": "session-1",
            "user_id": self.user["id"],
            "status": "waiting_for_admin",
            "pending_approval": pending,
        }

        self.assertEqual(
            routes.admin_pending(),
            {
                "session_id": "session-1",
                "status": "waiting_for_admin",
                "pending_approval": pending,
            },
        )

    def test_admin_decision_requires_existing_session(self):
        with self.assertRaises(HTTPException) as raised:
            routes.admin_decision(
                AdminDecisionRequest(session_id="unknown", approved=True)
            )

        self.assertEqual(raised.exception.status_code, 404)

    def test_admin_decision_requires_pending_approval(self):
        routes.active_sessions[self.user["id"]] = {
            "session_id": "session-1",
            "user_id": self.user["id"],
            "status": "active",
            "pending_approval": None,
        }

        with self.assertRaises(HTTPException) as raised:
            routes.admin_decision(
                AdminDecisionRequest(session_id="session-1", approved=True)
            )

        self.assertEqual(raised.exception.status_code, 409)

    def test_admin_approval_resolves_and_clears_pending_refund(self):
        pending = {"order_id": "ORD-001", "amount": 75.0}
        routes.active_sessions[self.user["id"]] = {
            "session_id": "session-1",
            "user_id": self.user["id"],
            "contents": [],
            "pending_approval": pending,
            "status": "waiting_for_admin",
            "reply": None,
            "update_id": 2,
        }
        with patch(
            "app.api.routes.resolve_refund",
            return_value={"reply": "Refund approved.", "pending_approval": None},
        ) as resolve:
            result = routes.admin_decision(
                AdminDecisionRequest(session_id="session-1", approved=True)
            )

        resolve.assert_called_once_with(
            routes.active_sessions[self.user["id"]]["contents"],
            order_id="ORD-001",
            amount=75.0,
            approved=True,
            user_id=self.user["id"],
        )
        self.assertEqual(
            result,
            {"reply": "Refund approved.", "pending_approval": None, "update_id": 3},
        )
        self.assertEqual(
            routes.active_sessions[self.user["id"]]["status"], "active"
        )
        self.assertIsNone(
            routes.active_sessions[self.user["id"]]["pending_approval"]
        )

    def test_admin_rejection_is_forwarded_to_refund_resolution(self):
        routes.active_sessions[self.user["id"]] = {
            "session_id": "session-1",
            "user_id": self.user["id"],
            "contents": [],
            "pending_approval": {"order_id": "ORD-001", "amount": 75.0},
            "status": "waiting_for_admin",
            "reply": None,
            "update_id": 0,
        }
        with patch(
            "app.api.routes.resolve_refund",
            return_value={"reply": "Refund rejected.", "pending_approval": None},
        ) as resolve:
            routes.admin_decision(
                AdminDecisionRequest(session_id="session-1", approved=False)
            )

        self.assertFalse(resolve.call_args.kwargs["approved"])

    def test_admin_decision_restores_pending_approval_on_failure(self):
        pending = {"order_id": "ORD-001", "amount": 75.0}
        routes.active_sessions[self.user["id"]] = {
            "session_id": "session-1",
            "user_id": self.user["id"],
            "contents": [],
            "pending_approval": pending,
            "status": "waiting_for_admin",
            "reply": None,
            "update_id": 0,
        }
        with self.assertLogs("app.api.routes", level="ERROR"):
            with (
                patch(
                    "app.api.routes.resolve_refund",
                    side_effect=RuntimeError("resolution failed"),
                ),
                self.assertRaises(HTTPException) as raised,
            ):
                routes.admin_decision(
                    AdminDecisionRequest(session_id="session-1", approved=True)
                )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(
            routes.active_sessions[self.user["id"]]["status"], "waiting_for_admin"
        )
        self.assertEqual(
            routes.active_sessions[self.user["id"]]["pending_approval"], pending
        )

    def test_reset_clears_current_session(self):
        routes.active_sessions[self.user["id"]] = {"session_id": "session-1"}

        result = routes.reset(
            ResetRequest(session_id="session-1"), user=self.user
        )

        self.assertEqual(result, {"ok": True})
        self.assertNotIn(self.user["id"], routes.active_sessions)

    def test_reset_rejects_different_session(self):
        routes.active_sessions[self.user["id"]] = {"session_id": "session-1"}

        with self.assertRaises(HTTPException) as raised:
            routes.reset(ResetRequest(session_id="session-2"), user=self.user)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(
            routes.active_sessions[self.user["id"]]["session_id"], "session-1"
        )


if __name__ == "__main__":
    unittest.main()
