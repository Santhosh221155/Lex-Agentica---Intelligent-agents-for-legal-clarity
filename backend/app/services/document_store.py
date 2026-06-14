from datetime import datetime
import os
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update, text

from app.models import documents, chunks, embeddings, ingestion_jobs, document_audits
from app.services.db import get_session_factory, DATABASE_BACKEND
from app.observability import log_event


# NOTE:
# asyncpg + Postgres timestamptz/timestamp mismatch can raise:
#   can't subtract offset-naive and offset-aware datetimes
# This code previously used timezone-aware UTC datetimes.
# Use a timezone-naive UTC timestamp for compatibility with the DB column type.
def _now():
    return datetime.utcnow()


async def create_document(owner_id: int, filename: str, source: str = "upload", metadata: Optional[Dict[str, Any]] = None, tenant_id: Optional[int] = None, workspace_id: Optional[int] = None):
    if tenant_id is None or workspace_id is None:
        from app.services.auth import _get_or_create_default_scope

        default_tenant, default_workspace = await _get_or_create_default_scope()
        tenant_id = tenant_id if tenant_id is not None else default_tenant
        workspace_id = workspace_id if workspace_id is not None else default_workspace

    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        values = {
            "owner_id": owner_id,
            "title": filename,
            "source_uri": source,
            "metadata": metadata or {},
            "status": "active",
            "soft_deleted": False,
        }
        if tenant_id is not None:
            values["tenant_id"] = tenant_id
        if workspace_id is not None:
            values["workspace_id"] = workspace_id

        stmt = documents.insert().values(**values)
        res = await session.execute(stmt)
        await session.commit()
        doc_id = res.inserted_primary_key[0] if res.inserted_primary_key else None
        if doc_id:
            await log_document_audit(doc_id, owner_id, "create", None, {"title": filename, "source_uri": source})
        return await get_document(doc_id, owner_id)


async def get_document(document_id: int, owner_id: int):
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = select(documents).where(documents.c.id == document_id).where(documents.c.owner_id == owner_id)
        res = await session.execute(stmt)
        return res.mappings().first()


async def list_documents(owner_id: int, include_deleted: bool = False) -> List[Dict[str, Any]]:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = select(documents).where(documents.c.owner_id == owner_id)
        if not include_deleted:
            stmt = stmt.where(documents.c.soft_deleted.is_(False))
        res = await session.execute(stmt)
        return res.mappings().all()


async def update_document(document_id: int, owner_id: int, updates: Dict[str, Any]):
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        before = await session.execute(
            select(documents).where(documents.c.id == document_id).where(documents.c.owner_id == owner_id)
        )
        before_row = before.mappings().first()
        if not before_row:
            return None

        safe_updates = {}
        if "status" in updates:
            safe_updates["status"] = updates["status"]
        if "metadata" in updates:
            safe_updates["metadata"] = updates["metadata"]
        if "source" in updates:
            safe_updates["source_uri"] = updates["source"]
        if "filename" in updates:
            safe_updates["title"] = updates["filename"]
        if not safe_updates:
            return before_row

        await session.execute(
            update(documents)
            .where(documents.c.id == document_id)
            .where(documents.c.owner_id == owner_id)
            .values(**safe_updates)
        )
        await session.commit()
        await log_document_audit(document_id, owner_id, "update", dict(before_row), safe_updates)
        return await get_document(document_id, owner_id)


async def soft_delete_document(document_id: int, owner_id: int):
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        before = await session.execute(
            select(documents).where(documents.c.id == document_id).where(documents.c.owner_id == owner_id)
        )
        before_row = before.mappings().first()
        if not before_row:
            return None

        await session.execute(
            update(documents)
            .where(documents.c.id == document_id)
            .where(documents.c.owner_id == owner_id)
            .values(status="deleted", soft_deleted=True)
        )
        await session.commit()
        await log_document_audit(document_id, owner_id, "soft_delete", dict(before_row), {"status": "deleted"})
        return await get_document(document_id, owner_id)


