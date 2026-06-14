from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.auth import get_current_user, get_admin_user
from app.services.document_store import (
    create_document,
    list_documents,
    get_document,
    update_document,
    soft_delete_document,
    list_chunks,
    list_audits,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentCreate(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    source: str = Field(default="manual", max_length=255)
    metadata: Optional[Dict[str, Any]] = None


class DocumentUpdate(BaseModel):
    status: Optional[str] = Field(None, max_length=32)
    metadata: Optional[Dict[str, Any]] = None
    source: Optional[str] = Field(None, max_length=255)
    filename: Optional[str] = Field(None, max_length=255)


@router.post("")
async def create_doc(payload: DocumentCreate, user: dict = Depends(get_current_user)):
    doc = await create_document(owner_id=user.get("id"), filename=payload.filename, source=payload.source, metadata=payload.metadata)
    if not doc:
        raise HTTPException(status_code=500, detail="document_create_failed")
    return doc


@router.get("")
async def list_docs(include_deleted: bool = Query(False), user: dict = Depends(get_current_user)):
    return await list_documents(owner_id=user.get("id"), include_deleted=include_deleted)


@router.get("/{document_id}")
async def get_doc(document_id: int, user: dict = Depends(get_current_user)):
    doc = await get_document(document_id, user.get("id"))
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")
    return doc


@router.patch("/{document_id}")
async def update_doc(document_id: int, payload: DocumentUpdate, user: dict = Depends(get_current_user)):
    doc = await update_document(document_id, user.get("id"), payload.model_dump(exclude_none=True))
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")
    return doc


@router.delete("/{document_id}")
async def delete_doc(document_id: int, user: dict = Depends(get_current_user)):
    doc = await soft_delete_document(document_id, user.get("id"))
    if not doc:
        raise HTTPException(status_code=404, detail="not_found")
    return {"status": "deleted", "document": doc}


@router.get("/{document_id}/chunks")
async def get_chunks(document_id: int, user: dict = Depends(get_current_user)):
    return await list_chunks(document_id, user.get("id"))


@router.get("/{document_id}/audits")
async def get_audits(document_id: int, user: dict = Depends(get_current_user)):
    return await list_audits(document_id, user.get("id"))


@router.get("/admin/all")
async def admin_list_docs(include_deleted: bool = Query(False), user: dict = Depends(get_admin_user)):
    # For admin, list all docs by passing owner_id=None is not supported. Use direct DB query in future.
    raise HTTPException(status_code=501, detail="admin_list_not_implemented")
