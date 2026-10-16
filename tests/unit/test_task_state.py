"""
tests/unit/test_task_state.py

Unit tests for TaskStateMachine: transitions, invariants, and trajectory tracking.
"""
from __future__ import annotations

import pytest

from friday.agent.state import TaskStateMachine
from friday.agent.task import Task, TaskStatus


def test_task_state_valid_transitions():
    sm = TaskStateMachine()
    task = Task(goal="Clean codebase")
    assert task.status == TaskStatus.PENDING

    sm.transition(task, TaskStatus.PLANNING, reason="Creating plan")
    assert task.status == TaskStatus.PLANNING

    sm.transition(task, TaskStatus.EXECUTING, reason="Executing steps")
    assert task.status == TaskStatus.EXECUTING

    sm.transition(task, TaskStatus.VERIFYING, reason="Verifying result")
    assert task.status == TaskStatus.VERIFYING

    sm.transition(task, TaskStatus.COMPLETED, reason="Done")
    assert task.status == TaskStatus.COMPLETED
    assert task.completed_at is not None


def test_task_state_illegal_transitions():
    sm = TaskStateMachine()
    task = Task(goal="Clean codebase")

    # Direct illegal transition from PENDING to COMPLETED
    with pytest.raises(ValueError, match="Illegal transition"):
        sm.transition(task, TaskStatus.COMPLETED)


def test_task_state_history_tracking():
    transitions = []
    sm = TaskStateMachine(on_transition=lambda t, s, r: transitions.append((s, r)))
    task = Task(goal="Track history")

    sm.transition(task, TaskStatus.PLANNING, reason="Start planning")
    sm.transition(task, TaskStatus.EXECUTING, reason="Start execution")

    assert len(task.trajectory) == 2
    assert task.trajectory[0]["from"] == TaskStatus.PENDING
    assert task.trajectory[0]["to"] == TaskStatus.PLANNING
    assert len(transitions) == 2
