"""
Observation classification.
"""
from __future__ import annotations

import enum
from typing import Any
from friday.learning.trajectory import Trajectory

class ObservationType(enum.Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"
    CORRECTED = "CORRECTED"

class ObservationClassifier:
    """Classifies trajectory outcomes."""
    
    def classify(self, trajectory: Trajectory) -> ObservationType:
        """Determine outcome category from trajectory data."""
        # Normalize outcome string
        outcome = str(trajectory.outcome).upper()
        
        # Check for corrected failure
        failures = 0
        for step in trajectory.steps:
            res = step.get("result") if isinstance(step, dict) else getattr(step, "result", None)
            if isinstance(res, dict) and res.get("status") == "error":
                failures += 1
                
        if failures > 0 and outcome in ("SUCCESS", "DONE"):
            return ObservationType.CORRECTED

        if outcome in ("SUCCESS", "DONE"):
            return ObservationType.SUCCESS
            
        if outcome in ("FAILURE", "FAILED", "BLOCKED"):
            return ObservationType.FAILURE
            
        return ObservationType.PARTIAL
