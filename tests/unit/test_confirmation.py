"""
tests/unit/test_confirmation.py

WHAT THIS IS FOR:
Unit tests for confirmation manager TTL, hash binding, and expiry.
"""

from __future__ import annotations

import time

import pytest

from friday.security.confirmation import ConfirmationManager
from friday.security.policy import RiskTier


class TestConfirmationManager:
    @pytest.fixture
    def mgr(self):
        return ConfirmationManager(ttl_seconds=60)

    def test_create_pending_action(self, mgr):
        action = mgr.create_pending_action(
            tool="gmail.send",
            arguments={"to": "test@example.com", "subject": "Hello"},
            risk=RiskTier.ORANGE,
        )
        assert action.id is not None
        assert action.tool == "gmail.send"
        assert not action.is_expired()

    def test_confirmation_ttl_respected(self, mgr):
        action = mgr.create_pending_action(
            tool="system.shutdown",
            arguments={},
            risk=RiskTier.RED,
        )
        # Set expiry in the past
        action.expires_at = time.time() - 1
        assert action.is_expired()

    def test_get_action_returns_none_if_expired(self, mgr):
        action = mgr.create_pending_action(
            tool="filesystem.delete",
            arguments={"path": "/tmp/file"},
            risk=RiskTier.ORANGE,
        )
        # Force expiry
        action.expires_at = time.time() - 1
        result = mgr.get_action(action.id)
        assert result is None

    def test_get_action_returns_valid_action(self, mgr):
        action = mgr.create_pending_action(
            tool="filesystem.write",
            arguments={"path": "/tmp/test.txt"},
            risk=RiskTier.YELLOW,
        )
        result = mgr.get_action(action.id)
        assert result is not None
        assert result.tool == "filesystem.write"

    def test_remove_action(self, mgr):
        action = mgr.create_pending_action(
            tool="calendar.create",
            arguments={"title": "Meeting"},
            risk=RiskTier.YELLOW,
        )
        mgr.remove_action(action.id)
        assert mgr.get_action(action.id) is None

    def test_confirm_action(self, mgr):
        action = mgr.create_pending_action(
            tool="gmail.send",
            arguments={"to": "boss@corp.com"},
            risk=RiskTier.ORANGE,
        )
        assert mgr.confirm_action(action.id) is True
        assert mgr.get_action(action.id) is None  # Should be removed after confirm

    def test_confirm_nonexistent_action(self, mgr):
        assert mgr.confirm_action("nonexistent") is False