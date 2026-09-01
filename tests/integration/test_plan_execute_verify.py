"""
tests/integration/test_plan_execute_verify.py

WHAT THIS IS FOR:
Integration test verifying the end-to-end plan -> execute -> observe -> verify loop.
"""

from __future__ import annotations

from friday.agent.orchestrator import AgentOrchestrator
from friday.agent.task import TaskStatus
from friday.config import Settings
from friday.models.router import ModelRouter
from friday.security.policy import PolicyEngine
from friday.tools.registry import ToolRegistry


def test_plan_execute_verify_lifecycle(monkeypatch):
    settings = Settings()
    router = ModelRouter(settings)
    policy = PolicyEngine(settings)
    tools = ToolRegistry()

    from friday.tools.system import register_all_tools
    register_all_tools(tools)

    # The fastpath "hide yourself" resolves to system.toggle_orb. That tool's
    # honest verification is "the orb is hidden" - which cannot succeed when no
    # orb window is connected. Stub the orb so the loop can verify a real,
    # achieved state instead of reporting a false success.
    monkeypatch.setattr(
        "friday.ui.orb_server.set_orb_visibility",
        lambda visible: {"status": "ok", "visible": visible},
    )

    orch = AgentOrchestrator(
        settings=settings,
        model_router=router,
        policy_engine=policy,
        tool_registry=tools,
    )

    # Directly run a fastpath or planned task
    task = orch.run("hide yourself")
    assert task.status == TaskStatus.COMPLETED
    assert task.last_message != ""
    assert task.actions and task.actions[-1]["verified"] is True

