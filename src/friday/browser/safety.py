"""
src/friday/browser/safety.py

WHAT THIS IS FOR:
Prompt-injection defense, malicious URL detection, content sanitization, and browser sandboxing (Blueprint §8, §20).
Treats all untrusted web content as data, never as system instructions.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path
from typing import Any
from dataclasses import dataclass


# Common prompt injection triggers in scraped web text
INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|safety)?\s*instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(in\s+)?(a|an|the)?\s*developer\s+mode", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?(security|safety)\s+rules", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*override", re.IGNORECASE),
    re.compile(r"disregard\s+all\s+(security|safety)\s+rules", re.IGNORECASE),
    re.compile(r"call\s+tool\s+[a-z_.]+", re.IGNORECASE),
    re.compile(r"<system>.*?</system>", re.IGNORECASE | re.DOTALL),
    re.compile(r"\[INST\].*?\[/INST\]", re.IGNORECASE | re.DOTALL),
    re.compile(r"you\s+are\s+(a|an|the)\s+(?!helpful|assistant|AI)", re.IGNORECASE),
    re.compile(r"pretend\s+to\s+be", re.IGNORECASE),
    re.compile(r"simulate\s+(a|an|the)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+)?(a|an|the)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(previous|prior)", re.IGNORECASE),
    re.compile(r"bypass\s+(safety|security|filter)", re.IGNORECASE),
    re.compile(r"unrestricted\s+mode", re.IGNORECASE),
    re.compile(r"no\s+rules", re.IGNORECASE),
]

DISALLOWED_SCHEMES: set[str] = {"file", "data", "blob", "javascript", "vbscript", "about"}
RESTRICTED_HOSTS: set[str] = {"localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254"}

# High-impact action patterns that require PolicyEngine approval
HIGH_IMPACT_ACTIONS = {
    "submit", "purchase", "buy", "checkout", "payment", "order",
    "upload", "download", "delete", "remove", "destroy",
    "send", "email", "message", "post", "publish",
    "account", "password", "credential", "login", "auth",
    "transfer", "withdraw", "deposit", "pay",
    "execute_script", "eval", "javascript:",
}


@dataclass
class SanitizationResult:
    sanitized: str
    redacted_count: int
    high_risk_detected: bool
    high_risk_types: list[str]


class BrowserSafety:
    """Provides content sanitization and security enforcement for web browsing."""

    def __init__(self, workspace_root: Path | None = None) -> None:
        self.workspace_root = workspace_root or Path("workspace")
        self._redaction_count = 0

    def sanitize_content(self, content: str) -> SanitizationResult:
        """Strip or neutralize potential prompt injection instructions from untrusted text."""
        sanitized = content
        total_redacted = 0
        high_risk_types = []

        for pattern in INJECTION_PATTERNS:
            matches = list(pattern.finditer(sanitized))
            if matches:
                total_redacted += len(matches)
                # Categorize the type of injection
                pattern_str = pattern.pattern
                if "ignore" in pattern_str and "instruction" in pattern_str:
                    high_risk_types.append("instruction_override")
                elif "developer" in pattern_str and "mode" in pattern_str:
                    high_risk_types.append("dev_mode")
                elif "system" in pattern_str and "prompt" in pattern_str:
                    high_risk_types.append("system_prompt_override")
                elif "security" in pattern_str or "safety" in pattern_str:
                    high_risk_types.append("security_bypass")
                elif "tool" in pattern_str:
                    high_risk_types.append("tool_invocation")
                elif "pretend" in pattern_str or "simulate" in pattern_str or "act as" in pattern_str:
                    high_risk_types.append("role_play")
                elif "forget" in pattern_str:
                    high_risk_types.append("memory_wipe")
                elif "bypass" in pattern_str or "unrestricted" in pattern_str or "no rules" in pattern_str:
                    high_risk_types.append("restriction_bypass")

                sanitized = pattern.sub("[UNTRUSTED_INSTRUCTION_REDACTED]", sanitized)

        # Also check for high-impact action keywords
        content_lower = content.lower()
        detected_actions = [action for action in HIGH_IMPACT_ACTIONS if action in content_lower]

        return SanitizationResult(
            sanitized=sanitized,
            redacted_count=total_redacted,
            high_risk_detected=total_redacted > 0 or len(detected_actions) > 0,
            high_risk_types=list(set(high_risk_types + detected_actions))
        )

    def is_safe_url(self, url: str) -> bool:
        """Verify URL does not violate intranet or local scheme boundaries."""
        if not url:
            return False

        parsed = urllib.parse.urlparse(url.strip())
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()

        if scheme in DISALLOWED_SCHEMES or not scheme:
            return False

        if host in RESTRICTED_HOSTS or host.startswith("192.168.") or host.startswith("10."):
            return False

        return True

    def requires_policy_approval(self, action_type: str, url: str = "") -> bool:
        """Check if an action requires PolicyEngine approval."""
        action_lower = action_type.lower()

        # High-impact actions always require approval
        if action_lower in HIGH_IMPACT_ACTIONS:
            return True

        # Checkout/payment URLs
        if any(kw in url.lower() for kw in ("checkout", "payment", "purchase", "pay", "billing")):
            return True

        # Account management URLs
        if any(kw in url.lower() for kw in ("account", "password", "security", "settings", "delete")):
            return True

        return False

    def get_dedicated_profile_path(self) -> Path:
        """Return path for isolated sandboxed browser profile."""
        profile_dir = self.workspace_root / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir

    def sanitize_for_llm(self, content: str, max_length: int = 8000) -> str:
        """Sanitize content specifically for LLM consumption with length limit."""
        result = self.sanitize_content(content)
        # Truncate if needed
        if len(result.sanitized) > max_length:
            result.sanitized = result.sanitized[:max_length] + "\n...[TRUNCATED]"
        return result.sanitized
