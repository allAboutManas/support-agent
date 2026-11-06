import hashlib
import hmac
import secrets
import sqlite3
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.db import get_db_connection

PASSWORD_HASH_ITERATIONS = 600_000
AUTH_SESSION_TTL_SECONDS = 8 * 60 * 60
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
    )
    return f"pbkdf2_sha256${salt.hex()}${password_hash.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt_hex, expected_hash = password_hash.split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return False
        actual_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            PASSWORD_HASH_ITERATIONS,
        ).hex()
    except ValueError:
        return False
    return hmac.compare_digest(actual_hash, expected_hash)


def create_user(username: str, password: str) -> int:
    normalized_username = username.strip()
    password_hash = hash_password(password)
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (normalized_username, password_hash),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as error:
        raise ValueError("Username is already registered.") from error
    finally:
        conn.close()


def authenticate_user(username: str, password: str):
    conn = get_db_connection()
    try:
        user = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    finally:
        conn.close()
    if user is None or not verify_password(password, user["password_hash"]):
        return None
    return {"id": user["id"], "username": user["username"]}


def create_auth_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, expires_at) "
            "VALUES (?, ?, ?)",
            (token_hash, user_id, time.time() + AUTH_SESSION_TTL_SECONDS),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def get_current_user(token: str = Depends(oauth2_scheme)):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = get_db_connection()
    try:
        user = conn.execute(
            """
            SELECT users.id, users.username
            FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ? AND auth_sessions.expires_at > ?
            """,
            (token_hash, time.time()),
        ).fetchone()
        if user is None:
            conn.execute(
                "DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,)
            )
            conn.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired login session.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {"id": user["id"], "username": user["username"]}
    finally:
        conn.close()


def revoke_auth_session(token: str) -> None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))
        conn.commit()
    finally:
        conn.close()
