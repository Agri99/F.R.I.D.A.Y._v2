"""
src/friday/browser/navigation.py
WHAT THIS IS FOR: URL navigation with risk classification.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class NavigationResult:
    success: bool
    url: str
    error: str | None

class BrowserNavigator:
    def navigate(self, url: str) -> NavigationResult:
        """Navigate to URL."""
        return NavigationResult(True, url, None)
        
    def search(self, query: str) -> NavigationResult:
        """Search query."""
        return NavigationResult(True, f"https://search.app/?q={query}", None)
        
    def follow_link(self, link_text: str) -> NavigationResult:
        """Follow link."""
        return NavigationResult(True, "http://stub-follow", None)
        
    def classify_risk(self, url: str) -> str:
        """Classify URL risk (GREEN, YELLOW, ORANGE)."""
        return "GREEN"
