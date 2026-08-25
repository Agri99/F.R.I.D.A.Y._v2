"""
tests/test_confirmation_flow.py

WHAT THIS IS FOR:
Proves the AWAITING_CONFIRMATION resume path actually works: deny
blocks, wrong voice keeps waiting, right voice + non-critical tool
executes, critical/RED tool needs a second passphrase stage, wrong
passphrase blocks. Voice/passphrase checks are monkeypatched so this
runs without a microphone or real speechbrain model.
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
from core.tools.registry import Tool, ToolRegistry
from core.security.policy import RiskTier
from core.orchestrator import AgentOrchestrator


class FakeToolCallProvider(ModelProvider):
    def __init__(self, tool_name, tool_args):
        self.tool_name, self.tool_args = tool_name, tool_args

    def is_available(self):
        return True

    def generate(self, messages, tools=None):
        return ModelResponse(text="", tool_calls=[{"function": {"name": self.tool_name, "arguments": self.tool_args}}])


def _make_orch(tool_name, tool_args, tier, critical=False):
    settings = Settings.load(Path(__file__).resolve().parents[1] / "config" / "default.yaml")
    settings.ensure_dirs()

    registry = ToolRegistry()
    registry.register(Tool(
        name=tool_name,
        description="test tool",
        tier=tier,
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=lambda **kw: {"status": "ok"},
        critical=critical,
    ))

    router = ModelRouter(settings)
    router._cache["reasoning"] = FakeToolCallProvider(tool_name, tool_args)

    return AgentOrchestrator(
        settings=settings,
        model_router=router,
        policy_engine=PolicyEngine(settings),
        tool_registry=registry,
        task_manager=TaskManager(),
    )


def test_deny_blocks_task():
    orch = _make_orch("do_thing", {}, RiskTier.YELLOW)
    task = orch.run("do the thing")
    assert task.state == TaskState.AWAITING_CONFIRMATION

    task = orch.resume_with_voice(task.id, "no, cancel", audio_path=None)
    assert task.state == TaskState.BLOCKED


def test_unclear_reply_stays_parked():
    orch = _make_orch("do_thing", {}, RiskTier.YELLOW)
    task = orch.run("do the thing")

    task = orch.resume_with_voice(task.id, "maybe later", audio_path=None)
    assert task.state == TaskState.AWAITING_CONFIRMATION
    assert "yes or no" in task.last_message.lower()


def test_approve_with_bad_voiceprint_stays_parked(monkeypatch):
    import security.voice as voice_mod
    monkeypatch.setattr(voice_mod, "get_duration_seconds", lambda path: 2.0)
    monkeypatch.setattr(voice_mod, "is_authorized_voice", lambda path: False)

    orch = _make_orch("do_thing", {}, RiskTier.YELLOW)
    task = orch.run("do the thing")
    task = orch.resume_with_voice(task.id, "yes, confirm", audio_path="fake.wav")
    assert task.state == TaskState.AWAITING_CONFIRMATION
    assert "didn't sound like your voice" in task.last_message


def test_approve_with_good_voiceprint_executes_non_critical(monkeypatch):
    import security.voice as voice_mod
    monkeypatch.setattr(voice_mod, "get_duration_seconds", lambda path: 2.0)
    monkeypatch.setattr(voice_mod, "is_authorized_voice", lambda path: True)

    orch = _make_orch("do_thing", {}, RiskTier.YELLOW, critical=False)
    task = orch.run("do the thing")
    task = orch.resume_with_voice(task.id, "yes, confirm", audio_path="fake.wav")
    assert task.state == TaskState.DONE


def test_critical_tool_requires_passphrase_after_voice(monkeypatch):
    import security.voice as voice_mod
    import security.passphrase as pass_mod
    monkeypatch.setattr(voice_mod, "get_duration_seconds", lambda path: 2.0)
    monkeypatch.setattr(voice_mod, "is_authorized_voice", lambda path: True)
    monkeypatch.setattr(pass_mod, "verify_passphrase", lambda text: True)

    orch = _make_orch("shutdown_friday", {}, RiskTier.RED, critical=True)
    task = orch.run("shut down")

    task = orch.resume_with_voice(task.id, "yes, confirm", audio_path="fake.wav")
    assert task.state == TaskState.AWAITING_CONFIRMATION  # now waiting on passphrase
    assert "passphrase" in task.last_message.lower()

    task = orch.resume_with_voice(task.id, "the correct phrase", audio_path=None)
    assert task.state == TaskState.DONE


def test_wrong_passphrase_blocks(monkeypatch):
    import security.voice as voice_mod
    import security.passphrase as pass_mod
    monkeypatch.setattr(voice_mod, "get_duration_seconds", lambda path: 2.0)
    monkeypatch.setattr(voice_mod, "is_authorized_voice", lambda path: True)
    monkeypatch.setattr(pass_mod, "verify_passphrase", lambda text: False)

    orch = _make_orch("shutdown_friday", {}, RiskTier.RED, critical=True)
    task = orch.run("shut down")
    task = orch.resume_with_voice(task.id, "yes, confirm", audio_path="fake.wav")
    task = orch.resume_with_voice(task.id, "wrong phrase", audio_path=None)
    assert task.state == TaskState.BLOCKED
