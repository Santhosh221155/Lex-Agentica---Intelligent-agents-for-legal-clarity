import asyncio
import hashlib
import os
import json
import time
from typing import List, Dict, Tuple

from app.services.redis_client import cache_get, cache_set, get_redis_client
from app.observability import record_retrieval_latency, cache_hit, cache_miss, record_agent_latency, log_event
import logging

# Defer heavy/optional vectorstore and embeddings imports to runtime and provide
# a dummy fallback so tests can run without external deps or credentials.
LOGGER = logging.getLogger(__name__)
# Do NOT import langchain or langchain_openai at module import time; those
# packages trigger heavy imports (transformers, tokenizers) which can hang
# test discovery. Resolve optionally at runtime inside `_get_vectorstore()`.
Chroma = None
OpenAIEmbeddings = None
HAS_VS = False
from app.services.retrieval_filters import infer_retrieval_filters, build_metadata_filter, filter_items, summarize_filters
from app.services.reranker import rerank_candidates
from app.services.embedding_store import get_chroma_collection_name

try:
    from rank_bm25 import BM25Okapi
except Exception:
    class BM25Okapi:  # type: ignore
        def __init__(self, corpus):
            self.corpus = corpus

        def get_scores(self, query_tokens):
            query_set = set(query_tokens)
            scores = []
            for document_tokens in self.corpus:
                document_set = set(document_tokens)
                overlap = len(query_set.intersection(document_set))
                scores.append(float(overlap) / max(1, len(query_set)))
            return scores


# Concurrency settings for batched retrieval
DEFAULT_CONCURRENCY = int(os.getenv("RETRIEVAL_CONCURRENCY", "6"))
DEFAULT_RETRY = int(os.getenv("RETRIEVAL_RETRY", "2"))
DEFAULT_TIMEOUT = float(os.getenv("RETRIEVAL_TIMEOUT_SEC", "12.0"))
DEFAULT_SPARSE_TIMEOUT = float(os.getenv("RETRIEVAL_SPARSE_TIMEOUT_SEC", "5.0"))
DEFAULT_MAX_DISTANCE = float(os.getenv("RETRIEVAL_MAX_DISTANCE", "2.0"))

CHROMA_COLLECTION = get_chroma_collection_name()
CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", os.path.join("backend", "chroma_db"))


class _DummyVectorStore:
    def similarity_search_with_score(self, *args, **kwargs):
        return []


def _get_vectorstore():
    from app.services.embedding_store import get_chroma_vectorstore

    backend = os.getenv("VECTOR_BACKEND", "chroma").lower()
    if backend == "qdrant":
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            try:
                from importlib import import_module
                from app.services.embedding_store import get_embedding_function

                QdrantVS = import_module("langchain.vectorstores").Qdrant
                from app.clients.qdrant_client import get_qdrant, ensure_collection

                q = get_qdrant()
                embeddings = get_embedding_function()
                if q is not None and embeddings is not None:
                    try:
                        ensure_collection(CHROMA_COLLECTION)
                    except Exception:
                        pass
                    return QdrantVS(client=q, collection_name=CHROMA_COLLECTION, embedding_function=embeddings)
            except Exception as e:
                LOGGER.warning("Qdrant requested but unavailable: %s; falling back to Chroma", e)

    store = get_chroma_vectorstore(CHROMA_COLLECTION)
    if store is not None:
        return store

    LOGGER.info(
        "No embedding backend available (set OPENAI_API_KEY or ENABLE_SENTENCE_TRANSFORMERS=1); "
        "dense retrieval disabled — BM25 over uploaded chunks will still be used."
    )
    return _DummyVectorStore()


