"""
src/friday/browser/extractor.py
WHAT THIS IS FOR: Page content extraction.
"""
from __future__ import annotations
from typing import Any

class PageExtractor:
    def extract_text(self, page: Any) -> str:
        """Extract text from page."""
        return "Stub text"
        
    def extract_links(self, page: Any) -> list[dict]:
        """Extract links from page."""
        return []
        
    def extract_forms(self, page: Any) -> list[dict]:
        """Extract forms from page."""
        return []
        
    def extract_structured(self, page: Any) -> dict:
        """Extract structured data."""
        return {
            "title": "Stub Title",
            "url": "http://stub",
            "text": self.extract_text(page),
            "links": self.extract_links(page),
            "forms": self.extract_forms(page)
        }
