"""
core/tools/legacy_bridge.py

WHAT THIS IS FOR:
Ports every v1 tool (tools/*.py, registered via @register_tool into
TOOL_REGISTRY) into the new typed ToolRegistry, WITHOUT rewriting any of
them. Each v1 function keeps its own logic and imports; this only wraps
it in the new Tool contract (name, tier, input_schema, handler) so the
orchestrator's policy engine can gate it like any other tool.

WHY THIS FILE EXISTS:
`llm.py` is the one place that currently imports every tools/*.py module
(as a side effect - the @register_tool decorator populates TOOL_REGISTRY
on import). Rather than duplicate that import list here and have it
silently drift out of sync, this file imports `llm` itself to trigger
the same registration, then reads TOOL_REGISTRY from there. Add a new
v1 tool module -> add its import to llm.py as you already do -> it shows
up here automatically, no second list to maintain.

RISK MAPPING:
v1 RiskClass -> new RiskTier is 1:1 by name. Nothing is being
reclassified - a tool that was ORANGE in v1 stays ORANGE here. An
unmapped/unknown risk class fails closed to RED (Principle G), never
silently downgraded to something auto-approved.
"""

from __future__ import annotations

import inspect
from typing import Any, get_type_hints

import llm  # noqa: F401 - side-effect import: registers every tools/*.py module
from security.policy import RiskClass
from tools.registry import TOOL_REGISTRY

from core.security.policy import RiskTier
from core.tools.registry import Tool, ToolRegistry

_TIER_BY_RISK_CLASS = {
    RiskClass.GREEN: RiskTier.GREEN,
    RiskClass.YELLOW: RiskTier.YELLOW,
    RiskClass.ORANGE: RiskTier.ORANGE,
    RiskClass.RED: RiskTier.RED,
}

_PY_TYPE_TO_JSON = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    dict: "object",
    list: "array",
}


def _schema_for(func) -> dict:
    """Builds a JSON-schema-ish input spec from the function's real type hints,
    so the model sees accurate argument types without you writing them twice."""
    sig = inspect.signature(func)
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue  # *args / **kwargs (e.g. gmail.py's **kwargs) aren't model-facing params
        json_type = _PY_TYPE_TO_JSON.get(hints.get(name), "string")
        properties[name] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {"type": "object", "properties": properties, "required": required}


def _description_for(func) -> str:
    doc = inspect.getdoc(func)
    if doc:
        return doc.strip().splitlines()[0]
    # e.g. tools/gmail.py:check_inbox - the docstring sits after a statement,
    # so Python never treats it as __doc__. Falls back rather than erroring.
    return f"Legacy tool: {func.__name__} (no usable docstring found in v1 source)"


def register_legacy_tools(registry: ToolRegistry) -> list[str]:
    """Wraps every v1 tool into the new registry. Returns names skipped due
    to a collision with something already registered (e.g. base_tools.py)."""
    skipped: list[str] = []
    for name, legacy in TOOL_REGISTRY.items():
        tier = _TIER_BY_RISK_CLASS.get(legacy.risk, RiskTier.RED)

        tool = Tool(
            name=name,
            description=_description_for(legacy.func),
            tier=tier,
            input_schema=_schema_for(legacy.func),
            handler=legacy.func,
            preview=legacy.preview,
            critical=legacy.critical,
        )
        try:
            registry.register(tool)
        except ValueError:
            skipped.append(name)
    return skipped
