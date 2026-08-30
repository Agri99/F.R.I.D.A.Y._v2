"""
tests/learning/test_distiller.py

WHAT THIS IS FOR:
Unit tests for the PatternDistiller trajectory normalization and skill extraction.
"""

from __future__ import annotations

import pytest

from friday.learning.distiller import PatternDistiller, SkillCandidate


class TestPatternDistiller:
    @pytest.fixture
    def distiller(self):
        return PatternDistiller()

    @pytest.fixture
    def sample_trajectories(self):
        return [
            {
                "id": "traj_1",
                "goal": "Open VS Code and create file",
                "outcome": "SUCCESS",
                "steps": [
                    {"action": "applications.open", "arguments": {"app_id": "vscode"}},
                    {"action": "filesystem.write", "arguments": {"path": "/home/user/test.py", "content": "print('hello')"}},
                ],
            },
            {
                "id": "traj_2",
                "goal": "Open VS Code and create file",
                "outcome": "SUCCESS",
                "steps": [
                    {"action": "applications.open", "arguments": {"app_id": "vscode"}},
                    {"action": "filesystem.write", "arguments": {"path": "/home/user/other.py", "content": "print('world')"}},
                ],
            },
        ]

    def test_distill_requires_multiple_successes(self, distiller):
        """Need at least 2 successful trajectories."""
        trajectories = [{"outcome": "SUCCESS"}]
        result = distiller.distill(trajectories)
        assert result is None

    def test_distill_returns_candidate(self, distiller, sample_trajectories):
        candidate = distiller.distill(sample_trajectories)
        assert candidate is not None
        assert isinstance(candidate, SkillCandidate)
        assert candidate.proposed_name.startswith("open_vs_code")
        assert len(candidate.procedure) >= 2

    def test_normalize_removes_timestamps(self, distiller):
        traj = {
            "steps": [
                {"action": "test", "arguments": {}, "timestamp": "2026-01-01"},
                {"action": "test2", "arguments": {}},
            ]
        }
        normalized = distiller._normalize_trajectory(traj)
        assert "timestamp" not in normalized[0]

    def test_normalize_collapses_duplicates(self, distiller):
        traj = {
            "steps": [
                {"action": "test", "arguments": {"x": 1}},
                {"action": "test", "arguments": {"x": 1}},
                {"action": "test2", "arguments": {}},
            ]
        }
        normalized = distiller._normalize_trajectory(traj)
        assert len(normalized) == 2

    def test_remove_noise_replaces_paths(self, distiller):
        steps = [
            {"action": "write", "arguments": {"path": "/home/user/file.txt"}},
            {"action": "read", "arguments": {"path": "C:\\Users\\test\\doc.txt"}},
        ]
        cleaned = distiller._remove_noise(steps)
        assert cleaned[0]["arguments"]["path"] == "{path}"
        assert cleaned[1]["arguments"]["path"] == "{path}"

    def test_extract_variables(self, distiller):
        steps = [
            {"action": "write", "arguments": {"path": "/home/user/file.txt"}},
            {"action": "read", "arguments": {"path": "/home/user/other.txt"}},
        ]
        template, variables = distiller._extract_variables(steps)
        assert len(variables) == 2
        assert template[0]["arguments"]["path"] == "{var0}"
        assert template[1]["arguments"]["path"] == "{var1}"