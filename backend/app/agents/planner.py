import asyncio
import json
import hashlib
from .llm_client import call_planning_model
from app.services.redis_client import get_redis_client
from app.services.retrieval_filters import infer_retrieval_filters, is_general_knowledge_query


DEFAULT_PLAN = {
    "steps": [
        {"id": "retrieve", "agent": "retrieval"},
        {"id": "tools", "agent": "tool_agent"},
        {"id": "memory", "agent": "memory"},
        {"id": "validate", "agent": "validator"},
        {"id": "reflect", "agent": "reflection"},
    ],
    "retrieval_strategy": "hybrid",
    "max_docs": 8,
}
async def plan(query: str, user_id: str):
    """Planner that attempts to generate a fast JSON plan using a small LLM.
    Uses Redis to cache planning results for repeated queries to keep latency low.
    If the LLM call times out or fails, returns a deterministic fallback plan.
    """
    redis = get_redis_client()
    key = "plan:" + hashlib.sha256(query.encode("utf-8")).hexdigest()

    # Try cache first
    if redis is not None:
        try:
            cached = await redis.get(key)
            if cached:
                return json.loads(cached)
        except Exception:
            await asyncio.sleep(0)

    # Compose a compact planning prompt that asks for JSON only
    prompt = (
        "Given the user query, decompose the task into agents (retrieval, tools, memory, validator, synthesizer),"
        " decide if validation is required, choose a retrieval strategy, infer metadata filters when relevant, and return a JSON object with keys:"
        " query, user_id, steps (array of {id,agent}), requires_validation (bool), retrieval_strategy, max_docs, retrieval_filters."
        f"\nUser query: {query}"
    )

    resp = await call_planning_model(prompt)
    plan = None
    if resp:
        try:
            # Expecting JSON in the response
            parsed = json.loads(resp)
            plan = parsed
        except Exception:
            plan = None

    # Fallback deterministic plan
    if plan is None:
        requires_validation = any(k in query.lower() for k in ["why", "cause", "explain", "analyze"])
        retrieval_filters = infer_retrieval_filters(query, {})
        allow_web_search = is_general_knowledge_query(query)
        plan = {
            "query": query,
            "user_id": user_id,
            "steps": DEFAULT_PLAN["steps"],
            "requires_validation": requires_validation,
            "retrieval_strategy": DEFAULT_PLAN["retrieval_strategy"],
            "max_docs": DEFAULT_PLAN["max_docs"],
            "retrieval_filters": retrieval_filters,
            "candidates_k": 20,
            "allow_web_search": allow_web_search,
        }
    else:
        plan.setdefault("retrieval_filters", infer_retrieval_filters(query, plan))
        plan.setdefault("candidates_k", 20)
        plan.setdefault("allow_web_search", is_general_knowledge_query(query))

    # Cache the plan for short period
    if redis is not None:
        try:
            await redis.set(key, json.dumps(plan), ex=60 * 5)
        except Exception:
            await asyncio.sleep(0)

    await asyncio.sleep(0)
    return plan
