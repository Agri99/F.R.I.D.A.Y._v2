"""
src/friday/agent/steering.py

WHAT THIS IS FOR:
Verbal steering and operational mode switching during agent execution (Blueprint §9, §17.4).
Extended with progressive perception and observe-verify-replan steering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class AgentMode(Enum):
    NORMAL = "normal"
    FAST = "fast"
    DEEP_REASONING = "deep"
    OFFLINE = "offline"
    PAUSED = "paused"


class SteeringTrigger(Enum):
    VERIFICATION_FAILED = "verification_failed"
    TARGET_LOST = "target_lost"
    UNEXPECTED_DIALOG = "unexpected_dialog"
    UI_CHANGED = "ui_changed"
    BUDGET_WARNING = "budget_warning"
    USER_INTERRUPT = "user_interrupt"


@dataclass
class SteeringCommand:
    mode: AgentMode
    raw_text: str = ""
    trigger: SteeringTrigger | None = None
    payload: dict = field(default_factory=dict)


@dataclass
class SteeringAction:
    """Action to take based on steering."""
    type: str  # "replan", "re_resolve", "pause", "confirm", "continue", "abort"
    reason: str
    payload: dict = field(default_factory=dict)


class SteeringController:
    """Manages conversational mode switches, real-time agent steering, and observe-verify-replan triggers."""

    def __init__(self, on_replan: Callable[[dict], None] | None = None,
                 on_pause: Callable[[], None] | None = None) -> None:
        self.current_mode: AgentMode = AgentMode.NORMAL
        self._on_replan = on_replan
        self._on_pause = on_pause
        self._verification_failure_count = 0
        self._max_verification_failures_before_replan = 2

    def parse_command(self, text: str) -> SteeringCommand | None:
        """Parse natural language steering and mode switch instructions."""
        text_lower = (text or "").lower().strip()

        if any(phrase in text_lower for phrase in ["use fast mode", "be quick", "switch to fast", "fast mode"]):
            return SteeringCommand(mode=AgentMode.FAST, raw_text=text)

        if any(phrase in text_lower for phrase in ["use deep reasoning", "think carefully", "deep mode", "reasoning mode"]):
            return SteeringCommand(mode=AgentMode.DEEP_REASONING, raw_text=text)

        if any(phrase in text_lower for phrase in ["go offline", "disconnect", "offline mode", "stay local"]):
            return SteeringCommand(mode=AgentMode.OFFLINE, raw_text=text)

        if any(phrase in text_lower for phrase in ["stop", "pause", "hold on", "wait a second"]):
            return SteeringCommand(mode=AgentMode.PAUSED, raw_text=text)

        if any(phrase in text_lower for phrase in ["resume", "continue", "go ahead", "normal mode"]):
            return SteeringCommand(mode=AgentMode.NORMAL, raw_text=text)

        # Progressive perception commands
        if any(phrase in text_lower for phrase in ["look again", "check again", "recheck", "verify again"]):
            return SteeringCommand(mode=AgentMode.NORMAL, raw_text=text,
                                   trigger=SteeringTrigger.VERIFICATION_FAILED,
                                   payload={"action": "re_verify"})

        if any(phrase in text_lower for phrase in ["try different", "use another", "find another way"]):
            return SteeringCommand(mode=AgentMode.NORMAL, raw_text=text,
                                   trigger=SteeringTrigger.TARGET_LOST,
                                   payload={"action": "re_resolve"})

        return None

    def apply(self, command: SteeringCommand) -> str:
        """Apply the requested mode and return speakable confirmation."""
        self.current_mode = command.mode

        if command.mode == AgentMode.FAST:
            return "Switching to fast mode."
        elif command.mode == AgentMode.DEEP_REASONING:
            return "Engaging deep reasoning mode."
        elif command.mode == AgentMode.OFFLINE:
            return "Going offline."
        elif command.mode == AgentMode.PAUSED:
            if self._on_pause:
                self._on_pause()
            return "Paused. Let me know when to resume."
        elif command.mode == AgentMode.NORMAL:
            return "Resuming normal operation."
        return "Mode updated."

    def on_verification_failure(self, step_name: str, reason: str, context: dict | None = None) -> SteeringAction:
        """Handle verification failure - may trigger replan after threshold."""
        self._verification_failure_count += 1

        if self._verification_failure_count >= self._max_verification_failures_before_replan:
            self._verification_failure_count = 0
            if self._on_replan:
                self._on_replan({
                    "trigger": SteeringTrigger.VERIFICATION_FAILED,
                    "step": step_name,
                    "reason": reason,
                    "context": context or {},
                })
            return SteeringAction(
                type="replan",
                reason=f"Verification failed {self._max_verification_failures_before_replan} times: {reason}",
                payload={"trigger": SteeringTrigger.VERIFICATION_FAILED}
            )

        return SteeringAction(
            type="re_verify",
            reason=f"Verification failed ({self._verification_failure_count}/{self._max_verification_failures_before_replan}): {reason}",
            payload={"trigger": SteeringTrigger.VERIFICATION_FAILED}
        )

    def on_target_lost(self, target_description: str, context: dict | None = None) -> SteeringAction:
        """Handle target resolution failure."""
        if self._on_replan:
            self._on_replan({
                "trigger": SteeringTrigger.TARGET_LOST,
                "target": target_description,
                "context": context or {},
            })
        return SteeringAction(
            type="re_resolve",
            reason=f"Target lost: {target_description}",
            payload={"trigger": SteeringTrigger.TARGET_LOST, "target": target_description}
        )

    def on_unexpected_dialog(self, dialog_text: str, context: dict | None = None) -> SteeringAction:
        """Handle unexpected dialog/popup."""
        return SteeringAction(
            type="pause",
            reason=f"Unexpected dialog detected: {dialog_text}",
            payload={"trigger": SteeringTrigger.UNEXPECTED_DIALOG, "dialog": dialog_text}
        )

    def on_ui_changed(self, change_summary: str, context: dict | None = None) -> SteeringAction:
        """Handle significant UI change."""
        if self._on_replan:
            self._on_replan({
                "trigger": SteeringTrigger.UI_CHANGED,
                "change": change_summary,
                "context": context or {},
            })
        return SteeringAction(
            type="replan",
            reason=f"UI changed: {change_summary}",
            payload={"trigger": SteeringTrigger.UI_CHANGED}
        )

    def on_budget_warning(self, budget_type: str, percent_used: float) -> SteeringAction:
        """Handle budget threshold warning."""
        if percent_used >= 0.9:
            return SteeringAction(
                type="abort",
                reason=f"{budget_type} budget at {percent_used:.0%}",
                payload={"trigger": SteeringTrigger.BUDGET_WARNING, "budget_type": budget_type}
            )
        return SteeringAction(
            type="continue",
            reason=f"{budget_type} budget at {percent_used:.0%}",
            payload={"trigger": SteeringTrigger.BUDGET_WARNING}
        )

    def reset_verification_failures(self) -> None:
        """Reset verification failure counter after successful step."""
        self._verification_failure_count = 0

    def get_current_mode(self) -> AgentMode:
        return self.current_mode
