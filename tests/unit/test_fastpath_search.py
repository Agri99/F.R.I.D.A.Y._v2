"""
tests/unit/test_fastpath_search.py

WHAT THIS IS FOR:
Proves the fix for "always opens browser when asked to find information":
explicit "find/search/look up X" phrasings now route directly to
online.search via FastPathRouter, bypassing the model's tool choice -
which in practice didn't reliably follow the existing system-prompt and
tool-description instructions to prefer online.search over browser.open.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from friday.agent.fastpath import FastPathRouter


def test_find_information_about_routes_to_online_search():
    router = FastPathRouter()
    result = router.match("find information about the Eiffel Tower")
    assert result is not None
    assert result.tool_name == "online.search"
    assert result.arguments["query"] == "the Eiffel Tower"


def test_search_for_routes_to_online_search():
    router = FastPathRouter()
    result = router.match("search for python asyncio tutorials")
    assert result is not None
    assert result.tool_name == "online.search"
    assert result.arguments["query"] == "python asyncio tutorials"


def test_look_up_routes_to_online_search():
    router = FastPathRouter()
    result = router.match("look up the weather in Tokyo")
    assert result is not None
    assert result.tool_name == "online.search"


def test_query_preserves_original_casing_and_punctuation():
    """The query text should NOT be lowercased/stripped of punctuation -
    important for things like proper nouns or 'C++'."""
    router = FastPathRouter()
    result = router.match("search for C++ vs Rust performance")
    assert result is not None
    assert result.arguments["query"] == "C++ vs Rust performance"


def test_trailing_punctuation_is_trimmed():
    router = FastPathRouter()
    result = router.match("find information about black holes?")
    assert result is not None
    assert result.arguments["query"] == "black holes"


def test_empty_query_after_trigger_does_not_match():
    router = FastPathRouter()
    result = router.match("search for")
    assert result is None


def test_unrelated_text_does_not_match_search():
    router = FastPathRouter()
    result = router.match("what's the weather like today")
    assert result is None or result.tool_name != "online.search"


def test_shutdown_and_orb_fastpaths_still_work_unaffected():
    """Regression guard: adding the search trigger shouldn't break the
    existing fastpath intents."""
    router = FastPathRouter()
    assert router.match("shut down").tool_name == "system.shutdown_friday"
    assert router.match("hide yourself").tool_name == "system.toggle_orb"
