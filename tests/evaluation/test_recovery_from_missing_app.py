"""
tests/evaluation/test_recovery_from_missing_app.py

WHAT THIS IS FOR:
E2E evaluation test for recovery from a missing application.
"""

from __future__ import annotations

import pytest

from friday.agent.recovery import RecoveryManager, FailureCategory, RecoveryStrategy
from friday.agent.task import Task, Step


class TestRecoveryFromMissingApp:
    @pytest.fixture
    def recovery(self):
        return RecoveryManager(max_attempts=3)

    def test_missing_application_classified(self, recovery):
        """Missing application errors should be classified correctly."""
        category = recovery.classify("notepad.exe not found", {})
        assert category == FailureCategory.TARGET_NOT_FOUND

    def test_missing_app_triggers_replan(self, recovery):
        """Recovery from missing app should trigger re-resolve target then replan."""
        task = Task(goal="Open VS Code and edit file")
        step = Step(action="applications.open", arguments={"app_id": "vscode"})

        category = recovery.classify("No application found with ID vscode", {})
        action = recovery.recover(task, step, category)

        assert action.category == FailureCategory.TARGET_NOT_FOUND
        # TARGET_NOT_FOUND triggers RE_RESOLVE_TARGET first
        assert action.strategy == RecoveryStrategy.RE_RESOLVE_TARGET

    def test_model_unavailable_classified(self, recovery):
        category = recovery.classify("model service unavailable", {})
        assert category == FailureCategory.MODEL_UNAVAILABLE

    def test_model_unavailable_triggers_replan(self, recovery):
        task = Task(goal="Complex reasoning task")
        step = Step(action="model.reasoning", arguments={})
        category = recovery.classify("model service unavailable", {})
        action = recovery.recover(task, step, category)
        assert action.strategy == RecoveryStrategy.REPLAN

    def test_network_failure_classified(self, recovery):
        category = recovery.classify("Connection refused", {})
        assert category == FailureCategory.NETWORK_UNAVAILABLE

    def test_network_failure_triggers_replan(self, recovery):
        task = Task(goal="Search web")
        step = Step(action="online.search", arguments={"query": "test"})
        category = recovery.classify("offline", {})
        action = recovery.recover(task, step, category)
        assert action.strategy == RecoveryStrategy.REPLAN

    def test_permission_denied_asks_user(self, recovery):
        task = Task(goal="Send email")
        step = Step(action="gmail.send", arguments={})
        category = recovery.classify("access denied", {})
        action = recovery.recover(task, step, category)
        assert action.strategy == RecoveryStrategy.ASK_USER

    def test_invalid_argument_repair(self, recovery):
        task = Task(goal="Write file")
        step = Step(action="filesystem.write", arguments={})
        category = recovery.classify("missing argument: path", {})
        action = recovery.recover(task, step, category)
        assert action.strategy == RecoveryStrategy.REPAIR_INPUT

    def test_max_retries_exhausted_stops_safely(self, recovery):
        """After max retries, recovery must stop safely."""
        task = Task(goal="Flaky task")
        step = Step(action="flaky.tool", arguments={})
        step.retry_count = 3  # exceeds max_attempts

        action = recovery.recover(task, step, FailureCategory.TRANSIENT)
        assert action.strategy == RecoveryStrategy.STOP_SAFELY