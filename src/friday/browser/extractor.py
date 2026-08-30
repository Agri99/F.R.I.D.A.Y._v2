"""
src/friday/browser/extractor.py

WHAT THIS IS FOR:
Extracts structured data, plain text, links, and forms from HTML web pages.
All extracted content is sanitized for safe LLM consumption.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any


class PageExtractor:
    """Extracts text, metadata, links, and forms from raw HTML or page objects."""

    def extract_text(self, html_or_text: str) -> str:
        """Extract clean readable text from HTML."""
        if not html_or_text:
            return ""
        # Strip script, style, SVG, and noscript tags
        cleaned = re.sub(
            r"<(script|style|svg|noscript).*?>.*?</\1>",
            "",
            html_or_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Extract main text by replacing tags with spaces
        text = re.sub(r"<[^>]+>", " ", cleaned)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def extract_title(self, html: str) -> str:
        """Extract title from HTML."""
        match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else "Untitled Page"

    def extract_links(self, html: str, base_url: str = "") -> list[dict[str, str]]:
        """Extract anchor links with href and text."""
        links: list[dict[str, str]] = []
        pattern = re.compile(r'<a\s+(?:[^>]*?\s+)?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
        for match in pattern.finditer(html):
            href, link_text = match.group(1).strip(), self.extract_text(match.group(2)).strip()
            if href and not href.startswith(("javascript:", "#", "mailto:", "tel:")):
                if base_url and not href.startswith(("http://", "https://")):
                    href = urllib.parse.urljoin(base_url, href)
                links.append({"text": link_text or href, "href": href})
        return links[:50]

    def extract_forms(self, html: str) -> list[dict[str, Any]]:
        """Extract form actions and inputs."""
        forms: list[dict[str, Any]] = []
        form_pattern = re.compile(r"<form\b(.*?)>(.*?)</form>", re.IGNORECASE | re.DOTALL)
        for form_match in form_pattern.finditer(html):
            form_attrs, form_body = form_match.group(1), form_match.group(2)
            action_match = re.search(r'action=["\']([^"\']*)["\']', form_attrs, re.IGNORECASE)
            method_match = re.search(r'method=["\']([^"\']*)["\']', form_attrs, re.IGNORECASE)

            inputs: list[dict[str, str]] = []
            input_pattern = re.compile(r'<input\b([^>]*?)>', re.IGNORECASE)
            for inp in input_pattern.finditer(form_body):
                attrs = inp.group(1)
                name = re.search(r'name=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
                type_ = re.search(r'type=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
                inputs.append({
                    "name": name.group(1) if name else "",
                    "type": type_.group(1) if type_ else "text",
                })

            forms.append({
                "action": action_match.group(1) if action_match else "",
                "method": (method_match.group(1) if method_match else "GET").upper(),
                "inputs": inputs,
            })
        return forms

    def extract_structured(self, html_or_response: Any, base_url: str = "") -> dict[str, Any]:
        """Extract structured document metadata, links, and forms."""
        html = getattr(html_or_response, "text", str(html_or_response))
        url = getattr(html_or_response, "url", base_url)
        return {
            "title": self.extract_title(html),
            "url": url,
            "text": self.extract_text(html)[:4000],
            "links": self.extract_links(html, base_url=url),
            "forms": self.extract_forms(html),
        }

    def extract_and_sanitize(self, html_or_response: Any, base_url: str = "",
                              safety_module: Any = None) -> dict[str, Any]:
        """Extract structured data and sanitize all text fields for LLM consumption."""
        # First extract normally
        extracted = self.extract_structured(html_or_response, base_url)

        # Sanitize all text fields if safety module provided
        if safety_module:
            # Sanitize main text
            if "text" in extracted:
                extracted["text"] = safety_module.sanitize_for_llm(extracted["text"], max_length=4000)

            # Sanitize link text
            if "links" in extracted:
                for link in extracted["links"]:
                    link["text"] = safety_module.sanitize_for_llm(link.get("text", ""), max_length=200)

            # Sanitize form inputs
            if "forms" in extracted:
                for form in extracted["forms"]:
                    for inp in form.get("inputs", []):
                        inp["name"] = safety_module.sanitize_for_llm(inp.get("name", ""), max_length=100)
                    if "action" in form:
                        form["action"] = safety_module.sanitize_for_llm(form.get("action", ""), max_length=500)

        return extracted
