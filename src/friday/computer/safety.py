"""
src/friday/computer/safety.py
WHAT THIS IS FOR: Pre-action safety checks before performing computer actions.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class SafetyResult:
    safe: bool
    warnings: list[str]
    blocked_reason: str | None

class SafetyCheck:
    def check_before_action(self, action: str, target: str, args: dict) -> SafetyResult:
        """Evaluate safety before performing a computer action."""
        # Check for destructive actions
        # Check for system-critical targets
        # Check for data loss potential
        
        if action.lower() in ("delete", "format", "rm"):
            return SafetyResult(safe=False, warnings=[], blocked_reason="Destructive action blocked by safety checks")
        return SafetyResult(safe=True, warnings=[], blocked_reason=None)
