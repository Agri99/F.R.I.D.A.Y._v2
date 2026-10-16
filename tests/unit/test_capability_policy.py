"""
tests/unit/test_capability_policy.py

Unit tests for capability scopes and policy engine tier evaluation.
"""
from __future__ import annotations

from friday.config import Settings
from friday.security.capabilities import CapabilityRegistry, CapabilityScope
from friday.security.policy import PolicyDecision, PolicyEngine, RiskTier


def test_policy_tier_evaluation():
    settings = Settings()
    policy = PolicyEngine(settings)
    assert policy.evaluate("online.search", RiskTier.GREEN).decision == PolicyDecision.ALLOW
    assert (
        policy.evaluate("system.shutdown_friday", RiskTier.RED).decision
        == PolicyDecision.REQUIRE_SECOND_FACTOR
    )


def test_policy_scope_checking():
    registry = CapabilityRegistry(is_online=True)
    registry.enable(CapabilityScope.BROWSER_NAVIGATE)
    assert registry.check_scope(CapabilityScope.BROWSER_NAVIGATE) is True

    # Offline automatically disables online scopes
    registry.set_online_status(False)
    assert registry.check_scope(CapabilityScope.BROWSER_NAVIGATE) is False

    # Local scope remains unaffected
    registry.enable(CapabilityScope.FILESYSTEM_READ)
    assert registry.check_scope(CapabilityScope.FILESYSTEM_READ) is True


def test_policy_fail_closed():
    settings = Settings()
    policy = PolicyEngine(settings)
    result = policy.evaluate("non_existent_unregistered_tool")
    assert result.decision == PolicyDecision.DENY
    assert "fail closed" in result.reason