async def _query_chroma(query: str, top_k: int = 5):
    try:
        log_event("retrieval.before_to_thread", query=query[:120], top_k=top_k)
        vs = _get_vectorstore()
        log_event(
            "retrieval.before_await_chroma",
            query=query[:120],
            top_k=top_k,
            vectorstore_type=str(type(vs).__name__),
        )
        raw = await asyncio.to_thread(vs.similarity_search_with_score, query, k=top_k)
        log_event("retrieval.after_await_chroma", query=query[:120], top_k=top_k, returned=len(raw or []))
        log_event("retrieval.after_to_thread", query=query[:120], top_k=top_k, returned=len(raw or []))
        return raw
    except asyncio.CancelledError as exc:
        import traceback

        log_event(
            "retrieval.exception",
            stage="_query_chroma",
            error_type=type(exc).__name__,
            error_repr=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise
    except Exception as exc:
        import traceback

        log_event(
            "retrieval.exception",
            stage="_query_chroma",
            error_type=type(exc).__name__,
            error_repr=repr(exc),
            traceback=traceback.format_exc(),
        )
        log_event("retrieval.chroma_error", error=str(exc))
        log_event("retrieval.return_path", location="_query_chroma_exception", reason=str(exc), docs_count=0)
        return []


async def _bm25_retrieve(owner_id: int, query: str, top_k: int = 5) -> List[Dict[str, object]]:
    from app.services.document_store import list_user_chunks

    log_event("retrieval.bm25.enter", owner_id=owner_id, top_k=top_k)
    try:
        chunks = await asyncio.wait_for(list_user_chunks(owner_id), timeout=DEFAULT_SPARSE_TIMEOUT)
    except asyncio.TimeoutError as exc:
        log_event("retrieval.bm25.error", owner_id=owner_id, error="timeout", timeout_sec=DEFAULT_SPARSE_TIMEOUT)
        log_event("retrieval.return_path", location="_bm25_timeout", reason="timeout", docs_count=0)
        return []
    except Exception as exc:
        log_event("retrieval.bm25.error", owner_id=owner_id, error=str(exc))
        log_event("retrieval.return_path", location="_bm25_exception", reason=str(exc), docs_count=0)
        return []

    if not chunks:
        log_event("retrieval.bm25_return", owner_id=owner_id, reason="no_chunks", returned=0)
        log_event("retrieval.return_path", location="_bm25_no_chunks", reason="no_chunks", docs_count=0)
        return []

    def _tokenize(text: str) -> List[str]:
        import re

        return [t for t in re.split(r"\W+", (text or "").lower()) if len(t) >= 2]

    corpus = [c.get("content", "") for c in chunks]
    tokenized = [_tokenize(text) for text in corpus]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(_tokenize(query))

    scored = list(enumerate(scores))
    scored.sort(key=lambda x: x[1], reverse=True)
    results = []
    for idx, score in scored[:top_k]:
        c = chunks[idx]
        results.append(
            {
                "content": c.get("content"),
                "source": (c.get("metadata") or {}).get("filename") or c.get("document_filename") or "unknown",
                "page": c.get("page_number", -1),
                "score": float(score),
                "chunk_id": c.get("id"),
                "document_id": c.get("document_id"),
                "metadata": c.get("metadata") or {},
                "owner_id": c.get("owner_id"),
                "document_source": c.get("document_source"),
                "method": "bm25",
            }
        )
    log_event("retrieval.bm25.exit", owner_id=owner_id, returned=len(results))
    log_event("retrieval.return_path", location="_bm25_success", reason="ok", docs_count=len(results))
    return results
    


def _rrf_fuse(dense: List[Dict[str, object]], sparse: List[Dict[str, object]], k: int = 60) -> List[Dict[str, object]]:
    log_event("retrieval.rrf.enter", dense_count=len(dense or []), sparse_count=len(sparse or []), k=k)
    scores: Dict[str, float] = {}
    merged: Dict[str, Dict[str, object]] = {}

    def _add(rank_list: List[Dict[str, object]]):
        for rank, item in enumerate(rank_list, start=1):
            key = str(item.get("chunk_id") or item.get("id") or f"{item.get('source')}:{item.get('page')}:{rank}")
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in merged:
                merged[key] = dict(item)

    _add(dense)
    _add(sparse)

    fused = []
    for key, score in scores.items():
        item = merged.get(key, {})
        item["rrf_score"] = float(score)
        fused.append(item)
    fused.sort(key=lambda x: x.get("rrf_score", 0.0), reverse=True)
    log_event("retrieval.rrf.exit", fused_count=len(fused))
    return fused


async def _retrieve_impl(query: str, plan: dict):
    """Hybrid retrieval (dense + BM25) with RRF fusion.

    Returns dict: {strategy, chunks, source, warning}.
    """
    overall_started = time.time()
    log_event(
        "retrieval.start",
        query=query[:120],
        retrieval_strategy=plan.get("retrieval_strategy") if isinstance(plan, dict) else None,
        plan_keys=list(plan.keys()) if isinstance(plan, dict) else None,
    )
    log_event(
        "retrieval.enter",
        query=query[:120],
        retrieval_strategy=plan.get("retrieval_strategy") if isinstance(plan, dict) else None,
        plan_keys=list(plan.keys()) if isinstance(plan, dict) else None,
    )

    log_event(
        "retrieval.enter_try",
        query=query[:120],
        retrieval_strategy=plan.get("retrieval_strategy") if isinstance(plan, dict) else None,
    )

    redis = get_redis_client()
    user_id = None
    try:
        user_id = plan.get("user_id") if isinstance(plan, dict) else None
    except Exception:
        user_id = None

    retrieval_filters = infer_retrieval_filters(query, plan)
    metadata_filter = build_metadata_filter(user_id, retrieval_filters)
    disable_sparse = bool((plan or {}).get("disable_sparse")) if isinstance(plan, dict) else False
    cache_key = "retrieval:" + hashlib.sha256(json.dumps({"query": query, "user_id": user_id, "filters": retrieval_filters}, sort_keys=True).encode("utf-8")).hexdigest()

    # Try cache
    if redis is not None:
        try:
            cached = await cache_get(cache_key)
            if cached:
                cache_hit()
                try:
                    cached_json = json.loads(cached)
                    docs_count = len(cached_json.get("chunks") or []) if isinstance(cached_json, dict) else None
                    log_event("retrieval.return_path", location="cache_hit", reason="cache_matched", docs_count=docs_count)
                except Exception:
                    log_event("retrieval.return_path", location="cache_hit", reason="cache_matched", docs_count=None)
                return json.loads(cached)
        except Exception:
            await asyncio.sleep(0)
    cache_miss()

    # Pre-query verification (dense retrieval)
    try:
        from app.services.embedding_store import count_chroma_documents

        dense_doc_count = count_chroma_documents(CHROMA_COLLECTION)
    except Exception:
        dense_doc_count = None

    log_event(
        "retrieval.precheck",
        collection_name=CHROMA_COLLECTION,
        dense_doc_count=dense_doc_count,
        user_id=user_id,
        filter_summary=summarize_filters(retrieval_filters),
    )

    try:
        # Now run the real retrieval against the vectorstore
        t0 = time.time()

        vs = _get_vectorstore()

        if metadata_filter is None:
            raw = await _query_chroma(query, top_k=20)
        else:
            try:
                raw = await asyncio.to_thread(
                    vs.similarity_search_with_score,
                    query,
                    k=20,
                    filter=metadata_filter,
                )
            except asyncio.CancelledError:
                raise
    except asyncio.CancelledError as exc:
        # If the request task is being cancelled (timeout/caller cancellation), we still want
        # to return a safe empty result rather than propagating cancellation and triggering
        # higher-level fallback paths that can yield docs=0.
        import traceback

        log_event(
            "retrieval.cancelled",
            stage="_retrieve_impl_dense_boundary",
            error_type=type(exc).__name__,
            error_repr=repr(exc),
            traceback=traceback.format_exc(),
        )
        return {
            "strategy": plan.get("retrieval_strategy"),
            "chunks": [],
            "source": "chroma",
            "warning": "retrieval cancelled",
            "retrieval_filters": retrieval_filters,
            "candidate_count": 0,
        }
    except Exception as exc:
        import traceback

        log_event(
            "retrieval.exception",
            stage="_retrieve_impl_dense_boundary",
            error_type=type(exc).__name__,
            error_repr=repr(exc),
            traceback=traceback.format_exc(),
        )
        raise

    # Immediate after-call logging (first score/meta)
    try:
        if raw:
            first_doc, first_score = raw[0]
            first_meta = getattr(first_doc, "metadata", None) or {}
            log_event(
                "retrieval.chroma_call_result",
                returned=len(raw),
                first_score=first_score,
                first_meta=first_meta,
            )
        else:
            log_event("retrieval.chroma_call_result", returned=0)
    except Exception as exc:
        log_event("retrieval.chroma_call_result_error", error=str(exc))

    dense_elapsed = time.time() - t0
    log_event("retrieval.dense.exit", raw_count=len(raw or []), dense_latency_ms=round(dense_elapsed * 1000, 2))
    record_retrieval_latency(dense_elapsed)
    log_event("retrieval.after_chroma", query=query[:120], raw_count=len(raw or []), dense_latency_ms=round(dense_elapsed * 1000, 2))

    if not raw:
        log_event(
            "retrieval.empty",
            collection_name=CHROMA_COLLECTION,
            user_id=user_id,
            filter_summary=summarize_filters(retrieval_filters),
            metadata_filter=metadata_filter,
        )

    max_distance = DEFAULT_MAX_DISTANCE
    disable_distance_filter = os.getenv("RETRIEVAL_DISABLE_DISTANCE_FILTER", "0").strip().lower() in {"1", "true", "yes", "on"}
    dense_chunks = []
    skipped_by_distance = 0
    for index, (doc, score) in enumerate(raw or []):
        # Chroma returns distance (lower = more similar).
        accepted = disable_distance_filter or float(score) <= max_distance
        if not accepted:
            skipped_by_distance += 1
            continue
        meta = doc.metadata or {}
        combined_metadata = dict(meta)
        combined_metadata.update(retrieval_filters)
        dense_chunks.append(
            {
                "content": doc.page_content,
                "source": meta.get("filename") or meta.get("source") or "unknown",
                "page": int(meta.get("page_number") if meta.get("page_number") is not None else meta.get("page") or -1),
                "score": float(score),
                "chunk_id": meta.get("chunk_id") or meta.get("id") or None,
                "document_id": meta.get("document_id") or None,
                "metadata": combined_metadata,
                "owner_id": meta.get("owner_id"),
                "document_source": meta.get("source"),
                "method": "dense",
            }
        )
    log_event(
        "dense_conversion.exit",
        raw_results_count=len(raw or []),
        converted_chunks_count=len(dense_chunks),
        skipped_by_distance=skipped_by_distance,
    )

    sparse_chunks = []
    if disable_sparse:
        pass
    elif user_id is not None:
        try:
            log_event("retrieval.sparse.enter", user_id=user_id)
            sparse_chunks = await _bm25_retrieve(user_id, query, top_k=20)
            log_event("retrieval.sparse.after_bm25", user_id=user_id, returned=len(sparse_chunks))
            sparse_chunks = filter_items(sparse_chunks, retrieval_filters)
            log_event("retrieval.sparse.exit", user_id=user_id, returned=len(sparse_chunks))
        except asyncio.TimeoutError:
            log_event("retrieval.bm25.timeout", user_id=user_id, timeout_sec=DEFAULT_SPARSE_TIMEOUT)
            sparse_chunks = []
        except Exception as exc:
            log_event("retrieval.sparse.error", user_id=user_id, error=str(exc))
            sparse_chunks = []

    # Apply retrieval filters to dense results
    dense_chunks = filter_items(dense_chunks, retrieval_filters)

    log_event("retrieval.fusion.before", dense_count=len(dense_chunks), sparse_count=len(sparse_chunks))
    fused = _rrf_fuse(dense_chunks, sparse_chunks)
    log_event("retrieval.fusion.after", fused_count=len(fused), dense_count=len(dense_chunks), sparse_count=len(sparse_chunks))

    fused = filter_items(fused, retrieval_filters)

    sparse_count = len(sparse_chunks)

    # Candidate stage: keep more candidates for reranking
    candidates_k = max(20, plan.get("candidates_k", 20))
    candidates = fused[:candidates_k]
    candidates_count = len(candidates)

    rerank_started = time.time()
    rerank_res = await rerank_candidates(query, candidates, top_n=plan.get("top_k", 5))
    chunks = rerank_res.get("chunks") or []
    log_event(
        "retrieval.after_rerank",
        candidates=candidates_count,
        reranked_chunks=len(chunks),
        rerank_model=rerank_res.get("model"),
        rerank_latency_ms=rerank_res.get("latency_ms", 0.0),
    )

    rerank_elapsed = rerank_res.get("latency_ms", 0.0) / 1000.0 if rerank_res else time.time() - rerank_started
    total_elapsed = time.time() - overall_started
    record_agent_latency("retrieval", total_elapsed)

    # ---- Indirect prompt-injection defense ----
    # Sanitize chunk content to strip any instruction-like patterns embedded
    # in uploaded documents before the text reaches the LLM as context.
    try:
        from app.services.security import sanitize_retrieved_text
        for chunk in chunks:
            if isinstance(chunk, dict) and "content" in chunk:
                chunk["content"] = sanitize_retrieved_text(chunk["content"])
    except Exception:
        pass  # defense-in-depth; never block retrieval on sanitization failure

    log_event(
        "retrieval.completed",
        user_id=user_id,
        query=query[:160],
        dense_candidates=len(dense_chunks),
        sparse_candidates=len(sparse_chunks),
        fused_candidates=len(fused),
        reranked_candidates=len(chunks),
        filter_summary=summarize_filters(retrieval_filters),
        dense_latency_ms=round(dense_elapsed * 1000, 2),
        rerank_latency_ms=round(rerank_elapsed * 1000, 2),
    )
    log_event(
        "retrieval.complete",
        user_id=user_id,
        docs_count=len(chunks),
        total_latency_ms=round(total_elapsed * 1000, 2),
    )

    if not chunks:
        result = {
            "strategy": plan.get("retrieval_strategy"),
            "chunks": [],
            "source": "hybrid",
            "warning": "No relevant content found in documents",
            "retrieval_filters": retrieval_filters,
            "candidate_count": len(candidates),
            "timings": {
                "dense_ms": round(dense_elapsed * 1000, 2),
                "rerank_ms": round(rerank_elapsed * 1000, 2),
                "total_ms": round(total_elapsed * 1000, 2),
            },
        }
    else:
        result = {
            "strategy": plan.get("retrieval_strategy"),
            "chunks": chunks,
            "source": "hybrid",
            "retrieval_filters": retrieval_filters,
            "candidate_count": len(candidates),
            "reranker": {
                "model": rerank_res.get("model"),
                "scores": rerank_res.get("scores") or [],
                "latency_ms": rerank_res.get("latency_ms", 0.0),
            },
            "timings": {
                "dense_ms": round(dense_elapsed * 1000, 2),
                "rerank_ms": round(rerank_elapsed * 1000, 2),
                "total_ms": round(total_elapsed * 1000, 2),
            },
        }

    # Cache result (best-effort, non-blocking)
    if redis is not None:
        try:
            cache_timeout = float(os.getenv("REDIS_CACHE_WRITE_TIMEOUT_SEC", "0.5"))

            async def _bg_cache_write(key: str, payload: str, ex: int, timeout: float):
                try:
                    await asyncio.wait_for(cache_set(key, payload, ex=ex), timeout=timeout)
                    log_event("retrieval.cache_write.exit", cache_key_prefix=key[:16], timeout_sec=timeout)
                except Exception as exc:
                    import traceback

                    log_event(
                        "retrieval.cache_write.error_bg",
                        cache_key_prefix=key[:16],
                        error_type=type(exc).__name__,
                        error_repr=repr(exc),
                        traceback=traceback.format_exc(),
                    )

            # Schedule background cache write and do NOT await it. This makes Redis
            # outages or slow writes best-effort and prevents cache delays from
            # cancelling or delaying the retrieval critical path.
            try:
                asyncio.create_task(_bg_cache_write(cache_key, json.dumps(result), ex=60 * 5, timeout=cache_timeout))
            except Exception as exc:
                log_event("retrieval.cache_write.schedule_error", cache_key_prefix=cache_key[:16], error=str(exc))
        except Exception:
            # Defensive: do not allow any cache scheduling errors to impact retrieval
            await asyncio.sleep(0)

    await asyncio.sleep(0)
    # Final return path log
    try:
        log_event("retrieval.return_path", location="final", docs_count=len(result.get("chunks") or []), candidate_count=result.get("candidate_count"))
    except Exception:
        log_event("retrieval.return_path", location="final", docs_count=None)
    return result


async def retrieve(query: str, plan: dict):
    try:
        return await _retrieve_impl(query, plan)
    except asyncio.CancelledError as exc:
        import traceback

        log_event("retrieval.exception", stage="retrieve_wrapper", error_type=type(exc).__name__, error_repr=repr(exc), traceback=traceback.format_exc())
        raise
    except Exception as exc:
        import traceback
        log_event("retrieval.exception", stage="retrieve_wrapper", error_type=type(exc).__name__, error_repr=repr(exc), traceback=traceback.format_exc())
        raise


async def _retrieve_single_with_retries(query: str, plan: dict, retries: int = DEFAULT_RETRY):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            # run the normal retrieve flow but allow an overall timeout
            return await asyncio.wait_for(retrieve(query, plan), timeout=DEFAULT_TIMEOUT)
        except asyncio.TimeoutError as e:
            last_exc = e
            log_event("retrieval.retry_timeout", attempt=attempt, retries=retries, timeout_sec=DEFAULT_TIMEOUT, error=str(e))
            await asyncio.sleep(0.1 * (attempt + 1))
            continue
        except Exception as e:
            last_exc = e
            log_event("retrieval.retry_exception", attempt=attempt, retries=retries, error=str(e))
            await asyncio.sleep(0.1 * (attempt + 1))
            continue
    # All retries failed: return a safe empty result
    log_event("retrieval.return_path", location="_retrieve_single_with_retries_fallback", reason="all_retries_failed", docs_count=0)
    log_event("retrieval.retry_fallback", retries=retries, last_error=str(last_exc) if last_exc else None)
    return {
        "strategy": plan.get("retrieval_strategy"),
        "chunks": [],
        "source": "chroma",
        "warning": "No relevant content found in documents",
    }


async def batch_retrieve(queries: List[str], plan: dict, concurrency: int = DEFAULT_CONCURRENCY):
    """Run retrieval for multiple queries in parallel with limited concurrency.

    Returns a list of retrieval results in the same order as queries.
    """
    sem = asyncio.Semaphore(concurrency)

    async def worker(q):
        async with sem:
            try:
                return await _retrieve_single_with_retries(q, plan)
            except Exception:
                # Ensure worker never raises
                log_event("retrieval.worker.exception", query=q[:120], plan_keys=list(plan.keys()) if isinstance(plan, dict) else None)
                return {"strategy": plan.get("retrieval_strategy"), "docs": [], "source": "error"}

    tasks = [asyncio.create_task(worker(q)) for q in queries]
    results = await asyncio.gather(*tasks)
    return results
