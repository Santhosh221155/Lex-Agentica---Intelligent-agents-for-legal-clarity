import asyncio
import json
import os
import time
import sys
from pathlib import Path
from typing import Any, Optional

# Load logging config FIRST (before importing app modules)
import logging
import logging.config
try:
    import yaml  # type: ignore
    config_path = Path(__file__).parent.parent / "config" / "logging.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            logging_config = yaml.safe_load(f)
        logging.config.dictConfig(logging_config)
except Exception:
    # If yaml isn't installed or config missing, fall back to default logging
    pass


# Load `.env` early so downstream modules that read environment variables at import-time
# (e.g. LLM clients) behave correctly when running via `uvicorn ...`.
try:
    from dotenv import load_dotenv  # type: ignore

    _repo_root = Path(__file__).resolve().parents[2]
    _backend_root = Path(__file__).resolve().parents[1]
    load_dotenv(_repo_root / ".env", override=True)
    load_dotenv(_backend_root / ".env", override=True)
except Exception:
    pass

backend_root = Path(__file__).resolve().parents[1]
backend_root_str = str(backend_root)
if backend_root_str not in sys.path:
    sys.path.insert(0, backend_root_str)

from fastapi import BackgroundTasks, FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError
from app.agents import planner, retrieval, memory, tool_agent, validator, synthesizer
from langgraph.executor import run_plan
from app.observability import (
    inc_error,
    inc_request,
    log_event,
    new_trace_id,
    get_trace_id,
    observe_request,
    set_trace_id,
)
from app.services.trace_store import save_trace
from app.services.memory_store import save_memory
from app.services.review_store import create_review_request
from app.services.db import get_database_url, database_status, ensure_schema, DATABASE_BACKEND
from app.services.ingestion import chroma_status
from app.clients.qdrant_client import init_qdrant
from app.services.rate_limit import check_rate_limit, build_rate_key
from app.services.security import sanitize_query, is_suspicious_prompt, scan_text_fields, is_sensitive_request, detect_prompt_injection
from app.embeddings import warm_embedding_model
from app.services.embedding_store import get_chroma_vectorstore, get_chroma_collection_name
try:
    from prometheus_client import make_asgi_app
except Exception:
    make_asgi_app = None
from app.services.redis_client import get_redis_client, redis_status
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import HTTPException, status
from app.api.auth import router as auth_router, get_current_user, get_admin_user

RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    user_id: str = Field(default="user:local", max_length=128)
    doc_id: Optional[int] = None


class QueryResponse(BaseModel):
    plan: dict[str, Any]
    first_chunk: Any


class HealthResponse(BaseModel):
    status: str
    redis: str
    postgres: str
    vector_store: str
    metrics: str


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Fixed-window rate limit per client IP (no auth required)
        ip = None
        try:
            ip = request.client.host if request.client else 'anon'
        except Exception:
            ip = 'anon'
        redis = get_redis_client()
        if redis is None:
            return await call_next(request)
        key = f"rl:{ip}:{int(time.time()//60)}"
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 65)
            if count > RATE_LIMIT_PER_MIN:
                raise HTTPException(status_code=429, detail="rate limit exceeded")
        except HTTPException:
            raise
        except Exception:
            pass
        return await call_next(request)


class PromptInjectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        """Multi-layer prompt-injection gate.

        Scans ALL string fields in JSON bodies (not just 'query') and GET
        query parameters.  Blocked requests are logged with IP for forensic
        analysis.
        """
        ip = request.client.host if request.client else "anon"

        # --- Scan GET query parameters ---
        try:
            for key, value in request.query_params.items():
                if isinstance(value, str) and len(value) > 3 and is_suspicious_prompt(value):
                    log_event(
                        "security.injection_blocked",
                        source="query_param",
                        field=key,
                        ip=ip,
                        path=request.url.path,
                    )
                    polite_response = "Sorry, I can't help with requests that attempt to access hidden instructions, internal configuration, or restricted information. Please ask a question related to the available documents."
                    if request.url.path == "/api/stream-query":
                        async def polite_stream():
                            yield f"data: {json.dumps({'role': 'synthesizer', 'text': polite_response, 'provenance': []})}\n\n"
                        return StreamingResponse(polite_stream(), media_type="text/event-stream")
                    else:
                        return JSONResponse({
                            "plan": {},
                            "first_chunk": {
                                "role": "synthesizer",
                                "text": polite_response,
                                "provenance": []
                            }
                        })
        except Exception:
            pass

        # --- Scan JSON body (all string fields) ---
        body_bytes = None
        try:
            content_type = request.headers.get("content-type", "")
            if content_type.startswith("application/json"):
                body_bytes = await request.body()
                if body_bytes:
                    import json as _json
                    body = _json.loads(body_bytes)
                    if isinstance(body, dict):
                        # Scan every string field
                        flagged = scan_text_fields(body)
                        if flagged:
                            log_event(
                                "security.injection_blocked",
                                source="json_body",
                                field=flagged,
                                ip=ip,
                                path=request.url.path,
                            )
                            polite_response = "Sorry, I can't help with requests that attempt to access hidden instructions, internal configuration, or restricted information. Please ask a question related to the available documents."
                            if request.url.path == "/api/stream-query":
                                async def polite_stream():
                                    yield f"data: {json.dumps({'role': 'synthesizer', 'text': polite_response, 'provenance': []})}\n\n"
                                return StreamingResponse(polite_stream(), media_type="text/event-stream")
                            else:
                                return JSONResponse({
                                    "plan": {},
                                    "first_chunk": {
                                        "role": "synthesizer",
                                        "text": polite_response,
                                        "provenance": []
                                    }
                                })
        except Exception:
            pass

        # --- Re-construct the request body if we read it ---
        if body_bytes is not None:
            async def receive():
                return {"type": "http.request", "body": body_bytes}
            request._receive = receive

        return await call_next(request)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        trace_id = request.headers.get("x-trace-id") or new_trace_id()
        set_trace_id(trace_id)
        start = time.time()
        log_event("request.start", method=request.method, path=request.url.path, trace_id=trace_id)
        inc_request()
        response = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = getattr(response, "status_code", 200)
            return response
        except Exception as exc:
            inc_error("http", exc.__class__.__name__)
            log_event(
                "request.error",
                method=request.method,
                path=request.url.path,
                status=status_code,
                error=exc.__class__.__name__,
                message=str(exc),
                trace_id=trace_id,
            )
            raise
        finally:
            duration = time.time() - start
            observe_request(request.method, request.url.path, status_code, duration)
            if response is not None:
                response.headers["X-Trace-Id"] = trace_id
            log_event(
                "request.end",
                method=request.method,
                path=request.url.path,
                status=status_code,
                duration=round(duration, 4),
                trace_id=trace_id,
            )


RETRIEVAL_TIMEOUT = float(os.getenv("RETRIEVAL_TASK_TIMEOUT", "5.0"))
TOOLS_TIMEOUT = float(os.getenv("TOOLS_TASK_TIMEOUT", "10.0"))
MEMORY_TIMEOUT = float(os.getenv("MEMORY_TASK_TIMEOUT", "2.0"))
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "100"))
UPLOAD_LIMIT_PER_HOUR = int(os.getenv("UPLOAD_LIMIT_PER_HOUR", "20"))

app = FastAPI(title="Agentic RAG - Legal Document Intelligence Platform")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ObservabilityMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(PromptInjectionMiddleware)
# API key auth middleware (parses x-api-key or Authorization: ApiKey <key>)
try:
    from app.middleware.api_key_auth import APIKeyAuthMiddleware
    app.add_middleware(APIKeyAuthMiddleware)
except Exception:
    pass
