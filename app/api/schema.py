from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str


class UserResponse(BaseModel):
    user_id: int
    username: str


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