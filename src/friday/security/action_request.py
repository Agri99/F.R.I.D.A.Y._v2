"""
src/friday/security/action_request.py

WHAT THIS IS FOR:
The central typed object for ALL tool invocations (Formal Action Contracts, blueprint §24).
Ensures policy, capabilities, confirmation, and execution bind to an immutable, verifiable request.
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
    def from_tool(
        cls,
        tool: 'Tool',
        arguments: dict[str, Any] | None = None,
        task_id: str = "",
        step_id: str = "",
        requester: str = "planner",
        context_source: str = "agent",
        target: str | None = None,
    ) -> 'ActionRequest':
        args = arguments or {}
        raw_tier = getattr(tool, 'tier', getattr(tool, 'risk_tier', RiskTier.RED))
        if isinstance(raw_tier, str):
            try:
                tier = RiskTier[raw_tier.upper()]
            except KeyError:
                tier = RiskTier.RED
        elif isinstance(raw_tier, RiskTier):
            tier = raw_tier
        else:
            tier = RiskTier.RED

        cap = getattr(tool, 'capability_scope', getattr(tool, 'capability', 'unknown'))
        scopes = [cap] if isinstance(cap, str) and cap != 'unknown' else []

        return cls(
            task_id=task_id,
            step_id=step_id,
            capability=str(cap),
            tool=tool.name,
            arguments=args,
            target=target,
            risk_tier=tier,
            required_scopes=scopes,
            requester=requester,
            context_source=context_source,
            timestamp=datetime.now(timezone.utc)
        )
