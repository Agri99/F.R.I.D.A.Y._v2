"""
tests/unit/test_network_gate.py

WHAT THIS IS FOR:
Unit tests for network monitor and online capability gate.
"""

from __future__ import annotations

from unittest.mock import patch
import urllib.request

import pytest

from friday.online.network import NetworkMonitor
from friday.online.capability_gate import OnlineCapabilityGate


class TestNetworkMonitor:
    def test_is_online_when_assume_online(self):
        monitor = NetworkMonitor(assume_online=True)
        assert monitor.is_online() is True

    def test_is_offline_when_assume_offline(self):
        monitor = NetworkMonitor(assume_online=False)
        assert monitor.is_online() is False


class TestOnlineCapabilityGate:
    def test_online_tool_allowed_when_online(self):
        monitor = NetworkMonitor(assume_online=True)
        gate = OnlineCapabilityGate(monitor)
        assert gate.check_online_tool("online.search") is True

    def test_online_tool_denied_when_offline(self):
        monitor = NetworkMonitor(assume_online=False)
        gate = OnlineCapabilityGate(monitor)
        assert gate.check_online_tool("online.search") is False

    def test_failure_reason_on_offline(self):
        monitor = NetworkMonitor(assume_online=False)
        gate = OnlineCapabilityGate(monitor)
        reason = gate.get_failure_reason("online.search", "Web Search")
        assert "unavailable" in reason.lower() or "offline" in reason.lower()


from unittest.mock import MagicMock, patch
import urllib.request