# Initialize optional backends (best-effort) on startup
@app.on_event("startup")
async def _init_optional_backends():
    import logging
    import time
    logger = logging.getLogger("app.startup")

    def log_step_start(step_name):
        t0 = time.time()
        logger.info(f"[STARTUP STEP] ENTER: {step_name}")
        try:
            from app.observability import log_event
            log_event(f"startup.{step_name}.enter")
        except Exception:
            pass
        return t0
    
    def log_step_end(step_name, t_start):
        elapsed = time.time() - t_start
        logger.info(f"[STARTUP STEP] EXIT: {step_name} | elapsed: {elapsed:.2f}s")
        try:
            from app.observability import log_event
            log_event(f"startup.{step_name}.exit", duration=elapsed)
        except Exception:
            pass

    t = log_step_start("hugging_face_login")
    try:
        hf_token = (os.getenv("HF_TOKEN") or "").strip()
        if hf_token and hf_token != "your_token_here":
            from huggingface_hub import login

            login(token=hf_token, add_to_git_credential=False)
            logger.info(" Hugging Face Hub token loaded")
    except Exception as exc:
        logger.warning("Hugging Face login skipped: %s", exc)
    log_step_end("hugging_face_login", t)

    t = log_step_start("embedding_model_warmup")
    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            logger.info("OPENAI_API_KEY set — skipping local sentence-transformer warmup")
        else:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(warm_embedding_model), 
                    timeout=30.0
                )
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(get_chroma_vectorstore, get_chroma_collection_name()),
                        timeout=30.0
                    )
                except Exception as chroma_exc:
                    logger.warning("Chroma vectorstore init skipped: %s", chroma_exc)
            except asyncio.TimeoutError:
                logger.warning("Embedding model warmup timed out (30s), skipping")
    except Exception as exc:
        logger.warning("Embedding backend warmup skipped: %s", exc)
    log_step_end("embedding_model_warmup", t)

    # Warm up the CrossEncoder reranker at startup so first request doesn't pay model load cost.
    t = log_step_start("reranker_warmup")
    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            logger.info("OPENAI_API_KEY set — skipping local reranker warmup")
        else:
            from app.services.reranker import _load_encoder
            reranker_model = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("Starting reranker startup warm-up for model '%s'", reranker_model)
            
            from app.observability import log_event
            log_event("reranker.startup_warm_begin", model=reranker_model)
            encoder = await asyncio.wait_for(
                asyncio.to_thread(_load_encoder, reranker_model),
                timeout=30.0
            )
            
            # Lightweight warm-up inference (single pair) to fully initialize the model.
            dummy_query = "warmup query"
            dummy_doc = "warmup document text"
            _ = await asyncio.wait_for(
                asyncio.to_thread(encoder.predict, [[dummy_query, dummy_doc]], show_progress_bar=False),
                timeout=30.0
            )
            
            log_event("reranker.startup_warm_complete", model=reranker_model)
            logger.info(" Reranker startup warm-up complete for model '%s'", reranker_model)
    except asyncio.TimeoutError:
        try:
            from app.observability import log_event
            log_event("reranker.startup_warm_failed", model=os.getenv("RERANKER_MODEL", None), error="timeout")
        except Exception:
            pass
        logger.warning("Reranker startup warm-up timed out (30s), skipping")
    except Exception as exc:
        try:
            from app.observability import log_event
            log_event("reranker.startup_warm_failed", model=os.getenv("RERANKER_MODEL", None), error=str(exc))
        except Exception:
            pass
        logger.warning("Reranker startup warm-up skipped/failed: %s", exc)
    log_step_end("reranker_warmup", t)

    # CRITICAL: Verify database connectivity and schema before starting
    t = log_step_start("database_verification")
    from app.services.db import verify_database_connection, verify_database_schema, DATABASE_AVAILABLE, DATABASE_BACKEND
    try:
        await verify_database_connection()
        if not await verify_database_schema():
            raise RuntimeError("required database tables missing; run migrations before starting the server")
    except RuntimeError:
        raise
    log_step_end("database_verification", t)

    t = log_step_start("qdrant_initialization")
    qdrant_url = os.getenv("QDRANT_URL")
    if qdrant_url and qdrant_url.strip():
        try:
            await asyncio.to_thread(init_qdrant, url=qdrant_url, api_key=os.getenv("QDRANT_API_KEY"))
        except Exception:
            pass
    else:
        logger.info("QDRANT_URL not set, skipping Qdrant initialization")
    log_step_end("qdrant_initialization", t)
    
    t = log_step_start("ensure_schema")
    try:
        await ensure_schema()
    except Exception:
        pass
    log_step_end("ensure_schema", t)
    
    # Initialize database and check availability
    try:
        from app.services.db import _initialize_db
        _initialize_db()
    except Exception:
        pass
    # Health check: warn if database is unavailable
    try:
        from app.services.db import DATABASE_AVAILABLE, DATABASE_BACKEND
        if not DATABASE_AVAILABLE:
            logger.error("Database unavailable at startup")
        else:
            logger.info("Database available (%s)", DATABASE_BACKEND)
    except Exception:
        logger.error("Could not check database availability")
    
    t = log_step_start("opentelemetry_initialization")
    # Initialize OpenTelemetry (best-effort)
    try:
        from app.observability import init_opentelemetry

        init_opentelemetry(service_name="agentic_rag")
    except Exception:
        pass
    log_step_end("opentelemetry_initialization", t)

    t = log_step_start("session_cleanup_loop_start")
    # Start background session-expiry cleanup job (every 30 minutes)
    async def _session_cleanup_loop():
        import logging
        _logger = logging.getLogger("app.session_cleanup")
        while True:
            await asyncio.sleep(1800)  # 30 minutes
            try:
                from app.services.auth import find_expired_session_users
                from app.services.document_store import delete_user_documents_hard
                from app.services.cleanup import delete_chroma_chunks, cleanup_temp_files

                expired_user_ids = await find_expired_session_users()
                if not expired_user_ids:
                    continue

                _logger.info("session_cleanup: found %d users with expired sessions", len(expired_user_ids))
                for uid in expired_user_ids:
                    try:
                        delete_chroma_chunks(uid)
                        await delete_user_documents_hard(uid)
                        cleanup_temp_files(uid)
                        _logger.info("session_cleanup: cleaned up data for user_id=%s", uid)
                    except Exception as exc:
                        _logger.warning("session_cleanup: failed for user_id=%s: %s", uid, exc)
            except Exception as exc:
                _logger.warning("session_cleanup: error: %s", exc)

    asyncio.create_task(_session_cleanup_loop())
    log_step_end("session_cleanup_loop_start", t)
    
    logger.info("[STARTUP] All steps complete! Server is ready!")
