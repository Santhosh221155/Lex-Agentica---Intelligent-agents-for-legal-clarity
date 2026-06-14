from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from app.api.auth import get_admin_user
from app.models import evaluation_records, evaluation_runs, reflection_logs, review_requests, tools_history, traces
from app.services.db import AsyncSessionLocal
from sqlalchemy import select

router = APIRouter(prefix="/api/observability", tags=["observability"])


async def _rows(table) -> List[Dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(table).order_by(table.c.created_at.desc()))
        return res.mappings().all()


@router.get("/dashboard")
async def dashboard(user: dict = Depends(get_admin_user)):
    review_rows = await _rows(review_requests)
    reflection_rows = await _rows(reflection_logs)
    tool_rows = await _rows(tools_history)
    eval_runs = await _rows(evaluation_runs)
    eval_records = await _rows(evaluation_records)
    trace_rows = await _rows(traces)

    avg_confidence_values = [float(row.get("confidence_score") or 0.0) for row in review_rows if row.get("confidence_score") is not None]
    avg_confidence = sum(avg_confidence_values) / len(avg_confidence_values) if avg_confidence_values else 0.0
    tool_counts = Counter(row.get("tool_name") or "unknown" for row in tool_rows)

    return {
        "counts": {
            "traces": len(trace_rows),
            "reviews": len(review_rows),
            "pending_reviews": sum(1 for row in review_rows if row.get("status") == "pending"),
            "reflections": len(reflection_rows),
            "tool_executions": len(tool_rows),
            "evaluation_runs": len(eval_runs),
            "evaluation_records": len(eval_records),
        },
        "averages": {
            "review_confidence": round(avg_confidence, 4),
        },
        "tool_usage": dict(tool_counts.most_common()),
        "recent": {
            "latest_trace": trace_rows[0] if trace_rows else None,
            "latest_review": review_rows[0] if review_rows else None,
            "latest_reflection": reflection_rows[0] if reflection_rows else None,
        },
    }
