import os
import asyncio
import uuid
import traceback
from typing import Callable, Dict, List, Optional

# Placeholders for optional heavy dependencies. Resolve at runtime to avoid
# triggering large imports (transformers, sklearn, sentence-transformers, etc.)
PyPDFLoader = None
Chroma = None
OpenAIEmbeddings = None
RecursiveCharacterTextSplitter = None
HAS_LANGCHAIN = False
import mimetypes
import logging

from app.services.embedding_store import (
    count_chroma_documents,
    get_chroma_collection_name,
    get_chroma_persist_dir,
    get_chroma_vectorstore,
    invalidate_vectorstore_cache,
)
from app.services.text_sanitizer import sanitize_and_log, sanitize_metadata

LOGGER = logging.getLogger(__name__)


def _emit_progress(progress_callback: Optional[Callable[[str], None]], status: str) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(status)
    except Exception:
        pass


def _get_persist_dir() -> str:
    return get_chroma_persist_dir()


def _get_vectorstore(collection_name: str):
    store = get_chroma_vectorstore(collection_name)
    if store is None:
        raise RuntimeError(
            "embedding backend not available — "
            "ensure OPENAI_API_KEY is set, or that the sentence-transformer model "
            "has loaded (check startup logs). "
            "If the model loaded but this still fails, the server may need a restart "
            "so the embedding singleton is re-initialised."
        )
    return store


async def ingest_file(
    file_path: str,
    collection_name: str = "legal_docs",
    owner_id: Optional[int] = None,
    document_id: Optional[int] = None,
    document_metadata: Optional[Dict[str, object]] = None,
    tenant_id: Optional[int] = None,
    workspace_id: Optional[int] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
):
    """Dispatch ingestion based on file type (PDF, image)."""
    collection_name = collection_name or get_chroma_collection_name()
    mimetype, _ = mimetypes.guess_type(file_path)

    if file_path.lower().endswith(".pdf") or (mimetype and "pdf" in mimetype):
        return await ingest_pdf(
            file_path,
            collection_name,
            owner_id,
            document_id,
            document_metadata,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            progress_callback=progress_callback,
        )

    if (mimetype and mimetype.startswith("image/")) or any(
        file_path.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp")
    ):
        return await asyncio.to_thread(
            ingest_image,
            file_path,
            collection_name,
            owner_id,
            document_id,
            document_metadata,
            tenant_id,
            workspace_id,
        )

    return {"status": "failed", "error": "unsupported_file_type"}


def ingest_image(
    file_path: str,
    collection_name: str = "legal_docs",
    owner_id: Optional[int] = None,
    document_id: Optional[int] = None,
    document_metadata: Optional[Dict[str, object]] = None,
    tenant_id: Optional[int] = None,
    workspace_id: Optional[int] = None,
) -> dict:
    """Attempt to OCR an image and ingest resulting text as a single document."""
    try:
        try:
            import importlib
            Image = importlib.import_module("PIL.Image")
            pytesseract = importlib.import_module("pytesseract")
        except Exception:
            return {"status": "failed", "error": "pillow_or_pytesseract_missing"}

        img = Image.open(file_path)
        text = pytesseract.image_to_string(img)
        if not text or not text.strip():
            return {"status": "failed", "error": "no_text_extracted"}

        # Sanitize OCR output (removes \x00 and other control chars)
        text = sanitize_and_log(text, document_id=document_id, label="ocr_text")

        class Doc:
            def __init__(self, text):
                self.page_content = text
                self.metadata = {}

        doc = Doc(text)
        try:
            import importlib
            split_mod = importlib.import_module("langchain.text_splitter")
            RecursiveCharacterTextSplitter = getattr(split_mod, "RecursiveCharacterTextSplitter", None)
            if RecursiveCharacterTextSplitter is not None:
                splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
                chunks = splitter.split_documents([doc]) if hasattr(splitter, "split_documents") else splitter.split_text(text)
            else:
                chunks = [doc]
        except Exception:
            chunks = [doc]

        vectorstore = _get_vectorstore(collection_name)
        chunk_ids = [f"chunk_{uuid.uuid4().hex}" for _ in range(len(chunks))]
        chunk_rows = []
        embedding_rows = []
        for i, c in enumerate(chunks):
            c.metadata = {
                **(document_metadata or {}),
                "owner_id": owner_id,
                "document_id": document_id,
                "chunk_index": i,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
            }
            chunk_id = chunk_ids[i]
            chunk_rows.append(
                {
                    "id": chunk_id,
                    "document_id": document_id,
                    "tenant_id": tenant_id,
                    "workspace_id": workspace_id,
                    "chunk_index": i,
                    "page_number": -1,
                    "content": c.page_content,
                    "metadata": c.metadata,
                }
            )

        LOGGER.info(
            "Adding %s chunks to Chroma collection '%s' (owner_id=%s tenant_id=%s workspace_id=%s document_id=%s)",
            len(chunks),
            collection_name,
            owner_id,
            tenant_id,
            workspace_id,
            document_id,
        )
        try:
            vectorstore.add_documents(chunks, ids=chunk_ids)
        except Exception as exc:
            LOGGER.exception("Chroma add_documents failed (image path): %s", exc)
            raise

        try:
            from app.services.document_store import add_chunks, add_embeddings
            asyncio.run(add_chunks(document_id=document_id, chunk_rows=chunk_rows))
            model_name = os.getenv("EMBEDDING_MODEL", "unknown")
            for chunk_id in chunk_ids:
                embedding_rows.append({
                    "chunk_id": chunk_id,
                    "vector_id": f"chroma:{chunk_id}",
                    "model_name": model_name,
                    "tenant_id": tenant_id,
                    "workspace_id": workspace_id,
                })
            asyncio.run(add_embeddings(embedding_rows))
        except Exception as exc:
            LOGGER.warning("Failed to persist image chunks to DB (non-fatal): %s", exc)

        try:
            vectorstore.persist()
        except Exception as exc:
            LOGGER.warning("Chroma persist() failed (image path): %s", exc)

        return {"status": "success", "chunks_stored": len(chunks), "document_id": document_id}

    except Exception as e:
        LOGGER.exception("Image ingestion failed for file='%s': %s", file_path, e)
        return {"status": "failed", "error": str(e)}


