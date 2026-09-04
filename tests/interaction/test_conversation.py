"""
tests/interaction/test_conversation.py

WHAT THIS IS FOR:
Unit tests for ConversationManager (Runbook §21).
"""

from __future__ import annotations

import pytest

from friday.interaction.conversation import (
    ConnectivityState,
    ConversationManager,
    ModePreference,
)


class TestConversationManager:
    def test_begin_turn_allocates_id(self):
        cm = ConversationManager()
        snap = cm.snapshot()
        assert snap.active_turn_id is None
        turn_id = cm.begin_turn()
        snap = cm.snapshot()
        assert snap.active_turn_id == turn_id
        assert snap.listening is True
        assert snap.interrupted is False

    def test_end_turn_records_assistant(self):
        cm = ConversationManager()
        cm.begin_turn()
        cm.end_turn(assistant_text="Hello!")
        snap = cm.snapshot()
        assert snap.last_assistant_text == "Hello!"
        assert snap.listening is False

    def test_pending_authorization_sets_active_task(self):
        cm = ConversationManager()
        cm.begin_turn()
        cm.set_pending_authorization(True, task_id="task-42")
        snap = cm.snapshot()
        assert snap.pending_authorization is True
        assert snap.active_task_id == "task-42"

        cm.set_pending_authorization(False)
        snap = cm.snapshot()
        assert snap.pending_authorization is False
        assert snap.active_task_id is None

    def test_interrupt_sets_speaking_false(self):
        cm = ConversationManager()
        cm.set_speaking(True)
        cm.interrupt(reason="barge_in")
        snap = cm.snapshot()
        assert snap.speaking is False
        assert snap.interrupted is True
        assert snap.listening is True

    def test_followup_window_change(self):
        cm = ConversationManager(followup_window_seconds=2.0)
        assert cm.followup_window_seconds == 2.0
        cm.set_followup_window_seconds(7.5)
        assert cm.followup_window_seconds == 7.5

    def test_mode_and_connectivity(self):
        cm = ConversationManager(mode_preference=ModePreference.FAST, connectivity=ConnectivityState.OFFLINE)
        snap = cm.snapshot()
        assert snap.mode_preference == ModePreference.FAST
        assert snap.connectivity == ConnectivityState.OFFLINE

    def test_subscriber_receives_snapshot(self):
        cm = ConversationManager()
        received: list = []
        cm.subscribe(lambda s: received.append(s))
        cm.begin_turn()
        cm.set_speaking(True)
        assert len(received) >= 2
        assert received[-1].speaking is True

    def test_close_followup_clears_task(self):
        cm = ConversationManager()
        cm.begin_turn()
        cm.set_pending_authorization(True, task_id="x")
        cm.close_followup()
        snap = cm.snapshot()
        assert snap.active_task_id is None
        assert snap.followup_open is False

    def test_snapshot_is_consistent(self):
        cm = ConversationManager()
        cm.begin_turn()
        snap = cm.snapshot()
        assert snap.conversation_id == cm.conversation_id
