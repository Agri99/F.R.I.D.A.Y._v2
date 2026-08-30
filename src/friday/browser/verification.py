"""
src/friday/browser/verification.py

WHAT THIS IS FOR:
Post-navigation and post-action verification for browser operations.
Verifies page status, URL matches, expected content presence, and detects error states.
"""

from __future__ import annotations

import re
from typing import Any


class BrowserVerifier:
    """Verifies that browser actions produced the expected outcome."""

    def verify_url(self, actual_url: str, expected_url: str) -> bool:
        """Check if actual URL matches or contains expected URL."""
        if not actual_url or not expected_url:
            return False
        return expected_url.lower() in actual_url.lower()

    def verify_title(self, page_html_or_title: str, expected_title_substring: str) -> bool:
        """Check if page title matches expectation."""
        if not expected_title_substring:
            return True
        title = page_html_or_title
        if "<title>" in page_html_or_title:
            match = re.search(r"<title>(.*?)</title>", page_html_or_title, re.IGNORECASE | re.DOTALL)
            title = match.group(1).strip() if match else ""
        return expected_title_substring.lower() in title.lower()

    def verify_content(self, page_html_or_text: str, expected_text: str) -> bool:
        """Check if expected text is present in the rendered content."""
        if not expected_text:
            return True
        return expected_text.lower() in page_html_or_text.lower()

    def is_error_page(self, html_or_text: str, status_code: int | None = None) -> bool:
        """Detect HTTP error pages, Cloudflare challenge walls, or 404/500 errors."""
        if status_code and status_code >= 400:
            return True

        text_lower = html_or_text.lower()
        error_indicators = (
            "404 not found",
            "502 bad gateway",
            "503 service unavailable",
            "access denied",
            "cloudflare checking your browser",
            "attention required! | cloudflare",
            "this site can't be reached",
            "dns_probe_finished_nxdomain",
        )
        return any(indicator in text_lower for indicator in error_indicators)
