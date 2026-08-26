"""
Pattern detection -> skill candidate.
"""
from __future__ import annotations

from typing import Any
from friday.skills.learner import SkillCandidate
from friday.learning.trajectory import Trajectory

class PatternDistiller:
    """Identifies repeated successful workflows across trajectories."""
    
    def analyze(self, trajectories: list[Trajectory]) -> list[SkillCandidate]:
        """Extract skills from repeated successful patterns."""
        candidates = []
        
        # In a real system, we'd use sequence alignment or LLM analysis
        # to find common sub-sequences of actions across different tasks.
        
        successes = [t for t in trajectories if t.outcome == "DONE"]
        if len(successes) >= 2:
            candidates.append(
                SkillCandidate(
                    proposed_name="distilled_pattern",
                    procedure="Steps extracted from successful runs",
                    triggers=["context matching goal"],
                    required_capabilities=[]
                )
            )
            
        return candidates
