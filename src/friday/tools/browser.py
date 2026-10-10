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
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
        return {"status": "error", "message": str(exc)}


def _search(query: str) -> dict[str, Any]:
    """Search Google/web in default browser."""
    query = (query or "").strip()
    if not query:
        return {"status": "error", "message": "No search query provided."}
    try:
        url = _browser.search(query)
        return {"status": "ok", "query": query, "url": url}
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
        return {"status": "error", "message": str(exc)}


def _observe(url: str | None = None, query: str | None = None) -> dict[str, Any]:
    """Read the plain text content of a webpage. If no URL is provided, automatically detects active browser tab."""
    try:
        raw_target = (url or "").strip()
        query_str = (query or "").strip()
        target_url = ""
        page_title = None

        if raw_target.startswith(("http://", "https://")):
            target_url = raw_target
        elif raw_target and "." in raw_target and " " not in raw_target:
            target_url = f"https://{raw_target}"

        # 1. If target_url is not a direct URL, always check for an active browser tab first
        if not target_url:
            try:
                from friday.browser.active_tab import get_active_browser_info
                info = get_active_browser_info()
                if info:
                    if info.url:
                        target_url = info.url
                    page_title = info.title
                    if not target_url and page_title:
                        target_url = page_title
            except Exception:
                pass

        # 2. Check if query or raw_target was actually meant for an external web search
        # (Only if NO active browser tab could be resolved, or if the candidate looks like a plain search term)
        if not target_url:
            candidate = query_str or raw_target
            # Filter out meta-instructions like "summarize the active webpage", "read this page"
            meta_words = {"active", "this", "page", "webpage", "open", "current", "summarize", "read", "inspect"}
            is_meta = any(w in candidate.lower() for w in meta_words)
            if candidate and not is_meta:
                try:
                    from friday.online.search import WebSearchProvider
                    searcher = WebSearchProvider()
                    results = searcher.search(candidate, max_results=1)
                    if results and hasattr(results[0], "url"):
                        target_url = results[0].url
                except Exception:
                    pass

        # 3. Fetch content via Playwright DOM / PageExtractor if we have an HTTP/HTTPS URL
        if target_url and target_url.startswith(("http://", "https://")):
            content = _browser.fetch_text_content(target_url)
            return {
                "status": "ok",
                "url": target_url,
                "title": page_title or "",
                "content": content,
                "source": "playwright_dom",
            }

        # 5. Check if browser controller has a cached/open URL
        content = _browser.get_page_content()
        if content and content != "No URL currently open.":
            return {"status": "ok", "content": content, "source": "browser_cache"}

        # 6. Fallback: If page title detected or active window open, use UIA screen text
        if page_title:
            from friday.tools.computer import _read_text
            res = _read_text()
            if res.get("status") == "ok" and res.get("text"):
                return {
                    "status": "ok",
                    "title": page_title,
                    "content": res.get("text"),
                    "source": res.get("source", "accessibility_tree"),
                }

        return {
            "status": "ok",
            "content": "No active webpage could be detected. Please ensure your browser has a webpage open.",
            "source": "none",
        }
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
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
        description="Inspect and read the entire plain text content of a webpage without OCR using Playwright structured DOM and PageExtractor. If no URL is provided, automatically detects and inspects the active browser tab (Brave, Chrome, Edge, etc.). Pass empty arguments if no URL was provided.",
        tier="GREEN",
        capability_scope="browser.read",
        online_required=True,
        input_schema=build_schema({"url": {"type": "string"}, "query": {"type": "string"}}, []),
        handler=_observe,
    ))
