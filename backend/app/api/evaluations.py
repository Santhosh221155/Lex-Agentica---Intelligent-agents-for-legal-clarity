from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.auth import get_admin_user
from app.services.evaluation_runner import run_evaluation_dataset
from app.services.evaluation_store import list_evaluation_runs, list_evaluation_records, get_evaluation_run, summarize_run

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


class EvaluationRequest(BaseModel):
    dataset_path: str = Field(..., min_length=1)
    name: str = Field(default="portfolio-eval", max_length=255)


@router.post("/run")
async def run_evaluation(payload: EvaluationRequest, user: dict = Depends(get_admin_user)):
    return await run_evaluation_dataset(payload.dataset_path, name=payload.name, created_by=user.get("id"))


@router.get("/runs")
async def evaluation_runs(limit: int = Query(20, ge=1, le=100), user: dict = Depends(get_admin_user)):
    return await list_evaluation_runs(limit=limit)


@router.get("/runs/{run_id}")
async def evaluation_run_detail(run_id: int, user: dict = Depends(get_admin_user)):
    run = await get_evaluation_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="not_found")
    records = await list_evaluation_records(run_id)
    summary = await summarize_run(run_id)
    return {"run": run, "summary": summary, "records": records}


@router.get("/dashboard")
async def evaluation_dashboard(limit: int = Query(10, ge=1, le=50), user: dict = Depends(get_admin_user)):
    runs = await list_evaluation_runs(limit=limit)
    latest = runs[0] if runs else None
    latest_summary = await summarize_run(latest["id"]) if latest else {}
    return {
        "runs": runs,
        "latest_summary": latest_summary,
        "latest_run": latest,
    }
