"""
tests/interaction/test_online_offline_gate.py

Tests for online/offline capability gate (Runbook §35).
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from friday.interaction.online_offline_gate import (
    NetworkRequirement,
    NetworkStatus,
    OnlineOfflineGate,
    get_online_offline_gate,
)


class TestOnlineOfflineGate:
    """Tests for the online/offline gate."""

    def test_local_only_always_allowed(self):
        """Local-only capabilities work without network."""
        gate = OnlineOfflineGate()

        # Mock network as disconnected
        with patch.object(gate, 'check_network', return_value=NetworkStatus(connected=False, last_check=0)):
            assert gate.can_execute("stt")
            assert gate.can_execute("tts")
            assert gate.can_execute("local_llm")

    def test_online_required_needs_network(self):
        """Online-required capabilities fail without network."""
        gate = OnlineOfflineGate()

        # Mock network as disconnected
        with patch.object(gate, 'check_network', return_value=NetworkStatus(connected=False, last_check=0)):
            assert not gate.can_execute("gmail")
            assert not gate.can_execute("calendar")
            assert not gate.can_execute("cloud_llm")

    def test_online_required_works_with_network(self):
        """Online-required capabilities work with network."""
        gate = OnlineOfflineGate()

        # Mock network as connected
        with patch.object(gate, 'check_network', return_value=NetworkStatus(connected=True, last_check=0)):
            assert gate.can_execute("gmail")
            assert gate.can_execute("calendar")

    def test_online_optional_works_offline(self):
        """Online-optional capabilities always work (degraded)."""
        gate = OnlineOfflineGate()

        # Works when offline
        with patch.object(gate, 'check_network', return_value=NetworkStatus(connected=False, last_check=0)):
            assert gate.can_execute("browser")
            assert gate.can_execute("web_search")

    def test_fallback_for_cloud_llm(self):
        """Cloud LLM falls back to local when offline."""
        gate = OnlineOfflineGate()

        fallback = gate.get_fallback("cloud_llm")
        assert fallback == "local_llm"

    def test_no_fallback_for_gmail(self):
        """Gmail has no offline fallback."""
        gate = OnlineOfflineGate()

        fallback = gate.get_fallback("gmail")
        assert fallback is None

    def test_status_message_local(self):
        """Status message for local capability."""
        gate = OnlineOfflineGate()

        msg = gate.get_status_message("stt")
        assert "local" in msg.lower()

    def test_status_message_offline_required(self):
        """Status message for online-required capability when offline."""
        gate = OnlineOfflineGate()

        with patch.object(gate, 'check_network', return_value=NetworkStatus(connected=False, last_check=0)):
            msg = gate.get_status_message("gmail")
            assert "unavailable" in msg.lower()

    def test_register_custom_capability(self):
        """Can register custom capabilities."""
        gate = OnlineOfflineGate()

        gate.register_capability("custom_api", NetworkRequirement.ONLINE_REQUIRED)

        assert gate.get_requirement("custom_api") == NetworkRequirement.ONLINE_REQUIRED

    def test_list_capabilities(self):
        """Can list all capabilities."""
        gate = OnlineOfflineGate()

        caps = gate.list_capabilities()
        assert "stt" in caps
        assert "gmail" in caps

    def test_list_connected_only(self):
        """Can list only connected capabilities."""
        gate = OnlineOfflineGate()

        with patch.object(gate, 'check_network', return_value=NetworkStatus(connected=False, last_check=0)):
            caps = gate.list_capabilities(connected_only=True)
            assert "stt" in caps  # Local
            assert "gmail" not in caps  # Requires network

    def test_global_instance(self):
        """Global instance is available."""
        gate1 = get_online_offline_gate()
        gate2 = get_online_offline_gate()

        assert gate1 is gate2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
