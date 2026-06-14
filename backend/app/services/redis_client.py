import os
try:
    import redis.asyncio as redis_async
except Exception:
    redis_async = None


def get_redis_client():
    """Return an async Redis client. Falls back to None if redis.asyncio not available.
    Use `await client.get()` and `await client.set()` in async code.
    """
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    if redis_async is None:
        return None
    return redis_async.from_url(url)


async def redis_status() -> str:
    client = get_redis_client()
    if client is None:
        return "unavailable"
    try:
        await client.ping()
        return "available"
    except Exception:
        return "unavailable"


async def cache_get(key: str):
    client = get_redis_client()
    if client is None:
        return None
    try:
        return await client.get(key)
    except Exception:
        return None


async def cache_set(key: str, value, ex: int = 300):
    client = get_redis_client()
    if client is None:
        return False
    try:
        await client.set(key, value, ex=ex)
        return True
    except Exception:
        return False
