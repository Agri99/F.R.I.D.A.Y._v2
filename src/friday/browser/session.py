"""
src/friday/browser/session.py

WHAT THIS IS FOR:
Browser session isolation (blueprint §39).

Creates a dedicated FRIDAY browser context with its own:
- Cookies
- Local storage
- Downloads directory
- Session state

This ensures FRIDAY never silently automates the user's normal browser
profile. Authenticated access is an explicit configuration decision.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from playwright.async_api import BrowserContext, Browser, async_playwright
except ImportError:
    BrowserContext = Any  # type: ignore
    Browser = Any  # type: ignore


@dataclass
class SessionConfig:
    """Configuration for the isolated browser session."""
    headless: bool = True
    user_data_dir: str | None = None  # None = auto temp dir
    downloads_dir: str | None = None
    viewport_width: int = 1280
    viewport_height: int = 720
    user_agent: str | None = None
    locale: str = "en-US"
    timezone_id: str = "UTC"
    permissions: list[str] = None  # e.g., ["geolocation", "notifications"]
    bypass_csp: bool = False
    ignore_https_errors: bool = True


class BrowserSession:
    """Isolated browser session with dedicated profile and storage."""

    def __init__(
        self,
        config: SessionConfig | None = None,
        browser: Browser | None = None,
    ) -> None:
        self.config = config or SessionConfig()
        self._browser: Browser | None = browser
        self._context: BrowserContext | None = None
        self._playwright = None
        self._temp_dir: str | None = None
        self._owned_browser = False

    async def launch(self) -> None:
        """Launch the isolated browser context."""
        import asyncio
        from playwright.async_api import async_playwright

        if self._context is not None:
            return  # Already launched

        # Create temp directory for user data if not provided
        if self.config.user_data_dir is None:
            self._temp_dir = tempfile.mkdtemp(prefix="friday_browser_")
            user_data_dir = self._temp_dir
        else:
            user_data_dir = self.config.user_data_dir
            self._temp_dir = None

        # Setup downloads directory
        if self.config.downloads_dir is None:
            downloads_dir = Path(self._temp_dir or tempfile.gettempdir()) / "downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)
            self.config.downloads_dir = str(downloads_dir)

        # Launch Playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=self.config.headless is not False,  # Default to headless
            viewport={"width": self.config.viewport_width, "height": self.config.viewport_height},
            user_agent=self.config.user_agent,
            locale=self.config.locale,
            timezone_id=self.config.timezone_id,
            permissions=self.config.permissions or [],
            bypass_csp=self.config.bypass_csp,
            ignore_https_errors=self.config.ignore_https_errors,
            accept_downloads=True,
            downloads_path=self.config.downloads_dir,
        )

    async def close(self) -> None:
        """Close the browser context and clean up."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        # Clean up temp directory if we created it
        if self._temp_dir:
            import shutil
            try:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass

    @property
    def context(self) -> "BrowserContext":
        """Get the browser context."""
        if not self._context:
            raise RuntimeError("Session not launched. Call launch() first.")
        return self._context

    @property
    def browser(self) -> "Browser":
        if not self._browser:
            raise RuntimeError("Browser not launched. Call launch() first.")
        return self._browser

    def page(self):
        """Get the first page or create a new one."""
        if not self._context:
            raise RuntimeError("Session not launched. Call launch() first.")
        if self._context.pages:
            return self._context.pages[0]
        return self._context.new_page()

    async def new_page(self):
        """Create a new page in this session."""
        if not self._context:
            raise RuntimeError("Session not launched. Call launch() first.")
        return await self._context.new_page()

    async def clear_cookies(self) -> None:
        """Clear all cookies in this session."""
        if self._context:
            await self._context.clear_cookies()

    async def clear_storage(self) -> None:
        """Clear all local/session storage."""
        if self._context:
            await self._context.clear_cookies()
            # Note: Playwright doesn't have a direct API for localStorage/sessionStorage
            # Clear via JS on each page
            for page in self._context.pages:
                await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")


@dataclass
class SessionManager:
    """Manages multiple isolated browser sessions."""

    _sessions: dict[str, "BrowserSession"] = field(default_factory=dict)
    _default_session: "BrowserSession | None" = None

    def get_session(self, name: str = "default") -> "BrowserSession":
        """Get or create a named session."""
        if name not in self._sessions:
            self._sessions[name] = BrowserSession()
        return self._sessions[name]

    async def get_default_session(self) -> "BrowserSession":
        """Get or create the default session."""
        if self._default_session is None:
            self._default_session = BrowserSession()
            await self._default_session.launch()
        return self._default_session

    async def close_all(self) -> None:
        """Close all sessions."""
        for session in self._sessions.values():
            try:
                await session.close()
            except Exception:
                pass
        self._sessions.clear()
        if self._default_session:
            try:
                await self._default_session.close()
            except Exception:
                pass
            self._default_session = None


# Global session manager instance
_global_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get the global session manager."""
    global _global_session_manager
    if _global_session_manager is None:
        _global_session_manager = SessionManager()
    return _global_session_manager


__all__ = [
    "SessionConfig",
    "BrowserSession",
    "SessionManager",
    "get_session_manager",
]