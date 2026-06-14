from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update

from app.models import review_requests
from app.services.db import get_session_factory


def _now():
    return datetime.now(timezone.utc)


async def create_review_request(trace_id: Optional[str], query: str, answer_draft: Optional[str], confidence_score: float, threshold: float, session_id: Optional[int] = None, actor: Optional[dict] = None) -> Optional[Dict[str, Any]]:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        initial = {"event": "created", "timestamp": _now().isoformat()}
        if actor:
            initial["actor"] = actor
        stmt = review_requests.insert().values(
            trace_id=trace_id,
            session_id=session_id,
            query=query,
            answer_draft=answer_draft,
            confidence_score=str(round(confidence_score, 2)),
            threshold=str(round(threshold, 2)),
            status="pending",
            audit_log=[initial],
        )
        res = await session.execute(stmt)
        await session.commit()
        review_id = res.inserted_primary_key[0] if res.inserted_primary_key else None
        if review_id is None:
            return None
        return await get_review_request(review_id)


async def get_review_request(review_id: int) -> Optional[Dict[str, Any]]:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = select(review_requests).where(review_requests.c.id == review_id)
        res = await session.execute(stmt)
        return res.mappings().first()


async def list_pending_reviews(limit: int = 50) -> List[Dict[str, Any]]:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = select(review_requests).where(review_requests.c.status == "pending").order_by(review_requests.c.created_at.desc()).limit(limit)
        res = await session.execute(stmt)
        return res.mappings().all()


async def decide_review(review_id: int, reviewer_id: Optional[int], status: str, reviewer_notes: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if status not in {"approved", "rejected"}:
        raise ValueError("invalid review status")

    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        before = await session.execute(select(review_requests).where(review_requests.c.id == review_id))
        current = before.mappings().first()
        if not current:
            return None

        audit_log = list(current.get("audit_log") or [])
        audit_log.append({"event": status, "reviewer_id": reviewer_id, "notes": reviewer_notes, "timestamp": _now().isoformat()})
        await session.execute(
            update(review_requests)
            .where(review_requests.c.id == review_id)
            .values(
                status=status,
                reviewer_id=reviewer_id,
                reviewer_notes=reviewer_notes,
                audit_log=audit_log,
                decided_at=_now(),
            )
        )
        await session.commit()
        return await get_review_request(review_id)
