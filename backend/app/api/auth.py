from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError

from app.schemas.auth import TokenResponse
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    build_refresh_token,
    create_session,
    _get_or_create_default_scope,
    get_or_create_local_dev_user,
    decode_token,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    update_last_login,
    verify_password,
    create_user,
    verify_refresh_token,
    revoke_session,
    get_session_by_id,
    DatabaseUnavailableError,
)

try:
    import asyncpg
except Exception:
    asyncpg = None


def _set_auth_cookies(response: JSONResponse, access_token: str, refresh_token: str, is_secure: bool = False) -> JSONResponse:
    """Set httpOnly, Secure, SameSite cookies for JWT tokens."""
    response.set_cookie(
        key="agentic_access_token",
        value=access_token,
        max_age=3600,  # 1 hour
        httponly=True,
        secure=is_secure,
        samesite="lax",
    )
    response.set_cookie(
        key="agentic_refresh_token",
        value=refresh_token,
        max_age=60 * 60 * 24 * 7,  # 7 days
        httponly=True,
        secure=is_secure,
        samesite="lax",
    )
    return response


def _clear_auth_cookies(response: JSONResponse) -> JSONResponse:
    """Clear auth cookies by setting them to empty with max_age=0."""
    response.delete_cookie(key="agentic_access_token", samesite="lax")
    response.delete_cookie(key="agentic_refresh_token", samesite="lax")
    return response


def _is_database_error(exc: Exception) -> bool:
    if isinstance(exc, (DBAPIError, DatabaseUnavailableError)):
        return True
    if asyncpg is not None and isinstance(exc, asyncpg.InvalidPasswordError):
        return True
    return type(exc).__name__ in (
        "InvalidPasswordError",
        "OperationalError",
        "InterfaceError",
        "DatabaseError",
        "UndefinedTableError",
        "NoSuchTableError",
        "ProgrammingError",
    )

router = APIRouter(prefix="/api/auth", tags=["auth"])

DISABLE_AUTH = os.getenv("DISABLE_AUTH", "").strip().lower() in ("1", "true", "yes")

LOCAL_DEV_USER = {
    "id": 1,
    "username": "local",
    "email": "local@dev",
    "is_admin": True,
}


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)


async def _build_local_dev_tokens() -> TokenResponse:
    user = await get_or_create_local_dev_user()
    local_user = dict(user) if user else dict(LOCAL_DEV_USER)
    access = create_access_token(
        user_id=local_user["id"],
        username=local_user["username"],
        is_admin=local_user["is_admin"],
    )
    refresh = build_refresh_token(0, create_refresh_token())
    return TokenResponse(access_token=access, refresh_token=refresh)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_admin: bool = False
    tenant_id: Optional[int] = None
    workspace_id: Optional[int] = None
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None


