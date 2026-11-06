import logging
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException

from app.agent.runner import resolve_refund, run_gemini_agent
from app.auth import get_current_user
from app.api.schema import (
    AdminDecisionRequest,
    AdminPendingResponse,
    ChatRequest,
    ChatResponse,
    ResetRequest,
    ResetResponse,
    SessionStatusResponse,
)


logger = logging.getLogger(__name__)
router = APIRouter()
active_sessions: dict[int, dict] = {}
session_lock = Lock()


def _session_state(session_id: str) -> dict:
    session = next(
        (
            candidate
            for candidate in active_sessions.values()
            if candidate["session_id"] == session_id
        ),
        None,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Active chat session not found.")
    return session


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    user_id = user["id"]
    with session_lock:
        session = active_sessions.get(user_id)
        if any(
            candidate["session_id"] == request.session_id
            and candidate["user_id"] != user_id
            for candidate in active_sessions.values()
        ):
            raise HTTPException(
                status_code=409, detail="That chat session is already in use."
            )
        if session is None:
            session = {
                "session_id": request.session_id,
                "user_id": user_id,
                "contents": [],
                "pending_approval": None,
                "status": "active",
                "reply": None,
                "update_id": 0,
            }
            active_sessions[user_id] = session
        elif session["session_id"] != request.session_id:
            raise HTTPException(
                status_code=409,
                detail="A chat is already active for this account. Start a new chat first.",
            )

        if session["pending_approval"]:
            raise HTTPException(
                status_code=409,
                detail="Your refund is waiting for admin approval.",
            )
        if session["status"] == "processing":
            raise HTTPException(status_code=409, detail="The agent is still responding.")
        session["status"] = "processing"

    try:
        result = run_gemini_agent(
            request.message.strip(), session["contents"], user_id
        )
        with session_lock:
            session["pending_approval"] = result["pending_approval"]
            session["status"] = "waiting_for_admin" if result["pending_approval"] else "active"
            session["reply"] = result["reply"]
            session["update_id"] += 1
            return {**result, "update_id": session["update_id"]}
    except Exception as error:
        with session_lock:
            session["status"] = "active"
        logger.exception("Gemini chat request failed")
        raise HTTPException(
            status_code=502,
            detail="The agent could not respond. Check the server terminal for details.",
        ) from error


@router.get("/chat/status", response_model=SessionStatusResponse)
def chat_status(session_id: str, user: dict = Depends(get_current_user)):
    with session_lock:
        session = active_sessions.get(user["id"])
        if not session or session["session_id"] != session_id:
            return {
                "status": "idle",
                "reply": None,
                "pending_approval": None,
                "update_id": 0,
            }
        return {
            "status": session["status"],
            "reply": session["reply"],
            "pending_approval": session["pending_approval"],
            "update_id": session["update_id"],
        }


@router.get("/admin/pending", response_model=AdminPendingResponse)
def admin_pending():
    with session_lock:
        sessions = list(active_sessions.values())
        if not sessions:
            return {"session_id": None, "status": "idle", "pending_approval": None}
        session = next(
            (
                candidate
                for candidate in sessions
                if candidate["status"] == "waiting_for_admin"
            ),
            sessions[0],
        )
        return {
            "session_id": session["session_id"],
            "status": session["status"],
            "pending_approval": session["pending_approval"],
        }


@router.post("/admin/decision", response_model=ChatResponse)
def admin_decision(request: AdminDecisionRequest):
    with session_lock:
        session = _session_state(request.session_id)
        if session["status"] != "waiting_for_admin" or not session["pending_approval"]:
            raise HTTPException(status_code=409, detail="There is no pending approval.")

        pending = session["pending_approval"]
        session["pending_approval"] = None
        session["status"] = "processing"

    try:
        result = resolve_refund(
            session["contents"],
            **pending,
            approved=request.approved,
            user_id=session["user_id"],
        )
        with session_lock:
            session["pending_approval"] = result["pending_approval"]
            session["status"] = "waiting_for_admin" if result["pending_approval"] else "active"
            session["reply"] = result["reply"]
            session["update_id"] += 1
            return {**result, "update_id": session["update_id"]}
    except Exception as error:
        with session_lock:
            session["pending_approval"] = pending
            session["status"] = "waiting_for_admin"
        logger.exception("Refund approval request failed")
        raise HTTPException(
            status_code=502,
            detail="The agent could not complete the approval. Check the server terminal for details.",
        ) from error


@router.post("/reset", response_model=ResetResponse)
def reset(request: ResetRequest, user: dict = Depends(get_current_user)):
    with session_lock:
        session = active_sessions.get(user["id"])
        if session and session["session_id"] != request.session_id:
            raise HTTPException(status_code=409, detail="That chat session is not active.")
        active_sessions.pop(user["id"], None)
    return {"ok": True}