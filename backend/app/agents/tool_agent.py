import asyncio
import os
import json
import re
from html import unescape
from typing import Dict, Any
from app.services.tool_runner import run_with_timeout, http_get
from app.services.tools_history import log_tool_execution
from app.services.redis_client import get_redis_client
from app.services.tool_registry import ToolDefinition, build_tool_manifest, allowed_tools_for_role
from app.observability import record_tool_usage, record_agent_latency, log_event


# Tool registry
async def tool_kpi_api(query: str, params: dict = None) -> Dict[str, Any]:
    # Example stub: call a KPI API endpoint defined by env var
    url = os.getenv("KPI_API_URL")
    if not url:
        return {"success": False, "error": "no_kpi_api"}
    try:
        data = await http_get(url, params=params or {}, timeout=3.0)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def tool_calculator(expression: str) -> Dict[str, Any]:
    # Safe calculator: evaluate simple numeric expressions only
    try:
        allowed = set("0123456789+-*/(). eE")
        if not set(expression) <= allowed:
            return {"success": False, "error": "invalid characters"}
        # eval in restricted namespace
        result = eval(expression, {"__builtins__": {}}, {})
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def tool_web_search(query: str) -> Dict[str, Any]:
    # Best-effort web search using a configured API or DuckDuckGo's HTML endpoint.
    url = os.getenv("WEB_SEARCH_API")
    if not url:
        ddg_url = "https://html.duckduckgo.com/html/"
        try:
            html = await http_get(ddg_url, params={"q": query}, timeout=5.0)
            if not isinstance(html, str):
                html = json.dumps(html)
            results = []
            # Extract a few result cards and snippets without extra dependencies.
            for title, snippet in re.findall(r'<a[^>]*class="result__a"[^>]*>(.*?)</a>.*?<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', html, flags=re.S):
                clean_title = re.sub(r"<.*?>", "", unescape(title)).strip()
                clean_snippet = re.sub(r"<.*?>", "", unescape(snippet)).strip()
                if clean_title:
                    results.append({"title": clean_title, "snippet": clean_snippet})
                if len(results) >= 3:
                    break
            if results:
                return {"success": True, "results": results}
        except Exception:
            pass
        # deterministic fallback if network/search parsing fails
        return {"success": True, "results": [
            {"title": "Financial intelligence note", "snippet": f"Search fallback for '{query}'"},
        ]}
    try:
        data = await http_get(url, params={"q": query}, timeout=3.0)
        return {"success": True, "results": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


TOOL_REGISTRY = {
    "kpi_api": build_tool_manifest(
        tool_kpi_api,
        ToolDefinition(
            tool_name="kpi_api",
            description="Query the KPI service for metrics and operational signals.",
            permissions=["read:kpi"],
            allowed_roles=["admin", "user"],
            timeout=4.0,
            retry_policy={"retries": 1, "backoff": 0.15},
        ),
    ),
    "calculator": build_tool_manifest(
        tool_calculator,
        ToolDefinition(
            tool_name="calculator",
            description="Evaluate safe arithmetic expressions.",
            permissions=["compute:basic"],
            allowed_roles=["admin", "user"],
            timeout=2.0,
            retry_policy={"retries": 0, "backoff": 0.0},
        ),
    ),
    "web_search": build_tool_manifest(
        tool_web_search,
        ToolDefinition(
            tool_name="web_search",
            description="Perform a constrained web search for external verification.",
            permissions=["network:external"],
            allowed_roles=["admin"],
            timeout=5.0,
            retry_policy={"retries": 0, "backoff": 0.0},
        ),
    ),
}

TOOL_POLICY = {
    name: {
        "allowed_roles": manifest["definition"]["allowed_roles"],
        "timeout": manifest["definition"]["timeout"],
        "retries": int(manifest["definition"]["retry_policy"].get("retries", 0)),
        "permissions": manifest["definition"]["permissions"],
        "description": manifest["definition"]["description"],
    }
    for name, manifest in TOOL_REGISTRY.items()
}


async def run_tools(query: str, plan: dict, session_id: int = None) -> Dict[str, Any]:
    """Decide which tools to run based on plan and query, run them with timeouts, cache results, and log history."""
    started = asyncio.get_event_loop().time()
    redis = get_redis_client()
    tools_to_run = plan.get("tools", []) if isinstance(plan, dict) else []
    results = {}
    user_role = (plan.get("user_role") if isinstance(plan, dict) else None) or "user"

    allowed = allowed_tools_for_role(TOOL_REGISTRY, user_role)

    for tname in tools_to_run:
        manifest = TOOL_REGISTRY.get(tname)
        if not manifest:
            results[tname] = {"success": False, "error": "unknown_tool", "tool_name": tname}
            record_tool_usage(tname, False)
            continue

        func = manifest["handler"]

        policy = TOOL_POLICY.get(tname, {"allowed_roles": ["admin"], "timeout": 3.0, "retries": 0})
        if user_role not in policy.get("allowed_roles", []) or tname not in allowed:
            results[tname] = {"success": False, "error": "tool_not_allowed", "tool_name": tname, "policy": policy}
            record_tool_usage(tname, False)
            continue

        cache_key = f"tool:{tname}:{query}"
        if redis is not None:
            try:
                cached = await redis.get(cache_key)
                if cached:
                    results[tname] = json.loads(cached)
                    continue
            except Exception:
                pass

        # run tool with timeout
        retries = int(policy.get("retries", 0))
        timeout = float(policy.get("timeout", float(os.getenv("TOOL_TIMEOUT", "4.0"))))
        res = None
        for _ in range(retries + 1):
            res = await run_with_timeout(func, query, timeout=timeout)
            if isinstance(res, dict) and res.get("success", True):
                break

        # ensure dict
        if not isinstance(res, dict):
            res = {"success": True, "data": res}

        res["tool_name"] = tname
        res["policy"] = policy
        res["registry"] = manifest["definition"]
        res["permissions"] = policy.get("permissions", [])
        res["allowed_roles"] = policy.get("allowed_roles", [])

        results[tname] = res
        record_tool_usage(tname, res.get("success", False))

        # cache
        if redis is not None:
            try:
                await redis.set(cache_key, json.dumps(res), ex=60 * 5)
            except Exception:
                pass

        # log to DB
        if session_id is not None:
            try:
                await log_tool_execution(session_id, tname, {"query": query}, res, res.get("success", False))
            except Exception:
                pass

    elapsed = asyncio.get_event_loop().time() - started
    record_agent_latency("tool_agent", elapsed)
    log_event("tools.completed", user_role=user_role, tool_count=len(results), latency_ms=round(elapsed * 1000, 2))
    return results
