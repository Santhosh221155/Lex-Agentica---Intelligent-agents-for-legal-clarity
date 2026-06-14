from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agents import retrieval, synthesizer, validator, memory, tool_agent
from app.services.evaluation_metrics import compute_metric_bundle
from app.services.evaluation_store import create_evaluation_run, add_evaluation_record, summarize_run


async def _collect_answer(query: str, retrieval_res: Dict[str, Any], validation_res: Dict[str, Any]) -> str:
    prompt_plan = {"retrieval_strategy": "hybrid", "max_docs": 5}
    chunks = retrieval_res.get("chunks") or []
    if not chunks:
        return "No grounded answer could be generated."

    answer_parts: List[str] = []
    async for token in synthesizer.stream_synthesize(query, prompt_plan, retrieval_res, {}, {}, validation_res):
        if token.get("role") in {"synthesizer", "revision"} and token.get("text"):
            answer_parts.append(str(token["text"]))
    return "".join(answer_parts).strip()


async def run_evaluation_dataset(dataset_path: str, name: str = "portfolio-eval", created_by: Optional[int] = None) -> Dict[str, Any]:
    path = Path(dataset_path)
    with path.open("r", encoding="utf-8") as handle:
        dataset = json.load(handle)

    run = await create_evaluation_run(name=name, dataset_name=path.name, config={"dataset_path": dataset_path}, created_by=created_by)
    if not run:
        raise RuntimeError("failed_to_create_evaluation_run")

    for item in dataset:
        question = item.get("query", "")
        relevant_docs = item.get("relevant_docs", [])
        plan = {"retrieval_strategy": "hybrid", "max_docs": 5, "user_id": created_by or 0, "candidates_k": 20}
        retrieval_res = await retrieval.retrieve(question, plan)
        memory_res = await memory.fetch_memory(created_by or 0, question, plan)
        tools_res = {}
        validation_res = await validator.validate(question, plan, retrieval_res, tools_res, memory_res)
        answer = await _collect_answer(question, retrieval_res, validation_res)
        metrics = compute_metric_bundle(question, retrieval_res.get("chunks") or [], answer)
        metrics["expected_relevant_docs"] = len(relevant_docs)
        latencies = {
            "retrieval_ms": (retrieval_res.get("timings") or {}).get("total_ms", 0.0),
            "validation_ms": 0.0,
        }
        await add_evaluation_record(run["id"], question, retrieval_res.get("chunks") or [], answer, metrics, latencies)

    summary = await summarize_run(run["id"])
    return {"run": run, "summary": summary}
