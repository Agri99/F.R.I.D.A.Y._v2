"""
Policy engine for evaluating risk and capabilities (Principle D - separate intelligence from execution).
Determines whether an action is permitted based on risk tiers and capabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from friday.config import Settings
from friday.security.capabilities import CapabilityScope, CapabilityRegistry
from friday.security.sandbox import PathValidator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from friday.security.action_request import ActionRequest


class RiskTier(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    ORANGE = "ORANGE"
    RED = "RED"


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    REQUIRE_SECOND_FACTOR = "REQUIRE_SECOND_FACTOR"
    DENY = "DENY"


@dataclass
class PolicyResult:
    decision: PolicyDecision
    tier: RiskTier
    reason: str
    required_scopes: list[CapabilityScope]
    request: ActionRequest | None = None


class PolicyEngine:
    def __init__(self, settings: Settings, capability_registry: CapabilityRegistry | None = None, path_validator: PathValidator | None = None):
        self._settings = settings.security
        self._capability_registry = capability_registry or CapabilityRegistry()
        self._path_validator = path_validator or PathValidator(settings.paths.workspace_dir)

    def evaluate_request(self, request: ActionRequest) -> PolicyResult:
        result = self.evaluate(
            tool_name=request.tool,
            tier=request.risk_tier,
            required_scopes=request.required_scopes,
            target_path=request.target
        )
        result.request = request
        return result

    def evaluate(self, tool_name: str, tier: RiskTier | None = None, required_scopes: list[CapabilityScope] | None = None, target_path: str | Path | None = None) -> PolicyResult:
        required_scopes = required_scopes or []
        # Check capability scopes first
        for scope in required_scopes:
            if not self._capability_registry.check_scope(scope):
                return PolicyResult(PolicyDecision.DENY, RiskTier.RED, f"Required capability scope '{scope.value}' is disabled", required_scopes)

        # Normalize tier to RiskTier enum or fail closed
        if tier is None:
            tier = RiskTier(self._settings.default_risk_tier if hasattr(self._settings, 'default_risk_tier') else "RED")
            reason = f"'{tool_name}' has no declared risk tier — defaulting to {tier.value}"
        elif isinstance(tier, str):
            try:
                tier = RiskTier(tier.upper())
                reason = f"'{tool_name}' declared as {tier.value}"
            except ValueError:
                tier = RiskTier.RED
                reason = f"'{tool_name}' has invalid tier '{tier}' — defaulting to RED"
        else:
            reason = f"'{tool_name}' declared as {tier.value}"


        # Optional filesystem sandbox check
        if target_path is not None:
            try:
                allowed_roots = self._settings.allowed_roots if hasattr(self._settings, 'allowed_roots') else []
                self._path_validator.validate_path(target_path, allowed_roots)
            except ValueError as e:
                return PolicyResult(PolicyDecision.DENY, tier, f"Path validation failed: {e}", required_scopes)

        if hasattr(self._settings, 'hard_block_without_second_factor') and tier.value in self._settings.hard_block_without_second_factor:
            return PolicyResult(PolicyDecision.REQUIRE_SECOND_FACTOR, tier, reason, required_scopes)
        if hasattr(self._settings, 'confirm_required_tiers') and tier.value in self._settings.confirm_required_tiers:
            return PolicyResult(PolicyDecision.REQUIRE_CONFIRMATION, tier, reason, required_scopes)
        if hasattr(self._settings, 'auto_approve_tiers') and tier.value in self._settings.auto_approve_tiers:
            return PolicyResult(PolicyDecision.ALLOW, tier, reason, required_scopes)
        
        # Fallback to defaults if settings are not perfectly configured
        if tier == RiskTier.RED:
            return PolicyResult(PolicyDecision.REQUIRE_SECOND_FACTOR, tier, reason, required_scopes)
        if tier in (RiskTier.ORANGE, RiskTier.YELLOW):
            return PolicyResult(PolicyDecision.REQUIRE_CONFIRMATION, tier, reason, required_scopes)
        if tier == RiskTier.GREEN:
            return PolicyResult(PolicyDecision.ALLOW, tier, reason, required_scopes)

        return PolicyResult(PolicyDecision.DENY, tier, f"'{tool_name}' tier {tier.value} not classified in policy config", required_scopes)
