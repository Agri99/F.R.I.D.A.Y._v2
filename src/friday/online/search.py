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
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchProvider:
    """Provides web search functionality across Google News RSS, Wikipedia, and DuckDuckGo."""

    def __init__(self, api_key: str | None = None, timeout_seconds: int = 6):
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _clean_html(self, text: str) -> str:
        return re.sub(r"<[^>]+>", "", text).strip()

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
        except Exception:
            pass

        # 1. Wikipedia Search API + REST Lead Extract (encyclopedic, lore, entities, games)
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
                r_wiki = requests.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": wq,
                        "format": "json",
                        "utf8": 1,
                    },
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
                        except Exception:
                            pass

                        results.append(SearchResult(title=title, url=page_url, snippet=snippet))
                        if len(results) >= max_results:
                            break
            except Exception as exc:
                logger.debug(f"Wikipedia search failed for '{wq}': {exc}")

        # 2. Google News RSS for real-time news, awards, and recent developments
        if len(results) < max_results:
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
                        pub = p_elem.get_text(strip=True) if p_elem else ""
                        if not title or not url or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        snippet = f"[{pub}] {title}" if pub else title
                        results.append(SearchResult(title=title, url=url, snippet=snippet))
                        if len(results) >= max_results:
                            break
            except Exception as exc:
                logger.debug(f"Google News RSS search failed: {exc}")


        # 3. DuckDuckGo Instant Answer API
        if len(results) < max_results:
            try:
                r_ddg = requests.get(
                    "https://api.duckduckgo.com/",
                    params={"q": cleaned_query, "format": "json"},
                    headers=headers,
                    timeout=min(self.timeout_seconds, 4),
                )
                if r_ddg.status_code in (200, 202):
                    data = r_ddg.json()
                    abstract = data.get("AbstractText", "")
                    abstract_url = data.get("AbstractURL", "")
                    heading = data.get("Heading", cleaned_query)
                    if abstract and abstract_url and abstract_url not in seen_urls:
                        seen_urls.add(abstract_url)
                        results.append(SearchResult(title=heading, url=abstract_url, snippet=abstract))
            except Exception as exc:
                logger.debug(f"DuckDuckGo API search failed: {exc}")

        # 4. DuckDuckGo Lite HTML fallback
        if len(results) < max_results:
            try:
                from bs4 import BeautifulSoup
                resp = requests.post(
                    "https://lite.duckduckgo.com/lite/",
                    data={"q": cleaned_query},
                    headers=headers,
                    timeout=min(self.timeout_seconds, 4),
                )
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    links = soup.find_all("a", class_="result-link")
                    snippets = soup.find_all("td", class_="result-snippet")
                    for i in range(min(len(links), len(snippets), max_results - len(results))):
                        raw_url = links[i].get("href", "")
                        clean_title = links[i].get_text(strip=True)
                        clean_snippet = snippets[i].get_text(strip=True)
                        if raw_url.startswith("//"):
                            raw_url = "https:" + raw_url
                        if clean_title and raw_url and raw_url not in seen_urls:
                            seen_urls.add(raw_url)
                            results.append(SearchResult(title=clean_title, url=raw_url, snippet=clean_snippet))
            except Exception as exc:
                logger.debug(f"DuckDuckGo Lite fallback failed: {exc}")

        return results[:max_results]


# Alias for backward compatibility
DuckDuckGoScraper = WebSearchProvider

