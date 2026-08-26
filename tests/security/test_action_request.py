"""
Tests for ActionRequest.
"""
import pytest
from dataclasses import dataclass
from datetime import datetime

from friday.security.action_request import ActionRequest
from friday.security.policy import RiskTier, PolicyEngine, PolicyResult, PolicyDecision
from friday.security.secrets import SecretsManager

@dataclass
class DummyTool:
    name: str
    capability: str
    risk_tier: RiskTier
    required_scopes: list[str]

def test_action_request_from_tool():
    tool = DummyTool(name="test_tool", capability="system.read", risk_tier=RiskTier.YELLOW, required_scopes=["system.*"])
    req = ActionRequest.from_tool(tool, {"arg1": "value1"}, task_id="t1", step_id="s1")
    
    assert req.tool == "test_tool"
    assert req.capability == "system.read"
    assert req.risk_tier == RiskTier.YELLOW
    assert req.arguments == {"arg1": "value1"}
    assert req.task_id == "t1"
    assert req.requester == "planner"
    assert req.target is None

def test_confirmation_hash_integrity():
    tool = DummyTool(name="test_tool", capability="system.read", risk_tier=RiskTier.YELLOW, required_scopes=[])
    
    req1 = ActionRequest.from_tool(tool, {"b": 2, "a": 1})
    req2 = ActionRequest.from_tool(tool, {"a": 1, "b": 2})
    
    # Same arguments, different order -> should be same hash
    assert req1.to_confirmation_hash() == req2.to_confirmation_hash()
    
    # Different args -> different hash
    req3 = ActionRequest.from_tool(tool, {"a": 2, "b": 2})
    assert req1.to_confirmation_hash() != req3.to_confirmation_hash()

def test_secrets_manager(tmp_path):
    sm = SecretsManager(secrets_dir=tmp_path)
    (tmp_path / "google").mkdir()
    (tmp_path / "google" / "client_id").write_text("my_secret_id")
    
    assert sm.exists("google/client_id")
    assert sm.get("google/client_id") == "my_secret_id"
    assert not sm.exists("google/unknown")
