"""
tests/memory/test_retention.py

WHAT THIS IS FOR:
Unit tests for memory retention and confidence scoring.
"""

from __future__ import annotations

import pytest

from friday.memory.retention import MemoryRetentionEngine, RetentionScore


class TestMemoryRetentionEngine:
    @pytest.fixture
    def engine(self):
        return MemoryRetentionEngine()

    def test_compute_retention_score(self, engine):
        """Memory candidate should get a retention score based on evidence."""
        candidate = {
            "category": "preference",
            "content": "theme=dark",
            "source": "user",
            "confidence": 0.9,
            "evidence_count": 10,
        }
        score = engine.compute_retention(candidate)
        assert isinstance(score, RetentionScore)
        assert 0.0 <= score.value <= 1.0
        assert score.should_retain is True

    def test_low_confidence_not_retained(self, engine):
        """Low confidence memories should not be retained."""
        candidate = {
            "category": "preference",
            "content": "random statement",
            "source": "user",
            "confidence": 0.3,
            "evidence_count": 1,
        }
        score = engine.compute_retention(candidate)
        assert score.should_retain is False

    def test_expiry_applied(self, engine):
        """Expired memories should not be retained."""
        candidate = {
            "category": "knowledge",
            "content": "outdated info",
            "source": "web",
            "confidence": 0.8,
            "evidence_count": 5,
            "expiry": "2020-01-01",
        }
        score = engine.compute_retention(candidate)
        assert score.should_retain is False