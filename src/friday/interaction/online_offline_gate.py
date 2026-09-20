"""
src/friday/interaction/online_offline_gate.py

WHAT THIS IS FOR:
Online/Offline capability gate (Runbook §35 — Phase O1).

Classifies capabilities by their network requirements:
  - LOCAL_ONLY: Works without network (STT, TTS, local LLM)
  - ONLINE_OPTIONAL: Works offline with degraded experience (web search)
  - ONLINE_REQUIRED: Must have network (cloud LLM, Gmail API)

When offline:
  - Don't hang waiting for network
  - Don't invent results
  - Explain limitation
  - Use local fallback if possible
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class NetworkRequirement(str, Enum):
    """Network requirement classification for capabilities."""
    LOCAL_ONLY = "local_only"
    ONLINE_OPTIONAL = "online_optional"
    ONLINE_REQUIRED = "online_required"


@dataclass
class NetworkStatus:
    """Current network status."""
    connected: bool
    last_check: float
    error: str | None = None


class OnlineOfflineGate:
    """Gate that checks network availability before allowing operations.

    Usage:
        gate = OnlineOfflineGate()
        gate.register_capability("web_search", NetworkRequirement.ONLINE_OPTIONAL)
        gate.register_capability("gmail_send", NetworkRequirement.ONLINE_REQUIRED)
        gate.register_capability("stt", NetworkRequirement.LOCAL_ONLY)

        if gate.can_execute("gmail_send"):
            # Safe to proceed
            ...
        else:
            # Network unavailable, explain to user
            ...
    """

    def __init__(
        self,
        check_interval_seconds: float = 30.0,
        timeout_seconds: float = 2.0,
    ) -> None:
        self._check_interval = check_interval_seconds
        self._timeout = timeout_seconds
        self._capabilities: dict[str, NetworkRequirement] = {}
        self._status: NetworkStatus | None = None
        self._lock = threading.Lock()
        self._last_check_time: float = 0.0

        # Pre-register common capabilities
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default capability classifications."""
        defaults = {
            # Voice - all local
            "stt": NetworkRequirement.LOCAL_ONLY,
            "tts": NetworkRequirement.LOCAL_ONLY,
            "wake_word": NetworkRequirement.LOCAL_ONLY,
            "vad": NetworkRequirement.LOCAL_ONLY,

            # Local LLM
            "local_llm": NetworkRequirement.LOCAL_ONLY,
            "ollama": NetworkRequirement.LOCAL_ONLY,

            # Computer use - local
            "computer_control": NetworkRequirement.LOCAL_ONLY,
            "file_operations": NetworkRequirement.LOCAL_ONLY,
            "terminal": NetworkRequirement.LOCAL_ONLY,

            # Browser - local with optional online
            "browser": NetworkRequirement.ONLINE_OPTIONAL,

            # Cloud services
            "cloud_llm": NetworkRequirement.ONLINE_REQUIRED,
            "web_search": NetworkRequirement.ONLINE_OPTIONAL,
            "gmail": NetworkRequirement.ONLINE_REQUIRED,
            "calendar": NetworkRequirement.ONLINE_REQUIRED,
            "weather_api": NetworkRequirement.ONLINE_OPTIONAL,
        }
        for cap, req in defaults.items():
            self._capabilities[cap] = req

    def register_capability(self, name: str, requirement: NetworkRequirement) -> None:
        """Register a capability with its network requirement."""
        with self._lock:
            self._capabilities[name] = requirement

    def check_network(self, force: bool = False) -> NetworkStatus:
        """Check if network is available.

        Args:
            force: Skip cache and check immediately

        Returns:
            NetworkStatus with current connectivity state
        """
        now = time.time()

        with self._lock:
            # Use cached result if recent
            if not force and self._status and (now - self._last_check_time) < self._check_interval:
                return self._status

        # Attempt to connect to a reliable host
        try:
            # Try DNS resolution as connectivity check
            socket.setdefaulttimeout(self._timeout)
            socket.gethostbyname("api.openai.com")
            status = NetworkStatus(connected=True, last_check=now)
        except Exception as e:
            status = NetworkStatus(
                connected=False,
                last_check=now,
                error=str(e),
            )

        with self._lock:
            self._status = status
            self._last_check_time = now

        return status

    def can_execute(self, capability: str) -> bool:
        """Check if a capability can be executed given current network status.

        Args:
            capability: Name of the capability to check

        Returns:
            True if the capability can be executed
        """
        requirement = self._capabilities.get(capability, NetworkRequirement.ONLINE_OPTIONAL)

        if requirement == NetworkRequirement.LOCAL_ONLY:
            return True

        status = self.check_network()

        if requirement == NetworkRequirement.ONLINE_REQUIRED:
            return status.connected

        # ONLINE_OPTIONAL - always allowed, but may have degraded experience
        return True

    def get_requirement(self, capability: str) -> NetworkRequirement:
        """Get the network requirement for a capability."""
        return self._capabilities.get(capability, NetworkRequirement.ONLINE_OPTIONAL)

    def get_fallback(self, capability: str) -> str | None:
        """Get a fallback capability for when network is unavailable.

        Args:
            capability: Name of the capability that requires network

        Returns:
            Name of a local fallback capability, or None
        """
        fallbacks = {
            "cloud_llm": "local_llm",
            "web_search": None,  # No local fallback
            "gmail": None,  # Cannot work offline
            "calendar": None,  # Cannot work offline
            "weather_api": None,  # No local fallback
        }
        return fallbacks.get(capability)

    def get_status_message(self, capability: str) -> str:
        """Get a user-friendly status message for a capability.

        Args:
            capability: Name of the capability

        Returns:
            Human-readable status message
        """
        requirement = self.get_requirement(capability)
        status = self.check_network()

        if requirement == NetworkRequirement.LOCAL_ONLY:
            return f"{capability} is available (runs locally)"

        if status.connected:
            return f"{capability} is available"

        if requirement == NetworkRequirement.ONLINE_REQUIRED:
            fallback = self.get_fallback(capability)
            if fallback:
                return f"{capability} is unavailable (no network). Using {fallback} instead."
            return f"{capability} is unavailable (no network connection)"

        return f"{capability} is available with limited functionality (offline mode)"

    def list_capabilities(self, connected_only: bool = False) -> list[str]:
        """List all registered capabilities.

        Args:
            connected_only: Only return capabilities that can execute now

        Returns:
            List of capability names
        """
        if not connected_only:
            return list(self._capabilities.keys())

        return [cap for cap in self._capabilities if self.can_execute(cap)]


# Global instance
_gate: OnlineOfflineGate | None = None


def get_online_offline_gate() -> OnlineOfflineGate:
    """Get the global online/offline gate instance."""
    global _gate
    if _gate is None:
        _gate = OnlineOfflineGate()
    return _gate


__all__ = [
    "NetworkRequirement",
    "NetworkStatus",
    "OnlineOfflineGate",
    "get_online_offline_gate",
]
