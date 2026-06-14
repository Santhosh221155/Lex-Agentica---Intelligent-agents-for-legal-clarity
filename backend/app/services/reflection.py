import asyncio
from typing import Any, Dict, List

from app.observability import log_event, record_agent_latency


REFLECTION_PROMPT_TEMPLATE = (
    "You are a reflection agent. Review the answer for missing evidence, weak citations, or hallucinations. "
    "Return a short JSON object with keys: critique, missing_evidence, weak_citations, hallucination_flags, revised_answer, confidence."
)


def _extract_citations(retrieval_res: Dict[str, Any]) -> List[str]:
    citations = []
    for chunk in retrieval_res.get("chunks") or []:
        label = chunk.get("source") or chunk.get("filename") or chunk.get("chunk_id")
        if label and label not in citations:
            citations.append(label)
    return citations


async def reflect_answer(query: str, plan: Dict[str, Any], retrieval_res: Dict[str, Any], answer_text: str, validation_res: Dict[str, Any] | None = None) -> Dict[str, Any]:
    started = asyncio.get_event_loop().time()
    citations = _extract_citations(retrieval_res or {})
    issues = (validation_res or {}).get("issues") or []
    hallucination_risk = (validation_res or {}).get("hallucination_risk") or "LOW"

    missing_evidence = not citations
    weak_citations = len(citations) < 2
    hallucination_flags = []
    if hallucination_risk == "HIGH":
        hallucination_flags.append("high_validation_risk")
    if missing_evidence:
        hallucination_flags.append("no_citations")
    if any(issue.get("type") == "weak_support" for issue in issues):
        hallucination_flags.append("weak_support")

    critique_parts = []
    if missing_evidence:
        critique_parts.append("No explicit citations were available for the answer.")
    if weak_citations:
        critique_parts.append("Citation coverage is sparse and should be strengthened.")
    if hallucination_flags:
        critique_parts.append("Potential hallucination risk needs reviewer attention.")
    if not critique_parts:
        critique_parts.append("The answer is grounded in retrieved evidence and has acceptable citation coverage.")

    revised_answer = answer_text.strip()
    if hallucination_flags:
        revised_answer = revised_answer.rstrip() + "\n\nReflection note: Evidence coverage is limited, so this answer should be treated as a reviewed draft until it is approved."

    confidence = 0.9
    if missing_evidence:
        confidence -= 0.35
    if weak_citations:
        confidence -= 0.15
    if hallucination_flags:
        confidence -= 0.2
    if issues:
        confidence -= min(0.15, 0.05 * len(issues))
    confidence = max(0.0, min(1.0, confidence))

    elapsed = asyncio.get_event_loop().time() - started
    record_agent_latency("reflection", elapsed)
    result = {
        "prompt": REFLECTION_PROMPT_TEMPLATE,
        "critique": critique_parts,
        "missing_evidence": missing_evidence,
        "weak_citations": weak_citations,
        "hallucination_flags": hallucination_flags,
        "revised_answer": revised_answer,
        "confidence": round(confidence, 2),
        "citations": citations,
        "latency_ms": round(elapsed * 1000, 2),
    }
    log_event("reflection.completed", query=query[:160], confidence=result["confidence"], hallucination_flags=hallucination_flags, citations=len(citations))
    await asyncio.sleep(0)
    return result