async def get_current_user(request: Request) -> dict:
    if DISABLE_AUTH:
        user = await get_or_create_local_dev_user()
        return dict(user) if user else dict(LOCAL_DEV_USER)

    api_identity = getattr(request.state, "user", None) or getattr(request.state, "auth_identity", None)
    if api_identity:
        usr = dict(api_identity)
        if usr.get("identity_type") == "api_key":
            usr.setdefault("id", 0)
            usr.setdefault("api_key_id", usr.get("api_key_id") or None)
            usr.setdefault("is_admin", False)
        usr.setdefault("tenant_id", None)
        usr.setdefault("workspace_id", None)
        return usr

    auth_hdr = request.headers.get("authorization")
    if not auth_hdr:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")

    auth_low = auth_hdr.lower()
    if auth_low.startswith("bearer "):
        token = auth_hdr.split(" ", 1)[1]
        payload = decode_token(token)
        if not payload or not payload.get("sub"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")
        try:
            user = await get_user_by_id(int(payload["sub"]))
        except Exception as exc:
            if _is_database_error(exc):
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database_unavailable") from exc
            raise
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")
        return user

    if auth_low.startswith("apikey "):
        try:
            from app.api.keys import verify_api_key
        except Exception:
            verify_api_key = None
        if verify_api_key:
            raw = auth_hdr.split(" ", 1)[1]
            rec = verify_api_key(raw)
            if rec:
                return {
                    "id": f"api_key:{rec.get('id')}",
                    "tenant_id": rec.get("tenant_id"),
                    "workspace_id": rec.get("workspace_id"),
                    "scopes": rec.get("scopes"),
                    "is_admin": False,
                }

    cookie_token = request.cookies.get("agentic_access_token")
    if cookie_token:
        payload = decode_token(cookie_token)
        if not payload or not payload.get("sub"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")
        try:
            user = await get_user_by_id(int(payload["sub"]))
        except Exception as exc:
            if _is_database_error(exc):
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database_unavailable") from exc
            raise
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")
        return user

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")


async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
    return user


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


@router.post("/register", response_model=UserResponse)
async def register(payload: RegisterRequest):
    if DISABLE_AUTH:
        user = await get_or_create_local_dev_user()
        return UserResponse(**dict(user)) if user else UserResponse(**LOCAL_DEV_USER)

    try:
        existing = await get_user_by_username(payload.username)
    except Exception as exc:
        if _is_database_error(exc):
            raise HTTPException(status_code=503, detail="database_unavailable") from exc
        raise
    
    if existing:
        raise HTTPException(status_code=400, detail="username_taken")
    
    try:
        existing_email = await get_user_by_email(payload.email)
    except Exception as exc:
        if _is_database_error(exc):
            raise HTTPException(status_code=503, detail="database_unavailable") from exc
        raise
    
    if existing_email:
        raise HTTPException(status_code=400, detail="email_taken")

    try:
        user = await create_user(payload.username, payload.email, payload.password)
    except Exception as exc:
        if _is_database_error(exc):
            raise HTTPException(status_code=503, detail="database_unavailable") from exc
        raise
    
    if not user:
        raise HTTPException(status_code=500, detail="user_create_failed")
    
    # Automatically log in after registration
    access = create_access_token(user_id=user["id"], username=user["username"], is_admin=bool(user.get("is_admin")))
    raw_refresh = create_refresh_token()
    try:
        session_id = await create_session(user_id=user["id"], refresh_token=raw_refresh)
    except Exception as exc:
        if _is_database_error(exc):
            raise HTTPException(status_code=503, detail="database_unavailable") from exc
        raise
    
    refresh = build_refresh_token(session_id, raw_refresh)
    response = JSONResponse(content=UserResponse(**user).dict())
    return _set_auth_cookies(response, access, refresh)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    if DISABLE_AUTH:
        tokens = await _build_local_dev_tokens()
        response = JSONResponse(content=tokens.dict())
        return _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)

    try:
        user = await get_user_by_username(payload.username)
    except Exception as exc:
        if _is_database_error(exc):
            raise HTTPException(status_code=503, detail="database_unavailable") from exc
        raise

    if not user or not verify_password(payload.password, user.get("password_hash")):
        raise HTTPException(status_code=401, detail="invalid_credentials")

    try:
        await update_last_login(user.get("id"))
    except Exception as exc:
        if _is_database_error(exc):
            raise HTTPException(status_code=503, detail="database_unavailable") from exc
        raise

    access = create_access_token(user_id=user["id"], username=user["username"], is_admin=bool(user.get("is_admin")))
    raw_refresh = create_refresh_token()
    try:
        session_id = await create_session(user_id=user["id"], refresh_token=raw_refresh)
    except Exception as exc:
        if _is_database_error(exc):
            raise HTTPException(status_code=503, detail="database_unavailable") from exc
        raise

    refresh = build_refresh_token(session_id, raw_refresh)
    tokens = TokenResponse(access_token=access, refresh_token=refresh)
    response = JSONResponse(content=tokens.dict())
    return _set_auth_cookies(response, access, refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, request: Request):
    if DISABLE_AUTH:
        tokens = await _build_local_dev_tokens()
        response = JSONResponse(content=tokens.dict())
        return _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)

    refresh_token = payload.refresh_token or request.cookies.get("agentic_refresh_token")
    if not refresh_token or "." not in refresh_token:
        raise HTTPException(status_code=401, detail="invalid_refresh")

    session_id_str, raw_token = refresh_token.split(".", 1)
    if not session_id_str.isdigit():
        raise HTTPException(status_code=401, detail="invalid_refresh")

    try:
        session = await get_session_by_id(int(session_id_str))
    except Exception as exc:
        if _is_database_error(exc):
            raise HTTPException(status_code=503, detail="database_unavailable") from exc
        raise

    if not session or session.get("revoked_at") is not None:
        raise HTTPException(status_code=401, detail="invalid_refresh")
    if session.get("expires_at") and session.get("expires_at") < datetime.now(session.get("expires_at").tzinfo):
        raise HTTPException(status_code=401, detail="refresh_expired")
    if not verify_refresh_token(raw_token, session.get("refresh_token_hash") or ""):
        raise HTTPException(status_code=401, detail="invalid_refresh")

    try:
        user = await get_user_by_id(session.get("user_id"))
    except Exception as exc:
        if _is_database_error(exc):
            raise HTTPException(status_code=503, detail="database_unavailable") from exc
        raise

    if not user:
        raise HTTPException(status_code=401, detail="user_not_found")

    access = create_access_token(user_id=user["id"], username=user["username"], is_admin=bool(user.get("is_admin")))
    new_raw = create_refresh_token()
    try:
        new_session_id = await create_session(user_id=user["id"], refresh_token=new_raw)
    except Exception as exc:
        if _is_database_error(exc):
            raise HTTPException(status_code=503, detail="database_unavailable") from exc
        raise
    await revoke_session(session.get("id"))
    refresh = build_refresh_token(new_session_id, new_raw)

    tokens = TokenResponse(access_token=access, refresh_token=refresh)
    response = JSONResponse(content=tokens.dict())
    return _set_auth_cookies(response, access, refresh)


@router.post("/logout")
async def logout(request: Request, payload: Optional[LogoutRequest] = None):
    refresh_token = payload.refresh_token if payload and payload.refresh_token else request.cookies.get("agentic_refresh_token")

    # Determine user_id before revoking session (for cleanup)
    user_id = None
    if refresh_token and "." in refresh_token:
        session_id_str, _ = refresh_token.split(".", 1)
        if session_id_str.isdigit():
            try:
                session = await get_session_by_id(int(session_id_str))
                if session:
                    user_id = session.get("user_id")
                    await revoke_session(session.get("id"))
            except Exception as exc:
                if _is_database_error(exc):
                    raise HTTPException(status_code=503, detail="database_unavailable") from exc
                raise

    # Clean up user documents on logout (Chroma, PostgreSQL, filesystem)
    # Do NOT delete the user account.
    if user_id is not None:
        try:
            from app.services.document_store import delete_user_documents_hard
            from app.services.cleanup import delete_chroma_chunks, cleanup_temp_files

            await delete_user_documents_hard(user_id)
            delete_chroma_chunks(user_id)
            cleanup_temp_files(user_id)
        except Exception:
            pass  # best-effort cleanup; don't block logout

    response = JSONResponse(content={"status": "ok"})
    return _clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse)
async def me(user: dict = Depends(get_current_user)):
    return UserResponse(**user)