# Expose Prometheus metrics at /metrics if prometheus_client is installed
if make_asgi_app is not None:
    app.mount("/metrics", make_asgi_app())

# Register API routers
app.include_router(auth_router)
try:
    from app.api.ingest import router as ingest_router
    app.include_router(ingest_router, prefix="/api/ingest", tags=["ingest"])
except Exception:
    # best-effort; failure to import shouldn't crash the app at startup
    pass

try:
    from app.api.documents import router as documents_router
    app.include_router(documents_router)
except Exception:
    pass

try:
    from app.api.routes import router as routes_router
    app.include_router(routes_router)
except Exception:
    pass

try:
    from app.api.reviews import router as reviews_router
    app.include_router(reviews_router)
except Exception:
    pass

try:
    from app.api.evaluations import router as evaluations_router
    app.include_router(evaluations_router)
except Exception:
    pass

try:
    from app.api.observability import router as observability_router
    app.include_router(observability_router)
except Exception:
    pass

# API Keys router
try:
    from app.api.keys import router as keys_router
    app.include_router(keys_router)
except Exception:
    pass


@app.exception_handler(DBAPIError)
async def _database_exception_handler(request, exc):
    try:
        from app.observability import inc_error, log_event
        inc_error("http", exc.__class__.__name__)
        log_event(
            "http.database_exception",
            path=str(request.url),
            error=exc.__class__.__name__,
            message=str(exc),
        )
    except Exception:
        pass
    return JSONResponse(
        {"error": "database_unavailable", "detail": "Database temporarily unavailable."},
        status_code=503,
    )


@app.exception_handler(Exception)
async def _generic_exception_handler(request, exc):
    try:
        from app.observability import inc_error, log_event
        inc_error("http", exc.__class__.__name__)
        log_event("http.exception", path=str(request.url), error=exc.__class__.__name__, message=str(exc))
    except Exception:
        pass
    return JSONResponse({"error": "internal_server_error", "detail": "An unexpected error occurred."}, status_code=500)

# Initialize optional vector backends (best-effort)
try:
    from app.config import settings
    qdrant_url = getattr(settings, "QDRANT_URL", None)
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    if qdrant_url:
        try:
            init_qdrant(url=str(qdrant_url), api_key=qdrant_api_key)
        except Exception:
            pass
except Exception:
    pass


@app.get("/", response_model=dict)
async def root():
    return {
        "name": "Agentic RAG - Legal Document Intelligence Platform",
        "status": "ok",
        "docs": "/docs",
        "healthz": "/healthz",
        "readyz": "/readyz",
    }


@app.get("/healthz", response_model=HealthResponse)
async def healthz():
    redis = await redis_status()
    postgres_status = await database_status()
    postgres = postgres_status if DATABASE_BACKEND == "postgres" else f"{DATABASE_BACKEND}:{postgres_status}"
    vector_store = chroma_status()
    return {
        "status": "ok",
        "redis": redis,
        "postgres": postgres,
        "vector_store": vector_store,
        "metrics": "available" if make_asgi_app is not None else "unavailable",
    }