async def create_ingestion_job(owner_id: int, document_id: Optional[int] = None, tenant_id: Optional[int] = None, workspace_id: Optional[int] = None):
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        if tenant_id is None or workspace_id is None:
            from app.services.auth import _get_or_create_default_scope, get_user_by_id

            if owner_id is not None:
                owner = await get_user_by_id(owner_id)
                if owner is not None:
                    if tenant_id is None:
                        tenant_id = owner.get("tenant_id")
                    if workspace_id is None:
                        workspace_id = owner.get("workspace_id")

            if tenant_id is None or workspace_id is None:
                default_tenant_id, default_workspace_id = await _get_or_create_default_scope()
                if tenant_id is None:
                    tenant_id = default_tenant_id
                if workspace_id is None:
                    workspace_id = default_workspace_id

        values = {
            "owner_id": owner_id,
            "document_id": document_id,
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "status": "queued",
        }
        stmt = ingestion_jobs.insert().values(**values)
        res = await session.execute(stmt)
        await session.commit()
        return res.inserted_primary_key[0] if res.inserted_primary_key else None


async def update_ingestion_job(job_id: int, status: str, error: Optional[str] = None):
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        await session.execute(
            update(ingestion_jobs)
            .where(ingestion_jobs.c.id == job_id)
            .values(status=status, error=error, completed_at=_now() if status in {"completed", "failed"} else None)
        )
        await session.commit()


async def log_document_audit(document_id: int, actor_id: Optional[int], action: str, before: Any, after: Any):
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = document_audits.insert().values(
            document_id=document_id,
            actor_id=actor_id,
            action=action,
            before=before,
            after=after,
        )
        await session.execute(stmt)
        await session.commit()


async def add_chunks(document_id: int, chunk_rows: List[Dict[str, Any]]):
    if not chunk_rows:
        return
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        await session.execute(chunks.insert(), chunk_rows)
        await session.commit()


async def add_embeddings(embedding_rows: List[Dict[str, Any]]):
    if not embedding_rows:
        return
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        await session.execute(embeddings.insert(), embedding_rows)
        await session.commit()


async def list_chunks(document_id: int, owner_id: int) -> List[Dict[str, Any]]:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = (
            select(chunks)
            .select_from(chunks.join(documents, chunks.c.document_id == documents.c.id))
            .where(chunks.c.document_id == document_id)
            .where(documents.c.owner_id == owner_id)
        )
        res = await session.execute(stmt)
        return res.mappings().all()


async def list_user_chunks(owner_id: int) -> List[Dict[str, Any]]:
    started = time.time()
    session_wait_start = time.time()
    log_event("retrieval.list_user_chunks.enter", owner_id=owner_id)
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        session_acquired_at = time.time()
        session_wait_ms = round((session_acquired_at - session_wait_start) * 1000, 2)

        stmt = (
            select(
                chunks,
                documents.c.owner_id.label("owner_id"),
                documents.c.source_uri.label("document_source"),
                documents.c.metadata.label("document_metadata"),
                documents.c.title.label("document_filename"),
            )
            .select_from(chunks.join(documents, chunks.c.document_id == documents.c.id))
            .where(documents.c.owner_id == owner_id)
            .where(documents.c.soft_deleted.is_(False))
        )

        explain_enabled = os.getenv("RETRIEVAL_BM25_EXPLAIN", "0").strip().lower() in {"1", "true", "yes"}
        if explain_enabled:
            try:
                if DATABASE_BACKEND == "postgres":
                    explain_sql = text(
                        "EXPLAIN (ANALYZE, BUFFERS, VERBOSE) "
                        "SELECT c.*, d.owner_id AS owner_id, d.source_uri AS document_source, d.metadata AS document_metadata, d.title AS document_filename "
                        "FROM chunks c JOIN documents d ON c.document_id = d.id "
                        "WHERE d.owner_id = :owner_id AND d.soft_deleted IS FALSE"
                    )
                    plan_res = await session.execute(explain_sql, {"owner_id": owner_id})
                    plan_lines = [row[0] for row in plan_res.fetchall()]
                    log_event("retrieval.list_user_chunks.explain", owner_id=owner_id, backend=DATABASE_BACKEND, plan=plan_lines[:20])
                elif DATABASE_BACKEND == "sqlite":
                    explain_sql = text(
                        "EXPLAIN QUERY PLAN "
                        "SELECT c.*, d.owner_id AS owner_id, d.source_uri AS document_source, d.metadata AS document_metadata, d.title AS document_filename "
                        "FROM chunks c JOIN documents d ON c.document_id = d.id "
                        "WHERE d.owner_id = :owner_id AND d.soft_deleted = 0"
                    )
                    plan_res = await session.execute(explain_sql, {"owner_id": owner_id})
                    plan_lines = [str(tuple(row)) for row in plan_res.fetchall()]
                    log_event("retrieval.list_user_chunks.explain", owner_id=owner_id, backend=DATABASE_BACKEND, plan=plan_lines[:20])
            except Exception as exc:
                log_event("retrieval.list_user_chunks.explain_error", owner_id=owner_id, backend=DATABASE_BACKEND, error=str(exc))

        exec_started = time.time()
        res = await session.execute(stmt)
        exec_ms = round((time.time() - exec_started) * 1000, 2)

        materialize_started = time.time()
        rows = res.mappings().all()
        materialize_ms = round((time.time() - materialize_started) * 1000, 2)
        total_ms = round((time.time() - started) * 1000, 2)

        log_event(
            "retrieval.list_user_chunks.exit",
            owner_id=owner_id,
            row_count=len(rows),
            backend=DATABASE_BACKEND,
            session_wait_ms=session_wait_ms,
            query_exec_ms=exec_ms,
            materialize_ms=materialize_ms,
            total_ms=total_ms,
        )
        return rows


