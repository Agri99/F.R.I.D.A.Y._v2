from __future__ import annotations
from typing import Any, Dict

def build_schema(properties: Dict[str, Any], required: list[str] = None) -> dict:
    """Helper to build a JSON schema dict for tool parameters."""
    return {
        "type": "object",
        "properties": properties,
        "required": required or []
    }

TIER_TO_SCOPES = {
    "GREEN": ["system.read", "filesystem.read", "windows.observe", "browser.read", "gmail.read", "calendar.read"],
    "YELLOW": ["system.interact", "windows.interact", "browser.navigate", "system.control"],
    "ORANGE": ["filesystem.write", "calendar.write", "gmail.send"],
    "RED": ["filesystem.delete", "system.control", "calendar.write"]
}

def standard_verify_file_exists(path: str) -> bool:
    from pathlib import Path
    return Path(path).exists()
