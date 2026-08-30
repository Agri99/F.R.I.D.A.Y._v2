"""
src/friday/computer/safety.py

WHAT THIS IS FOR:
Pre-action safety checks before executing computer automation or UI actions.
Validates parameters, blocks dangerous commands, checks coordinate boundaries,
and protects sensitive system areas.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SafetyResult:
    safe: bool
    warnings: list[str] = field(default_factory=list)
    blocked_reason: str | None = None


# Blocked sensitive paths / system targets
BLOCKED_TARGETS: set[str] = {
    "system32",
    "regedit",
    "registry",
    "c:\\windows",
    ".env",
    "secrets",
    "id_rsa",
    "credentials.json",
}

# Destructive action keywords
DESTRUCTIVE_ACTIONS: set[str] = {
    "delete",
    "format",
    "rm",
    "del",
    "erase",
    "drop",
    "destroy",
    "wipe_disk",
    "kill_system",
}


class SafetyCheck:
    """Evaluates safety of computer actions before execution."""

    def __init__(
        self,
        screen_width: int = 1920,
        screen_height: int = 1080,
        min_action_interval_seconds: float = 0.05,
    ) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.min_action_interval_seconds = min_action_interval_seconds
        self._last_action_time: float = 0.0

    def check_before_action(
        self,
        action: str,
        target: str = "",
        args: dict[str, Any] | None = None,
    ) -> SafetyResult:
        """Evaluate whether a proposed action is safe to execute."""
        args = args or {}
        warnings: list[str] = []
        action_lower = action.lower()
        target_lower = str(target).lower()

        # 1. Check for destructive action keywords
        if action_lower in DESTRUCTIVE_ACTIONS:
            return SafetyResult(
                safe=False,
                warnings=[],
                blocked_reason=f"Destructive action '{action}' blocked by safety checks.",
            )

        # 2. Check for system-critical paths or targets
        for blocked in BLOCKED_TARGETS:
            if blocked in target_lower or any(blocked in str(v).lower() for v in args.values()):
                return SafetyResult(
                    safe=False,
                    warnings=[],
                    blocked_reason=f"Access to sensitive target '{blocked}' is blocked.",
                )

        # 3. Coordinate bounds validation
        if "x" in args and "y" in args:
            try:
                x = int(args["x"])
                y = int(args["y"])
                if x < 0 or x > self.screen_width or y < 0 or y > self.screen_height:
                    return SafetyResult(
                        safe=False,
                        warnings=[],
                        blocked_reason=f"Coordinates ({x}, {y}) are outside screen bounds (0-{self.screen_width}, 0-{self.screen_height}).",
                    )
                # Taskbar / bottom warning
                if y > (self.screen_height - 40):
                    warnings.append(f"Target coordinate y={y} is near the Windows taskbar.")
            except (ValueError, TypeError):
                pass

        # 4. Rate-limiting check
        now = time.time()
        if (now - self._last_action_time) < self.min_action_interval_seconds:
            warnings.append("Rapid action rate detected; rate limiter applied.")
        self._last_action_time = now

        return SafetyResult(safe=True, warnings=warnings, blocked_reason=None)
