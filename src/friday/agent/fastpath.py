"""
src/friday/agent/fastpath.py

WHAT THIS IS FOR:
Matches direct user intents (orb controls, shutdown, quick actions)
to bypass LLM planning while maintaining security policy parity (blueprint §17.2, §32.3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_NON_ALNUM = re.compile(r"[^a-z0-9\s]+")
_SPACES = re.compile(r"\s+")


@dataclass
class FastPathResult:
    tool_name: str
    arguments: dict[str, Any]
    success_reply: str


class FastPathRouter:
    """Matches direct intents to bypass LLM planning while using the same execution path."""

    HIDE_PHRASES = (
        "hide yourself",
        "hide the orb",
        "hide orb",
        "hide",
        "disappear",
        "go away",
        "stay out of sight",
    )
    SHOW_PHRASES = (
        "come back",
        "show yourself",
        "show the orb",
        "show orb",
        "appear",
        "unhide",
    )
    SHUTDOWN_EXACT = {
        "goodbye",
        "goodbye friday",
        "bye",
        "bye friday",
        "shut down",
        "shutdown",
        "shut down friday",
        "shutdown friday",
        "exit",
        "quit",
        "turn off",
        "turn yourself off",
        "close friday",
    }

    def _normalize(self, text: str) -> str:
        return _SPACES.sub(" ", _NON_ALNUM.sub(" ", (text or "").lower())).strip()

    def _negated(self, text: str) -> bool:
        return text.startswith("do not ") or text.startswith("dont ") or " never " in f" {text} "

    def match(self, user_text: str, last_assistant_text: str | None = None) -> FastPathResult | None:
        text = self._normalize(user_text)
        if not text or self._negated(text):
            return None

        if self._is_shutdown(text):
            return FastPathResult(tool_name="system.shutdown_friday", arguments={}, success_reply="Shutting down. Goodbye!")

        if any(text == p or text.startswith(p) for p in self.SHOW_PHRASES):
            return FastPathResult(tool_name="system.toggle_orb", arguments={"visible": True}, success_reply="I'm back.")

        if any(text == p or text.startswith(p) for p in self.HIDE_PHRASES):
            return FastPathResult(tool_name="system.toggle_orb", arguments={"visible": False}, success_reply="Okay, I'll stay out of sight.")

        return None

    def _is_shutdown(self, text: str) -> bool:
        if any(p in text for p in self.HIDE_PHRASES):
            return False
        if text in self.SHUTDOWN_EXACT:
            return True
        if "shut down" in text or text.startswith("shutdown") or "goodbye" in text or "turn off" in text:
            return True
        return False
