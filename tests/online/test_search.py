"""
tests/online/test_search.py

Unit tests for WebSearchProvider (SearXNG primary, Wikipedia and Google News fallbacks).
All external HTTP requests are mocked to ensure deterministic, isolated execution.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from friday.online.search import SearchResult, WebSearchProvider


def test_empty_query_returns_empty_list():
    provider = WebSearchProvider()
    with patch("requests.get") as mock_get:
        assert provider.search("") == []
        assert provider.search("   ") == []
        assert not mock_get.called


def test_searxng_successful_json_mapping():
    provider = WebSearchProvider(base_url="http://127.0.0.1:8080")
    fake_response = {
        "results": [
            {
                "title": "Python 3.14 Release Notes",
                "url": "https://docs.python.org/3.14",
                "content": "Python 3.14 is the latest version of Python.",
            },
            {
                "title": "Python Official Site",
                "url": "https://www.python.org",
                "snippet": "Welcome to Python.org",
            },
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response

    with patch("requests.get", return_value=mock_resp) as mock_get:
        results = provider.search("python", max_results=5)

        assert len(results) == 2
        assert isinstance(results[0], SearchResult)
        assert results[0].title == "Python 3.14 Release Notes"
        assert results[0].url == "https://docs.python.org/3.14"
        assert results[0].snippet == "Python 3.14 is the latest version of Python."
        assert results[1].title == "Python Official Site"
        assert results[1].snippet == "Welcome to Python.org"

        # Verify SearXNG endpoint and params were called
        mock_get.assert_called()
        first_call_url = mock_get.call_args_list[0][0][0]
        assert "127.0.0.1:8080/search" in first_call_url


def test_searxng_missing_content_fallback():
    provider = WebSearchProvider()
    fake_response = {
        "results": [
            {
                "title": "Title Without Content",
                "url": "https://example.com/no-content",
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response

    with patch("requests.get", return_value=mock_resp):
        results = provider.search("test", max_results=1)
        assert len(results) == 1
        assert results[0].snippet == ""


def test_searxng_duplicate_urls_removed():
    provider = WebSearchProvider(specialized_fallbacks=False)
    fake_response = {
        "results": [
            {
                "title": "First Entry",
                "url": "https://example.com/dup",
                "content": "Content 1",
            },
            {
                "title": "Duplicate Entry",
                "url": "https://example.com/dup",
                "content": "Content 2",
            },
            {
                "title": "Unique Entry",
                "url": "https://example.com/unique",
                "content": "Content 3",
            },
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response

    with patch("requests.get", return_value=mock_resp):
        results = provider.search("test", max_results=5)
        assert len(results) == 2
        assert results[0].url == "https://example.com/dup"
        assert results[1].url == "https://example.com/unique"


def test_max_results_respected():
    provider = WebSearchProvider(specialized_fallbacks=False)
    fake_response = {
        "results": [
            {"title": f"Result {i}", "url": f"https://example.com/{i}", "content": f"Snippet {i}"}
            for i in range(10)
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response

    with patch("requests.get", return_value=mock_resp):
        results = provider.search("test", max_results=3)
        assert len(results) == 3


def test_timeout_and_connection_errors_handled_gracefully():
    provider = WebSearchProvider(specialized_fallbacks=False)

    with patch("requests.get", side_effect=requests.exceptions.Timeout("Timeout")):
        results = provider.search("test query")
        assert results == []

    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("Refused")):
        results = provider.search("test query")
        assert results == []


def test_http_403_searxng_triggers_fallback():
    provider = WebSearchProvider(specialized_fallbacks=True)

    def side_effect(url, *args, **kwargs):
        resp = MagicMock()
        if "127.0.0.1:8080" in url:
            resp.status_code = 403
            resp.text = "Forbidden"
            return resp
        elif "wikipedia.org/w/api.php" in url:
            resp.status_code = 200
            resp.json.return_value = {
                "query": {
                    "search": [
                        {
                            "title": "Fallback Wiki Article",
                            "snippet": "Information from Wikipedia.",
                        }
                    ]
                }
            }
            return resp
        elif "wikipedia.org/api/rest_v1" in url:
            resp.status_code = 200
            resp.json.return_value = {"extract": "Detailed encyclopedic lead extract."}
            return resp
        resp.status_code = 404
        return resp

    with patch("requests.get", side_effect=side_effect):
        results = provider.search("knowledge query", max_results=3)
        assert len(results) >= 1
        assert "wikipedia" in results[0].url.lower()
        assert results[0].title == "Fallback Wiki Article"


def test_google_news_rss_fallback():
    provider = WebSearchProvider(specialized_fallbacks=True)

    def side_effect(url, *args, **kwargs):
        resp = MagicMock()
        if "127.0.0.1:8080" in url:
            resp.status_code = 500
            return resp
        elif "wikipedia.org" in url:
            resp.status_code = 200
            resp.json.return_value = {"query": {"search": []}}
            return resp
        elif "news.google.com" in url:
            resp.status_code = 200
            resp.text = """
            <rss><channel>
                <item>
                    <title>Breaking News: Major Discovery Announced</title>
                    <link>https://news.example.com/item1</link>
                    <pubDate>Sun, 27 Sep 2026 01:00:00 GMT</pubDate>
                </item>
            </channel></rss>
            """
            return resp
        resp.status_code = 404
        return resp

    with patch("requests.get", side_effect=side_effect):
        results = provider.search("breaking discovery", max_results=2)
        assert len(results) == 1
        assert results[0].title == "Breaking News: Major Discovery Announced"
        assert results[0].url == "https://news.example.com/item1"


def test_no_direct_ddg_endpoints_called():
    provider = WebSearchProvider(specialized_fallbacks=True)
    called_urls: list[str] = []

    def tracking_get(url, *args, **kwargs):
        called_urls.append(url)
        resp = MagicMock()
        resp.status_code = 200
        if "format=json" in str(kwargs.get("params", {})):
            resp.json.return_value = {"results": []}
        else:
            resp.json.return_value = {"query": {"search": []}}
            resp.text = "<rss></rss>"
        return resp

    with patch("requests.get", side_effect=tracking_get):
        provider.search("check ddg absence")

    for url in called_urls:
        assert "duckduckgo.com" not in url.lower()
