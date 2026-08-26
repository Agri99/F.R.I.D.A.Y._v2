"""
src/friday/browser/safety.py
WHAT THIS IS FOR: Prompt-injection defense and URL safety.
"""
from __future__ import annotations
from pathlib import Path

class BrowserSafety:
    def sanitize_content(self, content: str) -> str:
        """Strip potential prompt-injection from web content."""
        return content.replace("IGNORE ALL PREVIOUS INSTRUCTIONS", "[REDACTED]")
        
    def is_safe_url(self, url: str) -> bool:
        """Check if URL is safe."""
        return not url.startswith("file://")
        
    def get_dedicated_profile_path(self) -> Path:
        """Get path for sandboxed browser profile."""
        return Path("workspace/browser_profile")
