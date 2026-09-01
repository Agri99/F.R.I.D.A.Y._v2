"""Trusted-core plugin capability validation."""
from __future__ import annotations

from dataclasses import dataclass

from friday.plugins.manifest import PluginManifest


PROTECTED_CAPABILITIES = frozenset({
    "security.modify",
    "secrets.read",
    "audit.modify",
    "plugin.trust.modify",
    "resource_guard.modify",
    "core.modify",
    "terminal.host.unrestricted",
})


@dataclass(frozen=True)
class TrustDecision:
    approved: bool
    reason: str
    granted_capabilities: frozenset[str] = frozenset()


class PluginTrustValidator:
    def __init__(self, allowlist: set[str] | frozenset[str]) -> None:
        self.allowlist = frozenset(allowlist)

    def validate(self, manifest: PluginManifest) -> TrustDecision:
        requested = frozenset(manifest.capabilities)
        protected = requested & PROTECTED_CAPABILITIES
        if protected:
            return TrustDecision(False, f"Protected capabilities requested: {sorted(protected)}")
        denied = requested - self.allowlist
        if denied:
            return TrustDecision(False, f"Capabilities not approved: {sorted(denied)}")
        if manifest.risk == "RED":
            return TrustDecision(False, "RED-risk plugins require explicit external approval")
        return TrustDecision(True, "Plugin capabilities approved", requested)
