import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.db import get_session_factory
from app.models import memories


async def save_memory(user_id: Optional[int], memory_type: str, content: Dict[str, Any], tenant_id: Optional[int] = None, workspace_id: Optional[int] = None):
    """Persist a memory row when a real DB session is available.

    Align column names with the `memories` table (`kind` + `payload`) and
    include tenant/workspace when available.
    """
    try:
        SessionLocal = get_session_factory()
        async with SessionLocal() as session:
            values = {"user_id": user_id, "kind": memory_type, "payload": content}
            if tenant_id is not None:
                values["tenant_id"] = tenant_id
            if workspace_id is not None:
                values["workspace_id"] = workspace_id
            stmt = memories.insert().values(**values)
            await session.execute(stmt)
            await session.commit()
    except Exception:
        return


async def save_semantic_memory(user_id: Optional[int], content: Dict[str, Any]):
    payload = dict(content or {})
    payload.setdefault("kind", "semantic")
    payload.setdefault("importance_score", float(payload.get("importance_score", 0.7)))
    return await save_memory(user_id, "semantic", payload)


def _memory_timestamp(record: Dict[str, Any], index: int) -> float:
    created_at = record.get("created_at")
    try:
        if isinstance(created_at, datetime):
            return created_at.replace(tzinfo=created_at.tzinfo or timezone.utc).timestamp()
        if created_at:
            return datetime.fromisoformat(str(created_at)).timestamp()
    except Exception:
        pass
    return float(index)


def _score_memory_item(query: str, record: Dict[str, Any], index: int) -> Dict[str, Any]:
    content = record.get("content") or {}
    text = json.dumps(content).lower()
    q = (query or "").lower()
    tokens = [token for token in q.split() if len(token) > 2]
    overlap = sum(1 for token in tokens if token in text)
    retrieval_score = overlap / max(1, len(tokens))
    importance_score = float(content.get("importance_score", 0.6 if record.get("type") == "semantic" else 0.4))
    recency_anchor = _memory_timestamp(record, index)
    recency_score = 1.0 / (1.0 + math.log1p(max(0.0, float(index))))
    total_score = round((importance_score * 0.45) + (recency_score * 0.35) + (retrieval_score * 0.2), 4)
    return {
        "id": record.get("id"),
        "type": record.get("type"),
        "content": content,
        "user_id": record.get("user_id"),
        "importance_score": round(importance_score, 4),
        "recency_score": round(recency_score, 4),
        "retrieval_score": round(retrieval_score, 4),
        "total_score": total_score,
        "created_at": record.get("created_at"),
        "recency_anchor": recency_anchor,
    }


async def fetch_recent_memory(user_id: Optional[int], query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Best-effort retrieval of recent memory rows.

    With a real DB this can be extended to semantic search. For now it returns
    the most recent rows that can be fetched, filtered in Python for relevance.
    """
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        try:
            stmt = memories.select().order_by(memories.c.created_at.desc())
            if user_id is not None:
                stmt = stmt.where(memories.c.user_id == user_id)
            rows = await session.execute(stmt)
            mappings = rows.mappings().all() if hasattr(rows, "mappings") else []
            scored = [_score_memory_item(query, record, index) for index, record in enumerate(mappings)]
            scored.sort(key=lambda item: item.get("total_score", 0.0), reverse=True)
            return scored[:limit]
        except Exception:
            return []
