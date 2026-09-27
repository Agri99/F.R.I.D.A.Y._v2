"""
src/friday/online/search.py

WHAT THIS IS FOR:
Web search provider using self-hosted SearXNG as primary, with Wikipedia API
and Google News RSS as specialized fallbacks.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchProvider:
    """Provides web search functionality across SearXNG (primary), Wikipedia, and Google News."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float = 6.0,
        base_url: str = "http://127.0.0.1:8080",
        language: str = "en",
        safe_search: int = 1,
        specialized_fallbacks: bool = True,
    ):
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")
        self.language = language
        self.safe_search = safe_search
        self.specialized_fallbacks = specialized_fallbacks

    def _clean_html(self, text: str) -> str:
        return re.sub(r"<[^>]+>", "", text).strip()

    def _search_searxng(self, query: str, max_results: int) -> list[SearchResult]:
        """Search via local SearXNG instance with JSON output."""
        results: list[SearchResult] = []
        seen_urls: set[str] = set()
        headers = {
            "User-Agent": "FridayAssistant/1.0 (Mozilla/5.0; dev@friday.ai)"
        }

        try:
            url = f"{self.base_url}/search"
            params: dict[str, Any] = {
                "q": query,
                "format": "json",
                "language": self.language,
                "safesearch": self.safe_search,
            }
            resp = requests.get(url, params=params, headers=headers, timeout=self.timeout_seconds)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("results", [])[:max_results]:
                    title = item.get("title", "").strip()
                    url = item.get("url", "").strip()
                    snippet = item.get("content", item.get("snippet", "")).strip()
                    if not title or not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    results.append(SearchResult(title=title, url=url, snippet=snippet))
            elif resp.status_code == 403:
                logger.warning("SearXNG returned 403 - JSON format may not be enabled in settings.yml")
            else:
                logger.warning(f"SearXNG returned status {resp.status_code}")
        except requests.exceptions.Timeout:
            logger.warning("SearXNG request timed out")
        except requests.exceptions.ConnectionError:
            logger.warning("SearXNG connection failed - is the service running?")
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
            logger.debug(f"SearXNG search failed: {exc}")

        return results

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Execute multi-tier web search for real-time and encyclopedic data."""
        if not query or not query.strip():
            return []

        cleaned_query = query.strip()
        results: list[SearchResult] = []
        seen_urls: set[str] = set()
        headers = {
            "User-Agent": "FridayAssistant/1.0 (Mozilla/5.0; dev@friday.ai)"
        }

        # Silence XMLParsedAsHTMLWarning if beautifulsoup parses RSS with html.parser
        import warnings
        try:
            from bs4 import XMLParsedAsHTMLWarning
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            pass

        # 1. SearXNG Primary Search (general web)
        searxng_results = self._search_searxng(cleaned_query, max_results)
        for r in searxng_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                results.append(r)
        if len(results) >= max_results:
            return results[:max_results]

        # 2. Wikipedia Search API + REST Lead Extract (encyclopedic, lore, entities, games)
        if self.specialized_fallbacks:
            wiki_queries = [cleaned_query]
            words = cleaned_query.split()
            if len(words) > 1:
                # Fallback variations for typos (e.g. 'Luney Expedition 33' -> 'Expedition 33')
                wiki_queries.append(" ".join(w for w in words if len(w) > 3))
                wiki_queries.append(" ".join(words[1:]))

            for wq in wiki_queries:
                if len(results) >= max_results:
                    break
                try:
                    wiki_params: dict[str, Any] = {
                        "action": "query",
                        "list": "search",
                        "srsearch": wq,
                        "format": "json",
                        "utf8": 1,
                    }
                    r_wiki = requests.get(
                        "https://en.wikipedia.org/w/api.php",
                        params=wiki_params,
                        headers=headers,
                        timeout=min(self.timeout_seconds, 4),
                    )
                    if r_wiki.status_code == 200:
                        hits = r_wiki.json().get("query", {}).get("search", [])
                        for hit in hits:
                            title = hit.get("title", "")
                            snippet = self._clean_html(hit.get("snippet", ""))
                            safe_title = urllib.parse.quote(title.replace(" ", "_"))
                            page_url = f"https://en.wikipedia.org/wiki/{safe_title}"

                            if page_url in seen_urls or not title:
                                continue
                            seen_urls.add(page_url)

                            # Try to fetch lead extract for top encyclopedic hit
                            try:
                                r_sum = requests.get(
                                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{safe_title}",
                                    headers=headers,
                                    timeout=min(self.timeout_seconds, 3),
                                )
                                if r_sum.status_code == 200:
                                    extract = r_sum.json().get("extract")
                                    if extract:
                                        snippet = extract
                            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                                pass

                            results.append(SearchResult(title=title, url=page_url, snippet=snippet))
                            if len(results) >= max_results:
                                break
                except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
                    logger.debug(f"Wikipedia search failed for '{wq}': {exc}")

        # 3. Google News RSS for real-time news, awards, and recent developments
        if self.specialized_fallbacks and len(results) < max_results:
            try:
                from bs4 import BeautifulSoup
                news_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(cleaned_query)}"
                resp_news = requests.get(news_url, headers=headers, timeout=min(self.timeout_seconds, 4))
                if resp_news.status_code == 200:
                    soup = BeautifulSoup(resp_news.text, "html.parser")
                    items = soup.find_all("item")
                    for item in items[:max_results - len(results)]:
                        t_elem = item.find("title")
                        l_elem = item.find("link")
                        p_elem = item.find("pubdate")
                        title = t_elem.get_text(strip=True) if t_elem else ""
                        url = l_elem.get_text(strip=True) if l_elem else ""
                        if not url and l_elem and l_elem.next_sibling:
                            url = str(l_elem.next_sibling).strip()
                        pub = p_elem.get_text(strip=True) if p_elem else ""
                        if not title or not url or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        snippet = f"[{pub}] {title}" if pub else title
                        results.append(SearchResult(title=title, url=url, snippet=snippet))
                        if len(results) >= max_results:
                            break
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
                logger.debug(f"Google News RSS search failed: {exc}")

        return results[:max_results]