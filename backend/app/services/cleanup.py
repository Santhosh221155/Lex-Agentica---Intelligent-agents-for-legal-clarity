"""Chroma and filesystem cleanup service for document deletion."""

from __future__ import annotations

import logging
import os
import shutil
from typing import Optional

from app.services.embedding_store import get_chroma_collection_name, get_chroma_persist_dir

LOGGER = logging.getLogger(__name__)


def delete_chroma_chunks(owner_id: int, doc_id: Optional[int] = None) -> int:
    """Delete chunks from ChromaDB matching owner_id (and optionally doc_id).

    Returns the number of deleted chunk IDs, or 0 on failure.
    """
    try:
        import chromadb

        client = chromadb.PersistentClient(path=get_chroma_persist_dir())
        collection_name = get_chroma_collection_name()
        collection = client.get_or_create_collection(name=collection_name)

        # Build where clause
        if doc_id is not None:
            where = {"$and": [
                {"owner_id": {"$eq": str(owner_id)}},
                {"document_id": {"$eq": str(doc_id)}},
            ]}
        else:
            where = {"owner_id": {"$eq": str(owner_id)}}

        # Get matching IDs first
        result = collection.get(where=where, include=[])
        ids = result.get("ids") or []

        if not ids:
            LOGGER.info("cleanup.chroma: no chunks found for owner_id=%s doc_id=%s", owner_id, doc_id)
            return 0

        collection.delete(ids=ids)
        LOGGER.info("cleanup.chroma: deleted %d chunks for owner_id=%s doc_id=%s", len(ids), owner_id, doc_id)
        return len(ids)

    except Exception as exc:
        LOGGER.warning("cleanup.chroma: failed to delete chunks for owner_id=%s doc_id=%s: %s", owner_id, doc_id, exc)
        return 0


def cleanup_temp_files(owner_id: Optional[int] = None) -> None:
    """Clean up temporary upload files from the ingest temp directory.

    Best-effort: logs warnings on failure but never raises.
    """
    import tempfile

    tmp_base = tempfile.gettempdir()
    try:
        for entry in os.listdir(tmp_base):
            if entry.startswith("ingest-"):
                entry_path = os.path.join(tmp_base, entry)
                try:
                    if os.path.isdir(entry_path):
                        shutil.rmtree(entry_path, ignore_errors=True)
                    elif os.path.isfile(entry_path):
                        os.remove(entry_path)
                except Exception:
                    pass
    except Exception as exc:
        LOGGER.warning("cleanup.temp_files: failed: %s", exc)
