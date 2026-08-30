"""
src/friday/online/sources.py

WHAT THIS IS FOR:
Source registry mapping online capability names to public API providers and offline fallbacks (§8, §20).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CapabilitySource:
    name: str
    primary_url: str
    fallback_strategy: str
    requires_auth: bool = False
    is_available: bool = True


class OnlineSourceRegistry:
    """Registry of online data sources with fallback definitions."""

    def __init__(self) -> None:
        self._sources: dict[str, CapabilitySource] = {
            "search": CapabilitySource(
                name="DuckDuckGo",
                primary_url="https://html.duckduckgo.com/html/",
                fallback_strategy="browser_open",
                requires_auth=False,
            ),
            "weather": CapabilitySource(
                name="wttr.in",
                primary_url="https://wttr.in/",
                fallback_strategy="cached_memory",
                requires_auth=False,
            ),
            "news": CapabilitySource(
                name="Google News RSS",
                primary_url="https://news.google.com/rss",
                fallback_strategy="error_message",
                requires_auth=False,
            ),
        }

    def get_source(self, capability: str) -> CapabilitySource | None:
        """Get source configuration for capability."""
        return self._sources.get(capability.lower())

    def list_sources(self) -> list[CapabilitySource]:
        """List all registered online capability sources."""
        return list(self._sources.values())

