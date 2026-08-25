"""
tests/test_orchestrator_e2e.py

WHAT THIS IS FOR:
Proves what actually happens when the orchestrator runs a real legacy
tool end to end, using a fake ModelProvider (no live Ollama needed) so
this is fast and deterministic. Two things checked:

1. A GREEN tool runs all the way to DONE.
2. A YELLOW/ORANGE/RED tool stops at AWAITING_CONFIRMATION and does
   NOT execute - which is correct per the policy engine, but currently
   has no resume path. This test documents that gap on purpose so it
   doesn't get "fixed" accidentally by someone assuming AWAITING_
   CONFIRMATION should auto-proceed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from config.settings import Settings
from core.models.base import ModelProvider, ModelResponse
from core.models.router import ModelRouter
from core.security.policy import PolicyEngine
from core.tasks.state_machine import TaskManager, TaskState
from core.tools.registry import ToolRegistry
from core.tools.legacy_bridge import register_legacy_tools
from core.orchestrator import AgentOrchestrator


class FakeToolCallProvider(ModelProvider):
    """Always proposes calling one specific tool with fixed args - no Ollama needed."""

    def __init__(self, tool_name: str, tool_args: dict):
        self.tool_name = tool_name
        self.tool_args = tool_args

    def is_available(self) -> bool:
        return True

    def generate(self, messages, tools=None) -> ModelResponse:
        return ModelResponse(
            text="",
            tool_calls=[{"function": {"name": self.tool_name, "arguments": self.tool_args}}],
        )


def _build_orchestrator_with_fake_model(tool_name: str, tool_args: dict) -> AgentOrchestrator:
    settings = Settings.load(Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    settings.ensure_dirs()

    tool_registry = ToolRegistry()
    register_legacy_tools(tool_registry)

    router = ModelRouter(settings)
    router._cache["reasoning"] = FakeToolCallProvider(tool_name, tool_args)  # inject fake

    return AgentOrchestrator(
        settings=settings,
        model_router=router,
        policy_engine=PolicyEngine(settings),
        tool_registry=tool_registry,
        task_manager=TaskManager(),
    )


def test_green_legacy_tool_completes_end_to_end():
    orch = _build_orchestrator_with_fake_model("get_system_info", {})
    task = orch.run("how's my system doing?")
    assert task.state == TaskState.DONE


def test_yellow_legacy_tool_stops_at_confirmation_not_executed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # so create_text_file doesn't write into the real workspace
    orch = _build_orchestrator_with_fake_model(
        "create_text_file", {"filename": "should_not_exist.txt", "content": "test"}
    )
    task = orch.run("make a note")
    assert task.state == TaskState.AWAITING_CONFIRMATION
    assert not (tmp_path / "workspace" / "should_not_exist.txt").exists()
