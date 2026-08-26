"""
Browser security policies (§20).
"""
from __future__ import annotations

import enum

class BrowserScope(enum.Enum):
    GREEN = "GREEN"    # Observe, safe
    YELLOW = "YELLOW"  # Search, navigate
    ORANGE = "ORANGE"  # Submit forms, click non-navigation links
    RED = "RED"        # Upload files, checkout, execute JS

def evaluate_action(action_type: str) -> BrowserScope:
    """Map browser action to risk scope."""
    action_type = action_type.lower()
    if action_type in ("read", "observe", "get_content"):
        return BrowserScope.GREEN
    if action_type in ("search", "navigate", "back", "forward"):
        return BrowserScope.YELLOW
    if action_type in ("submit", "click_button", "fill_form"):
        return BrowserScope.ORANGE
    if action_type in ("upload", "download", "execute_script"):
        return BrowserScope.RED
    # Fail closed
    return BrowserScope.RED

def is_content_trusted() -> bool:
    """
    Web content is UNTRUSTED data - never trusted as agent commands.
    """
    return False
