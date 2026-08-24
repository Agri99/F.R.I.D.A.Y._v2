"""
core/security/policy.py

WHAT THIS IS FOR:
The gatekeeper (Principle D — separate intelligence from execution).
The LLM PROPOSES a tool call. This engine DECIDES whether it can run,
whether it needs a confirmation, or whether it's blocked outright.
The LLM never gets to skip this step, and a "learned skill" can never
grant itself a lower tier (Principle F).

RISK TIERS (from your v1 design, carried into v2):
  GREEN    - read-only / reversible, auto-approved
  YELLOW   - low-impact write, needs a preview+confirm
  ORANGE   - meaningful/hard-to-reverse action, needs preview+confirm
  RED      - high-impact/irreversible, hard-blocked without a
             second factor (voice+passphrase in your v1 auth design)

FAIL CLOSED (Principle G): any tool not explicitly registered with a
tier gets the config's `default_risk_tier` (RED in default.yaml) —
never assumed safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from config.settings import Settings


class RiskTier(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"                    # run immediately
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"   # show preview, wait for user yes
    REQUIRE_SECOND_FACTOR = "REQUIRE_SECOND_FACTOR"  # voice/passphrase auth needed
    DENY = "DENY"                      # unknown tool / invalid target / stale confirmation


@dataclass
class PolicyResult:
    decision: PolicyDecision
    tier: RiskTier
    reason: str


class PolicyEngine:
    def __init__(self, settings: Settings):
        self._settings = settings.security

    def evaluate(self, tool_name: str, tier: RiskTier | None) -> PolicyResult:
        # Fail closed: no tier info -> treat as the most restrictive default.
        if tier is None:
            tier = RiskTier(self._settings.default_risk_tier)
            reason = f"'{tool_name}' has no declared risk tier — defaulting to {tier.value}"
        else:
            reason = f"'{tool_name}' declared as {tier.value}"

        if tier.value in self._settings.hard_block_without_second_factor:
            return PolicyResult(PolicyDecision.REQUIRE_SECOND_FACTOR, tier, reason)
        if tier.value in self._settings.confirm_required_tiers:
            return PolicyResult(PolicyDecision.REQUIRE_CONFIRMATION, tier, reason)
        if tier.value in self._settings.auto_approve_tiers:
            return PolicyResult(PolicyDecision.ALLOW, tier, reason)

        # Tier exists but isn't sorted into any config bucket -> deny, don't guess.
        return PolicyResult(PolicyDecision.DENY, tier, f"'{tool_name}' tier {tier.value} not classified in policy config")
