from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import (
    authenticate_user,
    create_auth_session,
    create_user,
    get_current_user,
    oauth2_scheme,
    revoke_auth_session,
)
from app.api.schema import AuthResponse, RegisterRequest, UserResponse

router = APIRouter()


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(request: RegisterRequest):
    username = request.username.strip()
    if not 3 <= len(username) <= 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username must contain between 3 and 50 non-space characters.",
        )
    try:
        user_id = create_user(username, request.password)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    token = create_auth_session(user_id)
    return {
        "access_token": token,
        "user_id": user_id,
        "username": username,
    }


@router.post("/token", response_model=AuthResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "access_token": create_auth_session(user["id"]),
        "user_id": user["id"],
        "username": user["username"],
    }


@router.get("/me", response_model=UserResponse)
def current_user(user: dict = Depends(get_current_user)):
    return {"user_id": user["id"], "username": user["username"]}


@router.post("/logout", dependencies=[Depends(get_current_user)])
def logout(token: str = Depends(oauth2_scheme)):
    revoke_auth_session(token)
    return {"ok": True}
