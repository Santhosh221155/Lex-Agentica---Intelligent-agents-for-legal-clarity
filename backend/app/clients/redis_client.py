from typing import Optional
from . import __name__
try:
    import redis.asyncio as aioredis
except Exception:
    aioredis = None

_redis_client: Optional[object] = None


def init_redis(url: str):
    global _redis_client
    if aioredis is None:
        _redis_client = None
        return None
    _redis_client = aioredis.from_url(url)
    return _redis_client


def get_redis_client():
    return _redis_client
