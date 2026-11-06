import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "unit-test-key")

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import auth, db
from app.main import app


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path_patch = patch.object(
            db, "DB_PATH", Path(self.temp_dir.name) / "test.db"
        )
        self.db_path_patch.start()
        db.init_db()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_registration_hashes_password_and_login_returns_bearer_token(self):
        with TestClient(app) as client:
            registration = client.post(
                "/api/auth/register",
                json={"username": "alice", "password": "a-strong-password"},
            )
            self.assertEqual(registration.status_code, 201)
            registered = registration.json()

            conn = db.get_db_connection()
            try:
                row = conn.execute(
                    "SELECT password_hash FROM users WHERE id = ?",
                    (registered["user_id"],),
                ).fetchone()
            finally:
                conn.close()
            self.assertNotEqual(row["password_hash"], "a-strong-password")
            self.assertTrue(auth.verify_password("a-strong-password", row["password_hash"]))

            login = client.post(
                "/api/auth/token",
                data={"username": "alice", "password": "a-strong-password"},
            )
            self.assertEqual(login.status_code, 200)
            token = login.json()["access_token"]
            profile = client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
            self.assertEqual(profile.json()["username"], "alice")
            logout = client.post(
                "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
            )
            self.assertEqual(logout.status_code, 200)
            self.assertEqual(
                client.get(
                    "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
                ).status_code,
                401,
            )

    def test_authentication_rejects_bad_credentials_and_duplicate_usernames(self):
        with TestClient(app) as client:
            client.post(
                "/api/auth/register",
                json={"username": "alice", "password": "a-strong-password"},
            )
            duplicate = client.post(
                "/api/auth/register",
                json={"username": "ALICE", "password": "another-password"},
            )
            failed_login = client.post(
                "/api/auth/token",
                data={"username": "alice", "password": "wrong-password"},
            )

        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(failed_login.status_code, 401)

    def test_customer_routes_require_a_valid_bearer_token(self):
        with TestClient(app) as client:
            response = client.post(
                "/api/chat",
                json={"session_id": "session-1", "message": "Check my order"},
            )
            status_response = client.get(
                "/api/chat/status", params={"session_id": "session-1"}
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(status_response.status_code, 401)

    def test_customer_page_contains_login_and_registration_controls(self):
        with TestClient(app) as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="auth-form"', response.text)
        self.assertIn('id="auth-toggle"', response.text)

    def test_expired_or_revoked_tokens_cannot_load_the_user(self):
        user_id = auth.create_user("alice", "a-strong-password")
        token = auth.create_auth_session(user_id)
        self.assertEqual(auth.get_current_user(token)["id"], user_id)

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        conn = db.get_db_connection()
        try:
            conn.execute(
                "UPDATE auth_sessions SET expires_at = 0 WHERE token_hash = ?",
                (token_hash,),
            )
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(HTTPException) as expired:
            auth.get_current_user(token)
        self.assertEqual(expired.exception.status_code, 401)

        token = auth.create_auth_session(user_id)
        auth.revoke_auth_session(token)
        with self.assertRaises(HTTPException) as raised:
            auth.get_current_user(token)
        self.assertEqual(raised.exception.status_code, 401)

    def test_legacy_shared_orders_are_removed_during_migration(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        conn = sqlite3.connect(legacy_path)
        try:
            conn.executescript(
                """
                CREATE TABLE orders (
                    order_id TEXT PRIMARY KEY,
                    item_name TEXT NOT NULL,
                    price REAL NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE refunds (
                    id INTEGER PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES orders (order_id)
                );
                INSERT INTO orders VALUES ('ORD-001', 'Shared item', 10, 'Delivered');
                INSERT INTO refunds VALUES (1, 'ORD-001', 5, 'refunded');
                """
            )
            conn.commit()
        finally:
            conn.close()

        with patch.object(db, "DB_PATH", legacy_path):
            db.init_db()
            conn = db.get_db_connection()
            try:
                order_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
                refund_count = conn.execute(
                    "SELECT COUNT(*) FROM refunds"
                ).fetchone()[0]
                user_id_not_null = next(
                    row["notnull"]
                    for row in conn.execute("PRAGMA table_info(orders)")
                    if row["name"] == "user_id"
                )
            finally:
                conn.close()

        self.assertEqual(order_count, 0)
        self.assertEqual(refund_count, 0)
        self.assertEqual(user_id_not_null, 1)


if __name__ == "__main__":
    unittest.main()
