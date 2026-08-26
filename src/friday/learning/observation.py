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
        if trajectory.outcome == "DONE":
            return ObservationType.SUCCESS
            
        if trajectory.outcome == "FAILED":
            return ObservationType.FAILURE
            
        # Analyze steps to see if a failure was corrected
        failures = 0
        for step in trajectory.steps:
            if getattr(step.get("result"), "status", "") == "error":
                failures += 1
                
        if failures > 0 and trajectory.outcome == "DONE":
            return ObservationType.CORRECTED
            
        return ObservationType.PARTIAL
