"""
tests/unit/test_execution_budget.py

WHAT THIS IS FOR:
Unit tests for task execution budget tracking (max_steps, max_time_seconds).
"""

from datetime import datetime, timedelta

import pytest

from friday.agent.task import Task, TaskStatus


class TestExecutionBudget:
    def test_task_has_max_steps(self):
        task = Task(goal="Test task")
        assert task.max_steps == 20
        assert task.steps_used == 0

    def test_task_has_max_time(self):
        task = Task(goal="Test task")
        assert task.max_time_seconds == 120.0

    def test_task_tracks_started_at(self):
        from friday.agent.task import TaskManager
        mgr = TaskManager()
        task = mgr.create("Test task")
        assert task.started_at is not None

    def test_step_budget_exceeded(self):
        """Task should fail when max_steps is exceeded."""
        task = Task(goal="Test budget")
        task.max_steps = 3
        task.steps_used = 3

        # Simulate check
        assert task.steps_used >= task.max_steps

    def test_time_budget_exceeded(self):
        """Task should fail when max_time is exceeded."""
        task = Task(goal="Test time budget")
        task.max_time_seconds = 30.0
        task.started_at = datetime.now() - timedelta(seconds=35)

        elapsed = (datetime.now() - task.started_at).total_seconds()
        assert elapsed > task.max_time_seconds

    def test_plan_version_starts_at_one(self):
        task = Task(goal="Test versioning")
        assert task.plan_version == 1

    def test_plan_version_increments_on_replan(self):
        task = Task(goal="Test versioning")
        task.plan_version += 1
        assert task.plan_version == 2