@app.get("/readyz", response_model=HealthResponse)
async def readyz():
    redis = await redis_status()
    postgres_status = await database_status()
    postgres = postgres_status if DATABASE_BACKEND == "postgres" else f"{DATABASE_BACKEND}:{postgres_status}"
    vector_store = chroma_status()
    return {
        "status": "ready",
        "redis": redis,
        "postgres": postgres,
        "vector_store": vector_store,
        "metrics": "available" if make_asgi_app is not None else "unavailable",
    }


@app.get("/api/db-status")
async def db_status_debug():
    """Debug endpoint: detailed database connectivity status."""
    from app.services.db import DATABASE_AVAILABLE, DATABASE_BACKEND, get_database_url, verify_database_schema
    from app.services.database_utils import _postgres_reachable
    from urllib.parse import urlparse
    
    try:
        db_url = get_database_url()
        parsed = urlparse(db_url)
        postgres_host = parsed.hostname or "unknown"
        postgres_port = parsed.port or 5432
        
        # Test direct reachability
        postgres_reachable = _postgres_reachable(parsed) if DATABASE_BACKEND == "postgres" else None
        postgres_schema = None
        if DATABASE_BACKEND == "postgres":
            postgres_schema = "ok" if await verify_database_schema() else "missing"

        return {
            "status": "available" if DATABASE_AVAILABLE else "unavailable",
            "backend": DATABASE_BACKEND,
            "postgres_host": postgres_host,
            "postgres_port": postgres_port,
            "postgres_reachable": postgres_reachable,
            "postgres_schema": postgres_schema,
            "sqlite_available": DATABASE_BACKEND == "sqlite",
            "error": None if DATABASE_AVAILABLE else "Database engine creation failed or driver missing",
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }


# Authentication endpoints removed — this deployment runs without user authentication.


async def orchestrate(query: str, user: dict, doc_id: Optional[int] = None):
    # Normalize effective identity (user_id, api_key_id)
    from app.security.identity import get_effective_identity

    eff = get_effective_identity(user or {})
    numeric_user_id = eff.get("user_id") or 0
    log_event("orchestrate.start", user_id=numeric_user_id, query=query[:240])
    trace_id = get_trace_id() or new_trace_id()
    trace = {
        "trace_id": trace_id,
        "query": query,
        "user_id": str(numeric_user_id) if numeric_user_id else None,
        "actor": eff,
        "timestamp": time.time(),
        "timings": {},
        "retrieval": None,
        "tools": None,
        "memory": None,
        "validation": None,
        "review": None,
        "reflection": None,
    }

    # Planner determines the workflow and whether validation is needed
    t0 = time.time()
    plan = await planner.plan(query, numeric_user_id)
    plan["user_id"] = numeric_user_id
    if doc_id is not None:
        plan.setdefault("retrieval_filters", {})["document_id"] = doc_id
    plan["user_role"] = "admin" if (user or {}).get("is_admin") else ("service" if eff.get("identity_type") == "api_key" else "user")
    trace["timings"]["planner"] = time.time() - t0
    log_event("orchestrate.plan", user_id=numeric_user_id, requires_validation=bool(plan.get("requires_validation")), retrieval_strategy=plan.get("retrieval_strategy"))

    # Execute plan via LangGraph executor (or fallback)
    t_start = time.time()
    retrieval_res, tools_res, memory_res, validation_res = await run_plan(query, plan, user)
    elapsed = time.time() - t_start
    # Best-effort breakdown — individual timings may be populated by agents themselves
    trace["timings"]["execution"] = elapsed
    trace["retrieval"] = {"source": retrieval_res.get("source"), "num_docs": len(retrieval_res.get("chunks") or [])}
    trace["tools"] = tools_res
    trace["memory"] = memory_res
    if validation_res is not None:
        trace["validation"] = validation_res
        log_event("orchestrate.validation", user_id=numeric_user_id, confidence=validation_res.get("confidence"), issues=len(validation_res.get("issues") or []))
        if validation_res.get("review_required"):
            trace["review"] = {
                "required": True,
                "threshold": validation_res.get("confidence_threshold"),
                "status": "pending",
                "confidence": validation_res.get("confidence"),
            }

    # Synthesizer returns an async generator of tokens; record synth start when streaming begins
    synth_generator = synthesizer.stream_synthesize(
        query, plan, retrieval_res, tools_res, memory_res, validation_res
    )
    log_event("orchestrate.ready", user_id=numeric_user_id, docs=trace["retrieval"]["num_docs"], source=trace["retrieval"]["source"])
    return plan, synth_generator, trace


