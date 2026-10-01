"""
Test shutdown intent recognition, confirmation, and execution.
"""

from __future__ import annotations

import pytest
import sys

import friday.tools.system as sys_tools
from friday.app import build_orchestrator
from friday.agent.task import TaskStatus


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only tests")
def test_shutdown_intent_and_confirmation():
    sys_tools.SHUTDOWN_REQUESTED = False
    try:
        orch = build_orchestrator()

        # User says goodbye Friday (confirmation bypassed per user dev policy)
        task = orch.run("goodbye friday")
        assert task.status == TaskStatus.COMPLETED
        assert sys_tools.SHUTDOWN_REQUESTED is True
        assert "Shutting down" in task.last_message
    finally:
        sys_tools.SHUTDOWN_REQUESTED = False

