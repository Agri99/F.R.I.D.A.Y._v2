"""
tests/online/test_gate.py

WHAT THIS IS FOR:
Unit tests for the OnlineCapabilityGate (blueprint §43).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from friday.online.gate import (
    ConnectivityState,
    CapabilityGateConfig,
    OnlineCapabilityGate,
    get_capability_gate,
)


class TestOnlineCapabilityGate:
    def test_initial_state_unknown(self):
        gate = OnlineCapabilityGate(CapabilityGateConfig(auto_start_monitoring=False))
        assert gate.state == ConnectivityState.UNKNOWN

    def test_is_online_false_initially(self):
        gate = OnlineCapabilityGate(CapabilityGateConfig(auto_start_monitoring=False))
        assert not gate.is_online()

    def test_require_online_raises_when_offline(self):
        gate = OnlineCapabilityGate(CapabilityGateConfig(auto_start_monitoring=False))
        with pytest.raises(RuntimeError, match="requires online connectivity"):
            gate.require_online("test operation")

    def test_require_online_ok_when_online(self):
        gate = OnlineCapabilityGate(CapabilityGateConfig(auto_start_monitoring=False))
        with patch.object(gate, "is_online", return_value=True):
            assert gate.require_online("test") is True

    def test_check_online_returns_false_when_offline(self):
        gate = OnlineCapabilityGate(CapabilityGateConfig(auto_start_monitoring=False))
        ok, err = gate.check_online("test")
        assert ok is False
        assert "unknown" in err.lower()  # Initial state is UNKNOWN

    def test_subscribe_callback(self):
        gate = OnlineCapabilityGate(CapabilityGateConfig(auto_start_monitoring=False))
        calls = []
        gate.subscribe(lambda s: calls.append(s))
        # Manually trigger state change
        gate._state = ConnectivityState.ONLINE
        gate._notify()
        assert len(calls) == 1
        assert calls[0] == ConnectivityState.ONLINE

    def test_subscribe_unsubscribe(self):
        gate = OnlineCapabilityGate(CapabilityGateConfig(auto_start_monitoring=False))
        calls = []
        cb = lambda s: calls.append(s)
        gate.subscribe(cb)
        gate.unsubscribe(cb)
        gate._state = ConnectivityState.ONLINE
        gate._notify()
        assert len(calls) == 0

    def test_force_check(self):
        gate = OnlineCapabilityGate(CapabilityGateConfig(auto_start_monitoring=False))
        with patch.object(gate._monitor, "is_online", return_value=True):
            state = gate.force_check()
            assert state == ConnectivityState.ONLINE


class TestCapabilityGateConfig:
    def test_defaults(self):
        config = CapabilityGateConfig()
        assert config.check_interval_seconds == 10.0
        assert config.auto_start_monitoring is True
        assert config.offline_timeout_seconds == 30.0

    def test_custom_values(self):
        config = CapabilityGateConfig(
            check_interval_seconds=5.0,
            auto_start_monitoring=False,
            offline_timeout_seconds=60.0,
        )
        assert config.check_interval_seconds == 5.0
        assert config.auto_start_monitoring is False
        assert config.offline_timeout_seconds == 60.0


class TestGlobalGate:
    def test_singleton(self):
        gate1 = get_capability_gate()
        gate2 = get_capability_gate()
        assert gate1 is gate2