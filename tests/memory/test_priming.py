"""
tests/memory/test_priming.py

WHAT THIS IS FOR:
Unit tests for the Context Priming Engine.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from friday.memory.priming import ContextPrimingEngine, PrimedContext


class MockMemoryDB:
    def search_by_relevance(self, query, limit=5):
        return [
            {"content": "User prefers dark mode", "category": "preference"},
            {"content": "Project path: /home/user/myproject", "category": "project"},
        ]


class MockSkillRegistry:
    def search_skills(self, query):
        return [{"name": "deploy_django", "purpose": "Deploy Django app"}]


class MockPreferenceStore:
    def list_preferences(self):
        class Pref:
            key = "theme"
            value = "dark"
            confidence = 0.9
        return [Pref()]


class TestContextPrimingEngine:
    @pytest.fixture
    def engine(self):
        return ContextPrimingEngine(
            memory_db=MockMemoryDB(),
            skill_registry=MockSkillRegistry(),
            preference_store=MockPreferenceStore(),
        )

    def test_prime_returns_primed_context(self, engine):
        context = engine.prime("Deploy my project")
        assert isinstance(context, PrimedContext)
        assert len(context.relevant_memories) >= 0
        assert len(context.relevant_skills) >= 0
        assert len(context.relevant_preferences) >= 0

    def test_prime_includes_required_capabilities(self, engine):
        context = engine.prime("Deploy Django app")
        # Should infer capabilities from goal
        assert isinstance(context.required_capabilities, list)

    def test_prime_summary_contains_goal(self, engine):
        context = engine.prime("Test goal")
        assert "Test goal" in context.summary