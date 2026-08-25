"""
core/orchestrator.py

WHAT THIS IS FOR:
The assembly-line manager. Takes a user goal, creates a Task, asks
the model what tool to call, runs it PAST the policy engine (never
straight to execution), and moves the task through its state machine.

This is intentionally the ONLY file that talks to all four subsystems
at once. Everything else stays single-responsibility.

CONFIRMATION / SECOND-FACTOR FLOW:
Ports the proven flow from llm.py's Assistant class (v1) onto the new
task-based architecture, reusing the same security primitives
(security.confirmation.PendingConfirmation, security.voice, security.
passphrase) rather than reinventing them:

  - YELLOW/ORANGE tools -> policy says REQUIRE_CONFIRMATION -> task
    parks in AWAITING_CONFIRMATION. Caller must call resume_with_voice()
    with the next voice turn's text + audio. Approve words + a real
    voiceprint match -> executes. Deny words -> BLOCKED. Anything else
    -> task stays parked, caller re-prompts.
  - RED tools, OR any tool with `critical=True` (v1 parity - critical
    is a per-tool flag independent of tier) -> after voice approval,
    the task stays in AWAITING_CONFIRMATION for a second round asking
    for the passphrase, verified via security.passphrase.verify_passphrase.
  - A PendingConfirmation older than its TTL is treated as expired and
    the task moves to BLOCKED, exactly like v1 does.

NOTE: tool-call PARSING here is deliberately minimal — real models
return structured tool_calls (see ModelResponse.tool_calls). This
version handles that path plus a plain-text fallback so it's testable
without a live Ollama server.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import Settings
from core.models.router import ModelRouter
from core.models.base import ModelMessage
from core.security.policy import PolicyEngine, PolicyDecision, RiskTier
from core.tasks.state_machine import Task, TaskManager, TaskState
from core.tools.registry import ToolRegistry

from security.confirmation import PendingConfirmation
from security.audit import log_action

APPROVE_WORDS = {"yes", "yeah", "yep", "confirm", "do it", "proceed", "go ahead"}
DENY_WORDS = {"no", "nope", "cancel", "stop", "don't"}


@dataclass
class _PendingToolCall:
    confirmation: PendingConfirmation
    stage: str  # "voice" | "passphrase"


class AgentOrchestrator:
    def __init__(
        self,
        settings: Settings,
        model_router: ModelRouter,
        policy_engine: PolicyEngine,
        tool_registry: ToolRegistry,
        task_manager: TaskManager,
    ):
        self.settings = settings
        self.models = model_router
        self.policy = policy_engine
        self.tools = tool_registry
        self.tasks = task_manager

    def run(self, goal: str, on_transition=None) -> Task:
        task = self.tasks.create(goal)
        task.transition(TaskState.PLANNING, reason="orchestrator started planning", on_transition=on_transition)

        provider = self.models.get("reasoning")
        response = provider.generate(
            messages=[
                ModelMessage(role="system", content="You are FRIDAY. Use tools when helpful."),
                ModelMessage(role="user", content=goal),
            ],
            tools=self.tools.all_schemas(),
        )

        if not response.tool_calls:
            # No tool needed — pure conversational answer, nothing to gate.
            task.transition(TaskState.EXECUTING, reason="no tool call, direct answer", on_transition=on_transition)
            task.transition(TaskState.VERIFYING, reason="trivial: text answer needs no verification", on_transition=on_transition)
            task.transition(TaskState.DONE, reason=response.text, on_transition=on_transition)
            return task

        call = response.tool_calls[0]
        tool_name = call["function"]["name"] if "function" in call else call.get("name")
        tool_args = call.get("function", {}).get("arguments", call.get("arguments", {}))

        tier = self.tools.tier_of(tool_name)
        decision = self.policy.evaluate(tool_name, tier)

        if decision.decision == PolicyDecision.DENY:
            task.transition(TaskState.BLOCKED, reason=decision.reason, on_transition=on_transition)
            return task

        if decision.decision in (PolicyDecision.REQUIRE_CONFIRMATION, PolicyDecision.REQUIRE_SECOND_FACTOR):
            self._park_for_confirmation(task, tool_name, tool_args, on_transition=on_transition)
            return task

        # ALLOW path (GREEN)
        self._execute_and_verify(task, tool_name, tool_args, on_transition=on_transition)
        return task

    # ------------------------------------------------------------------

    def _park_for_confirmation(self, task: Task, tool_name: str, tool_args: dict, on_transition=None) -> None:
        tool = self.tools.get(tool_name)
        confirmation = PendingConfirmation(tool_name=tool_name, arguments=tool_args)
        task.pending = _PendingToolCall(confirmation=confirmation, stage="voice")

        if tool.preview:
            preview = tool.preview(**tool_args)
            if not preview.get("found", True):
                task.transition(TaskState.BLOCKED, reason=preview.get("message", "target not found"), on_transition=on_transition)
                return
            question = f"Found {preview.get('path', tool_name)}. Say a full phrase like 'yes, I confirm' to proceed, or 'no' to cancel."
        else:
            question = f"'{tool_name}' needs your confirmation. Say yes to proceed, or no to cancel."

        task.transition(TaskState.AWAITING_CONFIRMATION, reason=question, on_transition=on_transition)
        task.last_message = question

    def resume_with_voice(self, task_id: str, user_text: str, audio_path: str | None, on_transition=None) -> Task | None:
        """Call this with the next voice turn while a task sits in
        AWAITING_CONFIRMATION. Mirrors llm.py's _resolve_confirmation /
        _resolve_passphrase two-stage flow."""
        task = self.tasks.get(task_id)
        if task is None or task.state != TaskState.AWAITING_CONFIRMATION:
            return task

        pending: _PendingToolCall = task.pending
        confirmation = pending.confirmation

        if confirmation.is_expired():
            task.transition(TaskState.BLOCKED, reason="confirmation expired", on_transition=on_transition)
            return task

        if pending.stage == "voice":
            return self._resolve_voice_stage(task, pending, user_text, audio_path, on_transition)
        else:
            return self._resolve_passphrase_stage(task, pending, user_text, on_transition)

    def _resolve_voice_stage(self, task: Task, pending: _PendingToolCall, user_text: str, audio_path: str | None, on_transition) -> Task:
        normalized = user_text.strip().lower()

        if any(word in normalized for word in DENY_WORDS):
            task.transition(TaskState.BLOCKED, reason="user declined", on_transition=on_transition)
            return task

        if not any(word in normalized for word in APPROVE_WORDS):
            task.last_message = "I need a clear yes or no. Should I proceed?"
            return task  # stay parked, no transition

        from security.voice import is_authorized_voice, get_duration_seconds

        if not audio_path or get_duration_seconds(audio_path) < 1.0:
            task.last_message = "Please say a full phrase, like 'yes, I confirm', so I can verify it's you."
            return task

        if not is_authorized_voice(audio_path):
            task.last_message = "That didn't sound like your voice, so I won't proceed. Please confirm again."
            return task

        tool = self.tools.get(pending.confirmation.tool_name)
        if tool.critical or self.tools.tier_of(tool.name) == RiskTier.RED:
            pending.stage = "passphrase"
            task.last_message = "This is a critical action. Please say the passphrase to proceed."
            return task

        self._execute_and_verify(task, pending.confirmation.tool_name, pending.confirmation.arguments, on_transition=on_transition, confirmed=True)
        return task

    def _resolve_passphrase_stage(self, task: Task, pending: _PendingToolCall, user_text: str, on_transition) -> Task:
        from security.passphrase import verify_passphrase

        if not verify_passphrase(user_text):
            task.transition(TaskState.BLOCKED, reason="passphrase incorrect", on_transition=on_transition)
            return task

        self._execute_and_verify(task, pending.confirmation.tool_name, pending.confirmation.arguments, on_transition=on_transition, confirmed=True)
        return task

    def _execute_and_verify(self, task: Task, tool_name: str, tool_args: dict, on_transition=None, confirmed: bool = False) -> None:
        task.transition(TaskState.EXECUTING, reason=f"running tool '{tool_name}'", on_transition=on_transition)
        tool = self.tools.get(tool_name)
        try:
            result = tool.run(**tool_args)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, becomes a FAILED state
            task.transition(TaskState.FAILED, reason=str(exc), on_transition=on_transition)
            return

        log_action(tool_name, self.tools.tier_of(tool_name).value, tool_args, result, confirmed=confirmed)

        task.transition(TaskState.VERIFYING, reason="checking tool result", on_transition=on_transition)
        verified = result is not None
        if verified:
            task.transition(TaskState.DONE, reason=str(result), on_transition=on_transition)
        else:
            task.transition(TaskState.FAILED, reason="tool returned no result", on_transition=on_transition)
