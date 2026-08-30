"""
src/friday/skills/evaluator.py

WHAT THIS IS FOR:
Evaluates skill executions to track real performance metrics, success rates, latency,
and failure causes across versions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillEvaluation:
    success: bool
    duration: float
    error_message: str | None = None
    steps_completed: int = 0
    verification_passed: bool = True
    metrics: dict[str, Any] = field(default_factory=dict)


class SkillEvaluator:
    """Evaluates skill execution to track success/failure rates and performance."""

    def evaluate_execution(self, skill: Any, execution_result: Any) -> SkillEvaluation:
        """Score a skill execution and update cumulative stats."""
        success = getattr(execution_result, "success", True)
        duration = float(getattr(execution_result, "duration", 0.0))
        error = getattr(execution_result, "error", None) or getattr(execution_result, "error_message", None)
        steps = int(getattr(execution_result, "steps_completed", 1))
        verified = getattr(execution_result, "verified", True)

        # Update tracking
        skill.attempts += 1
        
        # We need total_duration to calculate avg_execution_time_ms, which requires reversing the current avg
        current_total = skill.avg_execution_time_ms * (skill.attempts - 1)
        skill.avg_execution_time_ms = (current_total + duration) / skill.attempts

        if success:
            skill.successes += 1
        else:
            skill.failures += 1
            if error:
                skill.failure_causes.append(str(error)[:100])
                if len(skill.failure_causes) > 10:
                    skill.failure_causes = skill.failure_causes[-10:]

        return SkillEvaluation(
            success=success,
            duration=duration,
            error_message=str(error) if error else None,
            steps_completed=steps,
            verification_passed=verified,
            metrics={"success_rate": skill.success_rate, "attempts": skill.attempts},
        )