async def list_audits(document_id: int, owner_id: int) -> List[Dict[str, Any]]:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = (
            select(document_audits)
            .select_from(document_audits.join(documents, document_audits.c.document_id == documents.c.id))
            .where(document_audits.c.document_id == document_id)
            .where(documents.c.owner_id == owner_id)
        )
        res = await session.execute(stmt)
        return res.mappings().all()


async def delete_document_hard(document_id: int, owner_id: int) -> bool:
    """Hard-delete a single document and its chunks/embeddings.

    Returns True if the document was found and deleted.
    """
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        # Verify ownership
        stmt = select(documents).where(documents.c.id == document_id).where(documents.c.owner_id == owner_id)
        res = await session.execute(stmt)
        doc = res.mappings().first()
        if not doc:
            return False

        # Delete embeddings for chunks belonging to this document
        chunk_ids_stmt = select(chunks.c.id).where(chunks.c.document_id == document_id)
        chunk_res = await session.execute(chunk_ids_stmt)
        chunk_ids = [row[0] for row in chunk_res.fetchall()]

        if chunk_ids:
            await session.execute(embeddings.delete().where(embeddings.c.chunk_id.in_(chunk_ids)))

        # Delete chunks
        await session.execute(chunks.delete().where(chunks.c.document_id == document_id))

        # Delete the document row itself
        await session.execute(documents.delete().where(documents.c.id == document_id))

        await session.commit()
        return True


async def delete_user_documents_hard(owner_id: int) -> List[int]:
    """Hard-delete all documents, chunks, and embeddings for a user.

    Returns list of deleted document IDs. Does NOT delete the user account.
    """
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        # Find all document IDs for this owner
        doc_stmt = select(documents.c.id).where(documents.c.owner_id == owner_id)
        doc_res = await session.execute(doc_stmt)
        doc_ids = [row[0] for row in doc_res.fetchall()]

        if not doc_ids:
            return []

        # Get all chunk IDs for these documents
        chunk_stmt = select(chunks.c.id).where(chunks.c.document_id.in_(doc_ids))
        chunk_res = await session.execute(chunk_stmt)
        chunk_ids = [row[0] for row in chunk_res.fetchall()]

        # Delete embeddings for these chunks
        if chunk_ids:
            await session.execute(embeddings.delete().where(embeddings.c.chunk_id.in_(chunk_ids)))

        # Delete chunks
        await session.execute(chunks.delete().where(chunks.c.document_id.in_(doc_ids)))

        # Delete documents
        await session.execute(documents.delete().where(documents.c.owner_id == owner_id))

        await session.commit()
        return doc_ids
