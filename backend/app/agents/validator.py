import asyncio
import json
from typing import Any, Dict, List

import os

from app.observability import record_validation_failure, record_hallucination_detection, record_agent_latency, log_event


async def validate(query: str, plan: dict, retrieval_res: dict, tools_res: dict, memory_res: dict):
    """Validate the plan and evidence bundle before synthesis.

    This is a deterministic validator that checks for evidence presence,
    tool failures, and whether the query appears to be answerable from the
    retrieved evidence and memory context.
    """
    started = asyncio.get_event_loop().time()
    issues: List[Dict[str, Any]] = []

    chunks = retrieval_res.get("chunks") or []
    if not chunks:
        issues.append({"type": "no_evidence", "msg": "No retrieval evidence found."})

    failed_tools = {
        name: result.get("error", "tool_failed")
        for name, result in (tools_res or {}).items()
        if isinstance(result, dict) and not result.get("success", True)
    }
    if failed_tools:
        issues.append({"type": "tool_failure", "msg": "One or more tools failed.", "tools": failed_tools})

    evidence_blob = " ".join(
        [
            query.lower(),
            json.dumps(chunks).lower(),
            json.dumps(memory_res or {}).lower(),
            json.dumps(tools_res or {}).lower(),
        ]
    )
    key_terms = [tok for tok in query.lower().split() if len(tok) > 3][:8]
    supported_terms = sum(1 for term in key_terms if term in evidence_blob)
    if key_terms and supported_terms == 0:
        issues.append({"type": "weak_support", "msg": "Evidence does not overlap with query terms."})

    rerank_scores = [float(chunk.get("rerank_score", chunk.get("score", 0.0)) or 0.0) for chunk in chunks]
    top_rerank = max(rerank_scores) if rerank_scores else 0.0
    avg_rerank = sum(rerank_scores) / len(rerank_scores) if rerank_scores else 0.0
    evidence_quality = min(1.0, max(0.0, (supported_terms / max(1, len(key_terms))) if key_terms else 0.5))
    rerank_quality = min(1.0, max(0.0, (top_rerank if top_rerank <= 1.0 else top_rerank / (abs(top_rerank) + 1.0))))

    if any(word in query.lower() for word in ["why", "cause", "analyze", "explain"]):
        required = ["retrieval", "memory"]
        missing = [step for step in required if step not in (plan.get("steps") or []) and not plan.get(step)]
        if missing:
            issues.append({"type": "plan_gap", "msg": "Planned workflow missing expected reasoning steps.", "missing": missing})

    confidence = 0.35 + (0.35 * evidence_quality) + (0.15 * rerank_quality) + (0.1 * (1.0 if not failed_tools else 0.0)) + (0.05 if chunks else 0.0)
    if failed_tools:
        confidence -= 0.15
    if any(i.get("type") == "weak_support" for i in issues):
        confidence -= 0.1
    if not chunks:
        confidence -= 0.2
    confidence = max(0.0, min(1.0, confidence))

    threshold = float(os.getenv("REVIEW_CONFIDENCE_THRESHOLD", "0.72"))
    review_required = confidence < threshold

    hallucination_risk = "LOW"
    if not chunks:
        hallucination_risk = "HIGH"
    elif any(i.get("type") == "weak_support" for i in issues):
        hallucination_risk = "MEDIUM"

    if issues:
        record_validation_failure(issues[0].get("type", "validation_issue"))
    if hallucination_risk != "LOW":
        record_hallucination_detection(hallucination_risk.lower())

    breakdown = {
        "evidence_quality": round(evidence_quality, 2),
        "rerank_quality": round(rerank_quality, 2),
        "avg_rerank_score": round(avg_rerank, 4),
        "supported_terms": supported_terms,
        "key_terms": len(key_terms),
        "threshold": threshold,
    }

    await asyncio.sleep(0)
    elapsed = asyncio.get_event_loop().time() - started
    record_agent_latency("validator", elapsed)
    log_event("validator.completed", confidence=round(confidence, 2), review_required=review_required, hallucination_risk=hallucination_risk)
    return {
        "issues": issues,
        "confidence": round(confidence, 2),
        "hallucination_risk": hallucination_risk,
        "review_required": review_required,
        "confidence_threshold": threshold,
        "confidence_breakdown": breakdown,
        "rerank_summary": {
            "top_rerank": round(top_rerank, 4),
            "avg_rerank": round(avg_rerank, 4),
            "chunks": len(chunks),
        },
    }
