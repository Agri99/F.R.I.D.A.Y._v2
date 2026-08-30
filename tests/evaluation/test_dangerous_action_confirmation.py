"""
tests/evaluation/test_dangerous_action_confirmation.py

WHAT THIS IS FOR:
E2E evaluation test for dangerous action confirmation flow.
Verifies that RED actions require passphrase, YELLOW/ORANGE require confirmation,
and that confirmation binds to exact action arguments.
"""

from __future__ import annotations

import time

import pytest

from friday.security.policy import PolicyEngine, PolicyDecision, RiskTier
from friday.security.confirmation import ConfirmationManager
from friday.security.action_request import ActionRequest
from friday.config import Settings


class TestDangerousActionConfirmation:
    @pytest.fixture
    def policy_engine(self):
        settings = Settings()
        return PolicyEngine(settings)

    @pytest.fixture
    def confirmation_mgr(self):
        return ConfirmationManager(ttl_seconds=60)

    def test_green_action_allows_without_confirmation(self, policy_engine):
        """GREEN tier should allow without any confirmation."""
        result = policy_engine.evaluate("online.search", RiskTier.GREEN)
        assert result.decision == PolicyDecision.ALLOW

    def test_yellow_action_requires_confirmation(self, policy_engine):
        """YELLOW tier should require confirmation."""
        result = policy_engine.evaluate("browser.navigate", RiskTier.YELLOW)
        assert result.decision == PolicyDecision.REQUIRE_CONFIRMATION

    def test_red_action_requires_second_factor(self, policy_engine):
        """RED tier requires passphrase / second factor."""
        result = policy_engine.evaluate("filesystem.delete", RiskTier.RED)
        assert result.decision == PolicyDecision.REQUIRE_SECOND_FACTOR

    def test_confirmation_hash_changes_with_args(self, confirmation_mgr):
        """Confirmations must bind to exact action arguments."""
        req1 = ActionRequest(
            task_id="task_a", step_id="step_0",
            capability="system", tool="system.shutdown",
            arguments={"confirm": True},
            target=None,
            risk_tier=RiskTier.RED,
            required_scopes=[], requester="planner", context_source="agent",
            timestamp=None
        )
        req2 = ActionRequest(
            task_id="task_a", step_id="step_0",
            capability="system", tool="system.shutdown",
            arguments={"confirm": False},
            target=None,
            risk_tier=RiskTier.RED,
            required_scopes=[], requester="planner", context_source="agent",
            timestamp=None
        )

        hash1 = confirmation_mgr.create_pending_action(
            tool=req1.tool, arguments=req1.arguments, risk=req1.risk_tier
        ).get_hash()
        hash2 = confirmation_mgr.create_pending_action(
            tool=req2.tool, arguments=req2.arguments, risk=req2.risk_tier
        ).get_hash()

        assert hash1 != hash2, "Confirmation hash must differ for different arguments"

    def test_expired_confirmation_rejected(self, confirmation_mgr):
        """Expired confirmations must be rejected."""
        action = confirmation_mgr.create_pending_action(
            tool="gmail.send",
            arguments={"to": "test@example.com"},
            risk=RiskTier.ORANGE,
        )

        # Set expiry to past
        action.expires_at = time.time() - 1
        retrieved = confirmation_mgr.get_action(action.id)
        assert retrieved is None, "Expired confirmation should return None"

    def test_expired_confirmation_returns_none(self, confirmation_mgr):
        """Expired confirmation should return None when retrieved."""
        action = confirmation_mgr.create_pending_action(
            tool="test.tool",
            arguments={},
            risk=RiskTier.YELLOW,
        )
        action.expires_at = time.time() - 5
        assert confirmation_mgr.get_action(action.id) is None

    def test_valid_confirmation_retrievable(self, confirmation_mgr):
        """Non-expired confirmation should be retrievable."""
        action = confirmation_mgr.create_pending_action(
            tool="test.tool",
            arguments={"param": "value"},
            risk=RiskTier.YELLOW,
        )
        retrieved = confirmation_mgr.get_action(action.id)
        assert retrieved is not None
        assert retrieved.tool == "test.tool"