"""
tests/integration/test_plan_execute_verify.py

WHAT THIS IS FOR:
Integration test verifying the end-to-end plan -> execute -> observe -> verify loop.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from friday.agent.orchestrator import AgentOrchestrator
from friday.agent.task import TaskStatus, Step
from friday.config import Settings
from friday.models.router import ModelRouter
from friday.security.policy import PolicyEngine
from friday.tools.registry import ToolRegistry


def test_plan_execute_verify_lifecycle():
    settings = Settings()
    router = ModelRouter(settings)
    policy = PolicyEngine(settings)
    tools = ToolRegistry()

    from friday.tools.system import register_all_tools
    register_all_tools(tools)


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

