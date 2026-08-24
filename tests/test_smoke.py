"""
tests/test_smoke.py

WHAT THIS IS FOR:
Appendix B, rule 9: "Maintain tests around security invariants before
refactors." These tests don't touch Ollama at all — they prove the
policy engine and state machine behave correctly in isolation, so you
can refactor the orchestrator later without silently breaking safety.

Run with: pytest tests/test_smoke.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from config.settings import Settings
from core.security.policy import PolicyEngine, PolicyDecision, RiskTier
from core.tasks.state_machine import Task, TaskState
from core.tools.registry import ToolRegistry
from core.tools.base_tools import register_base_tools


@pytest.fixture
def settings():
    return Settings.load(Path(__file__).resolve().parents[1] / "config" / "default.yaml")


@pytest.fixture
def policy(settings):
    return PolicyEngine(settings)


@pytest.fixture
def registry():
    r = ToolRegistry()
    register_base_tools(r)
    return r


def test_green_tool_auto_approved(policy):
    result = policy.evaluate("system.get_time", RiskTier.GREEN)
    assert result.decision == PolicyDecision.ALLOW


def test_orange_tool_requires_confirmation(policy):
    result = policy.evaluate("filesystem.write_note", RiskTier.ORANGE)
    assert result.decision == PolicyDecision.REQUIRE_CONFIRMATION


def test_unknown_tool_defaults_to_red_and_blocks_second_factor(policy):
    # No tier passed at all -> must fail closed to config default (RED),
    # which is hard-blocked without a second factor. Never auto-allow.
    result = policy.evaluate("some.made_up.tool", None)
    assert result.tier == RiskTier.RED
    assert result.decision == PolicyDecision.REQUIRE_SECOND_FACTOR


def test_registry_wires_correct_tiers(registry):
    assert registry.tier_of("system.get_time") == RiskTier.GREEN
    assert registry.tier_of("filesystem.write_note") == RiskTier.ORANGE


def test_duplicate_tool_registration_rejected(registry):
    from core.tools.base_tools import get_time_tool
    with pytest.raises(ValueError):
        registry.register(get_time_tool)


def test_task_legal_transition():
    task = Task(goal="test")
    task.transition(TaskState.PLANNING, "start")
    task.transition(TaskState.EXECUTING, "run tool")
    assert task.state == TaskState.EXECUTING
    assert len(task.history) == 2


def test_task_illegal_transition_raises():
    task = Task(goal="test")
    # Can't jump straight from PENDING to DONE — must go through the pipeline.
    with pytest.raises(ValueError):
        task.transition(TaskState.DONE, "skip everything")


def test_task_done_is_terminal():
    task = Task(goal="test")
    task.transition(TaskState.PLANNING, "start")
    task.transition(TaskState.EXECUTING, "run")
    task.transition(TaskState.VERIFYING, "check")
    task.transition(TaskState.DONE, "ok")
    with pytest.raises(ValueError):
        task.transition(TaskState.EXECUTING, "should not be allowed after DONE")
