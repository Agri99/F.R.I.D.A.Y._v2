"""
tests/browser/test_playwright_controller.py

WHAT THIS IS FOR:
Unit tests for the Playwright controller (mocked since Playwright requires
browser binaries). Verifies async API surface and safety logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Skip entire module if playwright isn't installed
playwright = pytest.importorskip("playwright")


class TestPlaywrightController:
    @pytest.fixture
    def mock_page(self):
        """Create a mock Playwright page."""
        page = AsyncMock()
        page.click = AsyncMock()
        page.fill = AsyncMock()
        # query_selector returns an element mock with inner_text method
        element_mock = AsyncMock()
        element_mock.inner_text = AsyncMock(return_value="Sample text")
        page.query_selector = AsyncMock(return_value=element_mock)
        page.goto = AsyncMock()
        page.accessibility = MagicMock()
        page.accessibility.snapshot = AsyncMock(return_value={"role": "document"})
        page.content = AsyncMock(return_value="<html><body>Test</body></html>")
        return page

    @pytest.fixture
    def mock_browser(self, mock_page):
        """Create a mock browser."""
        browser = AsyncMock()
        browser.new_page = AsyncMock(return_value=mock_page)
        browser.close = AsyncMock()
        return browser

    @pytest.fixture
    def controller(self, mock_browser, mock_page):
        """Create a controller with mocked Playwright."""
        with patch("playwright.async_api.async_playwright") as mock_playwright_mod:
            mock_pw = MagicMock()
            mock_pw.start = AsyncMock()
            mock_pw.start.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_playwright_mod.return_value = mock_pw

            from friday.browser.playwright_controller import PlaywrightController, PlaywrightConfig
            config = PlaywrightConfig(headless=True, timeout_seconds=5)
            ctrl = PlaywrightController(config)
            ctrl._browser = mock_browser
            ctrl._page = mock_page
            yield ctrl

    @pytest.mark.asyncio
    async def test_launch_and_close(self, controller):
        await controller.launch()
        assert controller._browser is not None
        assert controller._page is not None

        await controller.close()
        controller._page.close.assert_awaited_once()
        controller._browser.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_navigate_safe_url(self, controller):
        await controller.navigate("https://example.com")
        controller._page.goto.assert_awaited_with(
            "https://example.com",
            wait_until="networkidle",
            timeout=5000
        )

    @pytest.mark.asyncio
    async def test_navigate_unsafe_url_raises(self, controller):
        with pytest.raises(ValueError, match="Unsafe URL scheme"):
            await controller.navigate("file:///etc/passwd")

    @pytest.mark.asyncio
    async def test_click_selector(self, controller):
        await controller.click("button.submit")
        controller._page.click.assert_awaited_with("button.submit")

    @pytest.mark.asyncio
    async def test_type_text(self, controller):
        await controller.type("input[name='search']", "test query")
        controller._page.fill.assert_awaited_with("input[name='search']", "test query")

    @pytest.mark.asyncio
    async def test_get_text(self, controller):
        result = await controller.get_text("div.result")
        assert result == "Sample text"
        controller._page.query_selector.assert_awaited_with("div.result")

    @pytest.mark.asyncio
    async def test_get_accessibility_tree(self, controller):
        tree = await controller.get_accessibility_tree()
        assert tree == {"role": "document"}
        controller._page.accessibility.snapshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_page_content(self, controller):
        controller._current_url = "https://example.com"
        content = await controller.get_page_content()
        assert "Test" in content

    def test_is_safe_url_rejects_unsafe(self, controller):
        assert controller._is_safe_url("https://example.com") is True
        assert controller._is_safe_url("file:///etc/passwd") is False
        assert controller._is_safe_url("javascript:alert(1)") is False