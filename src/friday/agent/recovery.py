from __future__ import annotations

from enum import Enum
from .task import Task

class RecoveryStrategy(str, Enum):
    RETRY = "RETRY"
    REPAIR_INPUT = "REPAIR_INPUT"
    ASK_USER = "ASK_USER"
    DIAGNOSE = "DIAGNOSE"
    STOP_SAFELY = "STOP_SAFELY"

class RecoveryManager:
    """Classifies failures and attempts recovery."""
    
    def classify_failure(self, error: str, context: dict) -> RecoveryStrategy:
        error_lower = error.lower() if error else ""
        if "permission" in error_lower or "access denied" in error_lower:
            return RecoveryStrategy.ASK_USER
        if "timeout" in error_lower or "connection" in error_lower:
            return RecoveryStrategy.RETRY
        if "invalid" in error_lower or "value" in error_lower:
            return RecoveryStrategy.REPAIR_INPUT
        if "not found" in error_lower:
            return RecoveryStrategy.DIAGNOSE
        return RecoveryStrategy.STOP_SAFELY

    def attempt_recovery(self, task: Task, strategy: RecoveryStrategy) -> bool:
        task.observations.append(f"Attempting recovery strategy: {strategy.value}")
        # Stub for actual recovery logic
        if strategy == RecoveryStrategy.RETRY:
            return True # Will retry
        elif strategy == RecoveryStrategy.STOP_SAFELY:
            return False
        return False
