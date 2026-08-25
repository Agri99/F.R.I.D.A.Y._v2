"""
core/orchestrator.py

WHAT THIS IS FOR:
The assembly-line manager. Takes a user goal, creates a Task, asks
the model what tool to call, runs it PAST the policy engine (never
straight to execution), and moves the task through its state machine.

This is intentionally the ONLY file that talks to all four subsystems
at once. Everything else stays single-responsibility.

NOTE: tool-call PARSING here is deliberately minimal — real models
return structured tool_calls (see ModelResponse.tool_calls). This
version handles that path plus a plain-text fallback so it's testable
without a live Ollama server.
"""

from __future__ import annotations

from config.settings import Settings
from core.models.router import ModelRouter
from core.models.base import ModelMessage
from core.security.policy import PolicyEngine, PolicyDecision
from core.tasks.state_machine import Task, TaskManager, TaskState
from core.tools.registry import ToolRegistry


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
            task.transition(TaskState.AWAITING_CONFIRMATION, reason=decision.reason, on_transition=on_transition)
            # Real UI/voice confirmation hook goes here in a later sprint.
            return task

        # ALLOW path
        task.transition(TaskState.EXECUTING, reason=f"running tool '{tool_name}'", on_transition=on_transition)
        tool = self.tools.get(tool_name)
        try:
            result = tool.run(**tool_args)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, becomes a FAILED state
            task.transition(TaskState.FAILED, reason=str(exc), on_transition=on_transition)
            return task

        task.transition(TaskState.VERIFYING, reason="checking tool result", on_transition=on_transition)
        # Verification is a stub for now — a real check belongs per-tool later.
        verified = result is not None
        if verified:
            task.transition(TaskState.DONE, reason=str(result), on_transition=on_transition)
        else:
            task.transition(TaskState.FAILED, reason="tool returned no result", on_transition=on_transition)

        return task
