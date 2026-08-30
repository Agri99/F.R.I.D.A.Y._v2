from __future__ import annotations

from typing import Callable
from .task import Task, TaskStatus

_ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.PLANNING, TaskStatus.AWAITING_AUTHORIZATION, TaskStatus.EXECUTING, TaskStatus.CANCELLED},
    TaskStatus.PLANNING: {TaskStatus.AWAITING_AUTHORIZATION, TaskStatus.EXECUTING, TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.CANCELLED},

    TaskStatus.AWAITING_AUTHORIZATION: {TaskStatus.AWAITING_AUTHORIZATION, TaskStatus.EXECUTING, TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.EXECUTING: {TaskStatus.VERIFYING, TaskStatus.FAILED, TaskStatus.CANCELLED},

    TaskStatus.VERIFYING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.RECOVERING, TaskStatus.EXECUTING, TaskStatus.AWAITING_AUTHORIZATION},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: {TaskStatus.RECOVERING, TaskStatus.PLANNING},
    TaskStatus.BLOCKED: set(),
    TaskStatus.RECOVERING: {TaskStatus.EXECUTING, TaskStatus.PLANNING, TaskStatus.FAILED, TaskStatus.COMPLETED},
    TaskStatus.CANCELLED: set(),
}

class TaskStateMachine:
    """Enforces valid transitions for tasks, failing closed on invalid state changes."""
    def __init__(self, on_transition: Callable[[Task, TaskStatus, str], None] | None = None):
        self.on_transition = on_transition

    def transition(self, task: Task, new_status: TaskStatus, reason: str = "") -> None:
        """Transitions a task to a new state if allowed."""
        allowed = _ALLOWED_TRANSITIONS.get(task.status, set())
        if new_status not in allowed:
            raise ValueError(f"Illegal transition for task {task.id}: {task.status.value} -> {new_status.value}")
        
        task.trajectory.append({"from": task.status, "to": new_status, "reason": reason})
        task.status = new_status
        
        if new_status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED}:
            from datetime import datetime
            task.completed_at = datetime.now()

        if self.on_transition:
            self.on_transition(task, new_status, reason)
