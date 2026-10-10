"""
tests/unit/test_inspect_webpage.py

WHAT THIS IS FOR:
Tests for inspecting webpages without OCR and without asking the user for a URL.
Verifies FastPath routing, active browser tab auto-detection, and natural spoken replies.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from friday.agent.fastpath import FastPathRouter
from friday.agent.orchestrator import _format_natural_reply
from friday.browser.active_tab import ActiveBrowserInfo


def test_fastpath_inspect_webpage_exact():
    router = FastPathRouter()
    queries = [
        "inspect a webpage",
        "inspect the webpage",
        "inspect this webpage",
        "inspect webpage",
        "inspect web page",
        "inspect this page",
        "inspect the page",
        "inspect page",
        "inspect the whole webpage",
        "inspect the whole webpage without using ocr",
        "can friday inspect the whole webpage without using ocr",
        "read this webpage",
        "read the webpage",
        "read webpage",
        "read this page",
        "check this webpage",
        "check the webpage",
        "summarize this webpage",
        "summarize the webpage",
        "what is on this webpage",
        "what's on this webpage",
        "what is on this page",
        "what's on this page",
    ]
    for q in queries:
        res = router.match(q)
        assert res is not None, f"Failed to match query: {q}"
        assert res.tool_name == "browser.observe", f"Expected browser.observe for '{q}', got {res.tool_name}"
        assert res.arguments == {}, f"Expected empty arguments for auto-detection in '{q}', got {res.arguments}"


def test_fastpath_inspect_webpage_with_url():
    router = FastPathRouter()
    res = router.match("inspect webpage https://news.ycombinator.com")
    assert res is not None
    assert res.tool_name == "browser.observe"
    assert res.arguments == {"url": "https://news.ycombinator.com"}


def test_fastpath_inspect_screen_and_apps():
    router = FastPathRouter()
    queries = [
        "inspect this app",
        "inspect active app",
        "inspect this window",
        "read the screen",
        "read screen",
        "read screen text",
        "what's on my screen",
        "what is on my screen",
        "inspect my screen",
    ]
    for q in queries:
        res = router.match(q)
        assert res is not None, f"Failed to match query: {q}"
        assert res.tool_name == "computer.read_screen_text", f"Expected computer.read_screen_text for '{q}'"


def test_fastpath_negated_inspect():
    router = FastPathRouter()
    assert router.match("do not inspect the webpage") is None
    assert router.match("dont inspect this page") is None


def test_browser_observe_autodetect():
    from friday.tools.browser import _observe

    mock_info = ActiveBrowserInfo(
        url="https://example.com/test",
        title="Example Test Page",
        browser="brave",
        hwnd=12345,
    )

    with patch("friday.browser.active_tab.get_active_browser_info", return_value=mock_info):
        with patch("friday.tools.browser._browser.fetch_text_content", return_value="Welcome to Example Test Page. This is DOM content."):
            res = _observe()
            assert res["status"] == "ok"
            assert res["url"] == "https://example.com/test"
            assert res["title"] == "Example Test Page"
            assert "Welcome to Example Test Page" in res["content"]
            assert res["source"] == "playwright_dom"


def test_format_natural_reply_for_browser_observe():
    result = {
        "status": "ok",
        "url": "https://example.com",
        "title": "Example Domain",
        "content": "Example Domain. This domain is for use in illustrative examples in documents.",
    }
    reply = _format_natural_reply("browser.observe", result)
    assert "Example Domain" in reply
    assert "This domain is for use in illustrative examples" in reply
    assert "{" not in reply  # Never output raw JSON/dict formatting


def test_format_natural_reply_for_computer_read_screen_text():
    result = {
        "status": "ok",
        "source": "accessibility_tree",
        "text": "File Menu\nEdit Menu\nDocument text: Hello world",
    }
    reply = _format_natural_reply("computer.read_screen_text", result)
    assert "visible on your screen" in reply
    assert "File Menu" in reply
    assert "{" not in reply


def test_browser_observe_with_meta_query_prioritizes_active_tab():
    from friday.tools.browser import _observe

    mock_info = ActiveBrowserInfo(
        url="https://github.com/trending",
        title="Trending Repositories",
        browser="brave",
        hwnd=54321,
    )

    with patch("friday.browser.active_tab.get_active_browser_info", return_value=mock_info):
        with patch("friday.tools.browser._browser.fetch_text_content", return_value="Trending repos on GitHub today."):
            with patch("friday.online.search.WebSearchProvider.search") as mock_search:
                # Even if Gemini passes query="summarize the active webpage", it must NOT search the web
                res = _observe(query="summarize the active webpage")
                mock_search.assert_not_called()
                assert res["status"] == "ok"
                assert res["url"] == "https://github.com/trending"
                assert "Trending repos on GitHub" in res["content"]


def test_clean_live_speech_text():
    from friday.interaction.gemini_live import clean_live_speech_text

    raw_polluted = "terminal_run_host{command:ollcall:browser_observe[sigh] Yes, I do see that now, Boss. My apologies."
    cleaned = clean_live_speech_text(raw_polluted)
    assert "terminal_run_host" not in cleaned
    assert "ollcall" not in cleaned
    assert "browser_observe" not in cleaned
    assert cleaned == "[sigh] Yes, I do see that now, Boss. My apologies."

    raw_partial = "call:browser_observe() I have checked the page."
    cleaned2 = clean_live_speech_text(raw_partial)
    assert "call:browser_observe" not in cleaned2
    assert cleaned2 == "I have checked the page."


