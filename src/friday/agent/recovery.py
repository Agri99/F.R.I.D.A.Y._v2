"""
src/friday/agent/recovery.py

WHAT THIS IS FOR:
Failure classification and autonomous recovery strategy assignment (Blueprint §9, §10).
Enhanced with screen change detection, target verification, and progressive recovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
from .task import Task, Step


class FailureCategory(Enum):
    TRANSIENT = "transient"
    STALE_TARGET = "stale_target"
    MISSING_APPLICATION = "missing_app"
    PERMISSION_DENIED = "permission"
    INVALID_ARGUMENT = "invalid_arg"
    UI_CHANGED = "ui_changed"
    NETWORK_UNAVAILABLE = "network"
    MODEL_UNAVAILABLE = "model"
    AMBIGUOUS_STATE = "ambiguous"
    VERIFICATION_FAILED = "verification_failed"
    TARGET_NOT_FOUND = "target_not_found"
    DIALOG_INTERRUPTED = "dialog_interrupted"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNKNOWN = "unknown"


class RecoveryStrategy(str, Enum):
    RETRY = "RETRY"
    REPAIR_INPUT = "REPAIR_INPUT"
    ASK_USER = "ASK_USER"
    DIAGNOSE = "DIAGNOSE"
    REPLAN = "REPLAN"
    RE_RESOLVE_TARGET = "RE_RESOLVE_TARGET"
    WAIT_AND_RETRY = "WAIT_AND_RETRY"
    STOP_SAFELY = "STOP_SAFELY"


@dataclass
class RecoveryAction:
    strategy: RecoveryStrategy
    reasoning: str
    category: FailureCategory
    payload: dict | None = None  # Additional data for recovery (e.g., new target, wait time)


class RecoveryManager:
    """Classifies failures and prescribes evidence-driven recovery strategies."""

    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts

    def classify(self, error: str, context: dict | None = None) -> FailureCategory:
        error_lower = (error or "").lower()
        context = context or {}

        # Model unavailable - check first before network
        if "ollama" in error_lower or "model" in error_lower or "model service" in error_lower:
            return FailureCategory.MODEL_UNAVAILABLE

        # Target not found / stale target
        if ("not found" in error_lower or "no such window" in error_lower or
            "element not found" in error_lower or "no application found" in error_lower or
            "could not be resolved" in error_lower):
            return FailureCategory.TARGET_NOT_FOUND

        # Permission
        if "permission" in error_lower or "access denied" in error_lower or "unauthorized" in error_lower:
            return FailureCategory.PERMISSION_DENIED

        # Invalid argument
        if "invalid" in error_lower or "typeerror" in error_lower or "missing argument" in error_lower:
            return FailureCategory.INVALID_ARGUMENT

        # UI changed / dialog interrupted
        if "ui" in error_lower or "obscured" in error_lower or "dialog" in error_lower:
            if "dialog" in error_lower or "confirm" in error_lower or "alert" in error_lower:
                return FailureCategory.DIALOG_INTERRUPTED
            return FailureCategory.UI_CHANGED

        # Verification failed
        if "verification" in error_lower or "expected change" in error_lower or "not verified" in error_lower:
            return FailureCategory.VERIFICATION_FAILED

        # Transient - timeout without network context
        if "transient" in error_lower or "temporary" in error_lower:
            return FailureCategory.TRANSIENT

        # Network - connection refused, offline, but not timeout (which is transient)
        if "connection refused" in error_lower or "offline" in error_lower or "dns" in error_lower:
            return FailureCategory.NETWORK_UNAVAILABLE

        # Timeout by itself = transient
        if "timeout" in error_lower:
            return FailureCategory.TRANSIENT

        # Budget exceeded
        if "budget" in error_lower or "exceeded" in error_lower or "max steps" in error_lower:
            return FailureCategory.BUDGET_EXCEEDED

        if "ambiguous" in error_lower:
            return FailureCategory.AMBIGUOUS_STATE

        return FailureCategory.UNKNOWN

    def recover(self, task: Task, step: Step, category: FailureCategory) -> RecoveryAction:
        step_index = task.current_step_index
        # Check both task.retries dict and step.retry_count for backward compatibility
        retries = task.retries.get(str(step_index), getattr(step, "retry_count", 0))

        if retries >= self.max_attempts:
            return RecoveryAction(
                RecoveryStrategy.STOP_SAFELY,
                f"Maximum retry attempts ({self.max_attempts}) reached for step {step_index}.",
                category,
            )

        # Increment retry count
        task.retries[str(step_index)] = retries + 1

        if category == FailureCategory.TRANSIENT:
            return RecoveryAction(RecoveryStrategy.WAIT_AND_RETRY,
                "Transient failure detected; waiting briefly and retrying.",
                category,
                payload={"wait_seconds": 1.0 * (retries + 1)})

        elif category == FailureCategory.TARGET_NOT_FOUND:
            # Try to re-resolve the target with updated screen state
            return RecoveryAction(RecoveryStrategy.RE_RESOLVE_TARGET,
                "Target not found; re-resolving with current screen state.",
                category,
                payload={"step_description": step.arguments.get("text_label", step.action)})

        elif category in (FailureCategory.UI_CHANGED, FailureCategory.VERIFICATION_FAILED):
            # Trigger replan with observation
            return RecoveryAction(RecoveryStrategy.REPLAN,
                "UI changed or verification failed; triggering observe-replan with new state.",
                category)

        elif category == FailureCategory.DIALOG_INTERRUPTED:
            # Wait for dialog, then try to handle it
            return RecoveryAction(RecoveryStrategy.WAIT_AND_RETRY,
                "Dialog detected; waiting for it to resolve or user action.",
                category,
                payload={"wait_seconds": 2.0, "handle_dialog": True})

        elif category == FailureCategory.PERMISSION_DENIED:
            return RecoveryAction(RecoveryStrategy.ASK_USER,
                "Requires elevated authorization from user.",
                category)

        elif category == FailureCategory.INVALID_ARGUMENT:
            return RecoveryAction(RecoveryStrategy.REPAIR_INPUT,
                "Input parameters invalid; attempting auto-repair.",
                category)

        elif category == FailureCategory.NETWORK_UNAVAILABLE:
            return RecoveryAction(RecoveryStrategy.REPLAN,
                "Network unavailable; switching to local offline tool fallback.",
                category)

        elif category == FailureCategory.MODEL_UNAVAILABLE:
            return RecoveryAction(RecoveryStrategy.REPLAN,
                "Model unavailable; switching to fallback model or replanning.",
                category)

        elif category == FailureCategory.BUDGET_EXCEEDED:
            return RecoveryAction(RecoveryStrategy.STOP_SAFELY,
                "Execution budget exceeded; cannot continue.",
                category)

        else:
            return RecoveryAction(RecoveryStrategy.REPLAN,
                f"Unknown failure category ({category.value}); attempting replan.",
                category)