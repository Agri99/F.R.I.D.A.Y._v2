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
        "what's the time",
        "what time is it in",
    )
    TIME_IN_PATTERNS = re.compile(
        r"(?:what(?:'s|\s+is)\s+the\s+time|current\s+time|tell\s+me\s+the\s+time|time\s+is\s+it)\s+(?:in|for)\s+(.+?)(?:\s*\?|$)"
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

    APP_ALIASES = {
        "notepad": "notepad",
        "text editor": "notepad",
        "calculator": "calculator",
        "calc": "calculator",
        "vscode": "vscode",
        "vs code": "vscode",
        "visual studio code": "vscode",
        "code": "vscode",
        "explorer": "explorer",
        "file explorer": "explorer",
        "files": "explorer",
        "terminal": "terminal",
        "windows terminal": "terminal",
        "cmd": "cmd",
        "command prompt": "cmd",
        "powershell": "powershell",
    }

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

        # 5. Time queries - with timezone or without
        m = self.TIME_IN_PATTERNS.search(text)
        if m:
            location = m.group(1).strip().rstrip("?.!")
            return FastPathResult(
                tool_name="system.get_time",
                arguments={"timezone": location},
                success_reply="",
                risk_tier="GREEN",
            )
        # Basic "what time is it" without a city → local time
        if any(text == p or text.startswith(p) for p in self.TIME_PHRASES):
            return FastPathResult(
                tool_name="system.get_time",
                arguments={},
                success_reply="",
                risk_tier="GREEN",
            )

        # 6. Window controls (minimize, maximize, restore, close active, show desktop)
        if text in (
            "minimize all",
            "minimize all windows",
            "minimize everything",
            "show desktop",
            "show the desktop",
        ):
            return FastPathResult(
                tool_name="computer.minimize_all_windows",
                arguments={},
                success_reply="Minimizing all windows.",
                risk_tier="GREEN",
            )

        if text in (
            "minimize window",
            "minimize the window",
            "minimize this window",
            "minimize it",
            "minimize this",
        ):
            return FastPathResult(
                tool_name="computer.control_window",
                arguments={"action": "minimize"},
                success_reply="Minimized window.",
                risk_tier="GREEN",
            )

        if text in (
            "maximize window",
            "maximize the window",
            "maximize this window",
            "maximize it",
            "maximize this",
        ):
            return FastPathResult(
                tool_name="computer.control_window",
                arguments={"action": "maximize"},
                success_reply="Maximized window.",
                risk_tier="GREEN",
            )

        if text in (
            "restore window",
            "restore the window",
            "restore this window",
            "restore it",
            "unmaximize",
            "unminimize",
        ):
            return FastPathResult(
                tool_name="computer.control_window",
                arguments={"action": "restore"},
                success_reply="Restored window.",
                risk_tier="GREEN",
            )

        if text in (
            "close window",
            "close the window",
            "close this window",
            "close it",
            "close this",
        ):
            return FastPathResult(
                tool_name="computer.control_window",
                arguments={"action": "close"},
                success_reply="Closed window.",
                risk_tier="YELLOW",
            )

        # 7. Application launch & close
        app_open_match = re.match(r"^(?:open|launch|start)\s+(?:the\s+)?(.+)$", text)
        if app_open_match:
            app_target = app_open_match.group(1).strip()
            if app_target in self.APP_ALIASES:
                app_id = self.APP_ALIASES[app_target]
                return FastPathResult(
                    tool_name="applications.open",
                    arguments={"app_id": app_id},
                    success_reply=f"Opening {app_target}.",
                    risk_tier="GREEN",
                )

        app_close_match = re.match(r"^(?:close|quit|exit)\s+(?:the\s+)?(.+)$", text)
        if app_close_match:
            app_target = app_close_match.group(1).strip()
            if app_target in self.APP_ALIASES:
                app_id = self.APP_ALIASES[app_target]
                return FastPathResult(
                    tool_name="applications.close",
                    arguments={"app_id": app_id},
                    success_reply=f"Closing {app_target}.",
                    risk_tier="YELLOW",
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
