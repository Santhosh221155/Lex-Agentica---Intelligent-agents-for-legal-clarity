import asyncio
import os
import time
from collections import Counter
from typing import Any, Dict, List

from app.observability import log_event, record_agent_latency, record_reranker_latency

RERANK_TIMEOUT_SEC = float(os.getenv("RERANK_TIMEOUT_SEC", "5.0"))

_RERANKER_ENCODER = None
_RERANKER_MODEL_NAME: str | None = None


def _load_encoder(model_name: str):
    global _RERANKER_ENCODER, _RERANKER_MODEL_NAME
    load_started = time.time()
    log_event("reranker.model_load_start", model=model_name)
    if _RERANKER_ENCODER is not None and _RERANKER_MODEL_NAME == model_name:
        log_event(
            "reranker.model_load_complete",
            model=model_name,
            cached=True,
            latency_ms=round((time.time() - load_started) * 1000, 2),
        )
        return _RERANKER_ENCODER

    from sentence_transformers import CrossEncoder

    encoder = CrossEncoder(model_name)
    _RERANKER_ENCODER = encoder
    _RERANKER_MODEL_NAME = model_name
    log_event(
        "reranker.model_load_complete",
        model=model_name,
        latency_ms=round((time.time() - load_started) * 1000, 2),
    )
    return encoder


def _tokenize(text: str) -> List[str]:
    import re

    return [token for token in re.split(r"\W+", (text or "").lower()) if len(token) >= 2]


def _heuristic_score(query: str, content: str, prior_score: float = 0.0) -> float:
    q_tokens = Counter(_tokenize(query))
    c_tokens = Counter(_tokenize(content))
    overlap = sum(min(q_tokens[token], c_tokens[token]) for token in q_tokens)
    coverage = overlap / max(1, len(q_tokens))
    density = overlap / max(1, len(c_tokens))
    return float((coverage * 0.7) + (density * 0.2) + (prior_score * 0.1))


def _explain_score(query: str, candidate: Dict[str, Any], score: float, original_rank: int) -> str:
    query_terms = set(_tokenize(query))
    content_terms = set(_tokenize(candidate.get("content", "")))
    matched = sorted(query_terms.intersection(content_terms))[:6]
    source = candidate.get("source") or candidate.get("filename") or candidate.get("chunk_id") or "candidate"
    if matched:
        rationale = f"matched terms {', '.join(matched)}"
    else:
        rationale = "semantic relevance from the cross-encoder"
    return f"{source} moved from rank {original_rank + 1} because it {rationale}; rerank score {score:.3f}."


