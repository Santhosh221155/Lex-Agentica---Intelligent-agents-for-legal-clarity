import asyncio
import httpx
import json
from typing import Any, Dict


async def run_with_timeout(func, *args, timeout: float = 10.0, **kwargs) -> Dict[str, Any]:
    try:
        return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError:
        return {"success": False, "error": "timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def http_get(url: str, params: dict = None, timeout: float = 5.0):
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
