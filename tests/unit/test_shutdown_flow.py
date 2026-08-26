"""
Test shutdown intent recognition, confirmation, and execution.
"""

from __future__ import annotations

import friday.tools.system as sys_tools
from friday.app import build_orchestrator
from friday.agent.task import TaskStatus


def test_shutdown_intent_and_confirmation():
    sys_tools.SHUTDOWN_REQUESTED = False
    orch = build_orchestrator()

    # User says goodbye Friday
    task = orch.run("goodbye friday")
    assert task.status == TaskStatus.AWAITING_AUTHORIZATION
    assert "Do you want me to go off?" in task.last_message

    # User confirms
    res = orch.resume_with_voice(task.id, "yes please")
    assert res.status == TaskStatus.COMPLETED
    assert sys_tools.SHUTDOWN_REQUESTED is True
    assert "Going off now" in res.last_message or "Shutting down" in res.last_message

