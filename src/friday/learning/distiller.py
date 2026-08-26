"""
Pattern detection -> skill candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass
class SkillCandidate:
    name: str
    purpose: str
    triggers: list[str]
    prerequisites: list[str]
    required_capabilities: list[str]
    risk_profile: str
    inputs: list[dict]        # {name, type, description, required}
    procedure: list[dict]     # ordered action steps
    expected_observations: list[str]
    verification: list[dict]
    failure_modes: list[str]
    recovery: list[dict]
    source_trajectory_ids: list[str]

class PatternDistiller:
    def __init__(self, model_provider: Any = None):
        self.model_provider = model_provider

    def distill(self, trajectories: list[dict]) -> SkillCandidate | None:
        """Extract a reusable skill from successful trajectories."""
        # 1. Normalize trajectories (remove timestamps, IDs)
        # 2. Remove non-deterministic noise
        # 3. Detect repeated action subsequences
        # 4. Group by goal similarity
        # 5. Extract variable inputs
        # 6. Extract prerequisites
        # 7. Extract observations and verification conditions
        # 8. Produce structured SkillCandidate
        
        if not trajectories:
            return None
            
        successes = [t for t in trajectories if t.get("outcome") == "DONE"]
        if len(successes) >= 2:
            return SkillCandidate(
                name="distilled_skill",
                purpose="Extracted from successful runs",
                triggers=["context matching goal"],
                prerequisites=[],
                required_capabilities=[],
                risk_profile="low",
                inputs=[],
                procedure=[{"action": "extracted_step"}],
                expected_observations=[],
                verification=[],
                failure_modes=[],
                recovery=[],
                source_trajectory_ids=[t.get("id", "unknown") for t in successes]
            )
            
        return None