@app.post("/api/query", response_model=QueryResponse)
async def query_endpoint(payload: QueryRequest, background: BackgroundTasks, request: Request, user: dict = Depends(get_current_user)):
    query = sanitize_query(payload.query)
    user_id = int(user.get("id"))
    if not query:
        return JSONResponse({"error": "missing query"}, status_code=400)
    if detect_prompt_injection(query) or is_sensitive_request(query):
        return {
            "plan": {},
            "first_chunk": {
                "role": "synthesizer",
                "text": "I'm not able to help with that. Please ask a question related to the available documents.",
                "provenance": []
            }
        }
    if is_suspicious_prompt(query):
        # Return a polite chat response instead of an error
        polite_response = "I'm not able to help with that. Please ask a question related to the available documents."
        return {
            "plan": {},
            "first_chunk": {
                "role": "synthesizer",
                "text": polite_response,
                "provenance": []
            }
        }

    # rate limiting (per user + per ip)
    ip = request.client.host if request.client else "anon"
    user_key = build_rate_key("user", str(user.get("id")), 3600)
    ip_key = build_rate_key("ip", ip, 3600)
    if not await check_rate_limit(user_key, RATE_LIMIT_PER_HOUR, 3600):
        return JSONResponse({"error": "rate_limit_exceeded"}, status_code=429)
    if not await check_rate_limit(ip_key, RATE_LIMIT_PER_HOUR, 3600):
        return JSONResponse({"error": "rate_limit_exceeded"}, status_code=429)

    # Fire-and-forget orchestration; return a run id and initial plan
    try:
        plan, gen, trace = await orchestrate(query, user, payload.doc_id)
    except Exception as exc:
        inc_error("orchestrate", exc.__class__.__name__)
        log_event("query.error", user_id=user_id, error=exc.__class__.__name__, message=str(exc))
        return JSONResponse(
            {
                "error": "orchestration_failed",
                "detail": str(exc),
            },
            status_code=503,
        )

    # collect first chunk to return quickly
    try:
        first_chunk = await gen.__anext__()
    except Exception as exc:
        inc_error("synthesizer", exc.__class__.__name__)
        log_event("query.stream_error", user_id=user_id, error=exc.__class__.__name__, message=str(exc))
        return JSONResponse(
            {
                "error": "stream_initialization_failed",
                "detail": str(exc),
            },
            status_code=503,
        )

    # start background task to drain remaining generator and persist trace
    async def _drain_and_save(g, trace_obj):
        try:
            t_start = None
            async for _ in g:
                if t_start is None:
                    t_start = time.time()
            # record synthesis time as elapsed since first consume if available
            if t_start:
                trace_obj['timings']['synthesis'] = time.time() - t_start
            else:
                trace_obj['timings']['synthesis'] = 0.0
            from app.security.identity import get_effective_identity
            eff = get_effective_identity(user or {})
            await save_trace(eff.get("user_id"), trace_obj, tenant_id=(user or {}).get("tenant_id"), workspace_id=(user or {}).get("workspace_id"))
            await save_memory(eff.get("user_id"), "interaction", {
                "query": query,
                "plan": plan,
                "trace": trace_obj,
                "mode": "query_endpoint",
            }, tenant_id=(user or {}).get("tenant_id"), workspace_id=(user or {}).get("workspace_id"))
        except Exception:
            pass

    asyncio.create_task(_drain_and_save(gen, trace))
    return {"plan": plan, "first_chunk": first_chunk}


