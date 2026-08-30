"""
src/friday/online/search.py

WHAT THIS IS FOR:
Web search provider supporting free DuckDuckGo HTML queries without requiring API keys,
with browser launch fallback (§8, §20 of Blueprint).
"""

from __future__ import annotations

import logging
import re
import urllib.parse
import webbrowser
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchProvider:
    """Provides web search functionality with DuckDuckGo scraping and browser fallback."""

    def __init__(self, api_key: str | None = None, timeout_seconds: int = 8):
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Execute web search using DuckDuckGo Lite HTML scraping."""
        if not query or not query.strip():
            return []

        results: list[SearchResult] = []
        try:
            from bs4 import BeautifulSoup
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            url = "https://lite.duckduckgo.com/lite/"
            resp = requests.post(url, data={"q": query.strip()}, headers=headers, timeout=self.timeout_seconds)
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                # In DuckDuckGo Lite, results are often in tables
                # Links have class 'result-link'
                # Snippets have class 'result-snippet'
                links = soup.find_all('a', class_='result-link')
                snippets = soup.find_all('td', class_='result-snippet')
                
                for i in range(min(len(links), len(snippets), max_results)):
                    raw_url = links[i].get('href', '')
                    clean_title = links[i].get_text(strip=True)
                    clean_snippet = snippets[i].get_text(strip=True)
                    
                    if raw_url.startswith("//"):
                        raw_url = "https:" + raw_url
                        
                    # Skip empty titles or snippet links that are clearly ads
                    if not clean_title or not raw_url:
                        continue
                        
                    results.append(SearchResult(title=clean_title, url=raw_url, snippet=clean_snippet))

        except Exception as exc:
            logger.warning(f"DuckDuckGo direct search failed: {exc}")

        return results


# Alias for backward compatibility
DuckDuckGoScraper = WebSearchProvider
