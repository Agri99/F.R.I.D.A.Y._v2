"""
Test confirmation manager and orchestrator authorization flow.
"""

from __future__ import annotations

import time
from friday.security.confirmation import ConfirmationManager
from friday.security.policy import RiskTier
from friday.agent.task import Task, TaskStatus, Step
from friday.agent.state import TaskStateMachine
from friday.agent.orchestrator import AgentOrchestrator
from friday.config import Settings
from friday.models.router import ModelRouter
from friday.security.policy import PolicyEngine
from friday.security.capabilities import CapabilityRegistry
from friday.tools.registry import ToolRegistry, Tool


def test_confirmation_ttl_expiry():
    mgr = ConfirmationManager(ttl_seconds=1)
    action = mgr.create_pending_action(tool="test_tool", arguments={"k": "v"}, risk=RiskTier.YELLOW)
    assert mgr.get_action(action.id) is not None
    time.sleep(1.1)
    assert mgr.get_action(action.id) is None


def test_confirmation_action_binding():
    mgr = ConfirmationManager(ttl_seconds=60)
    action = mgr.create_pending_action(tool="applications.open", arguments={"app_id": "notepad"}, risk=RiskTier.YELLOW)
    h = action.get_hash()
    assert len(h) == 64
    assert mgr.confirm_action(action.id) is True
    assert mgr.get_action(action.id) is None


def test_confirmation_stage_transitions():
    settings = Settings.load("config/default.yaml")
    tools = ToolRegistry()

    tools.register(Tool(
        name="test_tool_yellow",
        description="A yellow test tool",
        tier="YELLOW",
        capability_scope="system.control",
        input_schema={"type": "object"},
        handler=lambda **kwargs: {"status": "ok"},
    ))

    orch = AgentOrchestrator(
        settings=settings,
        model_router=ModelRouter(settings),
        policy_engine=PolicyEngine(settings),
        tool_registry=tools,
    )

    # Manually run a task with step requiring confirmation
    task = orch.tasks.create("open notepad")
    task.plan = [Step(action="test_tool_yellow", args={})]
    res = orch._execute_plan(task)

    assert res.status == TaskStatus.AWAITING_AUTHORIZATION
    assert res.pending_auth is not None

    # Confirm with "yes"
    res_confirmed = orch.resume_with_voice(res.id, user_text="yes please proceed")
    assert res_confirmed.status == TaskStatus.COMPLETED
    assert res_confirmed.plan[0].authorized is True
