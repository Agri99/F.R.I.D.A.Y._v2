from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from .task import Task, Step

class FailureCategory(Enum):
    TRANSIENT = 'transient'
    STALE_TARGET = 'stale_target'
    MISSING_APPLICATION = 'missing_app'
    PERMISSION_DENIED = 'permission'
    INVALID_ARGUMENT = 'invalid_arg'
    UI_CHANGED = 'ui_changed'
    NETWORK_UNAVAILABLE = 'network'
    MODEL_UNAVAILABLE = 'model'
    AMBIGUOUS_STATE = 'ambiguous'
    UNKNOWN = 'unknown'

class RecoveryStrategy(str, Enum):
    RETRY = "RETRY"
    REPAIR_INPUT = "REPAIR_INPUT"
    ASK_USER = "ASK_USER"
    DIAGNOSE = "DIAGNOSE"
    STOP_SAFELY = "STOP_SAFELY"

@dataclass
class RecoveryAction:
    strategy: RecoveryStrategy
    reasoning: str
    category: FailureCategory

class RecoveryManager:
    """Classifies failures and attempts recovery."""
    
    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts
        
    def classify(self, error: str, context: dict) -> FailureCategory:
        error_lower = error.lower() if error else ""
        if "permission" in error_lower or "access denied" in error_lower:
            return FailureCategory.PERMISSION_DENIED
        if "timeout" in error_lower or "connection" in error_lower:
            return FailureCategory.NETWORK_UNAVAILABLE
        if "invalid" in error_lower or "value" in error_lower:
            return FailureCategory.INVALID_ARGUMENT
        if "not found" in error_lower:
            return FailureCategory.STALE_TARGET
        if "transient" in error_lower:
            return FailureCategory.TRANSIENT
        return FailureCategory.UNKNOWN

    def recover(self, task: Task, step: Step, category: FailureCategory) -> RecoveryAction:
        if category == FailureCategory.TRANSIENT:
            return RecoveryAction(RecoveryStrategy.RETRY, "Transient failure detected, retrying.", category)
        elif category == FailureCategory.PERMISSION_DENIED:
            return RecoveryAction(RecoveryStrategy.ASK_USER, "Requires user permission.", category)
        elif category == FailureCategory.INVALID_ARGUMENT:
            return RecoveryAction(RecoveryStrategy.REPAIR_INPUT, "Input needs to be repaired.", category)
        else:
            return RecoveryAction(RecoveryStrategy.STOP_SAFELY, "Unknown or unrecoverable error.", category)
