"""
src/friday/tools/schemas.py

WHAT THIS IS FOR:
Standardizes and formats typed JSON tool definitions for Ollama and LLM function calling (§17 of Blueprint).
"""

from __future__ import annotations

from typing import Any


def format_tool_schema(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """Format a single tool definition into standard OpenAI/Ollama function-calling schema."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def generate_all_schemas(registry: Any) -> list[dict[str, Any]]:
    """Extract and format schemas for all registered tools in the registry."""
    if hasattr(registry, "all_schemas"):
        return registry.all_schemas()

    schemas: list[dict[str, Any]] = []
    tools = getattr(registry, "_tools", {})
    for name, tool in tools.items():
        desc = getattr(tool, "description", "")
        params = getattr(tool, "parameters", {"type": "object", "properties": {}})
        schemas.append(format_tool_schema(name, desc, params))

    return schemas

