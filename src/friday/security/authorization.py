"""
Full authorization chain coordinating policy, capabilities, and confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass

from friday.security.policy import PolicyDecision, PolicyResult
from friday.security.capabilities import CapabilityRegistry


@dataclass
class AuthorizationDecision:
    is_authorized: bool
    reason: str
    requires_confirmation: bool = False
    requires_voice: bool = False
    requires_passphrase: bool = False


def authorize(tool_name: str, tool_args: dict, policy_result: PolicyResult, capability_registry: CapabilityRegistry) -> AuthorizationDecision:
    """
    Evaluates the full authorization chain.
    Chain: scope_allowed -> risk_allowed -> target_valid -> confirmation_required -> voice_auth_required -> passphrase_required -> EXECUTE
    """
    if policy_result.decision == PolicyDecision.DENY:
        return AuthorizationDecision(is_authorized=False, reason=policy_result.reason)
        
    if policy_result.decision == PolicyDecision.REQUIRE_CONFIRMATION:
        return AuthorizationDecision(
            is_authorized=False, 
            reason="Action requires user confirmation.",
            requires_confirmation=True
        )
        
    if policy_result.decision == PolicyDecision.REQUIRE_SECOND_FACTOR:
        return AuthorizationDecision(
            is_authorized=False,
            reason="Action requires second factor authentication (voice + passphrase).",
            requires_confirmation=True,
            requires_voice=True,
            requires_passphrase=True
        )
        
    if policy_result.decision == PolicyDecision.ALLOW:
        return AuthorizationDecision(is_authorized=True, reason="Action allowed by policy.")
        
    return AuthorizationDecision(is_authorized=False, reason="Unknown policy decision.")
