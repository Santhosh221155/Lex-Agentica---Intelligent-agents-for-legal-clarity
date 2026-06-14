"""Execute a planner-produced plan using available agents.

This module provides a thin runtime that either delegates to LangGraph (if
installed) or runs a best-effort fallback by invoking the planner, retrieval,
tools, memory, validator, and synthesizer agents in the expected order.
"""
import asyncio
import time
from typing import Any, Dict, Tuple

from app.observability import log_event

try:
    from langgraph import GraphRuntime  # type: ignore
except Exception:
    GraphRuntime = None

from app.agents import retrieval as retrieval_agent
from app.agents import tool_agent as tool_agent
from app.agents import memory as memory_agent
from app.agents import validator as validator_agent
from app.agents.planner import is_general_knowledge_query


async def run_plan_fallback(query: str, plan: Dict[str, Any], user_context: Any = "user:local") -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Any]:
    """Run retrieval, tools, memory (in parallel), then optional validation.

    Returns: (retrieval_res, tools_res, memory_res, validation_res)
    """
    RETRIEVAL_TIMEOUT = float(__import__('os').getenv('RETRIEVAL_TASK_TIMEOUT', '12.0'))
    TOOLS_TIMEOUT = float(__import__('os').getenv('TOOLS_TASK_TIMEOUT', '10.0'))
    MEMORY_TIMEOUT = float(__import__('os').getenv('MEMORY_TASK_TIMEOUT', '2.0'))

    # derive tenant/workspace if a user context dict was passed
    tenant_id = None
    workspace_id = None
    if isinstance(user_context, dict):
        tenant_id = user_context.get("tenant_id")
        workspace_id = user_context.get("workspace_id")
        user_id = user_context.get("id") or user_context.get("user_id") or "user:local"
    else:
        user_id = user_context or "user:local"
    log_event("retrieval.before_create_task", task="memory")
    memory_task = asyncio.create_task(memory_agent.fetch_memory(user_id, query, plan, tenant_id=tenant_id, workspace_id=workspace_id))
    log_event("retrieval.after_create_task", task="memory")

    log_event("retrieval.before_create_task", task="retrieval")
    retrieval_task = asyncio.create_task(retrieval_agent.retrieve(query, plan))
    log_event("retrieval.after_create_task", task="retrieval")

    tools_plan = dict(plan or {})
    requested_tools = list(tools_plan.get("tools", []) or [])
    allow_web_search = bool(tools_plan.get("allow_web_search") or is_general_knowledge_query(query))

    try:
        log_event("retrieval.wait_for_enter", task="retrieval", timeout_sec=RETRIEVAL_TIMEOUT, awaited="retrieval_task")
        retrieval_res = await asyncio.wait_for(retrieval_task, timeout=RETRIEVAL_TIMEOUT)
        log_event("retrieval.wait_for_exit", task="retrieval", timeout_sec=RETRIEVAL_TIMEOUT, awaited="retrieval_task")
    except asyncio.TimeoutError as exc:
        log_event(
            "orchestrate.retrieval_timeout",
            timeout_sec=RETRIEVAL_TIMEOUT,
            retrieval_strategy=plan.get("retrieval_strategy"),
            awaited="retrieval_task",
        )
        log_event(
            "retrieval.timeout",
            timeout_sec=RETRIEVAL_TIMEOUT,
            retrieval_strategy=plan.get("retrieval_strategy"),
            reason="run_plan_fallback_wait_for_timeout",
        )
        log_event(
            "retrieval.wait_for_exception",
            task="retrieval",
            timeout_sec=RETRIEVAL_TIMEOUT,
            error_type=type(exc).__name__,
            error_repr=repr(exc),
        )
        # Degrade gracefully: re-run retrieval in dense-only mode so sparse stalls
        # cannot erase already-retrievable dense results.
        dense_only_plan = dict(plan or {})
        dense_only_plan["disable_sparse"] = True
        try:
            log_event("retrieval.wait_for_enter", task="retrieval_recovery", timeout_sec=max(1.0, RETRIEVAL_TIMEOUT), awaited="dense_only_retrieve")
            retrieval_res = await asyncio.wait_for(
                retrieval_agent.retrieve(query, dense_only_plan),
                timeout=max(1.0, RETRIEVAL_TIMEOUT),
            )
            log_event("retrieval.wait_for_exit", task="retrieval_recovery", timeout_sec=max(1.0, RETRIEVAL_TIMEOUT), awaited="dense_only_retrieve")
            log_event(
                "retrieval.timeout_recovered_dense_only",
                timeout_sec=RETRIEVAL_TIMEOUT,
                recovered_docs=len(retrieval_res.get("chunks") or []),
            )
        except asyncio.TimeoutError as exc:
            log_event(
                "retrieval.wait_for_exception",
                task="retrieval_recovery",
                timeout_sec=max(1.0, RETRIEVAL_TIMEOUT),
                error_type=type(exc).__name__,
                error_repr=repr(exc),
            )
            log_event(
                "retrieval.timeout_recovery_failed",
                timeout_sec=RETRIEVAL_TIMEOUT,
                error=str(exc),
            )
            retrieval_res = {
                "strategy": plan.get("retrieval_strategy"),
                "chunks": [],
                "source": "chroma",
                "warning": "No relevant content found in documents",
            }
        except Exception as exc:
            log_event(
                "retrieval.timeout_recovery_failed",
                timeout_sec=RETRIEVAL_TIMEOUT,
                error=str(exc),
            )
            retrieval_res = {
                "strategy": plan.get("retrieval_strategy"),
                "chunks": [],
                "source": "chroma",
                "warning": "No relevant content found in documents",
            }

    if not retrieval_res.get("chunks") and not allow_web_search:
        requested_tools = [tool_name for tool_name in requested_tools if tool_name != "web_search"]
    elif not requested_tools and allow_web_search:
        requested_tools = ["web_search"]
    tools_plan["tools"] = requested_tools

    log_event("retrieval.before_create_task", task="tools")
    tools_task = asyncio.create_task(tool_agent.run_tools(query, tools_plan))
    log_event("retrieval.after_create_task", task="tools")

    # retrieval
    if not retrieval_res.get("chunks") and not allow_web_search:
        tools_res = {}
    else:
        try:
            log_event("retrieval.wait_for_enter", task="tools", timeout_sec=TOOLS_TIMEOUT, awaited="tools_task")
            tools_res = await asyncio.wait_for(tools_task, timeout=TOOLS_TIMEOUT)
            log_event("retrieval.wait_for_exit", task="tools", timeout_sec=TOOLS_TIMEOUT, awaited="tools_task")
        except asyncio.TimeoutError:
            tools_res = {"status": "timeout", "reason": "tools timed out"}
        except Exception:
            tools_res = {"status": "error", "reason": "tools error"}

    if not retrieval_res.get("chunks") and not retrieval_res.get("warning"):
        retrieval_res = {
            "strategy": plan.get("retrieval_strategy"),
            "chunks": [],
            "source": "chroma",
            "warning": "No relevant content found in documents",
        }

    # memory
    try:
        log_event("retrieval.wait_for_enter", task="memory", timeout_sec=MEMORY_TIMEOUT, awaited="memory_task")
        memory_res = await asyncio.wait_for(memory_task, timeout=MEMORY_TIMEOUT)
        log_event("retrieval.wait_for_exit", task="memory", timeout_sec=MEMORY_TIMEOUT, awaited="memory_task")
    except asyncio.TimeoutError:
        memory_res = {"short_term": [], "episodic": []}
    except Exception:
        memory_res = {"short_term": [], "episodic": []}

    validation_res = None
    if plan.get("requires_validation"):
        try:
            validation_res = await validator_agent.validate(query, plan, retrieval_res, tools_res, memory_res)
        except Exception:
            validation_res = {"status": "error", "reason": "validation_failed"}

    return retrieval_res, tools_res, memory_res, validation_res


async def run_plan(query: str, plan: Dict[str, Any], user_context: Any = "user:local") -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Any]:
    """Dispatch to LangGraph runtime if available, else fallback."""
    if GraphRuntime is not None:
        try:
            runtime = GraphRuntime()
            # Assuming a Graph named 'agentic_rag' is registered; best-effort call
            res = await runtime.run("agentic_rag", inputs={"query": query, "plan": plan, "user_context": user_context})
            # Expect the runtime to return a mapping with keys: retrieval, tools, memory, validation
            return res.get("retrieval", {}), res.get("tools", {}), res.get("memory", {}), res.get("validation")
        except Exception:
            return await run_plan_fallback(query, plan, user_context)
    else:
        return await run_plan_fallback(query, plan, user_context)
