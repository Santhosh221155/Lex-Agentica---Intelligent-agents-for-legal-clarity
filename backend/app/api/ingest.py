import asyncio
import json
import os
import tempfile
from uuid import uuid4
from typing import Dict, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
import httpx

from ..services.ingestion import ingest_file as dispatch_ingest_file, verify_ingestion
from app.services.document_store import create_document, create_ingestion_job, update_ingestion_job
from app.api.auth import get_current_user, get_admin_user
from app.services.rate_limit import check_rate_limit, build_rate_key
from app.services.security import validate_filename, is_allowed_content_type, max_upload_bytes
from app.services.text_sanitizer import sanitize_metadata

router = APIRouter()

# In-memory job store (placeholder). Replace with DB table in production.
JOBS: Dict[str, Dict] = {}


async def _process_file_job(
    job_id: str,
    db_job_id: int,
    path: str,
    user_id: int,
    document_id: int,
    tenant_id: Optional[int] = None,
    workspace_id: Optional[int] = None,
    metadata: Optional[dict] = None,
):
    try:
        def _report_stage(stage: str):
            JOBS[job_id]["status"] = stage
            JOBS[job_id]["stage"] = stage
            try:
                asyncio.create_task(update_ingestion_job(db_job_id, stage))
            except Exception:
                pass

        JOBS[job_id]["status"] = "processing"
        JOBS[job_id]["stage"] = "processing"
        await update_ingestion_job(db_job_id, "processing")
        res = await dispatch_ingest_file(
            path,
            collection_name=os.getenv("INGEST_COLLECTION", "legal_docs"),
            owner_id=user_id,
            document_id=document_id,
            document_metadata=metadata,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            progress_callback=_report_stage,
        )
        final_status = "completed" if res.get("status") == "success" else "failed"
        JOBS[job_id]["status"] = final_status
        JOBS[job_id]["stage"] = final_status
        JOBS[job_id]["result"] = res
        await update_ingestion_job(db_job_id, final_status, res.get("error"))
    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = "Something went wrong. Please try again."
        await update_ingestion_job(db_job_id, "failed", "Something went wrong. Please try again.")
    finally:
        # cleanup temporary files
        try:
            if os.path.exists(path):
                os.remove(path)
            # attempt to remove parent tempdir if empty
            parent = os.path.dirname(path)
            if parent and os.path.isdir(parent):
                try:
                    os.rmdir(parent)
                except Exception:
                    pass
        except Exception:
            pass


@router.post("/file")
async def ingest_file_endpoint(request: Request, file: UploadFile = File(...), metadata: Optional[str] = None, user: dict = Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="missing filename")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF files are supported")

    if not is_allowed_content_type(file.content_type, ["application/pdf"]):
        raise HTTPException(status_code=400, detail="invalid_content_type")

    ip = request.client.host if request.client else "anon"
    user_key = build_rate_key("user_upload", str(user.get("id")), 3600)
    ip_key = build_rate_key("ip_upload", ip, 3600)
    if not await check_rate_limit(user_key, int(os.getenv("UPLOAD_LIMIT_PER_HOUR", "20")), 3600):
        raise HTTPException(status_code=429, detail="upload_rate_limit_exceeded")
    if not await check_rate_limit(ip_key, int(os.getenv("UPLOAD_LIMIT_PER_HOUR", "20")), 3600):
        raise HTTPException(status_code=429, detail="upload_rate_limit_exceeded")

    job_id = str(uuid4())
    tmpdir = tempfile.mkdtemp(prefix="ingest-")
    safe_name = validate_filename(file.filename)
    dest = os.path.join(tmpdir, safe_name)
    with open(dest, "wb") as f:
        content = await file.read()
        if len(content) > max_upload_bytes():
            raise HTTPException(status_code=413, detail="file_too_large")
        f.write(content)
    parsed_metadata = {}
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except Exception:
            parsed_metadata = {}
    parsed_metadata = sanitize_metadata(parsed_metadata)

    # Clean up user's existing documents before creating a new one (single active doc model)
    try:
        from app.services.document_store import delete_user_documents_hard
        from app.services.cleanup import delete_chroma_chunks, cleanup_temp_files

        owner_id = user.get("id")
        if owner_id is not None:
            delete_chroma_chunks(owner_id)
            await delete_user_documents_hard(owner_id)
            cleanup_temp_files(owner_id)
    except Exception:
        pass  # best-effort; don't block upload

    document = await create_document(
        owner_id=user.get("id"),
        filename=safe_name,
        source="upload",
        metadata=parsed_metadata or None,
        tenant_id=user.get("tenant_id"),
        workspace_id=user.get("workspace_id"),
    )
    doc_id = document.get("id") if document else None
    db_job_id = await create_ingestion_job(owner_id=user.get("id"), document_id=doc_id, tenant_id=user.get("tenant_id"), workspace_id=user.get("workspace_id"))

    JOBS[job_id] = {
        "status": "queued",
        "file": safe_name,
        "user_id": user.get("id"),
        "document_id": doc_id,
        "db_job_id": db_job_id,
    }
    # schedule background processing (fire-and-forget)
    asyncio.create_task(
        _process_file_job(
            job_id,
            db_job_id,
            dest,
            user.get("id"),
            doc_id,
            tenant_id=user.get("tenant_id"),
            workspace_id=user.get("workspace_id"),
            metadata=parsed_metadata,
        )
    )
    return {"job_id": job_id, "db_job_id": db_job_id, "status": "queued", "document_id": doc_id}


