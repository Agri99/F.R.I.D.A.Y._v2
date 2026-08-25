"""
core/interaction/contracts.py

WHAT THIS IS FOR:
The typed messages that cross the process boundary between FRIDAY
Core and the two interaction processes (Section 4: Process B Voice I/O,
Process C Orb UI). This file is the contract - both sides serialize
to/from these shapes, nothing looser than this crosses the wire.

WHY IT'S BUILT THIS WAY:
Section 23 - the voice process sends recognized TEXT + metadata, never raw
audio, and never calls tools itself. Section 24 - the orb is UI-only and has
NO authority to execute tools; OrbCommand is a closed whitelist on
purpose. If it's not in this enum, the orb literally cannot ask for
it, regardless of what a compromised or buggy orb process sends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from core.tasks.state_machine import TaskState


# --- Voice -> Core -------------------------------------------------

@dataclass
class VoiceInput:
    """What Process B (voice) sends to Core. No raw audio crosses this boundary."""
    recognized_text: str
    session_id: str
    audio_path_for_authorization: str | None = None  # for voiceprint 2FA, not general use
    wake_word_meta: dict = field(default_factory=dict)


# --- Core -> Orb (state broadcast) ----------------------------------

class OrbState(str, Enum):
    """Exact list from Section 24 - the only states Core is allowed to publish to the orb."""
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    VERIFYING = "VERIFYING"
    LEARNING = "LEARNING"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


# Maps internal TaskState -> the orb-facing vocabulary. Deliberately
# explicit rather than reusing TaskState directly: the orb's contract
# must not silently change just because someone edits TaskState.
TASK_STATE_TO_ORB_STATE: dict[TaskState, OrbState] = {
    TaskState.PENDING: OrbState.THINKING,
    TaskState.PLANNING: OrbState.PLANNING,
    TaskState.AWAITING_CONFIRMATION: OrbState.WAITING_CONFIRMATION,
    TaskState.EXECUTING: OrbState.EXECUTING,
    TaskState.VERIFYING: OrbState.VERIFYING,
    TaskState.DONE: OrbState.IDLE,
    TaskState.FAILED: OrbState.ERROR,
    TaskState.BLOCKED: OrbState.ERROR,
}


# --- Orb -> Core (commands) -----------------------------------------

class OrbCommand(str, Enum):
    """
    Closed whitelist, Section 24: 'The orb has no authority to execute tools.
    Allowed orb commands are UI-only.' This enum IS the enforcement -
    there is no path for an arbitrary string to become a command.
    """
    SHOW = "show"
    HIDE = "hide"
    MOVE = "move"
    SET_STATE = "set_state"   # orb requesting a re-sync, not setting Core's state
    EXIT_UI = "exit_ui"


@dataclass
class OrbCommandMessage:
    command: OrbCommand
    payload: dict = field(default_factory=dict)  # e.g. {"x": 120, "y": 340} for MOVE
