"""
src/friday/agent/task.py

WHAT THIS IS FOR:
Task abstraction and Step representation with execution budget tracking and observation-aware metadata (blueprint §9.1, §11).
"""

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
    arguments: dict[str, Any] = field(default_factory=dict)
    args: dict[str, Any] | None = None
    authorized: bool = False
    intent: str = ''
    expected_observation: str = ''
    verification_strategy: str = 'auto'
    risk_scope: str = ''
    reversible: bool = True
    retry_policy: str = 'default'
    observation: str = ''
    verified: bool | None = None

    def __post_init__(self):
        if self.args is not None and not self.arguments:
            self.arguments = self.args


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
    started_at: datetime | None = None
    completed_at: datetime | None = None
    pending_auth: Any | None = None
    last_message: str | None = None

    max_steps: int = 20
    steps_used: int = 0
    max_time_seconds: float = 120.0
    plan_version: int = 1

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
        task.started_at = datetime.now()
        self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_all(self) -> list[Task]:
        return list(self._tasks.values())
