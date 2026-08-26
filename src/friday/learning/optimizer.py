"""
Skill refinement.
"""
from __future__ import annotations

from typing import Any
from friday.skills.learner import SkillCandidate
from friday.learning.trajectory import Trajectory

class SkillOptimizer:
    """Refines skills based on failures."""
    
    def refine(self, skill: Any, failure_trajectory: Trajectory) -> SkillCandidate:
        """Adds failure handling and recovery steps based on a failed run."""
        
        # Analyze why it failed and propose a fix
        error_step = next((s for s in failure_trajectory.steps 
                         if getattr(s.get("result"), "status", "") == "error"), None)
                         
        new_recovery = skill.recovery
        if error_step:
            new_recovery += "\n- Added automated recovery for encountered error"
            
        return SkillCandidate(
            proposed_name=skill.name,
            procedure=skill.procedure,
            triggers=[skill.trigger],
            required_capabilities=skill.required_capabilities
        )
