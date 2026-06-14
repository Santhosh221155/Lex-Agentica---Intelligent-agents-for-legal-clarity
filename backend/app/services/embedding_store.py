"""Shared embedding + Chroma helpers for ingestion and retrieval."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]

# Module-level singletons — set once, never cached as None by lru_cache.
_embedding_function: Optional[Any] = None
_embedding_function_resolved: bool = False

_vectorstore_cache: dict[str, Any] = {}


def get_chroma_collection_name() -> str:
    return os.getenv("CHROMA_COLLECTION", os.getenv("INGEST_COLLECTION", "legal_docs"))


def get_chroma_persist_dir() -> str:
    raw_dir = os.getenv("CHROMA_DB_DIR", os.path.join("backend", "chroma_db"))
    path = Path(raw_dir)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    resolved = str(path)
    # Ensure the directory exists so Chroma doesn't fail on first write
    Path(resolved).mkdir(parents=True, exist_ok=True)
    return resolved


class _LocalSentenceTransformerEmbeddings:
    """LangChain-compatible wrapper around app.embeddings."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        from app.embeddings import embed_texts
        return embed_texts(texts)

    def embed_query(self, text: str) -> list[float]:
        from app.embeddings import embed_text
        return embed_text(text)


def get_embedding_function() -> Optional[Any]:
    """
    Return the embedding function singleton.

    Resolution order:
      1. OpenAI  — if OPENAI_API_KEY is set
      2. Local sentence-transformers — always attempted as fallback
         (no ENABLE_SENTENCE_TRANSFORMERS guard needed; the model is already
          loading at startup so we should use it)

    Uses a module-level variable instead of @lru_cache so that a None result
    is never permanently cached — on the next call the function retries.
    """
    global _embedding_function, _embedding_function_resolved

    # Return cached non-None result immediately
    if _embedding_function is not None:
        return _embedding_function

    # Try OpenAI first
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key:
        try:
            from importlib import import_module
            OpenAIEmbeddings = import_module("langchain_openai").OpenAIEmbeddings
            _embedding_function = OpenAIEmbeddings(
                model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
            )
            LOGGER.info("✓ Using OpenAI embeddings (model=%s)", os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
            return _embedding_function
        except Exception as exc:
            LOGGER.warning("OpenAI embeddings unavailable: %s", exc)

    # Always try local sentence-transformers — the model is loaded at startup
    # regardless of the ENABLE_SENTENCE_TRANSFORMERS flag, so use it.
    try:
        from app.embeddings import get_model
        model = get_model()
        if model is not None:
            _embedding_function = _LocalSentenceTransformerEmbeddings()
            LOGGER.info("✓ Using local SentenceTransformer embeddings")
            return _embedding_function
        else:
            LOGGER.warning(
                "app.embeddings.get_model() returned None — "
                "sentence-transformer model not yet loaded. Will retry on next call."
            )
    except Exception as exc:
        LOGGER.warning("Local sentence-transformer embeddings unavailable: %s", exc)

    # Last resort: log a clear, actionable error
    LOGGER.error(
        " No embedding backend available. "
        "Set OPENAI_API_KEY for OpenAI embeddings, or ensure the sentence-transformer "
        "model has finished loading (check startup logs for 'Loading SentenceTransformer'). "
        "Ingestion will fail until an embedding backend is available."
    )
    return None


def get_chroma_vectorstore(collection_name: Optional[str] = None) -> Optional[Any]:
    """
    Return a LangChain Chroma vectorstore for the given collection.

    Uses a plain dict cache instead of @lru_cache so that a None result
    (caused by missing embedding backend) is never permanently stored —
    the next call will retry embedding initialisation.
    """
    collection_name = collection_name or get_chroma_collection_name()

    # Return cached instance only if it is a real vectorstore (not None)
    if collection_name in _vectorstore_cache:
        cached = _vectorstore_cache[collection_name]
        if cached is not None:
            return cached

    embeddings = get_embedding_function()
    if embeddings is None:
        LOGGER.error(
            " Cannot initialise Chroma vectorstore for collection '%s': "
            "no embedding function available. "
            "Check OPENAI_API_KEY or sentence-transformer model status.",
            collection_name,
        )
        return None

    persist_dir = get_chroma_persist_dir()
    LOGGER.info(
        "Initialising Chroma vectorstore: collection='%s' persist_dir='%s'",
        collection_name,
        persist_dir,
    )

    try:
        from importlib import import_module
        try:
            Chroma = import_module("langchain_chroma").Chroma
        except Exception:
            Chroma = import_module("langchain_community.vectorstores").Chroma
            LOGGER.warning(
                "langchain_chroma not installed; using deprecated "
                "langchain_community.vectorstores.Chroma. "
                "Fix: pip install -U langchain-chroma"
            )

        store = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=persist_dir,
        )
        _vectorstore_cache[collection_name] = store
        LOGGER.info("Chroma vectorstore ready for collection '%s'", collection_name)
        return store

    except Exception as exc:
        LOGGER.error(
            " Failed to initialise Chroma vectorstore for collection '%s': %s",
            collection_name,
            exc,
            exc_info=True,
        )
        # Do NOT cache None — allow retry on next call
        return None


def invalidate_vectorstore_cache(collection_name: Optional[str] = None) -> None:
    """Force re-initialisation of the vectorstore on the next call."""
    global _embedding_function, _embedding_function_resolved
    if collection_name:
        _vectorstore_cache.pop(collection_name, None)
        LOGGER.info("Vectorstore cache invalidated for collection '%s'", collection_name)
    else:
        _vectorstore_cache.clear()
        _embedding_function = None
        _embedding_function_resolved = False
        LOGGER.info("All vectorstore and embedding caches invalidated")


def count_chroma_documents(collection_name: Optional[str] = None) -> int:
    collection_name = collection_name or get_chroma_collection_name()
    try:
        from chromadb import PersistentClient
        client = PersistentClient(path=get_chroma_persist_dir())
        collection = client.get_or_create_collection(name=collection_name)
        count = int(collection.count())
        LOGGER.debug("Chroma collection '%s' document count: %s", collection_name, count)
        return count
    except Exception as exc:
        LOGGER.warning("Unable to verify Chroma collection '%s': %s", collection_name, exc)
        return -1