async def ingest_pdf(
    file_path: str,
    collection_name: str = "legal_docs",
    owner_id: Optional[int] = None,
    document_id: Optional[int] = None,
    document_metadata: Optional[Dict[str, object]] = None,
    tenant_id: Optional[int] = None,
    workspace_id: Optional[int] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    collection_name = collection_name or get_chroma_collection_name()

    LOGGER.info("[ingest] START file='%s' collection='%s' doc=%s", file_path, collection_name, document_id)
    _emit_progress(progress_callback, "processing")

    # ------------------------------------------------------------------ #
    # Wrap the ENTIRE pipeline so no exception is ever silently swallowed  #
    # ------------------------------------------------------------------ #
    try:
        return await _ingest_pdf_pipeline(
            file_path=file_path,
            collection_name=collection_name,
            owner_id=owner_id,
            document_id=document_id,
            document_metadata=document_metadata,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            progress_callback=progress_callback,
        )
    except BaseException as exc:
        # BaseException catches asyncio.CancelledError and SystemExit too
        LOGGER.exception("[ingest] FAILED doc=%s file='%s'", document_id, file_path)
        _emit_progress(progress_callback, "failed")
        # Best-effort: mark job as failed in DB
        try:
            from app.services.document_store import update_ingestion_job
            # find the job for this document — best effort
        except Exception:
            pass
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "document_id": document_id}


