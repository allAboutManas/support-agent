import logging

from fastapi import APIRouter, HTTPException

from agent.runner import resolve_refund, run_gemini_agent
from app.api.schema import (
    ApprovalRequest,
    ChatRequest,
    ChatResponse,
    ResetRequest,
    ResetResponse,
)


logger = logging.getLogger(__name__)
router = APIRouter()
sessions: dict[str, dict] = {}


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    session = sessions.setdefault(
        request.session_id,
        {"contents": [], "pending_approval": None},
    )
    if session["pending_approval"]:
        raise HTTPException(
            status_code=409,
            detail="Resolve the pending refund approval before sending another message.",
        )

    try:
        result = run_gemini_agent(request.message.strip(), session["contents"])
        session["pending_approval"] = result["pending_approval"]
        return result
    except Exception as error:
        logger.exception("Gemini chat request failed")
        raise HTTPException(
            status_code=502,
            detail="The agent could not respond. Check the server terminal for details.",
        ) from error


@router.post("/approval", response_model=ChatResponse)
def approval(request: ApprovalRequest):
    session = sessions.get(request.session_id)
    if not session or not session["pending_approval"]:
        raise HTTPException(status_code=409, detail="There is no pending approval.")

    pending = session["pending_approval"]
    try:
        result = resolve_refund(
            session["contents"],
            **pending,
            approved=request.approved,
        )
        session["pending_approval"] = result["pending_approval"]
        return result
    except Exception as error:
        logger.exception("Refund approval request failed")
        raise HTTPException(
            status_code=502,
            detail="The agent could not complete the approval. Check the server terminal for details.",
        ) from error


@router.post("/reset", response_model=ResetResponse)
def reset(request: ResetRequest):
    sessions.pop(request.session_id, None)
    return {"ok": True}