from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Dict, List

@dataclass
class VerificationResult:
    """Result of independently re-checking whether an action's expected state actually holds."""
    passed: bool
    message: str = ""

@dataclass
class Tool:
    """A registered capability that the agent can invoke."""
    name: str
    description: str
    tier: str  # RiskTier string
    capability_scope: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]
    preview: Optional[Callable[..., dict]] = None
    verify: Optional[Callable[[Dict[str, Any], Any], VerificationResult]] = None
    critical: bool = False
    preconditions: List[str] = field(default_factory=list)
    online_required: bool = False
    side_effects: List[str] = field(default_factory=list)

    def run(self, **kwargs) -> Any:
        allowed = set(self.input_schema.get("properties", {}).keys())
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        return self.handler(**filtered)

    def to_model_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

class ToolRegistry:
    """Registry holding all tools the agent can use."""
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        tool: Tool | None = None,
        name: str | None = None,
        description: str = "",
        tier: str = "GREEN",
        capability_scope: str = "system",
        parameters: dict[str, Any] | None = None,
        handler: Callable[..., Any] | None = None,
    ) -> None:
        if tool is None:
            if not name or not handler:
                raise ValueError("register requires either a Tool instance or 'name' and 'handler'")
            tool = Tool(
                name=name,
                description=description,
                tier=tier,
                capability_scope=capability_scope,
                input_schema=parameters or {"type": "object", "properties": {}},
                handler=handler,
            )

        if tool.name in self._tools:
            return  # Idempotent registration

        self._tools[tool.name] = tool


    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tier_of(self, name: str) -> str | None:
        tool = self._tools.get(name)
        return tool.tier if tool else None

    def all_schemas(self) -> list[dict]:
        return [t.to_model_schema() for t in self._tools.values()]

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def list_by_scope(self, scope: str) -> list[Tool]:
        return [t for t in self._tools.values() if t.capability_scope == scope]

    def list_online_tools(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.online_required]
