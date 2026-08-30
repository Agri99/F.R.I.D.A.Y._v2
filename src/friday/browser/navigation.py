"""
src/friday/browser/navigation.py

WHAT THIS IS FOR:
Handles browser navigation, search queries, link following, and risk tier evaluation.
Enhanced with safety checks and PolicyEngine integration for high-impact actions.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Any

import requests

from friday.browser.safety import BrowserSafety, HIGH_IMPACT_ACTIONS
from friday.online.network import NetworkMonitor
from friday.security.policy import PolicyEngine


@dataclass
class NavigationResult:
    success: bool
    url: str
    error: str | None = None
    status_code: int | None = None
    title: str | None = None
    risk_level: str = "GREEN"
    policy_approved: bool = False
    requires_approval: bool = False


class BrowserNavigator:
    """Manages browser navigation and risk assessment."""

    def __init__(self, timeout_seconds: int = 15, policy_engine: PolicyEngine | None = None,
                 safety: BrowserSafety | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.policy_engine = policy_engine
        self.safety = safety or BrowserSafety()

    def classify_risk(self, url: str) -> str:
        """
        Classify URL risk:
        - GREEN: Standard HTTPS content, search engines, documentation
        - YELLOW: Form submission, login portals, unknown domains
        - ORANGE: Financial, payments, destructive web apps, account deletion
        - RED: File schemes, internal admin ports, intranet IPs
        """
        parsed = urllib.parse.urlparse(url.strip())
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.lower()

        if scheme in ("file", "data", "blob", "javascript"):
            return "RED"

        if netloc in ("localhost", "127.0.0.1", "0.0.0.0") or netloc.startswith("192.168."):
            return "RED"

        if any(w in path or w in netloc for w in ("checkout", "payment", "buy", "delete-account", "transfer")):
            return "ORANGE"

        if any(w in path for w in ("login", "signin", "auth", "register", "submit")):
            return "YELLOW"

        return "GREEN"

    def navigate(self, url: str, action_type: str = "navigate") -> NavigationResult:
        """Perform navigation and fetch metadata with safety checks."""
        monitor = NetworkMonitor()
        if not monitor.is_online():
            return NavigationResult(success=False, url=url, error="Network is offline. Cannot navigate.")

        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Safety check
        if not self.safety.is_safe_url(url):
            return NavigationResult(success=False, url=url, error="Navigation to restricted/internal URL blocked by policy.")

        risk = self.classify_risk(url)
        requires_approval = self.safety.requires_policy_approval(action_type, url)

        # Policy check for high-impact actions
        policy_approved = False
        if requires_approval and self.policy_engine:
            from friday.security.policy import PolicyDecision
            decision = self.policy_engine.evaluate(f"browser.{action_type}", risk)
            dec_val = decision.decision.value if hasattr(decision.decision, "value") else str(decision.decision)
            policy_approved = dec_val == "ALLOW"
            if not policy_approved:
                return NavigationResult(
                    success=False, url=url, error=f"Policy denied: {getattr(decision, 'reason', 'High-impact action not approved')}",
                    risk_level=risk, requires_approval=True, policy_approved=False
                )
        elif requires_approval:
            return NavigationResult(
                success=False, url=url, error="High-impact action requires PolicyEngine approval",
                risk_level=risk, requires_approval=True, policy_approved=False
            )

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 FRIDAY/3.0"}
            resp = requests.get(url, headers=headers, timeout=self.timeout_seconds)
            resp.raise_for_status()

            # Simple title extraction
            import re
            match = re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
            title = match.group(1).strip() if match else "Untitled"

            return NavigationResult(
                success=True, url=resp.url, status_code=resp.status_code, title=title,
                risk_level=risk, policy_approved=policy_approved, requires_approval=requires_approval
            )
        except Exception as exc:
            return NavigationResult(success=False, url=url, error=str(exc), risk_level=risk)

    def search(self, query: str, engine: str = "google") -> NavigationResult:
        """Create a search engine query navigation result."""
        encoded = urllib.parse.quote_plus(query.strip())
        if engine == "duckduckgo":
            url = f"https://duckduckgo.com/html/?q={encoded}"
        else:
            url = f"https://www.google.com/search?q={encoded}"
        return self.navigate(url, action_type="search")

    def follow_link(self, current_url: str, link_target: str) -> NavigationResult:
        """Resolve and follow a relative or absolute link target."""
        resolved_url = urllib.parse.urljoin(current_url, link_target)
        return self.navigate(resolved_url, action_type="follow_link")

    def submit_form(self, url: str, form_data: dict, method: str = "POST") -> NavigationResult:
        """Submit a form with policy approval.

        FIXED BUG: this used to only check policy when self.policy_engine
        was truthy (`if requires_approval and self.policy_engine:`) - with
        no policy_engine configured (the actual real-world default: the
        BrowserController in tools/browser.py is built as
        BrowserController() with no policy_engine argument at all), that
        condition is False, the entire policy block was skipped, and the
        form would submit with ZERO approval despite "submit" being in
        HIGH_IMPACT_ACTIONS. navigate() already fails closed in this exact
        scenario (its `elif requires_approval:` branch below); this method
        was missing the equivalent guard. Not currently reachable via any
        registered tool, but a real gap the moment form-filling is wired up.
        """
        requires_approval = self.safety.requires_policy_approval("submit", url)

        if requires_approval and self.policy_engine:
            from friday.security.policy import PolicyDecision
            decision = self.policy_engine.evaluate("browser.submit", "ORANGE")
            dec_val = decision.decision.value if hasattr(decision.decision, "value") else str(decision.decision)
            if dec_val != "ALLOW":
                return NavigationResult(
                    success=False, url=url, error="Form submission not approved by policy",
                    risk_level="ORANGE", requires_approval=True, policy_approved=False
                )
        elif requires_approval:
            # No policy engine wired in at all - fail closed rather than
            # silently proceeding, same as navigate() already does.
            return NavigationResult(
                success=False, url=url, error="Form submission requires PolicyEngine approval",
                risk_level="ORANGE", requires_approval=True, policy_approved=False
            )

        if not self.safety.is_safe_url(url):
            return NavigationResult(success=False, url=url, error="Unsafe URL for form submission.")

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 FRIDAY/3.0"}
            if method.upper() == "POST":
                resp = requests.post(url, data=form_data, headers=headers, timeout=self.timeout_seconds)
            else:
                resp = requests.get(url, params=form_data, headers=headers, timeout=self.timeout_seconds)
            resp.raise_for_status()

            import re
            match = re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
            title = match.group(1).strip() if match else "Form Submitted"

            return NavigationResult(
                success=True, url=resp.url, status_code=resp.status_code, title=title,
                risk_level="ORANGE", policy_approved=True, requires_approval=requires_approval
            )
        except Exception as exc:
            return NavigationResult(success=False, url=url, error=str(exc), risk_level="ORANGE")
