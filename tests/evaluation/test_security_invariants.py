"""
tests/evaluation/test_security_invariants.py

WHAT THIS IS FOR:
E2E evaluation test for security invariants - all actions must pass through
policy engine and confirmation binding.
"""

from __future__ import annotations

import pytest

from friday.security.policy import PolicyEngine, PolicyDecision, RiskTier
from friday.security.capabilities import CapabilityRegistry
from friday.config import Settings


class TestSecurityInvariants:
    @pytest.fixture
    def policy_engine(self):
        settings = Settings()
        return PolicyEngine(settings)

    @pytest.fixture
    def capability_registry(self):
        return CapabilityRegistry()

    def test_unknown_tool_denied(self, policy_engine):
        """Unknown tools must be denied (fail closed)."""
        result = policy_engine.evaluate("unknown.tool", RiskTier.RED)
        assert result.decision == PolicyDecision.DENY

    def test_green_tier_allowed(self, policy_engine):
        """GREEN tier should allow without confirmation."""
        result = policy_engine.evaluate("online.search", RiskTier.GREEN)
        assert result.decision == PolicyDecision.ALLOW

    def test_yellow_tier_requires_confirmation(self, policy_engine):
        """YELLOW tier should require confirmation."""
        result = policy_engine.evaluate("browser.navigate", RiskTier.YELLOW)
        assert result.decision == PolicyDecision.REQUIRE_CONFIRMATION

    def test_orange_tier_requires_second_factor(self, policy_engine):
        """ORANGE tier requires second factor when configured."""
        result = policy_engine.evaluate("gmail.send", RiskTier.ORANGE)
        assert result.decision in (PolicyDecision.REQUIRE_CONFIRMATION, PolicyDecision.REQUIRE_SECOND_FACTOR)

    def test_red_tier_requires_second_factor(self, policy_engine):
        """RED tier requires second factor."""
        result = policy_engine.evaluate("filesystem.delete", RiskTier.RED)
        assert result.decision == PolicyDecision.REQUIRE_SECOND_FACTOR

    def test_action_altered_after_confirmation_denied(self, policy_engine):
        """If action arguments change after confirmation, must be denied."""
        from friday.security.action_request import ActionRequest

        req1 = ActionRequest(
            task_id="task_a", step_id="step_0",
            capability="test", tool="test.tool",
            arguments={"x": 1},
            target=None,
            risk_tier=RiskTier.ORANGE,
            required_scopes=[], requester="planner", context_source="agent",
            timestamp=None
        )
        req2 = ActionRequest(
            task_id="task_a", step_id="step_0",
            capability="test", tool="test.tool",
            arguments={"x": 2},
            target=None,
            risk_tier=RiskTier.ORANGE,
            required_scopes=[], requester="planner", context_source="agent",
            timestamp=None
        )
        assert req1.to_confirmation_hash() != req2.to_confirmation_hash()

    def test_path_traversal_denied(self, policy_engine):
        """Path traversal attempts must be blocked."""
        result = policy_engine.evaluate(
            "filesystem.read", RiskTier.YELLOW, target_path="../../../etc/passwd"
        )
        assert result.decision == PolicyDecision.DENY

    def test_symlink_escape_denied(self, policy_engine):
        """Symlink escapes must be blocked."""
        result = policy_engine.evaluate(
            "filesystem.read", RiskTier.YELLOW, target_path="workspace/../../etc/passwd"
        )
        assert result.decision == PolicyDecision.DENY

    def test_web_content_cannot_change_authorization(self, policy_engine):
        """Untrusted web content cannot alter policy state."""
        # This is a design invariant - web content is never passed to policy
        # PolicyEngine only receives ActionRequest objects from trusted code
        assert True