async def rerank_candidates(query: str, candidates: List[Dict[str, Any]], top_n: int = 5) -> Dict[str, Any]:
    started = time.time()
    doc_lengths = [len(str(candidate.get("content", "") or "")) for candidate in candidates]
    log_event(
        "reranker.enter",
        query=query[:120],
        candidates=len(candidates),
        top_n=top_n,
        timeout_sec=RERANK_TIMEOUT_SEC,
        model=os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
        doc_length_min=min(doc_lengths) if doc_lengths else None,
        doc_length_max=max(doc_lengths) if doc_lengths else None,
        doc_length_avg=(sum(doc_lengths) / len(doc_lengths)) if doc_lengths else None,
    )
    if not candidates:
        elapsed = time.time() - started
        record_reranker_latency(elapsed)
        record_agent_latency("reranker", elapsed)
        log_event(
            "reranker.exit",
            model=None,
            candidates=0,
            top_n=top_n,
            outcome="empty_input",
            latency_ms=round(elapsed * 1000, 2),
        )
        return {"chunks": [], "latency_ms": round(elapsed * 1000, 2), "model": None, "scores": []}

    model_name = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    enable_model = os.getenv("ENABLE_RERANKER", "1").lower() not in {"0", "false", "no"}
    ranked = list(candidates)

    scores: List[float]
    used_model = None
    rerank_outcome = "heuristic"

    def _build_output(ranked_candidates: List[Dict[str, Any]], score_list: List[float], model: str | None, outcome: str) -> Dict[str, Any]:
        elapsed_local = time.time() - started
        record_reranker_latency(elapsed_local)
        record_agent_latency("reranker", elapsed_local)
        log_event(
            "reranker.exit",
            model=model or "heuristic",
            candidates=len(candidates),
            top_n=top_n,
            outcome=outcome,
            latency_ms=round(elapsed_local * 1000, 2),
        )
        return {
            "chunks": ranked_candidates[: max(1, top_n)],
            "latency_ms": round(elapsed_local * 1000, 2),
            "model": model or "heuristic",
            "scores": [float(score) for score in score_list],
        }

    def _fallback(reason: str, exc: Exception | None = None) -> Dict[str, Any]:
        if exc is not None:
            log_event(
                "reranker.error",
                model=model_name,
                candidates=len(candidates),
                top_n=top_n,
                reason=reason,
                error_type=type(exc).__name__,
                error_repr=repr(exc),
            )
        else:
            log_event("reranker.error", model=model_name, candidates=len(candidates), top_n=top_n, reason=reason)

        # Preserve original candidate order; use heuristic scores as a deterministic
        # stand-in without forcing semantic re-ranking.
        scores_local = [
            _heuristic_score(
                query,
                c.get("content", ""),
                float(c.get("rrf_score", c.get("score", 0.0))),
            )
            for c in ranked
        ]
        return _build_output(list(candidates), scores_local, None, reason)

    if enable_model:
        try:
            def _predict() -> List[float]:
                predict_started = time.time()
                log_event("reranker.predict_start", model=model_name, candidates=len(ranked), top_n=top_n)
                encoder = _load_encoder(model_name)
                pairs = [[query, candidate.get("content", "")[:10000]] for candidate in ranked]
                scores_local = [float(score) for score in encoder.predict(pairs, show_progress_bar=False)]
                log_event(
                    "reranker.predict_complete",
                    model=model_name,
                    candidates=len(ranked),
                    latency_ms=round((time.time() - predict_started) * 1000, 2),
                    score_min=min(scores_local) if scores_local else None,
                    score_max=max(scores_local) if scores_local else None,
                    score_avg=(sum(scores_local) / len(scores_local)) if scores_local else None,
                )
                return scores_local

            scores = await asyncio.wait_for(asyncio.to_thread(_predict), timeout=RERANK_TIMEOUT_SEC)
            used_model = model_name
            rerank_outcome = "model"
        except asyncio.TimeoutError as exc:
            log_event(
                "reranker.timeout",
                model=model_name,
                candidates=len(candidates),
                top_n=top_n,
                timeout_sec=RERANK_TIMEOUT_SEC,
            )
            return _fallback("timeout", exc)
        except asyncio.CancelledError as exc:
            # If the request task is cancelled, we must not treat that as a successful
            # rerank. But we also should not crash the request path.
            # Return deterministic heuristic stand-in while preserving ordering.
            log_event(
                "reranker.cancelled",
                model=model_name,
                candidates=len(candidates),
                top_n=top_n,
                timeout_sec=RERANK_TIMEOUT_SEC,
            )
            return _fallback("cancelled", exc)
        except Exception:
            return _fallback("model_error")
    else:
        log_event(
            "reranker.predict_start",
            model=model_name,
            candidates=len(ranked),
            top_n=top_n,
            disabled=True,
        )
        scores = [
            _heuristic_score(query, c.get("content", ""), float(c.get("rrf_score", c.get("score", 0.0))))
            for c in ranked
        ]
        log_event(
            "reranker.predict_complete",
            model=model_name,
            candidates=len(ranked),
            top_n=top_n,
            disabled=True,
            latency_ms=0.0,
            score_min=min(scores) if scores else None,
            score_max=max(scores) if scores else None,
            score_avg=(sum(scores) / len(scores)) if scores else None,
        )
        rerank_outcome = "heuristic_disabled"

    for original_rank, (candidate, score) in enumerate(zip(ranked, scores)):
        candidate["rerank_score"] = float(score)
        candidate["original_rank"] = original_rank
        candidate["ranking_explanation"] = _explain_score(query, candidate, float(score), original_rank)

    ranked.sort(key=lambda item: item.get("rerank_score", 0.0), reverse=True)
    top_candidates = ranked[: max(1, top_n)]

    elapsed = time.time() - started
    record_reranker_latency(elapsed)
    record_agent_latency("reranker", elapsed)
    log_event(
        "reranker.completed",
        model=used_model or "heuristic",
        candidates=len(candidates),
        top_n=top_n,
        outcome=rerank_outcome,
        latency_ms=round(elapsed * 1000, 2),
    )

    return {
        "chunks": top_candidates,
        "latency_ms": round(elapsed * 1000, 2),
        "model": used_model or "heuristic",
        "scores": [float(score) for score in scores],
    }

