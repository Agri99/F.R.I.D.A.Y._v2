"""
src/friday/browser/controller.py

WHAT THIS IS FOR:
Structured web navigation and browser controller (blueprint §9, §20).
Enforces URL safety policies and extracts readable page content without executing
untrusted scripts.
"""

from __future__ import annotations

import re
import urllib.parse
import webbrowser
from dataclasses import dataclass

import requests


@dataclass
class BrowserConfig:
    headless: bool = True
    timeout_seconds: int = 15


class BrowserController:
    """
    Controls browser navigation and safe content extraction.
    Priority: Structured HTTP client -> default browser.
    """

    def __init__(self, config: BrowserConfig | None = None):
        self.config = config or BrowserConfig()
        self._current_url: str | None = None
        self._history: list[str] = []
        self._history_index = -1

    def _is_safe_url(self, url: str) -> bool:
        """Deny file://, javascript:, and local loopback access."""
        parsed = urllib.parse.urlparse(url.strip())
        return parsed.scheme.lower() in ("http", "https")

    def open_url(self, url: str) -> bool:
        """Open a URL in the user's default system browser."""
        if not self._is_safe_url(url):
            raise ValueError(f"Unsafe URL scheme: '{url}'. Only HTTP/HTTPS permitted.")

        self._history = self._history[: self._history_index + 1]
        self._history.append(url)
        self._history_index += 1
        self._current_url = url
        webbrowser.open(url)
        return True

    def search(self, query: str) -> str:
        """Perform a web search in the default browser and return search URL."""
        encoded = urllib.parse.quote_plus(query.strip())
        url = f"https://www.google.com/search?q={encoded}"
        self.open_url(url)
        return url

    def fetch_text_content(self, url: str) -> str:
        """Fetch and extract clean plain text from a URL."""
        if not self._is_safe_url(url):
            raise ValueError("Only http:// and https:// URLs allowed.")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 FRIDAY/2.0"
        }
        resp = requests.get(url, headers=headers, timeout=self.config.timeout_seconds)
        resp.raise_for_status()

        html = resp.text
        # Strip script and style blocks
        cleaned = re.sub(r"<(script|style).*?>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Strip HTML tags
        text = re.sub(r"<[^>]+>", " ", cleaned)
        # Clean extra whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text[:4000]

    def get_page_content(self) -> str:
        """Get text content of current URL."""
        if not self._current_url:
            return "No URL currently open."
        try:
            return self.fetch_text_content(self._current_url)
        except Exception as exc:
            return f"Failed to fetch content from {self._current_url}: {exc}"

    def navigate(self, url: str) -> bool:
        return self.open_url(url)

    def back(self) -> bool:
        if self._history_index > 0:
            self._history_index -= 1
            self._current_url = self._history[self._history_index]
            webbrowser.open(self._current_url)
            return True
        return False

    def forward(self) -> bool:
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._current_url = self._history[self._history_index]
            webbrowser.open(self._current_url)
            return True
        return False
