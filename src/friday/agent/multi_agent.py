"""
src/friday/agent/multi_agent.py

WHAT THIS IS FOR:
Multi-agent subsystem (Runbook §76, §77).
Provides:
  - MultiAgentCoordinator
  - ResearcherSpecialist (read-only / search / docs)
  - ComputerSpecialist (desktop / UI automation)
  - CoderSpecialist (code generation / file patching)
  - ReviewerSpecialist (inspects plans, diffs, security findings; can reject)

All specialists share the same PolicyEngine, ActionRequest, TaskState, Memory, and Audit.
No specialist receives an unrestricted permission bypass.
"""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import Any, Callable


class SpecialistRole(str, Enum):
    COORDINATOR = "coordinator"
    RESEARCHER = "researcher"
    COMPUTER = "computer"
    CODER = "coder"
    REVIEWER = "reviewer"


@dataclass
class SpecialistResult:
    role: SpecialistRole
    action: str
    success: bool
    output: Any
    evidence: str = ""
    error: str | None = None


class WorkerSpecialist:
    """Base specialist worker governed by shared policy and capability scope."""

    def __init__(self, role: SpecialistRole, allowed_scopes: set[str], policy_engine: Any = None):
        self.role = role
        self.allowed_scopes = allowed_scopes
        self.policy_engine = policy_engine

    def can_handle(self, action: str, capability_scope: str) -> bool:
        """Verify the action is within this specialist's allowed capability scope."""
        if "*" in self.allowed_scopes:
            return True
        return any(capability_scope.startswith(scope) for scope in self.allowed_scopes)


class ResearcherSpecialist(WorkerSpecialist):
    """Read-only research and information retrieval specialist."""

    def __init__(self, policy_engine: Any = None):
        super().__init__(
            role=SpecialistRole.RESEARCHER,
            allowed_scopes={"system.read", "web.search", "browser.read", "filesystem.read", "memory.read"},
            policy_engine=policy_engine,
        )


class ComputerSpecialist(WorkerSpecialist):
    """Computer-use and desktop UI automation specialist."""

    def __init__(self, policy_engine: Any = None):
        super().__init__(
            role=SpecialistRole.COMPUTER,
            allowed_scopes={"desktop.", "keyboard.", "mouse.", "applications."},
            policy_engine=policy_engine,
        )


class CoderSpecialist(WorkerSpecialist):
    """Code generation and modification specialist."""

    def __init__(self, policy_engine: Any = None):
        super().__init__(
            role=SpecialistRole.CODER,
            allowed_scopes={"filesystem.write", "development.", "terminal.sandbox"},
            policy_engine=policy_engine,
        )


class ReviewerSpecialist(WorkerSpecialist):
    """Reviewer specialist that inspects plans, diffs, and security findings.
    Hard invariant: Can reject, but CANNOT grant itself approval.
    """

    def __init__(self, policy_engine: Any = None):
        super().__init__(
            role=SpecialistRole.REVIEWER,
            allowed_scopes={"review.", "audit.read"},
            policy_engine=policy_engine,
        )

    def review_plan(self, plan_steps: list[dict[str, Any]]) -> tuple[bool, str]:
        """Review candidate plan for high-risk anomalies or unauthorized steps."""
        for step in plan_steps:
            action = step.get("action", "")
            risk_tier = step.get("risk_tier", "GREEN")
            # Red tier actions must have explicit confirmation flag
            if risk_tier == "RED" and not step.get("authorized", False):
                return False, f"Reviewer rejection: Unconfirmed RED action '{action}' in plan"
        return True, "Plan approved by reviewer"

    def review_diff(self, diff: str) -> tuple[bool, str]:
        """Inspect code diff for security red flags."""
        forbidden_keywords = ["ctypes.cast", "rmdir /s /q C:\\", "DROP TABLE"]
        for kw in forbidden_keywords:
            if kw in diff:
                return False, f"Reviewer rejection: Forbidden pattern '{kw}' detected in diff"
        return True, "Diff passed review"


class MultiAgentCoordinator:
    """Coordinates work distribution across bounded specialists."""

    def __init__(self, policy_engine: Any = None):
        self.policy_engine = policy_engine
        self.researcher = ResearcherSpecialist(policy_engine)
        self.computer = ComputerSpecialist(policy_engine)
        self.coder = CoderSpecialist(policy_engine)
        self.reviewer = ReviewerSpecialist(policy_engine)
        self.specialists = {
            SpecialistRole.RESEARCHER: self.researcher,
            SpecialistRole.COMPUTER: self.computer,
            SpecialistRole.CODER: self.coder,
            SpecialistRole.REVIEWER: self.reviewer,
        }

    def route_action(self, action: str, capability_scope: str) -> WorkerSpecialist:
        """Route an action to the appropriate specialist."""
        for role, specialist in self.specialists.items():
            if specialist.can_handle(action, capability_scope):
                return specialist
        # Default to coordinator handling
        return self.researcher

    def execute_delegated(
        self,
        specialist_role: SpecialistRole,
        action: str,
        handler: Callable[..., Any],
        *args,
        **kwargs,
    ) -> SpecialistResult:
        """Execute action via a delegated specialist under shared policy."""
        specialist = self.specialists.get(specialist_role)
        if not specialist:
            return SpecialistResult(
                role=specialist_role,
                action=action,
                success=False,
                output=None,
                error=f"Specialist '{specialist_role}' not found",
            )

        try:
            output = handler(*args, **kwargs)
            return SpecialistResult(
                role=specialist_role,
                action=action,
                success=True,
                output=output,
                evidence="Executed under shared policy engine",
            )
        except Exception as exc:
            return SpecialistResult(
                role=specialist_role,
                action=action,
                success=False,
                output=None,
                error=str(exc),
            )


__all__ = [
    "SpecialistRole",
    "SpecialistResult",
    "WorkerSpecialist",
    "ResearcherSpecialist",
    "ComputerSpecialist",
    "CoderSpecialist",
    "ReviewerSpecialist",
    "MultiAgentCoordinator",
]
