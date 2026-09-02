"""
src/friday/agent/fastpath.py

WHAT THIS IS FOR:
Matches direct user intents (orb controls, volume, time queries, shutdown)
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
    risk_tier: str = "GREEN"
    capability: str = "SYSTEM"


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
    TIME_PHRASES = (
        "what time is it",
        "current time",
        "what is the time",
        "tell me the time",
    )

    # Explicit "go search for X" phrasings. Routed directly to online.search,
    # bypassing the model's tool choice entirely - the model already has
    # explicit instructions (system prompt + both browser tool descriptions)
    # to prefer online.search over browser.open for exactly this case, and
    # in practice still doesn't reliably follow them. Prompting alone was
    # tried twice and still failed, so this closes the gap the same way
    # shutdown/orb/volume already bypass unreliable LLM tool selection.
    SEARCH_TRIGGERS = (
        "find information about ",
        "find information on ",
        "find info about ",
        "find info on ",
        "look up ",
        "search for ",
        "search the web for ",
        "google ",
    )

    def _normalize(self, text: str) -> str:
        return _SPACES.sub(" ", _NON_ALNUM.sub(" ", (text or "").lower())).strip()

    def _negated(self, text: str) -> bool:
        return text.startswith("do not ") or text.startswith("dont ") or " never " in f" {text} "

    def match(self, user_text: str, last_assistant_text: str | None = None) -> FastPathResult | None:
        text = self._normalize(user_text)
        if not text or self._negated(text):
            return None

        # 1. Shutdown
        if self._is_shutdown(text):
            return FastPathResult(
                tool_name="system.shutdown_friday",
                arguments={},
                success_reply="Shutting down FRIDAY. Goodbye!",
                risk_tier="RED",
            )

        # 2. Orb visibility
        if any(text == p or text.startswith(p) for p in self.SHOW_PHRASES):
            return FastPathResult(
                tool_name="system.toggle_orb",
                arguments={"visible": True},
                success_reply="I'm back.",
            )

        if any(text == p or text.startswith(p) for p in self.HIDE_PHRASES):
            return FastPathResult(
                tool_name="system.toggle_orb",
                arguments={"visible": False},
                success_reply="Okay, I'll stay out of sight.",
            )

        # 3. Audio volume fastpaths
        if text in ("mute", "mute volume", "silence"):
            return FastPathResult(
                tool_name="audio.set_volume",
                arguments={"volume": 0},
                success_reply="Muted audio.",
            )
        if text in ("unmute", "restore volume"):
            return FastPathResult(
                tool_name="audio.set_volume",
                arguments={"volume": 50},
                success_reply="Volume set to 50%.",
            )

        # 4. Explicit "find/search/look up X" -> online.search directly.
        # Matched against the lowercased-but-unstripped text (not the fully
        # normalized `text` above) so the extracted query keeps its original
        # punctuation/casing - important for things like "C++" or proper nouns.
        lower_text = (user_text or "").strip().lower()
        for trigger in self.SEARCH_TRIGGERS:
            if lower_text.startswith(trigger):
                query = user_text.strip()[len(trigger):].strip().rstrip("?.!")
                if query:
                    return FastPathResult(
                        tool_name="online.search",
                        arguments={"query": query},
                        success_reply="Let me look that up.",
                    )

        return None

    def _is_shutdown(self, text: str) -> bool:
        if any(p in text for p in self.HIDE_PHRASES):
            return False
        if text in self.SHUTDOWN_EXACT:
            return True
        if "shut down" in text or text.startswith("shutdown") or "goodbye" in text or "turn off" in text:
            return True
        return False
