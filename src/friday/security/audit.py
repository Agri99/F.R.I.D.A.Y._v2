"""
src/friday/security/audit.py

WHAT THIS IS FOR:
Structured audit logging system (blueprint §25).
Logs security and tool events into daily JSONL files in data/audit/
with automatic redaction of credentials and sensitive arguments.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, TYPE_CHECKING

from friday.security.policy import RiskTier

if TYPE_CHECKING:
    from friday.security.action_request import ActionRequest


@dataclass
class AuditEvent:
    timestamp: str
    task_id: str
    event: str
    tool: str
    risk: str
    arguments: dict[str, Any]
    authorization: Any
    result: str
    verification: Any
    action_request: ActionRequest | None = None


class AuditLogger:
    SENSITIVE_KEYS = {"password", "token", "secret", "key", "passphrase", "auth"}

    def __init__(self, log_dir: str | Path = "data/audit"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_file(self) -> Path:
        date_str = time.strftime("%Y-%m-%d")
        return self.log_dir / f"audit_{date_str}.jsonl"

    def _redact_arguments(self, arguments: Any) -> Any:
        if not isinstance(arguments, dict):
            return arguments
        redacted = {}
        for k, v in arguments.items():
            if any(sensitive in str(k).lower() for sensitive in self.SENSITIVE_KEYS):
                redacted[k] = "***REDACTED***"
            elif isinstance(v, dict):
                redacted[k] = self._redact_arguments(v)
            else:
                redacted[k] = v
        return redacted

    def _log(self, event: AuditEvent) -> None:
        event.arguments = self._redact_arguments(event.arguments)
        log_file = self._get_log_file()
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), default=str) + "\n")

    def log_tool_execution(
        self,
        task_id: str,
        tool: str | None = None,
        tool_name: str | None = None,
        risk: RiskTier | str | None = None,
        risk_tier: RiskTier | str | None = None,
        arguments: dict[str, Any] | None = None,
        authorization: Any = None,
        result: Any = None,
        verification: Any = None,
    ) -> None:
        name = tool_name or tool or "unknown"
        r_tier = risk_tier or risk or "GREEN"
        r_str = r_tier.value if hasattr(r_tier, "value") else str(r_tier)

        event = AuditEvent(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            task_id=task_id,
            event="TOOL_EXECUTION",
            tool=name,
            risk=r_str,
            arguments=arguments or {},
            authorization=authorization or "ALLOWED",
            result=str(result),
            verification=verification or "PASSED",
        )
        self._log(event)

    def log_authorization(
        self,
        task_id: str,
        tool: str,
        risk: RiskTier | str,
        arguments: dict[str, Any],
        auth_decision: dict[str, Any] | str,
    ) -> None:
        r_str = risk.value if hasattr(risk, "value") else str(risk)
        event = AuditEvent(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            task_id=task_id,
            event="AUTHORIZATION",
            tool=tool,
            risk=r_str,
            arguments=arguments,
            authorization=auth_decision,
            result="",
            verification={},
        )
        self._log(event)

    def log_verification(self, task_id: str, tool: str, verification_details: Any) -> None:
        event = AuditEvent(
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            task_id=task_id,
            event="VERIFICATION",
            tool=tool,
            risk="",
            arguments={},
            authorization={},
            result="",
            verification=verification_details,
        )
        self._log(event)
