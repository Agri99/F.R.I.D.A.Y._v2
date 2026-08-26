from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    RECOVERING = "RECOVERING"
    CANCELLED = "CANCELLED"


@dataclass
class Step:
    """A discrete unit of work within a larger task plan."""
    action: str
    args: dict[str, Any] = field(default_factory=dict)
    expected_outcome: str = ""
    actual_outcome: str | None = None
    verification_result: bool | None = None
    authorized: bool = False



@dataclass
class Task:
    """The central representation of a user goal and its execution trajectory."""
    goal: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: TaskStatus = TaskStatus.PENDING
    plan: list[Step] = field(default_factory=list)
    current_step_index: int = -1
    observations: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    pending_auth: Any | None = None
    last_message: str | None = None

    def get_current_step(self) -> Step | None:
        if 0 <= self.current_step_index < len(self.plan):
            return self.plan[self.current_step_index]
        return None

    @property
    def history(self) -> list[tuple[TaskStatus, str]]:
        return [(t["to"], t.get("reason", "")) for t in self.trajectory]


class TaskManager:
    """Manages the creation and lookup of tasks."""
    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def create(self, goal: str) -> Task:
        task = Task(goal=goal)
        self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_all(self) -> list[Task]:
        return list(self._tasks.values())

