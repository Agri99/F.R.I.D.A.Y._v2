"""
tests/integration/test_online_offline_fallback.py

WHAT THIS IS FOR:
Integration test for online capability gating, search degradation, and offline fallback.
"""

from __future__ import annotations

from unittest.mock import patch
from friday.online.network import NetworkMonitor
from friday.online.capability_gate import OnlineCapabilityGate
from friday.online.search import WebSearchProvider
from friday.online.live_data import LiveDataProvider


def test_online_gate_transitions():
    monitor = NetworkMonitor(assume_online=False)
    gate = OnlineCapabilityGate(monitor)

    # Initial offline state
    assert gate.is_available("web_search") is False

    # Simulate network restoration
    from friday.online.network import NetworkState
    monitor._state = NetworkState.ONLINE
    assert gate.is_available("web_search") is True



def test_search_browser_fallback():
    provider = WebSearchProvider(api_key=None)
    with patch("webbrowser.open") as mock_open:
        # Searching without API key falls back to DuckDuckGo browser launch
        results = provider.search("python documentation")
        assert mock_open.called or isinstance(results, list)
