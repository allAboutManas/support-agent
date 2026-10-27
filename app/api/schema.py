from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: str
    message: str


class PendingApproval(BaseModel):
    order_id: str
    amount: float


class ChatResponse(BaseModel):
    reply: str
    pending_approval: PendingApproval | None = None
    update_id: int


class AdminDecisionRequest(BaseModel):
    session_id: str
    approved: bool


class ResetRequest(BaseModel):
    session_id: str


class ResetResponse(BaseModel):
    ok: bool


class SessionStatusResponse(BaseModel):
    status: str
    reply: str | None = None
    pending_approval: PendingApproval | None = None
    update_id: int


class AdminPendingResponse(BaseModel):
    session_id: str | None = None
    status: str
    pending_approval: PendingApproval | None = None