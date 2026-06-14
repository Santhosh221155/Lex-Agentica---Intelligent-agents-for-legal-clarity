from typing import Set, Any
from sqlalchemy import select
from .. import models
from ..db import SessionLocal
import json


def _aggregate_permissions_from_roles(db, role_rows) -> Set[str]:
    perms: Set[str] = set()
    for r in role_rows:
        role = dict(r._mapping)
        raw = role.get('permissions')
        if not raw:
            continue
        # permissions may be stored as list or dict in JSON
        if isinstance(raw, list):
            perms.update([str(p) for p in raw])
        elif isinstance(raw, dict):
            # dict mapping permission:true/false
            for k, v in raw.items():
                if v:
                    perms.add(k)
        else:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    perms.update([str(p) for p in parsed])
                elif isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if v:
                            perms.add(k)
            except Exception:
                # unknown format, skip
                pass
    return perms


def get_user_permissions(user_id: int) -> Set[str]:
    db = SessionLocal()
    try:
        # join user_roles -> roles
        q = select(models.roles).select_from(models.user_roles.join(models.roles)).where(models.user_roles.c.user_id == user_id)
        rows = db.execute(q).all()
        return _aggregate_permissions_from_roles(db, rows)
    finally:
        db.close()


def has_permission(user_id: int, permission: str) -> bool:
    perms = get_user_permissions(user_id)
    return permission in perms


def require_permission(permission: str):
    # returns a dependency callable for FastAPI
    from fastapi import Depends, HTTPException
    from . import jwt_util
    from ..api.auth import get_current_user

    def _dep(user: dict = Depends(get_current_user)):
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        user_id = int(user.get('id'))
        # admins bypass permissions
        if user.get('is_admin'):
            return user
        if not has_permission(user_id, permission):
            raise HTTPException(status_code=403, detail="permission_denied")
        return user

    return _dep
