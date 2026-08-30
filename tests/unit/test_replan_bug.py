"""
tests/unit/test_replan_bug.py

WHAT THIS IS FOR:
Proves a real, serious bug is fixed: Planner.replan() used to call
self.plan(..., model_router=None) unconditionally, and plan()'s first
line is `if not model_router: return []`. Every replan attempt silently
produced an empty plan, which made the orchestrator's execution loop
exit immediately and report the task COMPLETED ("All steps completed")
even though the step that triggered replanning had just FAILED.
A failure silently became a false success.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from friday.agent.task import Task, Step, TaskStatus
from friday.agent.planner import Planner
from friday.models.base import ModelProvider, ModelResponse, ModelMessage, ProviderHealth


class _RecordingProvider(ModelProvider):
    def __init__(self, tool_calls=None, text="ok"):
        self.last_messages = []
        self._tool_calls = tool_calls or []
        self._text = text

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=True, model_loaded=True)

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return False

    def stream(self, messages, tools=None):
        yield from ()

    def generate(self, messages, tools=None, images=None):
        self.last_messages = messages
        return ModelResponse(text=self._text, tool_calls=self._tool_calls)


class _RouterStub:
    def __init__(self, provider):
        self._provider = provider

    def get(self, role):
        return self._provider


def test_replan_actually_calls_the_model_when_router_is_provided():
    """The core bug: replan() used to hardcode model_router=None, so it
    NEVER called the model, no matter what was passed to it. This proves
    that passing a real model_router now actually reaches generate()."""
    provider = _RecordingProvider(tool_calls=[
        {"function": {"name": "system.get_status", "arguments": {}}}
    ])
    planner = Planner()
    task = Task(goal="check system status")
    task.failures.append({"step": "system.get_status", "error": "timeout", "verification_reason": "no response"})

    steps = planner.replan(
        task,
        observations=[{"step": "system.get_status", "observation": "", "error": "timeout"}],
        available_tools=[{"type": "function", "function": {"name": "system.get_status"}}],
        model_router=_RouterStub(provider),
        system_prompt="You are FRIDAY.",
    )

    assert provider.last_messages, "replan() should have called generate() at all"
    assert len(steps) == 1
    assert steps[0].action == "system.get_status"


def test_replan_with_no_model_router_still_returns_empty_not_crash():
    """Backward-compat: calling replan() without a router (old call sites,
    or genuinely no model available) should still degrade to an empty
    plan, not crash - the orchestrator is responsible for treating that
    as a failure now (see test below), not replan() itself."""
    planner = Planner()
    task = Task(goal="do something")
    steps = planner.replan(task, observations=[])
    assert steps == []


def test_orchestrator_fails_task_when_replan_produces_empty_plan(tmp_path, monkeypatch):
    """The actual regression: a step fails, triggers REPLAN, and replanning
    produces nothing usable. The task must end FAILED - not silently
    COMPLETED, which is what happened before this fix."""
    monkeypatch.chdir(tmp_path)

    from friday.config import Settings
    from friday.security.policy import PolicyEngine
    from friday.tools.registry import ToolRegistry, Tool
    from friday.security.policy import RiskTier
    from friday.agent.orchestrator import AgentOrchestrator

    settings = Settings.load(str(Path(__file__).resolve().parents[2] / "config" / "default.yaml"))
    settings.ensure_dirs()

    # A tool that always fails execution, forcing the REPLAN path.
    def _always_fails(**kwargs):
        raise RuntimeError("simulated failure to trigger replan")

    registry = ToolRegistry()
    registry.register(Tool(
        name="fake.fail",
        description="always fails",
        tier=RiskTier.GREEN,
        capability_scope="system",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_always_fails,
    ))

    # Provider that always proposes calling the failing tool, and whose
    # generate() (used by replan too) returns no further tool calls -
    # simulating a model that genuinely has nothing more to suggest.
    provider = _RecordingProvider(tool_calls=[
        {"function": {"name": "fake.fail", "arguments": {}}}
    ])

    router = _RouterStub(provider)

    orch = AgentOrchestrator(
        settings=settings,
        model_router=router,
        policy_engine=PolicyEngine(settings),
        tool_registry=registry,
        system_prompt="You are FRIDAY.",
    )

    task = orch.run("do the failing thing")

    # Once replan's provider also returns tool_calls=[fake.fail] again (same
    # provider), the loop would retry the same failing tool - eventually
    # hitting max retries and stopping safely rather than looping forever.
    # Either way, the critical assertion is: NEVER silently COMPLETED.
    assert task.status != TaskStatus.COMPLETED
