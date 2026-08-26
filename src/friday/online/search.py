"""
Web search provider.
"""
from __future__ import annotations

from dataclasses import dataclass
import urllib.parse
import webbrowser
import logging

logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

class WebSearchProvider:
    """Provides web search functionality with browser fallback."""
    
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    def search(self, query: str) -> list[SearchResult]:
        """
        Execute search. If no API key, falls back to opening browser.
        Returns results.
        """
        if not self._api_key:
            logger.info("No search API key configured, falling back to browser.")
            self._fallback_browser_search(query)
            return []
            
        # Stub API call
        return [
            SearchResult(
                title=f"Result for {query}",
                url="https://example.com",
                snippet="This is a stub result since real API requires config."
            )
        ]

    def _fallback_browser_search(self, query: str) -> None:
        """Open default browser with duckduckgo search."""
        encoded = urllib.parse.quote_plus(query)
        webbrowser.open(f"https://duckduckgo.com/?q={encoded}")
