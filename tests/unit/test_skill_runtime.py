from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from friday.security.capabilities import CapabilityRegistry
from friday.security.policy import PolicyEngine
from friday.skills.registry import SkillRegistry
from friday.skills.runtime import SkillRuntime


@dataclass
class FakeTool:
    name: str
    tier: str = "GREEN"
    capability_scope: str = ""
    last_args: dict | None = None

    def run(self, **kwargs):
        self.last_args = kwargs
        return {"status": "ok", "message": "done"}


@dataclass
class FakeToolRegistry:
    tools: dict[str, Any] = field(default_factory=dict)

    def get(self, name):
        return self.tools.get(name)


@dataclass
class Skill:
    name: str
    procedure_steps: list[dict] = field(default_factory=list)
    variables: dict = field(default_factory=dict)


def _policy() -> PolicyEngine:
    from friday.config import Settings

    return PolicyEngine(Settings())


def test_skill_runtime_executes_steps_via_action_request():
    tool = FakeTool(name="computer.click", tier="GREEN")
    registry = FakeToolRegistry({"computer.click": tool})
    skill = Skill(
        name="sample",
        procedure_steps=[
            {"action": "computer.click", "args": {"x": 10}, "expected": "done"},
        ],
    )
    skill_registry = SkillRegistry()
    skill_registry.register(skill)
    runtime = SkillRuntime(registry, _policy(), CapabilityRegistry(), skill_registry)

    result = runtime.run("sample", {})

    assert result.success is True
    assert tool.last_args == {"x": 10}
    assert "done" in result.step_results[0]["observation"].lower()


def test_skill_runtime_fails_when_policy_denies():
    tool = FakeTool(name="unknown.tool", tier="GREEN")
    registry = FakeToolRegistry({"unknown.tool": tool})
    skill = Skill(
        name="unsafe",
        procedure_steps=[{"action": "unknown.tool", "args": {}, "expected": "ok"}],
    )
    skill_registry = SkillRegistry()
    skill_registry.register(skill)
    runtime = SkillRuntime(registry, _policy(), CapabilityRegistry(), skill_registry)

    result = runtime.run("unsafe", {})

    assert result.success is False
    assert result.error and "blocked" in result.error.lower()


def test_skill_runtime_interpolates_inputs():
    tool = FakeTool(name="system.toggle_orb", tier="GREEN")
    registry = FakeToolRegistry({"system.toggle_orb": tool})
    skill = Skill(
        name="templated",
        procedure_steps=[
            {"action": "system.toggle_orb", "args": {"visible": "{flag}"}, "expected": "ok"},
        ],
    )
    skill_registry = SkillRegistry()
    skill_registry.register(skill)
    runtime = SkillRuntime(registry, _policy(), CapabilityRegistry(), skill_registry)

    result = runtime.run("templated", {"flag": True})

    assert result.success is True
    assert tool.last_args == {"visible": "True"}


def test_skill_runtime_fails_on_missing_skill():
    runtime = SkillRuntime(FakeToolRegistry(), _policy(), CapabilityRegistry(), SkillRegistry())
    result = runtime.run("does_not_exist", {})
    assert result.success is False
    assert "not found" in (result.error or "")
