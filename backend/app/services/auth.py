import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext
from sqlalchemy import select, update

from app.models import users, sessions, tenants, workspaces
from app.services.db import get_session_factory


PWD_CONTEXT = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


class DatabaseUnavailableError(Exception):
    pass


def _ensure_db_available() -> None:
    from app.services.db import DATABASE_AVAILABLE
    if not DATABASE_AVAILABLE:
        raise DatabaseUnavailableError("database_unavailable")
JWT_ALG = "HS256"
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME")
ACCESS_TTL_MIN = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TTL_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
ADMIN_EMAILS = [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]


def hash_password(password: str) -> str:
    return PWD_CONTEXT.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return PWD_CONTEXT.verify(password, password_hash)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: int, username: str, is_admin: bool) -> str:
    exp = _now() + timedelta(minutes=ACCESS_TTL_MIN)
    payload = {"sub": str(user_id), "username": username, "is_admin": bool(is_admin), "exp": exp}
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALG)


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def build_refresh_token(session_id: int, raw_token: str) -> str:
    return f"{session_id}.{raw_token}"


def hash_refresh_token(token: str) -> str:
    return PWD_CONTEXT.hash(token)


def verify_refresh_token(token: str, token_hash: str) -> bool:
    return PWD_CONTEXT.verify(token, token_hash)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALG])
    except Exception:
        return None


def is_admin_email(email: str) -> bool:
    return email.lower() in ADMIN_EMAILS if email else False


async def _get_or_create_default_scope():
    _ensure_db_available()
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        tenant_row = await session.execute(select(tenants).where(tenants.c.name == "default"))
        tenant = tenant_row.mappings().first()
        if tenant is None:
            tenant_stmt = tenants.insert().values(name="default")
            tenant_result = await session.execute(tenant_stmt)
            await session.commit()
            tenant_id = tenant_result.inserted_primary_key[0]
        else:
            tenant_id = tenant["id"]

        workspace_row = await session.execute(
            select(workspaces)
            .where(workspaces.c.tenant_id == tenant_id)
            .where(workspaces.c.name == "default")
        )
        workspace = workspace_row.mappings().first()
        if workspace is None:
            workspace_stmt = workspaces.insert().values(tenant_id=tenant_id, name="default", settings={})
            workspace_result = await session.execute(workspace_stmt)
            await session.commit()
            workspace_id = workspace_result.inserted_primary_key[0]
        else:
            workspace_id = workspace["id"]

        return tenant_id, workspace_id


async def get_or_create_local_dev_user():
    _ensure_db_available()
    existing = await get_user_by_username("local")
    if existing is not None:
        return existing

    tenant_id, workspace_id = await _get_or_create_default_scope()
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = users.insert().values(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            username="local",
            email="local@dev",
            password_hash=hash_password(os.getenv("LOCAL_DEV_PASSWORD", "local-dev-pass")),
            is_admin=True,
        )
        result = await session.execute(stmt)
        await session.commit()
        user_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
        return await get_user_by_id(user_id) if user_id else None


async def get_user_by_username(username: str):
    _ensure_db_available()
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        result = await session.execute(select(users).where(users.c.username == username))
        return result.mappings().first()


async def get_user_by_email(email: str):
    _ensure_db_available()
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        result = await session.execute(select(users).where(users.c.email == email))
        return result.mappings().first()


async def get_user_by_id(user_id: int):
    _ensure_db_available()
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        result = await session.execute(select(users).where(users.c.id == user_id))
        return result.mappings().first()


async def create_user(username: str, email: str, password: str):
    _ensure_db_available()
    password_hash = hash_password(password)
    is_admin = is_admin_email(email)
    tenant_id, workspace_id = await _get_or_create_default_scope()
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = users.insert().values(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            username=username,
            email=email,
            password_hash=password_hash,
            is_admin=is_admin,
        )
        result = await session.execute(stmt)
        await session.commit()
        user_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
        return await get_user_by_id(user_id) if user_id else None


async def update_last_login(user_id: int):
    _ensure_db_available()
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        await session.execute(update(users).where(users.c.id == user_id).values(last_login=_now()))
        await session.commit()


async def create_session(user_id: int, refresh_token: str):
    _ensure_db_available()
    expires_at = _now() + timedelta(days=REFRESH_TTL_DAYS)
    token_hash = hash_refresh_token(refresh_token)
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = sessions.insert().values(
            user_id=user_id,
            refresh_token_hash=token_hash,
            expires_at=expires_at,
        )
        result = await session.execute(stmt)
        await session.commit()
        session_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
        return session_id


async def revoke_session(session_id: int):
    _ensure_db_available()
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        await session.execute(update(sessions).where(sessions.c.id == session_id).values(revoked_at=_now()))
        await session.commit()


async def find_session_for_refresh(user_id: int):
    _ensure_db_available()
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        result = await session.execute(
            select(sessions)
            .where(sessions.c.user_id == user_id)
            .where(sessions.c.revoked_at.is_(None))
            .order_by(sessions.c.created_at.desc())
        )
        return result.mappings().first()


async def get_session_by_id(session_id: int):
    _ensure_db_available()
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        result = await session.execute(select(sessions).where(sessions.c.id == session_id))
        return result.mappings().first()


async def find_expired_session_users() -> list[int]:
    """Find user IDs that have ONLY expired/revoked sessions (no active sessions).

    Returns a list of user_ids whose sessions are all expired or revoked,
    meaning they have no valid refresh token remaining.
    """
    _ensure_db_available()
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        now = _now()
        # Find users who have at least one expired/revoked session
        expired_users_stmt = (
            select(sessions.c.user_id)
            .where(sessions.c.user_id.isnot(None))
            .where(
                (sessions.c.expires_at < now) | (sessions.c.revoked_at.isnot(None))
            )
            .distinct()
        )
        expired_res = await session.execute(expired_users_stmt)
        candidate_user_ids = [row[0] for row in expired_res.fetchall()]

        if not candidate_user_ids:
            return []

        # Filter out users who still have at least one active (non-expired, non-revoked) session
        active_users_stmt = (
            select(sessions.c.user_id)
            .where(sessions.c.user_id.in_(candidate_user_ids))
            .where(sessions.c.expires_at >= now)
            .where(sessions.c.revoked_at.is_(None))
            .distinct()
        )
        active_res = await session.execute(active_users_stmt)
        active_user_ids = {row[0] for row in active_res.fetchall()}

        return [uid for uid in candidate_user_ids if uid not in active_user_ids]
