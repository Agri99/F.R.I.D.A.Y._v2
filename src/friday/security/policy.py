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

# Known tools mapping (name -> risk tier)
KNOWN_TOOLS = {
    "online.search": RiskTier.GREEN,
    "online.weather": RiskTier.GREEN,
    "browser.navigate": RiskTier.YELLOW,
    "browser.open": RiskTier.YELLOW,
    "browser.search": RiskTier.GREEN,
    "browser.observe": RiskTier.GREEN,
    "browser.read": RiskTier.GREEN,
    "browser.click": RiskTier.YELLOW,
    "browser.type": RiskTier.YELLOW,
    "browser.submit": RiskTier.ORANGE,
    "browser.upload": RiskTier.RED,
    "gmail.search": RiskTier.GREEN,
    "gmail.read": RiskTier.GREEN,
    "gmail.send": RiskTier.ORANGE,
    "calendar.list": RiskTier.GREEN,
    "calendar.read": RiskTier.GREEN,
    "calendar.create": RiskTier.ORANGE,
    "calendar.update": RiskTier.ORANGE,
    "calendar.delete": RiskTier.ORANGE,
    "filesystem.read": RiskTier.YELLOW,
    "filesystem.write": RiskTier.ORANGE,
    "filesystem.delete": RiskTier.RED,
    "filesystem.list": RiskTier.YELLOW,
    "applications.open": RiskTier.YELLOW,
    "applications.close": RiskTier.YELLOW,
    "system.get_time": RiskTier.GREEN,
    "system.get_status": RiskTier.GREEN,
    "system.lock": RiskTier.ORANGE,
    "system.shutdown_friday": RiskTier.RED,
    "system.shutdown": RiskTier.RED,
    "system.toggle_orb": RiskTier.GREEN,
    "system.remember": RiskTier.GREEN,
    "computer.click": RiskTier.YELLOW,
    "computer.type": RiskTier.YELLOW,
    "computer.press": RiskTier.YELLOW,
    "computer.control_window": RiskTier.YELLOW,
    "computer.capture": RiskTier.YELLOW,
    "computer.describe_screen": RiskTier.YELLOW,
    "computer.read_screen_text": RiskTier.GREEN,
    "computer.scroll": RiskTier.YELLOW,
    "computer.wait": RiskTier.GREEN,
    "computer.active_window": RiskTier.GREEN,
    "computer.control_window": RiskTier.YELLOW,
    "terminal.run_sandbox": RiskTier.GREEN,
    "terminal.run_host": RiskTier.ORANGE,
}

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

        # Check if tool is known
        if tool_name not in KNOWN_TOOLS:
            return PolicyResult(PolicyDecision.DENY, RiskTier.RED, f"Unknown tool '{tool_name}' — fail closed", required_scopes)

        # Check capability scopes first
        for scope in required_scopes:
            if not self._capability_registry.check_scope(scope):
                return PolicyResult(PolicyDecision.DENY, RiskTier.RED, f"Required capability scope '{scope.value}' is disabled", required_scopes)

        # Use known tier if not provided
        if tier is None:
            tier = KNOWN_TOOLS.get(tool_name, RiskTier.RED)
            reason = f"'{tool_name}' default tier: {tier.value}"
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