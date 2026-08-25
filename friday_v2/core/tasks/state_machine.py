"""
core/tasks/state_machine.py

WHAT THIS IS FOR:
Gives every user request an explicit lifecycle instead of the
orchestrator just "doing stuff" and hoping. This is what makes
Principle C (observe -> decide -> act -> observe -> verify) a real,
inspectable state trail rather than a vibe.

STATES:
  PENDING       -> just created
  PLANNING      -> model is deciding what to do
  AWAITING_CONFIRMATION -> policy engine asked the user to confirm
  EXECUTING     -> a tool is running
  VERIFYING     -> checking the tool's effect, not just its return value
  DONE          -> verified success
  FAILED        -> verification failed or tool errored
  BLOCKED       -> policy engine denied it
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TaskState(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    DONE = "DONE"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


# States a task is allowed to move TO, from each current state.
# Anything not listed here is an illegal transition -> fail closed.
_ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.PENDING: {TaskState.PLANNING},
    TaskState.PLANNING: {TaskState.AWAITING_CONFIRMATION, TaskState.EXECUTING, TaskState.BLOCKED, TaskState.FAILED},
    TaskState.AWAITING_CONFIRMATION: {TaskState.EXECUTING, TaskState.BLOCKED, TaskState.FAILED},
    TaskState.EXECUTING: {TaskState.VERIFYING, TaskState.FAILED},
    TaskState.VERIFYING: {TaskState.DONE, TaskState.FAILED},
    TaskState.DONE: set(),
    TaskState.FAILED: {TaskState.PLANNING},  # allow a retry loop
    TaskState.BLOCKED: set(),
}


@dataclass
class Task:
    goal: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    state: TaskState = TaskState.PENDING
    history: list[tuple[TaskState, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    # Orchestrator-owned, opaque to the state machine on purpose: holds the
    # tool name/args/expiry while AWAITING_CONFIRMATION, and which stage of
    # confirmation it's on (voice / passphrase). The state machine never
    # inspects this - it just carries it between transitions.
    pending: object | None = None
    # Transient prompt for the caller to speak (e.g. "say the passphrase")
    # that does NOT itself represent a state transition.
    last_message: str | None = None

    def transition(self, new_state: TaskState, reason: str = "", on_transition=None) -> None:
        allowed = _ALLOWED_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Illegal transition for task {self.id}: {self.state.value} -> {new_state.value}"
            )
        self.history.append((self.state, reason))
        self.state = new_state
        # Optional hook so the interaction server (orb broadcast) can react
        # to every state change without the state machine importing it.
        if on_transition is not None:
            on_transition(new_state)


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def create(self, goal: str) -> Task:
        task = Task(goal=goal)
        self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)
