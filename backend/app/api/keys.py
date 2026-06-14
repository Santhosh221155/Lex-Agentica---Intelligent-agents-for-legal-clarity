from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime
import secrets, hashlib

from ..db import SessionLocal
from .. import models
from ..security.permissions import require_permission
from ..api.auth import get_current_user

router = APIRouter(prefix="/api/keys", tags=["keys"])


class CreateKeyIn(BaseModel):
    workspace_id: int | None = None
    scopes: list[str] | None = None


class KeyOut(BaseModel):
    id: int
    workspace_id: int | None
    scopes: list[str] | None
    created_at: datetime


@router.post("/create", response_model=dict)
def create_key(payload: CreateKeyIn, user: dict = Depends(require_permission("api_keys.create"))):
    db = SessionLocal()
    try:
        raw_key = secrets.token_urlsafe(40)
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        tenant_id = user.get("tenant_id")
        r = db.execute(models.api_keys.insert().values(
            tenant_id=tenant_id,
            workspace_id=payload.workspace_id,
            key_hash=key_hash,
            scopes=payload.scopes,
            created_by=user.get("id"),
            created_at=datetime.utcnow()
        ).returning(models.api_keys.c.id))
        db.commit()
        kid = int(r.scalar())
        return {"key": raw_key, "id": kid}
    finally:
        db.close()


@router.post("/revoke", status_code=204)
def revoke_key(key_id: int, user: dict = Depends(require_permission("api_keys.revoke"))):
    db = SessionLocal()
    try:
        # soft delete by removing key_hash
        db.execute(models.api_keys.update().where(models.api_keys.c.id == key_id).values(key_hash=None))
        db.commit()
        return {}
    finally:
        db.close()


@router.get("/list", response_model=list[KeyOut])
def list_keys(user: dict = Depends(require_permission("api_keys.list"))):
    db = SessionLocal()
    try:
        tenant_id = user.get("tenant_id")
        rows = db.execute(models.api_keys.select().where(models.api_keys.c.tenant_id == tenant_id)).all()
        result = []
        for r in rows:
            row = dict(r._mapping)
            result.append({
                "id": row.get("id"),
                "workspace_id": row.get("workspace_id"),
                "scopes": row.get("scopes"),
                "created_at": row.get("created_at"),
            })
        return result
    finally:
        db.close()


def verify_api_key(raw_key: str):
    if not raw_key:
        return None
    k = raw_key.strip()
    key_hash = hashlib.sha256(k.encode("utf-8")).hexdigest()
    db = SessionLocal()
    try:
        row = db.execute(models.api_keys.select().where(models.api_keys.c.key_hash == key_hash)).first()
        if not row:
            return None
        return dict(row._mapping)
    finally:
        db.close()
