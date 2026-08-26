"""
Test network capability gate.
"""
from friday.online.network import NetworkMonitor, NetworkState
from friday.online.capability_gate import OnlineCapabilityGate

class MockCapabilityRegistry:
    def __init__(self):
        self.enabled = set()
    def enable(self, cap): self.enabled.add(cap)
    def disable(self, cap): self.enabled.discard(cap)
    def is_enabled(self, cap): return cap in self.enabled

def test_network_gate_online_transitions():
    monitor = NetworkMonitor(interval=10)
    monitor._state = NetworkState.ONLINE
    gate = OnlineCapabilityGate(monitor)
    
    assert gate.check_online_tool("search") == True
    
    registry = MockCapabilityRegistry()
    gate.enable_online_capabilities(registry)
    assert registry.is_enabled("web_search")

def test_network_gate_offline_transitions():
    monitor = NetworkMonitor(interval=10)
    monitor._state = NetworkState.OFFLINE
    gate = OnlineCapabilityGate(monitor)
    
    assert gate.check_online_tool("search") == False
    
    registry = MockCapabilityRegistry()
    registry.enable("web_search")
    gate.disable_online_capabilities(registry)
    assert not registry.is_enabled("web_search")
