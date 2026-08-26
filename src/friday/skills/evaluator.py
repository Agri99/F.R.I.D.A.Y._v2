"""
Skill evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass
class SkillEvaluation:
    success: bool
    duration: float
    error_message: str | None = None

class SkillEvaluator:
    """Evaluates skill execution to track success/failure rates."""
    
    def evaluate_execution(self, skill: Any, execution_result: Any) -> SkillEvaluation:
        # In a real system, we'd extract this from the execution trace
        success = getattr(execution_result, "success", True)
        
        # Track stats
        if not hasattr(skill, "success_stats"):
            skill.success_stats = {"attempts": 0, "successes": 0}
            
        skill.success_stats["attempts"] += 1
        if success:
            skill.success_stats["successes"] += 1
            
        return SkillEvaluation(
            success=success,
            duration=getattr(execution_result, "duration", 0.0),
            error_message=getattr(execution_result, "error", None)
        )
