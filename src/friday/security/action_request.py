"""
The central typed object for ALL tool invocations (Formal Action Contracts).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from friday.security.policy import RiskTier

if TYPE_CHECKING:
    from friday.tools.registry import Tool

@dataclass
class ActionRequest:
    task_id: str
    step_id: str
    capability: str
    tool: str
    arguments: dict[str, Any]
    target: str | None
    risk_tier: RiskTier
    required_scopes: list[str]
    requester: str
    context_source: str
    timestamp: datetime

    def to_confirmation_hash(self) -> str:
        """Produces a SHA-256 hash of tool + sorted arguments + target + risk_tier."""
        payload = {
            "tool": self.tool,
            "args": self.arguments,
            "target": self.target,
            "risk_tier": self.risk_tier.value if hasattr(self.risk_tier, 'value') else str(self.risk_tier)
        }
        json_payload = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(json_payload.encode('utf-8')).hexdigest()

    @classmethod
    def from_tool(cls, tool: 'Tool', arguments: dict[str, Any], task_id: str = "", step_id: str = "", requester: str = "planner", context_source: str = "agent", target: str | None = None) -> 'ActionRequest':
        return cls(
            task_id=task_id,
            step_id=step_id,
            capability=getattr(tool, 'capability', 'unknown'),
            tool=tool.name,
            arguments=arguments,
            target=target,
            risk_tier=getattr(tool, 'risk_tier', RiskTier.RED),
            required_scopes=getattr(tool, 'required_scopes', []),
            requester=requester,
            context_source=context_source,
            timestamp=datetime.now(timezone.utc)
        )
