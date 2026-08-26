from __future__ import annotations

import pytest
from friday.memory.priming import ContextPrimingEngine

class MockMemoryDB:
    def search_by_relevance(self, query: str, limit: int = 5):
        return [{"subject": "mock", "predicate": "is", "value": "test", "confidence": 0.9, "source": "test"}]

class MockPreferenceStore:
    def list_preferences(self):
        from friday.memory.preferences import Preference
        return [Preference(key="test_pref", value="on", confidence=0.8)]

class MockSkillRegistry:
    def search_skills(self, query: str):
        return [{"name": "test_skill"}]

def test_context_priming_builds_bundle():
    engine = ContextPrimingEngine(
        memory_db=MockMemoryDB(),
        skill_registry=MockSkillRegistry(),
        preference_store=MockPreferenceStore()
    )
    
    context = engine.prime("test goal")
    
    assert len(context.relevant_memories) == 1
    assert context.relevant_memories[0]["subject"] == "mock"
    
    assert len(context.relevant_preferences) == 1
    assert context.relevant_preferences[0]["key"] == "test_pref"
    
    assert len(context.relevant_skills) == 1
    assert context.relevant_skills[0]["name"] == "test_skill"
    
    assert "test goal" in context.summary
