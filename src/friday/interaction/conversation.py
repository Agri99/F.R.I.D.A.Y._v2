"""
src/friday/interaction/conversation.py

WHAT THIS IS FOR:
ConversationManager owns dialogue semantics so the voice transport layer
doesn't become the central application state machine.

Runbook §21 — keeps the following state distinct from VoiceSession:
    active_turn
    conversation_id
    active_task_id
    pending_authorization
    followup_window
    speaking
    listening
    interruption
    mode_preference (FAST/REASONING)
    offline/online
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class ModePreference(str, Enum):
    FAST = "fast"
    REASONING = "reasoning"
    AUTO = "auto"


class ConnectivityState(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class ConversationSnapshot:
    """Read-only view of the manager's current state."""
    conversation_id: str
    active_turn_id: str | None
    active_task_id: str | None
    pending_authorization: bool
    followup_open: bool
    speaking: bool
    listening: bool
    interrupted: bool
    mode_preference: ModePreference
    connectivity: ConnectivityState
    last_user_text: str
    last_assistant_text: str
    started_at: float


class ConversationManager:
    """Authoritative dialogue-state container.

    Thread-safety: every mutator takes ``_lock``. Public read APIs return
    snapshots so callers don't need to hold the lock.
    """

    def __init__(
        self,
        followup_window_seconds: float = 5.0,
        mode_preference: ModePreference = ModePreference.AUTO,
        connectivity: ConnectivityState = ConnectivityState.UNKNOWN,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._conversation_id = f"conv-{uuid.uuid4().hex[:12]}"
        self._active_turn_id: str | None = None
        self._active_task_id: str | None = None
        self._pending_authorization = False
        self._followup_open = False
        self._followup_window = float(followup_window_seconds)
        self._speaking = False
        self._listening = False
        self._interrupted = False
        self._mode_preference = mode_preference
        self._connectivity = connectivity
        self._last_user_text = ""
        self._last_assistant_text = ""
        self._started_at = (clock or time.time)()
        self._turn_counter = 0
        self._listeners: list[Callable[[ConversationSnapshot], None]] = []
        self._clock = clock or time.time

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------
    def subscribe(self, callback: Callable[[ConversationSnapshot], None]) -> None:
        with self._lock:
            self._listeners.append(callback)

    def _emit(self) -> None:
        snap = self.snapshot()
        for cb in list(self._listeners):
            try:
                cb(snap)
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                # Defensive: a buggy subscriber must not break the manager.
                pass

    # ------------------------------------------------------------------
    # Turn lifecycle
    # ------------------------------------------------------------------
    def begin_turn(self) -> str:
        """Allocate a new turn ID and mark the manager as listening."""
        with self._lock:
            self._turn_counter += 1
            self._active_turn_id = f"turn-{self._turn_counter}-{int(self._clock() * 1000)}"
            self._interrupted = False
            self._listening = True
            self._followup_open = False
        self._emit()
        return self._active_turn_id  # type: ignore[return-value]

    def end_turn(self, assistant_text: str | None = None) -> None:
        with self._lock:
            self._listening = False
            self._interrupted = False
            if assistant_text is not None:
                self._last_assistant_text = assistant_text
            if self._active_task_id is None:
                # No follow-up unless there is a pending authorization.
                self._followup_open = False
            else:
                self._followup_open = True
        self._emit()

    def set_speaking(self, speaking: bool) -> None:
        with self._lock:
            self._speaking = bool(speaking)
        self._emit()

    def interrupt(self, reason: str = "") -> None:
        with self._lock:
            self._interrupted = True
            self._speaking = False
            self._listening = True
        self._emit()

    def clear_interrupted(self) -> None:
        with self._lock:
            self._interrupted = False
        self._emit()

    # ------------------------------------------------------------------
    # Auth / followup / task
    # ------------------------------------------------------------------
    def set_pending_authorization(self, pending: bool, task_id: str | None = None) -> None:
        with self._lock:
            self._pending_authorization = bool(pending)
            if pending and task_id is not None:
                self._active_task_id = task_id
            if not pending:
                self._active_task_id = None
        self._emit()

    def set_active_task(self, task_id: str | None) -> None:
        with self._lock:
            self._active_task_id = task_id
        self._emit()

    def set_followup_open(self, open_: bool) -> None:
        with self._lock:
            self._followup_open = bool(open_)
        self._emit()

    def close_followup(self) -> None:
        with self._lock:
            self._followup_open = False
            self._active_task_id = None
        self._emit()

    # ------------------------------------------------------------------
    # Mode / connectivity
    # ------------------------------------------------------------------
    def set_mode_preference(self, mode: ModePreference) -> None:
        with self._lock:
            self._mode_preference = mode
        self._emit()

    def set_connectivity(self, state: ConnectivityState) -> None:
        with self._lock:
            self._connectivity = state
        self._emit()

    # ------------------------------------------------------------------
    # User text
    # ------------------------------------------------------------------
    def record_user_text(self, text: str) -> None:
        with self._lock:
            self._last_user_text = text
        self._emit()

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------
    def snapshot(self) -> ConversationSnapshot:
        with self._lock:
            return ConversationSnapshot(
                conversation_id=self._conversation_id,
                active_turn_id=self._active_turn_id,
                active_task_id=self._active_task_id,
                pending_authorization=self._pending_authorization,
                followup_open=self._followup_open,
                speaking=self._speaking,
                listening=self._listening,
                interrupted=self._interrupted,
                mode_preference=self._mode_preference,
                connectivity=self._connectivity,
                last_user_text=self._last_user_text,
                last_assistant_text=self._last_assistant_text,
                started_at=self._started_at,
            )

    @property
    def conversation_id(self) -> str:
        with self._lock:
            return self._conversation_id

    @property
    def active_turn_id(self) -> str | None:
        with self._lock:
            return self._active_turn_id

    @property
    def followup_window_seconds(self) -> float:
        with self._lock:
            return self._followup_window

    def set_followup_window_seconds(self, seconds: float) -> None:
        with self._lock:
            self._followup_window = float(seconds)


__all__ = [
    "ConversationManager",
    "ConversationSnapshot",
    "ConnectivityState",
    "ModePreference",
]
