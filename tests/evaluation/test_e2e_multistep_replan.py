"""
tests/evaluation/test_e2e_multistep_replan.py

WHAT THIS IS FOR:
E2E evaluation test for multi-step plan with replan on observation change.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from friday.agent.task import Task, Step
from friday.agent.planner import Planner


class TestE2EMultistepReplan:
    def test_planner_replan_increments_version(self):
        """Replan should increment plan_version."""
        planner = Planner()
        task = Task(goal="Test replan")
        task.plan_version = 1

        # Mock the model to return no tool calls
        mock_router = MagicMock()
        mock_router.get.return_value = None

        new_steps = planner.replan(task, [{"step": "web.search", "observation": "Found link"}])
        assert task.plan_version == 2
        assert isinstance(new_steps, list)

    def test_observation_triggers_replan(self):
        """When observation doesn't match expected, replan should be invoked."""
        from friday.agent.evaluator import Evaluator, EvaluationResult
        from friday.agent.executor import ExecutionResult

        evaluator = Evaluator()
        task = Task(goal="Test")
        step = Step(action="search", arguments={}, expected_observation="Results found")

        exec_result = ExecutionResult(
            result=None,
            observation="Port 8000 already in use",
            verification_passed=False,
            error="port in use"
        )

        eval_result = evaluator.evaluate(task, step, exec_result, None)

        assert eval_result.passed is False
        assert eval_result.needs_replan is True

    def test_recovery_action_retry(self):
        """Transient failures should trigger wait-and-retry strategy."""
        from friday.agent.recovery import RecoveryManager, FailureCategory

        recovery = RecoveryManager()
        task = Task(goal="Test")
        step = Step(action="online.search", arguments={})

        category = recovery.classify("Connection timeout", {})
        assert category == FailureCategory.TRANSIENT

        action = recovery.recover(task, step, category)
        assert action.strategy.value == "WAIT_AND_RETRY"

    def test_recovery_stale_target_triggers_replan(self):
        """Stale target errors should trigger re-resolve target then replan."""
        from friday.agent.recovery import RecoveryManager, FailureCategory

        recovery = RecoveryManager()
        task = Task(goal="Click Save")
        step = Step(action="computer.click", arguments={})

        category = recovery.classify("Element not found", {})
        assert category == FailureCategory.TARGET_NOT_FOUND

        action = recovery.recover(task, step, category)
        assert action.strategy.value == "RE_RESOLVE_TARGET"

    def test_recovery_network_unavailable_triggers_replan(self):
        """Network failures should trigger replan to offline path."""
        from friday.agent.recovery import RecoveryManager, FailureCategory

        recovery = RecoveryManager()
        task = Task(goal="Search web")
        step = Step(action="online.search", arguments={})

        category = recovery.classify("offline", {})
        assert category == FailureCategory.NETWORK_UNAVAILABLE

        action = recovery.recover(task, step, category)
        assert action.strategy.value == "REPLAN"