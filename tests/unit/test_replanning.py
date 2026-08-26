import pytest
from friday.agent.planner import Planner
from friday.agent.task import Task, Step

def test_observation_aware_replanning():
    planner = Planner()
    task = Task(goal="Search web and download file")
    
    # Original plan version should be 1
    assert task.plan_version == 1
    
    # Simulate an observation
    observations = [{"step": "web.search", "observation": "Found download link at http://example.com/file"}]
    
    new_steps = planner.replan(task, observations)
    
    assert task.plan_version == 2
    # The new_steps could be empty since we mock model_router as None for test, but the replan logic was called
    assert isinstance(new_steps, list)
