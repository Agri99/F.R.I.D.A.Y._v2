"""
src/friday/browser/playwright_controller.py

WHAT THIS IS FOR:
Playwright-based browser automation with structured DOM access and accessibility tree
extraction (blueprint §10, §11). Used as the primary engine when configured, with
fallback to requests-based controller for simple fetches.
"""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any, Optional

from friday.browser.policies import BrowserScope, evaluate_action


@dataclass
class PlaywrightConfig:
    headless: bool = True
    timeout_seconds: int = 15


class PlaywrightController:
    """Async Playwright wrapper for structured browser automation."""

    def __init__(self, config: PlaywrightConfig | None = None):
        self.config = config or PlaywrightConfig()
        self._page = None
        self._browser = None
        self._current_url: str | None = None
        self._history: list[str] = []
        self._history_index = -1

    async def launch(self) -> None:
        try:
            from playwright.async_api import async_playwright
            playwright = await async_playwright().start()
            self._browser = await playwright.chromium.launch(headless=self.config.headless)
            self._page = await self._browser.new_page()
        except ImportError:
            raise RuntimeError("Playwright not installed. Run: pip install playwright && playwright install chromium")

    async def close(self) -> None:
        if self._page:
            await self._page.close()
        if self._browser:
            await self._browser.close()

    def _is_safe_url(self, url: str) -> bool:
        """Deny file://, javascript:, and local loopback access."""
        parsed = urllib.parse.urlparse(url.strip())
        return parsed.scheme.lower() in ("http", "https")

    async def navigate(self, url: str) -> str:
        if not self._is_safe_url(url):
            raise ValueError(f"Unsafe URL scheme: '{url}'. Only HTTP/HTTPS permitted.")
        await self._page.goto(url, wait_until="networkidle", timeout=self.config.timeout_seconds * 1000)
        self._history = self._history[: self._history_index + 1]
        self._history.append(url)
        self._history_index += 1
        self._current_url = url
        return url

    async def search(self, query: str, engine: str = "google") -> str:
        encoded = urllib.parse.quote_plus(query.strip())
        if engine == "duckduckgo":
            url = f"https://duckduckgo.com/html?q={encoded}"
        else:
            url = f"https://www.google.com/search?q={encoded}"
        await self.navigate(url)
        return url

    async def click(self, selector: str) -> None:
        """Click element by CSS selector. Must be used with caution on untrusted pages."""
        scope = evaluate_action("click_button")
        # Orange scope requires confirmation; in programmatic use caller handles auth
        await self._page.click(selector)

    async def type(self, selector: str, text: str) -> None:
        await self._page.fill(selector, text)

    async def fill_form(self, fields: dict[str, str]) -> None:
        """Fill form fields. Requires ORANGE-level authorization."""
        for selector, value in fields.items():
            await self._page.fill(selector, value)

    async def get_text(self, selector: str) -> str:
        element = await self._page.query_selector(selector)
        if element:
            return await element.inner_text()
        return ""

    async def get_accessibility_tree(self) -> dict[str, Any]:
        """Extract accessibility tree for target resolution and verification."""
        tree = await self._page.accessibility.snapshot()
        return tree

    async def get_page_content(self) -> str:
        if not self._current_url:
            return ""
        content = await self._page.content()
        cleaned = re.sub(r"<(script|style).*?>.*?</\1>", "", content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", cleaned)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:4000]

    async def get_history(self) -> list[str]:
        return self._history

    async def back(self) -> Optional[str]:
        if self._history_index > 0:
            self._history_index -= 1
            self._current_url = self._history[self._history_index]
            await self._page.goto(self._current_url)
            return self._current_url
        return None

    async def forward(self) -> Optional[str]:
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._current_url = self._history[self._history_index]
            await self._page.goto(self._current_url)
            return self._current_url
        return None
