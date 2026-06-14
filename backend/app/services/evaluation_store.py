from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.models import evaluation_records, evaluation_runs
from app.services.db import get_session_factory


async def create_evaluation_run(name: str, dataset_name: Optional[str] = None, config: Optional[Dict[str, Any]] = None, summary: Optional[Dict[str, Any]] = None, created_by: Optional[int] = None) -> Optional[Dict[str, Any]]:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = evaluation_runs.insert().values(
            name=name,
            dataset_name=dataset_name,
            config=config or {},
            summary=summary or {},
            created_by=created_by,
        )
        res = await session.execute(stmt)
        await session.commit()
        run_id = res.inserted_primary_key[0] if res.inserted_primary_key else None
        if run_id is None:
            return None
        return await get_evaluation_run(run_id)


async def get_evaluation_run(run_id: int) -> Optional[Dict[str, Any]]:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = select(evaluation_runs).where(evaluation_runs.c.id == run_id)
        res = await session.execute(stmt)
        return res.mappings().first()


async def list_evaluation_runs(limit: int = 50) -> List[Dict[str, Any]]:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = select(evaluation_runs).order_by(evaluation_runs.c.created_at.desc()).limit(limit)
        res = await session.execute(stmt)
        return res.mappings().all()


async def add_evaluation_record(run_id: int, question: str, retrieved_context: Optional[List[Dict[str, Any]]], answer: Optional[str], metrics: Optional[Dict[str, Any]], latencies: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = evaluation_records.insert().values(
            run_id=run_id,
            question=question,
            retrieved_context=retrieved_context or [],
            answer=answer,
            metrics=metrics or {},
            latencies=latencies or {},
        )
        res = await session.execute(stmt)
        await session.commit()
        record_id = res.inserted_primary_key[0] if res.inserted_primary_key else None
        if record_id is None:
            return None
        return await get_evaluation_record(record_id)


async def get_evaluation_record(record_id: int) -> Optional[Dict[str, Any]]:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = select(evaluation_records).where(evaluation_records.c.id == record_id)
        res = await session.execute(stmt)
        return res.mappings().first()


async def list_evaluation_records(run_id: int) -> List[Dict[str, Any]]:
    SessionLocal = get_session_factory()
    async with SessionLocal() as session:
        stmt = select(evaluation_records).where(evaluation_records.c.run_id == run_id).order_by(evaluation_records.c.created_at.asc())
        res = await session.execute(stmt)
        return res.mappings().all()


async def summarize_run(run_id: int) -> Dict[str, Any]:
    records = await list_evaluation_records(run_id)
    metric_names = ["faithfulness", "context_precision", "context_recall", "answer_relevancy", "hallucination_score", "answer_quality_score"]
    summary: Dict[str, Any] = {f"avg_{name}": 0.0 for name in metric_names}
    if not records:
        return summary

    for metric_name in metric_names:
        values = [float((record.get("metrics") or {}).get(metric_name, 0.0)) for record in records]
        summary[f"avg_{metric_name}"] = sum(values) / len(values) if values else 0.0
    return summary
