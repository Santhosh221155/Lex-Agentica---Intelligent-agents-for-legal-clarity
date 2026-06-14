from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Awaitable, Callable, Dict, List, Optional


ToolHandler = Callable[..., Awaitable[Dict[str, Any]]]


@dataclass(frozen=True)
class ToolDefinition:
    tool_name: str
    description: str
    permissions: List[str]
    allowed_roles: List[str]
    timeout: float
    retry_policy: Dict[str, Any]


def build_tool_manifest(handler: ToolHandler, definition: ToolDefinition) -> Dict[str, Any]:
    return {"handler": handler, "definition": asdict(definition)}


def describe_tool(tool_name: str, registry: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    entry = registry.get(tool_name)
    if not entry:
        return None
    return dict(entry.get("definition") or {})


def allowed_tools_for_role(registry: Dict[str, Dict[str, Any]], role: str) -> List[str]:
    permitted = []
    for tool_name, entry in registry.items():
        definition = entry.get("definition") or {}
        if role in (definition.get("allowed_roles") or []):
            permitted.append(tool_name)
    return permitted