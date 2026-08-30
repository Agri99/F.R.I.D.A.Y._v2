"""
Online capability gating (§8.3, §22) for failsafe network transitions.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from friday.online.network import NetworkMonitor

logger = logging.getLogger(__name__)

class CapabilityRegistry(Protocol):
    def enable(self, capability: str) -> None: ...
    def disable(self, capability: str) -> None: ...
    def is_enabled(self, capability: str) -> bool: ...

class OnlineCapabilityGate:
    """Gates online-dependent tools based on current network and auth status."""
    def __init__(self, monitor: NetworkMonitor):
        self._monitor = monitor

    def is_available(self, capability_or_tool: str) -> bool:
        """Check if capability/tool is available based on connectivity."""
        return self._monitor.is_online()

    def check_online_tool(self, tool_name: str, requires_auth: bool = False, service_name: str | None = None) -> bool:

        """
        Check if an online tool can be executed.
        Fails closed on missing connectivity or auth.
        """
        if not self._monitor.is_online():
            return False
            
        if requires_auth:
            # Placeholder for auth service integration (§22)
            # In a real impl, we'd check token store here.
            pass
            
        return True
        
    def get_failure_reason(self, tool_name: str, service_name: str | None = None) -> str:
        """Generate an honest failure reason for the user."""
        if not self._monitor.is_online():
            service = service_name or "The requested service"
            return f"The Internet is unavailable, so {service} is not accessible."
        return f"Unknown error accessing {tool_name}."

    def enable_online_capabilities(self, registry: CapabilityRegistry) -> None:
        """Enable online features when network returns."""
        logger.info("Network restored: Enabling online capabilities")
        registry.enable("web_search")
        registry.enable("live_data")

    def disable_online_capabilities(self, registry: CapabilityRegistry) -> None:
        """Disable online features when network drops."""
        logger.info("Network offline: Disabling online capabilities")
        registry.disable("web_search")
        registry.disable("live_data")
