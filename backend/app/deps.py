from typing import AsyncIterator, Generator, Optional
from .db import get_db
from .clients.redis_client import get_redis_client
from .clients.qdrant_client import get_qdrant


def get_db_sync() -> Generator:
    # Wrapper kept for import compatibility with sync code
    yield from get_db()


def get_redis() -> Optional[object]:
    return get_redis_client()


def get_qdrant_client() -> Optional[object]:
    return get_qdrant()
