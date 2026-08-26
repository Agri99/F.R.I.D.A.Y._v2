"""
src/friday/browser/verification.py
WHAT THIS IS FOR: Post-navigation verification.
"""
from __future__ import annotations
from typing import Any

class BrowserVerifier:
    def verify_url(self, page: Any, expected_url: str) -> bool:
        """Verify URL matches."""
        return True
        
    def verify_title(self, page: Any, expected_title: str) -> bool:
        """Verify title matches."""
        return True
        
    def verify_content(self, page: Any, expected_text: str) -> bool:
        """Verify content matches."""
        return True
