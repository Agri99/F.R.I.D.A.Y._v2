from __future__ import annotations

import pytest
from friday.learning.distiller import PatternDistiller

def test_distiller_extracts_pattern():
    distiller = PatternDistiller()
    
    trajectories = [
        {"id": "t1", "outcome": "DONE", "goal": "test1"},
        {"id": "t2", "outcome": "DONE", "goal": "test2"},
        {"id": "t3", "outcome": "FAILED", "goal": "test3"}
    ]
    
    candidate = distiller.distill(trajectories)
    
    assert candidate is not None
    assert candidate.name == "distilled_skill"
    assert len(candidate.source_trajectory_ids) == 2
    assert "t1" in candidate.source_trajectory_ids
    assert "t2" in candidate.source_trajectory_ids
    assert "t3" not in candidate.source_trajectory_ids

def test_distiller_needs_multiple_successes():
    distiller = PatternDistiller()
    
    trajectories = [
        {"id": "t1", "outcome": "DONE", "goal": "test1"},
        {"id": "t3", "outcome": "FAILED", "goal": "test3"}
    ]
    
    candidate = distiller.distill(trajectories)
    assert candidate is None
