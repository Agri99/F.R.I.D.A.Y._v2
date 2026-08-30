"""
src/friday/learning/optimizer.py

WHAT THIS IS FOR:
Skill procedure optimization and failure-driven refinement (§14.3).
Enhanced with performance metrics and regression detection for measured self-improvement (Phase 4).
"""

from __future__ import annotations

from typing import Any
from friday.skills.learner import SkillCandidate
from friday.learning.trajectory import Trajectory
from datetime import datetime


class SkillOptimizer:
    """Refines skills based on execution traces and failure trajectories."""

    def refine(self, skill: Any, failure_trajectory: Trajectory) -> SkillCandidate:
        """Add error mitigation and recovery steps based on a failed run."""
        steps = getattr(failure_trajectory, "steps", [])

        # Find step where failure occurred
        failed_action = None
        error_msg = ""
        for s in steps:
            res = s.get("result") if isinstance(s, dict) else getattr(s, "result", None)
            if isinstance(res, dict) and res.get("status") == "error":
                failed_action = s.get("action") if isinstance(s, dict) else getattr(s, "action", None)
                error_msg = res.get("error") or res.get("message") or ""
                break

        # Generate refined procedure
        procedure = getattr(skill, "procedure", "")
        if failed_action and error_msg:
            recovery_clause = f"\n# Recovery note: If '{failed_action}' encounters '{error_msg[:60]}', retry with fallback target."
            procedure += recovery_clause

        name = getattr(skill, "name", "refined_skill")
        triggers = [getattr(skill, "trigger", "run")] if hasattr(skill, "trigger") else ["run"]
        caps = getattr(skill, "required_capabilities", [])

        candidate = SkillCandidate(
            proposed_name=name,
            purpose=getattr(skill, "purpose", f"Optimized version of {name}"),
            triggers=triggers,
            procedure=procedure,
            required_capabilities=caps,
            risk_profile=getattr(skill, "risk_profile", "GREEN"),
            expected_observations=getattr(skill, "expected_observations", []),
            verification=getattr(skill, "verification", "Verify all steps succeeded."),
        )

        # Copy metrics from original skill if available
        if hasattr(skill, "attempts"):
            candidate.attempts = skill.attempts
            candidate.successes = skill.successes
            candidate.failures = skill.failures
            candidate.failure_causes = skill.failure_causes.copy()
            candidate.avg_execution_time_ms = skill.avg_execution_time_ms
            candidate.verification_rate = skill.verification_rate
            candidate.user_corrections = skill.user_corrections
            candidate.regression_history = skill.regression_history.copy()
            candidate.version = getattr(skill, "version", "1.0")

        return candidate

    def optimize_steps(self, steps: list[dict]) -> list[dict]:
        """Eliminate redundant steps and simplify sequential arguments."""
        optimized: list[dict] = []
        for s in steps:
            # Drop empty no-op steps
            if s.get("action") in ("noop", "pass", "wait_zero"):
                continue
            optimized.append(s)
        return optimized

    def detect_regression(self, current: SkillCandidate, previous: SkillCandidate) -> dict | None:
        """Detect if current version regressed compared to previous version."""
        current_rate = current.success_rate
        previous_rate = previous.success_rate

        if previous_rate > 0 and current_rate < previous_rate - 0.1:  # 10% drop threshold
            return {
                "regression": True,
                "from_version": previous.version,
                "to_version": current.version,
                "previous_success_rate": previous_rate,
                "current_success_rate": current_rate,
                "drop": previous_rate - current_rate,
            }
        return None