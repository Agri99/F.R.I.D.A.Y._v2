"""
src/friday/online/gate.py

WHAT THIS IS FOR:
Online/offline capability gate (blueprint §43).

Single authoritative component that tracks network state and gates
network-capable tools. All network tools must consult it before executing.

States:
  ONLINE   - network available, all network tools enabled
  OFFLINE  - network unavailable, network tools disabled
  UNKNOWN  - state not yet determined
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from friday.online.network import NetworkMonitor


class ConnectivityState(str, Enum):
    """Network connectivity state."""
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class CapabilityGateConfig:
    """Configuration for the capability gate."""
    check_interval_seconds: float = 10.0
    auto_start_monitoring: bool = True
    offline_timeout_seconds: float = 30.0  # How long to wait before marking offline


class OnlineCapabilityGate:
    """Single authoritative component for online/offline capability gating.

    All network-capable tools must consult this gate before executing.
    The gate monitors network state and notifies subscribers of changes.
    """

    def __init__(self, config: CapabilityGateConfig | None = None) -> None:
        self.config = config or CapabilityGateConfig()
        self._state = ConnectivityState.UNKNOWN
        self._lock = threading.Lock()
        self._monitor = NetworkMonitor()
        self._callbacks: list[Callable[[ConnectivityState], None]] = []
        self._monitoring = False
        self._monitor_thread: threading.Thread | None = None

        if self.config.auto_start_monitoring:
            self.start_monitoring()

    @property
    def state(self) -> ConnectivityState:
        """Current connectivity state."""
        with self._lock:
            return self._state

    def is_online(self) -> bool:
        """Check if network is currently available."""
        with self._lock:
            return self._state == ConnectivityState.ONLINE

    def is_offline(self) -> bool:
        """Check if network is currently unavailable."""
        with self._lock:
            return self._state == ConnectivityState.OFFLINE

    def get_state(self) -> ConnectivityState:
        """Get current state (alias for state property)."""
        return self.state

    def require_online(self, operation: str) -> bool:
        """Check if online; raise if offline.

        Returns True if online. Raises RuntimeError if offline.
        """
        if not self.is_online():
            raise RuntimeError(
                f"Operation '{operation}' requires online connectivity. "
                f"Current state: {self.state.value}."
            )
        return True

    def _notify(self) -> None:
        """Notify subscribers of state change."""
        with self._lock:
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb(self._state)
            except Exception:
                pass

    def check_online(self, operation: str) -> tuple[bool, str | None]:
        """Check if online; return (bool, error_message).

        Returns (True, None) if online.
        Returns (False, error_message) if offline.
        """
        if self.is_online():
            return True, None
        return False, f"Operation '{operation}' requires online connectivity. Current state: {self.state.value}."

    def subscribe(self, callback: Callable[[ConnectivityState], None]) -> None:
        """Subscribe to state changes."""
        with self._lock:
            self._callbacks.append(callback)

    def unsubscribe(self, callback: Callable[[ConnectivityState], None]) -> None:
        """Unsubscribe from state changes."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def start_monitoring(self) -> None:
        """Start background network monitoring."""
        with self._lock:
            if self._monitoring:
                return
            self._monitoring = True

        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

        # Initial check
        self._check_and_update()

    def stop_monitoring(self) -> None:
        """Stop background network monitoring."""
        with self._lock:
            self._monitoring = False

        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
            self._monitor_thread = None

    def force_check(self) -> ConnectivityState:
        """Force an immediate connectivity check and return the new state."""
        self._check_and_update()
        return self.state

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """Background loop that periodically checks connectivity."""
        while self._monitoring:
            try:
                self._check_and_update()
            except Exception:
                pass  # Continue monitoring even if check fails

            # Sleep with small intervals to allow quick shutdown
            for _ in range(int(self.config.check_interval_seconds * 10)):
                if not self._monitoring:
                    break
                time.sleep(0.1)

    def _check_and_update(self) -> None:
        """Check network and update state if changed."""
        is_online = self._monitor.is_online()
        new_state = ConnectivityState.ONLINE if is_online else ConnectivityState.OFFLINE

        with self._lock:
            if self._state != new_state:
                self._state = new_state
                callbacks = list(self._callbacks)
            else:
                callbacks = []

        # Notify outside lock
        for cb in callbacks:
            try:
                cb(self._state)
            except Exception:
                pass


# Global gate instance
_global_gate: "OnlineCapabilityGate | None" = None


def get_capability_gate(config: CapabilityGateConfig | None = None) -> "OnlineCapabilityGate":
    """Get the global capability gate (singleton)."""
    global _global_gate
    if _global_gate is None:
        _global_gate = OnlineCapabilityGate(config)
    return _global_gate


__all__ = [
    "ConnectivityState",
    "CapabilityGateConfig",
    "OnlineCapabilityGate",
    "get_capability_gate",
]