"""
src/friday/skills/versioning.py

WHAT THIS IS FOR:
Semantic versioning, change logging, regression detection, and rollback support for skills (§14.4).
Enhanced with performance metrics for measured self-improvement (Phase 4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SkillVersion:
    version: str
    changes: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    procedure_snapshot: str = ""
    success_rate: float = 0.0

    # Extended metrics for measured improvement
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    avg_execution_time_ms: float = 0.0
    verification_rate: float = 0.0
    user_corrections: int = 0


class SkillVersionManager:
    """Manages skill semantic versioning and regression rollback."""

    def __init__(self) -> None:
        self._history: dict[str, list[SkillVersion]] = {}

    def create_version(self, skill: Any, changes: str, major_bump: bool = False) -> str:
        """Bump version, snapshot procedure, and record change log with metrics."""
        current_v = getattr(skill, "version", "1.0")
        match = re.match(r"v?(\d+)\.(\d+)(?:\.(\d+))?", current_v)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            if major_bump:
                new_v = f"{major + 1}.0"
            else:
                new_v = f"{major}.{minor + 1}"
        else:
            new_v = "1.1"

        skill.version = new_v
        name = getattr(skill, "name", "skill")

        if name not in self._history:
            self._history[name] = []

        # Collect metrics from skill
        attempts = getattr(skill, "attempts", 0)
        successes = getattr(skill, "successes", 0)
        failures = getattr(skill, "failures", 0)
        success_rate = successes / attempts if attempts > 0 else 0.0

        version_entry = SkillVersion(
            version=new_v,
            changes=changes,
            procedure_snapshot=getattr(skill, "procedure", ""),
            success_rate=success_rate,
            attempts=attempts,
            successes=successes,
            failures=failures,
            avg_execution_time_ms=getattr(skill, "avg_execution_time_ms", 0.0),
            verification_rate=getattr(skill, "verification_rate", 0.0),
            user_corrections=getattr(skill, "user_corrections", 0),
        )
        self._history[name].append(version_entry)
        return new_v

    def rollback(self, skill: Any, to_version: str | None = None) -> bool:
        """Roll back a skill to a previous version if a regression occurs."""
        name = getattr(skill, "name", "")
        history = self._history.get(name, [])
        if not history:
            return False

        if to_version:
            target = next((v for v in history if v.version == to_version), None)
        else:
            # Default to previous version before current
            target = history[-2] if len(history) >= 2 else history[0]

        if target:
            skill.version = target.version
            if target.procedure_snapshot:
                skill.procedure = target.procedure_snapshot
            # Restore metrics
            skill.attempts = target.attempts
            skill.successes = target.successes
            skill.failures = target.failures
            skill.avg_execution_time_ms = target.avg_execution_time_ms
            skill.verification_rate = target.verification_rate
            skill.user_corrections = target.user_corrections
            return True

        return False

    def get_history(self, skill_name: str) -> list[SkillVersion]:
        """Return version history for a skill."""
        return self._history.get(skill_name, [])

    def get_latest_version(self, skill_name: str) -> SkillVersion | None:
        """Get the latest version entry for a skill."""
        history = self._history.get(skill_name, [])
        return history[-1] if history else None

    def compare_versions(self, skill_name: str, v1: str, v2: str) -> dict | None:
        """Compare metrics between two versions."""
        history = self._history.get(skill_name, [])
        v1_entry = next((v for v in history if v.version == v1), None)
        v2_entry = next((v for v in history if v.version == v2), None)

        if not v1_entry or not v2_entry:
            return None

        return {
            "version_1": {"version": v1_entry.version, "success_rate": v1_entry.success_rate, "attempts": v1_entry.attempts},
            "version_2": {"version": v2_entry.version, "success_rate": v2_entry.success_rate, "attempts": v2_entry.attempts},
            "success_rate_diff": v2_entry.success_rate - v1_entry.success_rate,
            "regression": v2_entry.success_rate < v1_entry.success_rate - 0.1,
        }