async def _ingest_pdf_pipeline(
    file_path: str,
    collection_name: str,
    owner_id: Optional[int],
    document_id: Optional[int],
    document_metadata: Optional[Dict[str, object]],
    tenant_id: Optional[int],
    workspace_id: Optional[int],
    progress_callback: Optional[Callable[[str], None]],
) -> dict:
    """The actual ingestion pipeline — called inside a try/except in ingest_pdf."""

    if not file_path.lower().endswith(".pdf"):
        return {"status": "failed", "error": "only PDF files are supported"}

    # ---- Step 1: verify embedding backend is available BEFORE loading PDF ----
    LOGGER.info("[ingest] PROCESSING doc=%s", document_id)
    embedding_fn = None
    try:
        from app.services.embedding_store import get_embedding_function
        embedding_fn = get_embedding_function()
    except Exception as exc:
        LOGGER.error("[ingest] Failed to resolve embedding function: %s", exc)

    if embedding_fn is None:
        # Try invalidating cache and retrying once (handles cold-start race)
        LOGGER.warning(
            "[ingest] Embedding function is None on first check — "
            "invalidating cache and retrying (doc=%s)",
            document_id,
        )
        invalidate_vectorstore_cache()
        try:
            from app.services.embedding_store import get_embedding_function
            embedding_fn = get_embedding_function()
        except Exception as exc:
            LOGGER.error("[ingest] Retry also failed: %s", exc)

    if embedding_fn is None:
        LOGGER.error(
            "[ingest] ABORT: no embedding backend available. "
            "Set OPENAI_API_KEY or ensure sentence-transformer model has loaded. (doc=%s)",
            document_id,
        )
        return {
            "status": "failed",
            "error": "no_embedding_backend: set OPENAI_API_KEY or check sentence-transformer model startup logs",
            "document_id": document_id,
        }
    LOGGER.info("[ingest] EMBEDDING backend ready doc=%s", document_id)

    # ---- Step 2: lazy-import LangChain PDF components ----
    _emit_progress(progress_callback, "chunking")
    try:
        import importlib

        PyPDFLoader = importlib.import_module("langchain_community.document_loaders").PyPDFLoader

        try:
            RecursiveCharacterTextSplitter = importlib.import_module(
                "langchain_text_splitters"
            ).RecursiveCharacterTextSplitter
        except ImportError:
            split_mod = importlib.import_module("langchain.text_splitter")
            RecursiveCharacterTextSplitter = getattr(split_mod, "RecursiveCharacterTextSplitter")

    except ImportError as e:
        LOGGER.exception("[ingest] Missing LangChain PDF dependencies (doc=%s): %s", document_id, e)
        return {"status": "failed", "error": f"Missing dependencies: {str(e)}", "document_id": document_id}
    except Exception as exc:
        LOGGER.exception("[ingest] Failed to import LangChain components (doc=%s)", document_id)
        return {"status": "failed", "error": "langchain_components_unavailable", "document_id": document_id}

    # ---- Step 3: load and chunk PDF ----
    try:
        loader = PyPDFLoader(file_path)
        docs = await asyncio.to_thread(loader.load)
        LOGGER.info("[ingest] CHUNKING doc=%s pages=%s", document_id, len(docs))
    except Exception as exc:
        LOGGER.exception("[ingest] PyPDFLoader failed for file='%s' (doc=%s): %s", file_path, document_id, exc)
        _emit_progress(progress_callback, "failed")
        return {"status": "failed", "error": f"pdf_load_failed: {exc}", "document_id": document_id}

    # ---- Step 3b: sanitize extracted page text (removes \x00 etc.) ----
    for doc in docs:
        if hasattr(doc, "page_content") and isinstance(doc.page_content, str):
            doc.page_content = sanitize_and_log(
                doc.page_content, document_id=document_id, label="page_text"
            )
        # Sanitize metadata string values on each page doc
        if isinstance(getattr(doc, "metadata", None), dict):
            doc.metadata = sanitize_metadata(doc.metadata)

    try:
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
        chunks = await asyncio.to_thread(splitter.split_documents, docs)
        LOGGER.info("[ingest] CHUNKED doc=%s chunks=%s", document_id, len(chunks))
    except Exception as exc:
        LOGGER.exception("[ingest] Text splitting failed (doc=%s): %s", document_id, exc)
        _emit_progress(progress_callback, "failed")
        return {"status": "failed", "error": f"chunking_failed: {exc}", "document_id": document_id}

    if not chunks:
        LOGGER.warning("[ingest] Zero chunks extracted from file='%s' (doc=%s) — PDF may be empty or image-only", file_path, document_id)
        _emit_progress(progress_callback, "failed")
        return {"status": "failed", "error": "zero_chunks_extracted", "document_id": document_id}

    # ---- Step 4: build metadata and persist chunks to DB ----
    _emit_progress(progress_callback, "embedding")
    LOGGER.info("[ingest] EMBEDDING doc=%s chunks=%s", document_id, len(chunks))

    if document_metadata is None and document_id is not None:
        try:
            from app.services.document_store import get_document
            document_row = await get_document(document_id, owner_id or 0)
            document_metadata = dict(document_row.get("metadata") or {}) if document_row else {}
        except Exception:
            document_metadata = {}

    if tenant_id is None or workspace_id is None:
        from app.services.auth import _get_or_create_default_scope
        tenant_id, workspace_id = await _get_or_create_default_scope()

    base_metadata = dict(document_metadata or {})
    filename = os.path.basename(file_path)
    chunk_ids = []
    chunk_rows = []
    embedding_rows = []

    for i, doc in enumerate(chunks):
        # Sanitize chunk content (defense-in-depth: already sanitized at page level)
        if hasattr(doc, "page_content") and isinstance(doc.page_content, str):
            doc.page_content = sanitize_and_log(
                doc.page_content, document_id=document_id, label=f"chunk_{i}"
            )

        page_num = doc.metadata.get("page") if isinstance(doc.metadata, dict) else None
        chunk_id = f"chunk_{uuid.uuid4().hex}"
        chunk_ids.append(chunk_id)
        chunk_metadata = sanitize_metadata({
            **base_metadata,
            "filename": filename,
            "page_number": page_num if page_num is not None else -1,
            "chunk_index": i,
            "owner_id": owner_id,
            "document_id": document_id,
            "chunk_id": chunk_id,
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
        })
        doc.metadata = chunk_metadata
        chunk_rows.append(
            {
                "id": chunk_id,
                "document_id": document_id,
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "chunk_index": i,
                "page_number": page_num if page_num is not None else -1,
                "content": doc.page_content,
                "metadata": chunk_metadata,
            }
        )

    stored_in_db = False
    db_error = None
    try:
        from app.services.document_store import add_chunks, add_embeddings

        await add_chunks(document_id=document_id, chunk_rows=chunk_rows)
        LOGGER.info("[ingest] DB chunks saved doc=%s rows=%s", document_id, len(chunk_rows))

        model_name = os.getenv("EMBEDDING_MODEL", "unknown")
        for chunk_id in chunk_ids:
            embedding_rows.append(
                {
                    "chunk_id": chunk_id,
                    "vector_id": f"chroma:{chunk_id}",
                    "model_name": model_name,
                    "tenant_id": tenant_id,
                    "workspace_id": workspace_id,
                }
            )
        await add_embeddings(embedding_rows)
        LOGGER.info("[ingest] DB embeddings saved doc=%s rows=%s", document_id, len(embedding_rows))
        stored_in_db = True
    except Exception as exc:
        db_error = str(exc)
        LOGGER.error("[ingest] ✗ Failed to persist chunks/embeddings to DB (doc=%s): %s", document_id, exc, exc_info=True)
        _emit_progress(progress_callback, "failed")

    # ---- Step 5: write to Chroma vector store ----
    _emit_progress(progress_callback, "indexing")
    LOGGER.info("[ingest] INDEXING doc=%s collection='%s' chunks=%s", document_id, collection_name, len(chunk_ids))

    vector_warning = None
    try:
        before_count = count_chroma_documents(collection_name)
        vectorstore = _get_vectorstore(collection_name)
        await asyncio.to_thread(vectorstore.add_documents, chunks, ids=chunk_ids)
        after_count = count_chroma_documents(collection_name)

        # persist() is a no-op in newer Chroma but harmless to call
        try:
            vectorstore.persist()
        except Exception as exc:
            LOGGER.debug("[ingest] Chroma persist skipped: %s", exc)


    except Exception as exc:
        vector_warning = str(exc)
        LOGGER.exception("[ingest] Chroma write failed for collection='%s' doc=%s", collection_name, document_id)
        _emit_progress(progress_callback, "failed")

    # ---- Post-ingest verification ----
    try:
        post_count = count_chroma_documents(collection_name)
        LOGGER.info("[ingest] POST-INGEST doc=%s total_docs=%s", document_id, post_count)
    except Exception as exc:
        LOGGER.warning("[ingest] Post-ingest Chroma count check failed (doc=%s): %s", document_id, exc)
        post_count = None

    # ---- State consistency: COMPLETED only if BOTH PG and Chroma succeed ----
    if not stored_in_db:
        LOGGER.error("[ingest] FAILED: chunks not stored in DB (doc=%s) error=%s", document_id, db_error)
        _emit_progress(progress_callback, "failed")
        return {
            "status": "failed",
            "error": db_error or "chunk_persist_failed",
            "document_id": document_id,
        }

    if vector_warning:
        # Chroma indexing failed — mark as FAILED (not partial)
        LOGGER.error(
            "[ingest] FAILED: DB stored but Chroma indexing failed (doc=%s): %s",
            document_id, vector_warning,
        )
        _emit_progress(progress_callback, "failed")
        return {
            "status": "failed",
            "error": f"chroma_index_failed: {vector_warning}",
            "document_id": document_id,
            "chunks_stored": len(chunks),
            "chroma_doc_count": post_count,
        }

    LOGGER.info("[ingest] COMPLETE file='%s' collection='%s' chunks=%s doc=%s", os.path.basename(file_path), collection_name, len(chunks), document_id)
    _emit_progress(progress_callback, "completed")

    return {
        "status": "success",
        "chunks_stored": len(chunks),
        "document_id": document_id,
        "chroma_doc_count": post_count,
    }


def verify_ingestion(collection_name: str = "legal_docs") -> Dict[str, object]:
    collection_name = collection_name or get_chroma_collection_name()
    total = count_chroma_documents(collection_name)
    sample = []
    if total > 0:
        from chromadb import PersistentClient
        client = PersistentClient(path=_get_persist_dir())
        collection = client.get_or_create_collection(name=collection_name)
        res = collection.get(limit=3, include=["documents"])
        sample = res.get("documents", []) if isinstance(res, dict) else []
    return {
        "collection": collection_name,
        "total_vectors": int(total),
        "sample_chunks": sample[:3],
        "status": "ok" if total > 0 else "empty",
    }


def chroma_status(collection_name: str = "legal_docs") -> str:
    try:
        status = verify_ingestion(collection_name)
        return "available" if status.get("total_vectors", 0) > 0 else "empty"
    except Exception:
        return "unavailable"