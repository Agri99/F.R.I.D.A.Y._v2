"""
src/friday/development/canary.py

WHAT THIS IS FOR:
Manages the promotion stages of an upgrade candidate:
  CANDIDATE -> SANDBOXED -> TESTED -> BENCHMARKED -> CANARY -> ACTIVE
Runbook §60.
"""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
import time


class UpgradeStage(str, Enum):
    CANDIDATE = "CANDIDATE"
    SANDBOXED = "SANDBOXED"
    TESTED = "TESTED"
    BENCHMARKED = "BENCHMARKED"
    CANARY = "CANARY"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class CanaryState:
    upgrade_id: str
    stage: UpgradeStage = UpgradeStage.CANDIDATE
    canary_runs: int = 0
    canary_successes: int = 0
    canary_failures: int = 0
    min_canary_runs: int = 3
    history: list[dict] = field(default_factory=list)

    def transition(self, to_stage: UpgradeStage, reason: str = "") -> None:
        self.stage = to_stage
        self.history.append({
            "stage": to_stage.value,
            "timestamp": time.time(),
            "reason": reason,
        })

    def record_run(self, success: bool) -> bool:
        """Record one execution during canary evaluation.
        Returns True if canary is still safe, False if rollback triggered.
        """
        self.canary_runs += 1
        if success:
            self.canary_successes += 1
        else:
            self.canary_failures += 1

        # Strict canary rule: even 1 failure during canary triggers rollback
        if self.canary_failures > 0:
            self.transition(UpgradeStage.ROLLED_BACK, "Failure observed during canary trial")
            return False

        if self.canary_runs >= self.min_canary_runs and self.stage == UpgradeStage.CANARY:
            self.transition(UpgradeStage.ACTIVE, f"Passed {self.canary_runs} successful canary trials")

        return True


__all__ = ["UpgradeStage", "CanaryState"]