@app.get("/api/stream-query")
async def stream_query(request: Request, q: str, doc_id: Optional[int] = None, user: dict = Depends(get_current_user)):
    query = sanitize_query(q)
    user_id = int(user.get("id"))
    if not query:
        return JSONResponse({"error": "missing query"}, status_code=400)
    if detect_prompt_injection(query) or is_sensitive_request(query):
        polite_response = "I'm not able to help with that. Please ask a question related to the available documents."
        async def polite_stream():
            yield f"data: {json.dumps({'role': 'synthesizer', 'text': polite_response, 'provenance': []})}\n\n"
        return StreamingResponse(polite_stream(), media_type="text/event-stream")
    if is_suspicious_prompt(query):
        # Return a polite chat response as a streaming response instead of an error
        polite_response = "I'm not able to help with that. Please ask a question related to the available documents."
        async def polite_stream():
            yield f"data: {json.dumps({'role': 'synthesizer', 'text': polite_response, 'provenance': []})}\n\n"
        return StreamingResponse(polite_stream(), media_type="text/event-stream")

    ip = request.client.host if request and request.client else "anon"
    user_key = build_rate_key("user", str(user.get("id")), 3600)
    ip_key = build_rate_key("ip", ip, 3600)
    if not await check_rate_limit(user_key, RATE_LIMIT_PER_HOUR, 3600):
        return JSONResponse({"error": "rate_limit_exceeded"}, status_code=429)
    if not await check_rate_limit(ip_key, RATE_LIMIT_PER_HOUR, 3600):
        return JSONResponse({"error": "rate_limit_exceeded"}, status_code=429)

    try:
        plan, generator, trace = await orchestrate(query, user, doc_id)
    except Exception as exc:
        error_detail = str(exc)
        inc_error("orchestrate", exc.__class__.__name__)
        log_event("stream_query.error", user_id=int(user.get("id")), error=exc.__class__.__name__, message=error_detail)

        async def error_stream():
            yield f"data: {json.dumps({'error': 'orchestration_failed', 'detail': error_detail})}\n\n"

        return StreamingResponse(error_stream(), media_type="text/event-stream", status_code=503)

    async def event_generator():
        synth_start = None
        final_answer_parts = []
        reflection_state = None
        review_state = None
        validation_state = trace.get("validation") if isinstance(trace, dict) else None
        try:
            async for token in generator:
                if synth_start is None:
                    synth_start = time.time()
                if isinstance(token, dict):
                    if token.get("role") in {"synthesizer", "revision"} and token.get("text"):
                        final_answer_parts.append(str(token.get("text")))
                    if token.get("role") == "reflection":
                        reflection_state = token.get("reflection") or token
                        trace["reflection"] = reflection_state
                    if token.get("role") == "review":
                        review_state = token
                        trace["review"] = token
                yield f"data: {json.dumps(token)}\n\n"
                if await request.is_disconnected():
                    break
            # finish: record synthesis timing
            trace['timings']['synthesis'] = time.time() - synth_start if synth_start else 0.0
            if reflection_state is not None:
                trace["reflection"] = reflection_state
            if validation_state and validation_state.get("review_required") and not (trace.get("review") or {}).get("review_id"):
                from app.security.identity import get_effective_identity
                eff = get_effective_identity(user or {})
                review_record = await create_review_request(
                    trace_id=trace.get("trace_id"),
                    query=query,
                    answer_draft="".join(final_answer_parts).strip() or None,
                    confidence_score=float(validation_state.get("confidence", 0.0)),
                    threshold=float(validation_state.get("confidence_threshold", 0.72)),
                    session_id=None,
                    actor=eff,
                )
                trace["review"] = {
                    "required": True,
                    "status": review_record.get("status") if review_record else "pending",
                    "review_id": review_record.get("id") if review_record else None,
                    "threshold": validation_state.get("confidence_threshold"),
                }
            from app.security.identity import get_effective_identity
            eff = get_effective_identity(user or {})
            await save_trace(eff.get("user_id"), trace, tenant_id=(user or {}).get("tenant_id"), workspace_id=(user or {}).get("workspace_id"))
            await save_memory(eff.get("user_id"), "interaction", {
                "query": query,
                "plan": plan,
                "trace": trace,
                "mode": "stream_query",
            }, tenant_id=(user or {}).get("tenant_id"), workspace_id=(user or {}).get("workspace_id"))
        except Exception as e:
            try:
                trace['error'] = str(e)
                from app.security.identity import get_effective_identity
                eff = get_effective_identity(user or {})
                await save_trace(eff.get("user_id"), trace, tenant_id=(user or {}).get("tenant_id"), workspace_id=(user or {}).get("workspace_id"))
            except Exception:
                pass
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
