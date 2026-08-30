"""
src/friday/tools/browser.py

WHAT THIS IS FOR:
Browser interaction tools for F.R.I.D.A.Y. v2 (blueprint §9, §20, §46).
Opens URLs, runs searches in the default system browser, and extracts clean text
from public webpages.
"""

from __future__ import annotations

from typing import Any

from .registry import Tool, VerificationResult
from .metadata import build_schema
from friday.browser.controller import BrowserController

_browser = BrowserController()


def _open_url(url: str) -> dict[str, Any]:
    """Open a web link in the user's default browser."""
    try:
        _browser.open_url(url)
        return {"status": "ok", "url": url}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _search(query: str) -> dict[str, Any]:
    """Search Google/web in default browser."""
    query = (query or "").strip()
    if not query:
        return {"status": "error", "message": "No search query provided."}
    try:
        url = _browser.search(query)
        return {"status": "ok", "query": query, "url": url}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _observe(url: str | None = None) -> dict[str, Any]:
    """Read the plain text content of a webpage."""
    try:
        if url:
            content = _browser.fetch_text_content(url)
        else:
            content = _browser.get_page_content()
        return {"status": "ok", "content": content}
    except Exception as exc:
        return {"status": "error", "message": f"Could not read webpage content: {exc}"}


def _verify_open_url(args: dict, result: dict) -> VerificationResult:
    if isinstance(result, dict) and result.get("status") == "ok":
        return VerificationResult(True, f"Opened URL: {result.get('url')}")
    return VerificationResult(False, result.get("message", "Failed to open URL"))


def register_all_tools(registry) -> None:
    registry.register(Tool(
        name="browser.open",
        description="Open a web link in the UI. DO NOT use this to find information in the background; use online.search.",
        tier="YELLOW",
        capability_scope="browser.navigate",
        online_required=True,
        input_schema=build_schema({"url": {"type": "string"}}, ["url"]),
        handler=_open_url,
        verify=_verify_open_url,
    ))
    registry.register(Tool(
        name="browser.search",
        description="Open a search query in the browser UI. DO NOT use this to answer questions; use online.search instead.",
        tier="YELLOW",
        capability_scope="browser.navigate",
        online_required=True,
        input_schema=build_schema({"query": {"type": "string"}}, ["query"]),
        handler=_search,
    ))
    registry.register(Tool(
        name="browser.observe",
        description="Fetch and read the readable plain text content of a webpage.",
        tier="GREEN",
        capability_scope="browser.read",
        online_required=True,
        input_schema=build_schema({"url": {"type": "string"}}, []),
        handler=_observe,
    ))
