import time
from typing import Optional

from app.services.redis_client import get_redis_client


async def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """Return True if allowed, False if limit exceeded."""
    client = get_redis_client()
    if client is None:
        return True

    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window_seconds)
        return count <= limit
    except Exception:
        return True


def build_rate_key(prefix: str, identifier: str, window_seconds: int) -> str:
    window = int(time.time() // window_seconds)
    return f"rl:{prefix}:{identifier}:{window}"