@router.post("")
async def ingest_pdf_direct(request: Request, file: UploadFile = File(...), metadata: Optional[str] = None, user: dict = Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="missing filename")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF files are supported")

    if not is_allowed_content_type(file.content_type, ["application/pdf"]):
        raise HTTPException(status_code=400, detail="invalid_content_type")

    ip = request.client.host if request.client else "anon"
    user_key = build_rate_key("user_upload", str(user.get("id")), 3600)
    ip_key = build_rate_key("ip_upload", ip, 3600)
    if not await check_rate_limit(user_key, int(os.getenv("UPLOAD_LIMIT_PER_HOUR", "20")), 3600):
        raise HTTPException(status_code=429, detail="upload_rate_limit_exceeded")
    if not await check_rate_limit(ip_key, int(os.getenv("UPLOAD_LIMIT_PER_HOUR", "20")), 3600):
        raise HTTPException(status_code=429, detail="upload_rate_limit_exceeded")

    tmpdir = tempfile.mkdtemp(prefix="ingest-")
    safe_name = validate_filename(file.filename)
    dest = os.path.join(tmpdir, safe_name)
    with open(dest, "wb") as f:
        content = await file.read()
        if len(content) > max_upload_bytes():
            raise HTTPException(status_code=413, detail="file_too_large")
        f.write(content)

    try:
        parsed_metadata = {}
        if metadata:
            try:
                parsed_metadata = json.loads(metadata)
            except Exception:
                parsed_metadata = {}
        parsed_metadata = sanitize_metadata(parsed_metadata)
        # Clean up user's existing documents before creating a new one (single active doc model)
        try:
            from app.services.document_store import delete_user_documents_hard
            from app.services.cleanup import delete_chroma_chunks, cleanup_temp_files

            owner_id = user.get("id")
            if owner_id is not None:
                delete_chroma_chunks(owner_id)
                await delete_user_documents_hard(owner_id)
                cleanup_temp_files(owner_id)
        except Exception:
            pass  # best-effort; don't block upload

        document = await create_document(
            owner_id=user.get("id"),
            filename=safe_name,
            source="upload",
            tenant_id=user.get("tenant_id"),
            workspace_id=user.get("workspace_id"),
        )
        doc_id = document.get("id") if document else None
        db_job_id = await create_ingestion_job(owner_id=user.get("id"), document_id=doc_id, tenant_id=user.get("tenant_id"), workspace_id=user.get("workspace_id"))
        res = await dispatch_ingest_file(
            dest,
            collection_name=os.getenv("INGEST_COLLECTION", "legal_docs"),
            owner_id=user.get("id"),
            document_id=doc_id,
            document_metadata=parsed_metadata,
            tenant_id=user.get("tenant_id"),
            workspace_id=user.get("workspace_id"),
        )
        await update_ingestion_job(db_job_id, res.get("status", "failed"), res.get("error"))
        res["document_id"] = doc_id
        res["job_id"] = db_job_id
        return res
    finally:
        try:
            if os.path.exists(dest):
                os.remove(dest)
            if os.path.isdir(tmpdir):
                os.rmdir(tmpdir)
        except Exception:
            pass


@router.post("/url")
async def ingest_url(url: str, user: dict = Depends(get_current_user)):
    job_id = str(uuid4())
    tmpdir = tempfile.mkdtemp(prefix="ingest-")
    # derive filename from url or fallback to uuid
    import urllib.parse

    parsed = urllib.parse.urlparse(url)
    fname = os.path.basename(parsed.path) or f"{job_id}.html"
    dest = os.path.join(tmpdir, fname)
    document = await create_document(
        owner_id=user.get("id"),
        filename=fname,
        source="url",
        tenant_id=user.get("tenant_id"),
        workspace_id=user.get("workspace_id"),
    )
    doc_id = document.get("id") if document else None
    db_job_id = await create_ingestion_job(owner_id=user.get("id"), document_id=doc_id, tenant_id=user.get("tenant_id"), workspace_id=user.get("workspace_id"))
    JOBS[job_id] = {"status": "queued", "url": url, "user_id": user.get("id"), "document_id": doc_id, "db_job_id": db_job_id}
    try:
        async def _download_and_schedule(u: str, outpath: str):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    r = await client.get(u)
                    r.raise_for_status()
                    with open(outpath, "wb") as fh:
                        fh.write(r.content)
                asyncio.create_task(
                    _process_file_job(
                        job_id,
                        db_job_id,
                        outpath,
                        user.get("id"),
                        doc_id,
                        tenant_id=user.get("tenant_id"),
                        workspace_id=user.get("workspace_id"),
                        metadata=None,
                    )
                )
            except Exception as e:
                JOBS[job_id]["status"] = "failed"
                JOBS[job_id]["error"] = str(e)
                await update_ingestion_job(db_job_id, "failed", str(e))

        asyncio.create_task(_download_and_schedule(url, dest))
        return {"job_id": job_id, "status": "queued"}
    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)
        return {"job_id": job_id, "status": "failed", "error": str(e)}


@router.get("/status/{job_id}")
async def job_status(job_id: str, user: dict = Depends(get_current_user)):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.get("user_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="forbidden")
    return {"job_id": job_id, "status": job.get("status"), "meta": {k: v for k, v in job.items() if k not in ("result", "error", "user_id", "db_job_id")}}


@router.get("/list")
async def list_indexed(collection: str = None, user: dict = Depends(get_admin_user)):
    """Return a list of documents currently indexed in Chroma (debug view)."""
    status = verify_ingestion(collection_name=collection or "legal_docs")
    return {"count": status.get("total_vectors", 0), "docs": status.get("sample_chunks", [])}
