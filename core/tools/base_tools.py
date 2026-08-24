"""
core/tools/base_tools.py

WHAT THIS IS FOR:
The first two real tools, deliberately picked to be one GREEN
(read-only) and one ORANGE (writes to disk) tool. They exist to prove
the registry -> policy -> execution wiring actually works end to end,
not to be a real tool catalog yet.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from core.security.policy import RiskTier
from core.tools.registry import Tool


def _get_time() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


get_time_tool = Tool(
    name="system.get_time",
    description="Get the current local date and time.",
    tier=RiskTier.GREEN,
    input_schema={"type": "object", "properties": {}, "required": []},
    handler=_get_time,
)


def _write_note(filename: str, content: str, notes_dir: str = "./data/notes") -> str:
    Path(notes_dir).mkdir(parents=True, exist_ok=True)
    path = Path(notes_dir) / filename
    path.write_text(content, encoding="utf-8")
    return str(path)


write_note_tool = Tool(
    name="filesystem.write_note",
    description="Write a plain-text note file to the local notes directory.",
    tier=RiskTier.ORANGE,  # writes to disk -> not auto-approved, Principle G
    input_schema={
        "type": "object",
        "properties": {
            "filename": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["filename", "content"],
    },
    handler=_write_note,
)


def register_base_tools(registry) -> None:
    registry.register(get_time_tool)
    registry.register(write_note_tool)
