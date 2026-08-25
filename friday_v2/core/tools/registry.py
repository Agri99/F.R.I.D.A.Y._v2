"""
core/tools/registry.py

WHAT THIS IS FOR:
Implements Principle B — "capability over raw access". Every action
FRIDAY can take is a `Tool` with a name, a typed input schema, a risk
tier, and a `run()` method. There is no `execute_arbitrary_command`.
If a tool doesn't exist for something, FRIDAY can't do that thing —
it has to be added deliberately, with a tier assigned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from core.security.policy import RiskTier


@dataclass
class Tool:
    name: str
    description: str
    tier: RiskTier
    input_schema: dict          # JSON-schema-ish dict describing args
    handler: Callable[..., Any]  # the actual Python function that runs
    preview: Callable[..., dict] | None = None   # optional: shows what would happen before confirming
    critical: bool = False        # if True, needs passphrase on top of voice confirmation (v1 parity)

    def run(self, **kwargs) -> Any:
        return self.handler(**kwargs)

    def to_model_schema(self) -> dict:
        """Shape the model router / provider expects when advertising tools."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tier_of(self, name: str) -> RiskTier | None:
        tool = self._tools.get(name)
        return tool.tier if tool else None

    def all_schemas(self) -> list[dict]:
        return [t.to_model_schema() for t in self._tools.values()]

    def list_names(self) -> list[str]:
        return list(self._tools.keys())
