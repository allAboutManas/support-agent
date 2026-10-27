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


class ApprovalRequest(BaseModel):
    session_id: str
    approved: bool


class ResetRequest(BaseModel):
    session_id: str


class ResetResponse(BaseModel):
    ok: bool