import asyncio
from typing import Any, Dict, Optional

from app.services.memory_store import fetch_recent_memory, save_memory


async def fetch_memory(user_id, query: str, plan: dict, tenant_id: Optional[int] = None, workspace_id: Optional[int] = None):
    """Return relevant short-term and episodic memory items.

    This implementation is best-effort: it reads from persistent memory rows when
    available and always returns a deterministic fallback so the synthesizer has
    context even in empty local environments.
    """
    numeric_user_id = None
    try:
        if isinstance(user_id, str) and user_id.startswith("user:"):
            numeric_user_id = int(user_id.split(":", 1)[1])
        elif isinstance(user_id, int):
            numeric_user_id = user_id
        elif isinstance(user_id, str) and user_id.isdigit():
            numeric_user_id = int(user_id)
    except Exception:
        numeric_user_id = None

    recent = await fetch_recent_memory(numeric_user_id, query, limit=5)
    short_term = []
    semantic = []
    for idx, item in enumerate(recent):
        content = item.get("content") or {}
        text = content.get("summary") or content.get("text") or str(content)
        payload = {
            "id": item.get("id") or f"mem:{idx}",
            "text": text,
            "type": item.get("type", "recent"),
            "importance_score": item.get("importance_score", 0.0),
            "recency_score": item.get("recency_score", 0.0),
            "retrieval_score": item.get("retrieval_score", 0.0),
            "total_score": item.get("total_score", 0.0),
        }
        short_term.append(payload)
        if item.get("type") in {"semantic", "fact", "preference", "entity"} or item.get("total_score", 0.0) >= 0.6:
            semantic.append(payload)

    if not short_term:
        short_term = [
            {
                "id": "mem:bootstrap",
                "text": "No prior memory found; start a fresh evidence trail for this session.",
                "type": "bootstrap",
            }
        ]

    mem = {
        "short_term": short_term,
        "semantic": semantic[:5],
        "ranked": recent,
        "episodic": [
            {
                "id": f"episode:{user_id}",
                "text": f"User {user_id} asked about {query[:120]}",
                "plan": {
                    "requires_validation": bool(plan.get("requires_validation")),
                    "retrieval_strategy": plan.get("retrieval_strategy"),
                },
            }
        ],
    }

    # Keep a lightweight audit trail for later retrieval if the DB is available.
    try:
        await save_memory(numeric_user_id, "interaction", {"query": query, "plan": plan, "memory": mem}, tenant_id=tenant_id, workspace_id=workspace_id)
    except Exception:
        pass

    await asyncio.sleep(0)
    return mem
