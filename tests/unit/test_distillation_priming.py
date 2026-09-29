"""
tests/unit/test_distillation_priming.py

Tests for the Distillation Feedback Loop and Few-Shot Demonstration Priming:
1. Successful episodes in EpisodicMemory are retrieved by ContextPrimingEngine.
2. Failed or non-success episodes are strictly excluded from demonstrations.
3. Planner injects retrieved demonstrations into the system prompt for local brain reasoning.
4. GeminiLiveSession records successful tool trajectories directly to EpisodicMemory.
"""

from unittest.mock import MagicMock

from friday.agent.planner import Planner
from friday.agent.task import Task
from friday.memory.database import MemoryDatabase
from friday.memory.episodic import EpisodicMemory
from friday.memory.preferences import PreferenceMemory
from friday.memory.priming import ContextPrimingEngine
from friday.memory.semantic import SemanticMemory
from friday.skills.registry import SkillRegistry


def test_episodic_demonstration_priming(tmp_path):
    """Verify that ContextPrimingEngine recalls SUCCESS episodes and ignores FAILED ones."""
    db = MemoryDatabase(tmp_path / "priming_test.db")
    ep = EpisodicMemory(db)
    sem = SemanticMemory(db)
    prefs = PreferenceMemory(db)
    skills = SkillRegistry()

    # 1. Record a successful episode
    ep.record_episode(
        task_id="gemini_succ_1",
        goal="Search the web for current weather in Tokyo",
        steps=[{"action": "online.search", "arguments": {"query": "Tokyo weather"}, "result": "Sunny 22C"}],
        outcome="SUCCESS",
        duration=0.8,
    )

    # 2. Record a failed episode
    ep.record_episode(
        task_id="gemini_fail_1",
        goal="Search the web for current weather in London",
        steps=[{"action": "online.search", "arguments": {"query": "London weather"}, "result": "Network timeout"}],
        outcome="FAILED",
        duration=5.0,
    )

    engine = ContextPrimingEngine(
        memory_db=sem,
        skill_registry=skills,
        preference_store=prefs,
        episodic_memory=ep,
    )

    # Prime with goal matching the successful demonstration
    primed = engine.prime(user_goal="Check the current weather in Tokyo")

    assert hasattr(primed, "successful_demonstrations")
    assert len(primed.successful_demonstrations) == 1

    demo = primed.successful_demonstrations[0]
    assert demo["goal"] == "Search the web for current weather in Tokyo"
    assert "online.search" in demo["actions_summary"]

    # Ensure failed episode was not included
    for item in primed.successful_demonstrations:
        assert "London" not in item.get("goal", "")


def test_planner_injects_demonstrations_into_prompt():
    """Verify that Planner injects successful demonstrations into the model prompt."""
    planner = Planner()

    mock_primed = MagicMock()
    mock_primed.relevant_memories = []
    mock_primed.relevant_preferences = []
    mock_primed.relevant_skills = []
    mock_primed.required_capabilities = ["system"]
    mock_primed.known_failures = []
    mock_primed.successful_demonstrations = [
        {
            "goal": "Check system resources",
            "actions_summary": "system.get_status",
            "steps": [{"action": "system.get_status"}],
        }
    ]

    captured_messages = []

    class MockProvider:
        def generate(self, messages, tools):
            captured_messages.extend(messages)
            class MockResponse:
                tool_calls = []
                text = "System is healthy."
            return MockResponse()

    mock_router = MagicMock()
    mock_router.get.return_value = MockProvider()

    task = Task(goal="How is my CPU doing?")
    steps = planner.plan(
        goal=task.goal,
        available_tools=[],
        memories=[],
        model_router=mock_router,
        system_prompt="You are Friday.",
        primed_context=mock_primed,
    )

    assert isinstance(steps, list)
    assert len(captured_messages) > 0

    system_content = captured_messages[0].content
    assert "--- PRIMED CONTEXT ---" in system_content
    assert "Proven strategy demonstrations (from previous successful executions):" in system_content
    assert '- Goal: "Check system resources" -> Actions: system.get_status' in system_content


def test_gemini_live_records_episode_to_episodic_memory():
    """Verify that GeminiLiveSession records executed tools to EpisodicMemory."""
    try:
        from friday.interaction.gemini_live import GeminiLiveSession
    except (ImportError, RuntimeError):
        return  # Skip if google-genai is not available

    mock_registry = MagicMock()
    mock_tool = MagicMock()
    mock_tool.run.return_value = {"time": "02:15 PM", "timezone": "local"}
    mock_registry.get.return_value = mock_tool

    mock_episodic_memory = MagicMock()

    session = GeminiLiveSession(
        api_key="fake-test-key",
        tool_registry=mock_registry,
        episodic_memory=mock_episodic_memory,
    )
    session._last_user_text = "What time is it right now?"

    res = session._execute_local_tool("system_get_time", {})
    assert res == {"time": "02:15 PM", "timezone": "local"}

    # Verify episodic memory recorded the successful execution
    assert mock_episodic_memory.record_episode.called
    call_args = mock_episodic_memory.record_episode.call_args
    assert call_args[0][1] == "What time is it right now?"
    assert call_args[0][2] == [{"action": "system_get_time", "arguments": {}, "result": res}]
    assert call_args[0][3] == "SUCCESS"


def test_pattern_distiller_from_memory(tmp_path):
    """Verify that PatternDistiller can extract skill candidates directly from EpisodicMemory."""
    from friday.learning.distiller import PatternDistiller

    db = MemoryDatabase(tmp_path / "distill_test.db")
    ep = EpisodicMemory(db)

    # Record 2 successful episodes with identical repeated goal
    ep.record_episode(
        task_id="task_1",
        goal="Open Spotify and play favorites",
        steps=[
            {"action": "applications.open", "arguments": {"app_name": "Spotify"}},
            {"action": "computer.mouse_click", "arguments": {"x": 500, "y": 300}},
        ],
        outcome="SUCCESS",
        duration=1.2,
    )
    ep.record_episode(
        task_id="task_2",
        goal="Open Spotify and play favorites",
        steps=[
            {"action": "applications.open", "arguments": {"app_name": "Spotify"}},
            {"action": "computer.mouse_click", "arguments": {"x": 500, "y": 300}},
        ],
        outcome="SUCCESS",
        duration=1.1,
    )

    distiller = PatternDistiller()
    candidate = distiller.distill_from_memory(ep, query="Spotify")
    assert candidate is not None
    assert "spotify" in candidate.proposed_name.lower()
    assert len(candidate.procedure_steps) >= 1

