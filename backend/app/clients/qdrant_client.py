from typing import Optional

# Lazy-import Qdrant to avoid pulling heavy pydantic models at module import time.
_qdrant: Optional[object] = None


def init_qdrant(url: str = None, api_key: str = None):
    global _qdrant
    try:
        from qdrant_client import QdrantClient
    except Exception:
        return None

    params = {}
    if url:
        params["url"] = url
    if api_key:
        params["api_key"] = api_key
    # Skip the client-server compatibility check to avoid noisy warnings when
    # the server does not expose version info or is unreachable in some envs.
    params["check_compatibility"] = False
    _qdrant = QdrantClient(**params)
    return _qdrant


def get_qdrant():
    return _qdrant


def ensure_collection(collection_name: str, vector_size: int = 1536, distance: str = "Cosine"):
    """Best-effort: create collection if it doesn't exist. No-op if client missing.

    This avoids raising during startup when Qdrant isn't reachable; it's a best-effort helper
    used by vectorstore initialization paths.
    """
    client = get_qdrant()
    if client is None:
        return False
    try:
        from qdrant_client.http import models as rest_models
        # Check if collection exists
        try:
            info = client.get_collection(collection_name)
            return True
        except Exception:
            # create collection
            client.recreate_collection(collection_name=collection_name, vectors_config={"size": vector_size, "distance": distance})
            return True
    except Exception:
        try:
            # fallback: attempt a no-arg create
            client.recreate_collection(collection_name=collection_name)
            return True
        except Exception:
            return False
