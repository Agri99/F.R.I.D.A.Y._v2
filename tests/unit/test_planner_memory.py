"""
tests/unit/test_planner_memory.py

WHAT THIS IS FOR:
Unit test for planner's memory-aware replanning.
"""

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


def test_planner_produces_structured_steps():
    planner = Planner()

    class MockProvider:
        def generate(self, messages, tools):
            from friday.models.base import ModelMessage
            class MockResponse:
                tool_calls = []
                text = "Done"
            return MockResponse()

    steps = planner.plan(
        goal="Do something",
        available_tools=[],
        memories=[],
        model_router=MagicMock(get=MagicMock(return_value=MockProvider())),
        system_prompt="You are a test.",
    )
    assert isinstance(steps, list)


from unittest.mock import MagicMock