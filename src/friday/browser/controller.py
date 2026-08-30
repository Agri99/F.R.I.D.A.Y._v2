"""
src/friday/browser/controller.py

WHAT THIS IS FOR:
Structured web navigation and browser controller (blueprint §9, §20).
Supports dual engine: Playwright for rich DOM automation when installed,
falling back to requests/urllib safe extraction.
Integrated with BrowserSafety, BrowserNavigator for security hardening.
"""

from __future__ import annotations

import re
import urllib.parse
import webbrowser
from dataclasses import dataclass
from typing import Any, Optional

import requests

from friday.browser.policies import BrowserScope, evaluate_action
from friday.browser.safety import BrowserSafety, SanitizationResult
from friday.browser.navigation import BrowserNavigator, NavigationResult
from friday.browser.extractor import PageExtractor
from friday.online.network import NetworkMonitor
from friday.security.policy import PolicyEngine


@dataclass
class BrowserConfig:
    engine: str = "requests"  # "requests" | "playwright"
    headless: bool = True
    timeout_seconds: int = 15


class BrowserController:
    """
    Controls browser navigation and safe content extraction.
    Priority: Playwright (if configured & available) -> Safe HTTP/Requests -> Default system browser.
    All web content treated as UNTRUSTED data.
    """

    def __init__(self, config: BrowserConfig | None = None,
                 policy_engine: PolicyEngine | None = None,
                 safety: BrowserSafety | None = None):
        self.config = config or BrowserConfig()
        self._current_url: str | None = None
        self._history: list[str] = []
        self._history_index = -1
        self._playwright = None

        # Security components
        self.safety = safety or BrowserSafety()
        self.navigator = BrowserNavigator(
            timeout_seconds=self.config.timeout_seconds,
            policy_engine=policy_engine,
            safety=self.safety
        )
        self.extractor = PageExtractor()
        self.network_monitor = NetworkMonitor()

    async def _ensure_playwright(self) -> Optional["PlaywrightController"]:
        """Lazily initialize Playwright controller if engine is configured."""
        if self.config.engine != "playwright":
            return None
        if self._playwright is not None:
            return self._playwright
        try:
            from friday.browser.playwright_controller import PlaywrightController, PlaywrightConfig
            pc = PlaywrightController(PlaywrightConfig(headless=self.config.headless, timeout_seconds=self.config.timeout_seconds))
            await pc.launch()
            self._playwright = pc
            return self._playwright
        except Exception:
            return None

    def _is_safe_url(self, url: str) -> bool:
        """Deny file://, javascript:, and local loopback access."""
        return self.safety.is_safe_url(url)

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
        result = self.navigator.search(query)
        if result.success:
            self._current_url = result.url
            return result.url
        raise ValueError(f"Search failed: {result.error}")

    def fetch_text_content(self, url: str) -> str:
        """Fetch and extract clean plain text from a URL."""
        if not self._is_safe_url(url):
            raise ValueError("Only http:// and https:// URLs allowed.")

        result = self.navigator.navigate(url, action_type="fetch")
        if not result.success:
            raise ValueError(f"Fetch failed: {result.error}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 FRIDAY/3.0"
        }
        resp = requests.get(url, headers=headers, timeout=self.config.timeout_seconds)
        resp.raise_for_status()

        html = resp.text
        # Strip script, style, SVG, and noscript tags
        cleaned = re.sub(
            r"<(script|style|svg|noscript).*?>.*?</\1>",
            "",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Strip HTML tags
        text = re.sub(r"<[^>]+>", " ", cleaned)
        # Clean extra whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Sanitize for LLM consumption
        sanitized = self.safety.sanitize_for_llm(text)
        return sanitized[:4000]

    def get_page_content(self) -> str:
        """Get text content of current URL (sync fallback)."""
        if not self._current_url:
            return "No URL currently open."
        try:
            return self.fetch_text_content(self._current_url)
        except Exception as exc:
            return f"Failed to fetch content from {self._current_url}: {exc}"

    async def get_page_content_async(self) -> str:
        """Get text content using Playwright if available, else sync fallback."""
        pc = await self._ensure_playwright()
        if pc:
            return await pc.get_page_content()
        return self.get_page_content()

    def navigate(self, url: str) -> bool:
        result = self.navigator.navigate(url, action_type="navigate")
        if result.success:
            self._current_url = result.url
            return True
        raise ValueError(f"Navigation failed: {result.error}")

    async def navigate_async(self, url: str) -> bool:
        """Navigate using Playwright if available, else fallback."""
        pc = await self._ensure_playwright()
        if pc:
            await pc.navigate(url)
            self._current_url = url
            return True
        return self.navigate(url)

    def back(self) -> bool:
        if self._history_index > 0:
            self._history_index -= 1
            self._current_url = self._history[self._history_index]
            result = self.navigator.navigate(self._current_url, action_type="back")
            return result.success
        return False

    def forward(self) -> bool:
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._current_url = self._history[self._history_index]
            result = self.navigator.navigate(self._current_url, action_type="forward")
            return result.success
        return False

    def extract_page(self, html_or_response: Any, base_url: str = "") -> dict[str, Any]:
        """Extract structured data from page with sanitization."""
        html = getattr(html_or_response, "text", str(html_or_response))
        url = getattr(html_or_response, "url", base_url)

        # Sanitize before extraction
        sanitized_html = self.safety.sanitize_for_llm(html)

        extracted = self.extractor.extract_structured(sanitized_html, base_url=url)

        # Sanitize all extracted text fields
        if "text" in extracted:
            extracted["text"] = self.safety.sanitize_for_llm(extracted["text"], max_length=4000)

        if "links" in extracted:
            for link in extracted["links"]:
                link["text"] = self.safety.sanitize_for_llm(link.get("text", ""), max_length=200)

        if "forms" in extracted:
            for form in extracted["forms"]:
                for inp in form.get("inputs", []):
                    inp["name"] = self.safety.sanitize_for_llm(inp.get("name", ""), max_length=100)

        return extracted

    def sanitize_content(self, content: str) -> SanitizationResult:
        """Sanitize content for safe LLM consumption."""
        return self.safety.sanitize_content(content)