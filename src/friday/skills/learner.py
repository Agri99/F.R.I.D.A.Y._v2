"""
src/friday/skills/learner.py

WHAT THIS IS FOR:
Extracts reusable workflows from successful trajectory traces and synthesizes structured SKILL.md candidates.
Enhanced with performance metrics for measured self-improvement (Phase 4) and full procedural metadata for lifecycle (Phase 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from friday.skills.sandbox import SkillSandbox
from pathlib import Path


@dataclass
class SkillCandidate:
    proposed_name: str
    purpose: str
    triggers: list[str]
    procedure: str
    required_capabilities: list[str] = field(default_factory=list)
    risk_profile: str = "GREEN"
    expected_observations: list[str] = field(default_factory=list)
    verification: str = ""

    # Procedural metadata (Phase 5)
    procedure_steps: list[dict] = field(default_factory=list)
    verification_rules: list[dict] = field(default_factory=list)
    failure_recovery: list[dict] = field(default_factory=list)
    variables: dict = field(default_factory=dict)
    prerequisites: list[str] = field(default_factory=list)
    context_requirements: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    examples: list[dict] = field(default_factory=list)

    # Performance metrics for measured self-improvement (Phase 4)
    version: str = "1.0"
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    failure_causes: list[str] = field(default_factory=list)
    avg_execution_time_ms: float = 0.0
    verification_rate: float = 0.0
    user_corrections: int = 0
    regression_history: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def success_rate(self) -> float:
        if self.attempts == 0:
            return 0.0
        return self.successes / self.attempts

    def record_regression(self, regression_data: dict) -> None:
        self.regression_history.append(regression_data)

    def to_markdown(self) -> str:
        """Render skill candidate into valid SKILL.md format."""
        triggers_str = "\n".join(f"- \"{t}\"" for t in self.triggers)
        caps_str = ", ".join(self.required_capabilities) or "none"
        obs_str = "\n".join(f"- {o}" for o in self.expected_observations) or "- Action completed successfully"

        # Include metrics in markdown
        metrics_str = f"""**Version:** {self.version}
**Attempts:** {self.attempts} | **Successes:** {self.successes} | **Failures:** {self.failures}
**Success Rate:** {(self.successes/self.attempts*100) if self.attempts > 0 else 0:.1f}%
**Avg Execution Time:** {self.avg_execution_time_ms:.1f}ms
**Verification Rate:** {self.verification_rate:.1%}
**User Corrections:** {self.user_corrections}
**Last Updated:** {self.updated_at}"""

        return f"""# {self.proposed_name}

## Purpose
{self.purpose}

## Triggers
{triggers_str}

## Capabilities
{caps_str}

## Risk Profile
{self.risk_profile}

## Procedure
{self.procedure}

## Expected Observations
{obs_str}

## Verification
{self.verification or "Check that all steps finished without error."}

## Performance Metrics
{metrics_str}
"""

    @property
    def success_rate(self) -> float:
        if self.attempts == 0:
            return 0.0
        return self.successes / self.attempts

    def record_execution(self, success: bool, execution_time_ms: float, verification_passed: bool, error: str = "") -> None:
        """Record an execution attempt for metrics."""
        self.attempts += 1
        self.updated_at = datetime.now().isoformat()

        if success:
            self.successes += 1
        else:
            self.failures += 1
            if error:
                self.failure_causes.append(f"{datetime.now().isoformat()}: {error}")

        # Update running average of execution time
        total_time = self.avg_execution_time_ms * (self.attempts - 1) + execution_time_ms
        self.avg_execution_time_ms = total_time / self.attempts

        # Update verification rate
        total_verified = self.verification_rate * (self.attempts - 1) + (1 if verification_passed else 0)
        self.verification_rate = total_verified / self.attempts

    def record_user_correction(self) -> None:
        """Record a user correction."""
        self.user_corrections += 1
        self.updated_at = datetime.now().isoformat()

    def record_regression(self, from_version: str, to_version: str, metric_drop: float) -> None:
        """Record a regression event."""
        self.regression_history.append({
            "from_version": from_version,
            "to_version": to_version,
            "metric_drop": metric_drop,
            "timestamp": datetime.now().isoformat()
        })
        self.updated_at = datetime.now().isoformat()


class SkillLearner:
    """Generates new skills from observed successful trajectories."""

    def __init__(self, sandbox_workspace: Path | str | None = None):
        self.sandbox = None
        if sandbox_workspace:
            self.sandbox = SkillSandbox(sandbox_workspace, allowed_capabilities=[])

    def set_sandbox(self, sandbox: SkillSandbox) -> None:
        self.sandbox = sandbox

    def detect_pattern(self, trajectories: list[Any]) -> SkillCandidate | None:
        """Analyze multiple trajectories to find a repeatable pattern."""
        if len(trajectories) < 2:
            return None

        # Extract sequence of tool names from successful trajectories
        sequences: list[list[str]] = []
        for t in trajectories:
            steps = getattr(t, "steps", [])
            actions = [getattr(s, "action", str(s)) for s in steps if getattr(s, "action", None)]
            if actions:
                sequences.append(actions)

        if not sequences:
            return None

        # Find common sequence prefix or match
        first_seq = sequences[0]
        match_count = sum(1 for seq in sequences if seq == first_seq)
        if match_count >= 2:
            return self.generate_candidate(trajectories[0])

        return None

    def generate_candidate(self, trajectory: Any) -> SkillCandidate:
        """Create a structured skill candidate from a successful execution trajectory."""
        goal = getattr(trajectory, "goal", "Automated routine")
        steps = getattr(trajectory, "steps", [])

        procedure_lines: list[str] = []
        procedure_steps: list[dict] = []
        capabilities: set[str] = set()
        observations: list[str] = []
        variables: dict = {}
        verification_rules: list[dict] = []
        failure_recovery: list[dict] = []

        for i, step in enumerate(steps, 1):
            action = getattr(step, "action", "action")
            args = getattr(step, "arguments", {})
            obs = getattr(step, "expected_observation", f"Step {i} completed")
            intent = getattr(step, "intent", f"Execute {action}")

            # Map action domain to capability
            domain = action.split(".")[0] if "." in action else "system"
            capabilities.add(domain)

            # Build markdown procedure
            procedure_lines.append(f"{i}. action: {action}\n   args: {args}")
            observations.append(obs)

            # Build structured procedure steps
            procedure_steps.append({
                "action": action,
                "args": args,
                "intent": intent,
                "expected": obs
            })

            # Extract variables from args
            for k, v in args.items():
                if isinstance(v, str) and ("{" in v and "}" in v):
                    variables[k] = {"type": "string", "description": f"Variable from {action}", "required": True}
                elif k not in variables:
                    variables[k] = {"type": type(v).__name__, "description": f"Parameter for {action}", "required": True}

            # Build verification rule
            verification_rules.append({
                "check": f"Step {i} ({action}) completed",
                "expected": obs,
                "tolerance": "auto"
            })

            # Build failure recovery
            failure_recovery.append({
                "on_failure": f"{action} failed",
                "action": "retry",
                "max_attempts": 2
            })

        safe_name = goal.lower().replace(" ", "_").replace("-", "_")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")[:40] or "custom_skill"

        return SkillCandidate(
            proposed_name=safe_name,
            purpose=f"Automates: {goal}",
            triggers=[goal.lower(), f"run {safe_name}"],
            procedure="\n".join(procedure_lines),
            procedure_steps=procedure_steps,
            required_capabilities=sorted(list(capabilities)),
            risk_profile="YELLOW" if any(c in capabilities for c in ("filesystem", "terminal", "computer")) else "GREEN",
            expected_observations=observations,
            verification="Verify all actions completed and target state was achieved.",
            verification_rules=verification_rules,
            failure_recovery=failure_recovery,
            variables=variables,
            prerequisites=["System online", "Required applications available"],
            context_requirements=["Active user session"],
            permissions=[],
            examples=[]
        )

    def validate_candidate(self, candidate: SkillCandidate, tool_registry: Any, policy_engine: Any) -> bool:
        """Validate a skill candidate using the sandbox if available."""
        if not self.sandbox:
            return True  # No sandbox configured, skip validation

        # Create a temporary skill object for validation
        from friday.skills.loader import Skill
        skill = Skill(
            name=candidate.proposed_name,
            purpose=candidate.purpose,
            trigger=candidate.triggers[0] if candidate.triggers else "",
            required_capabilities=candidate.required_capabilities,
            risk_profile=candidate.risk_profile,
            procedure=candidate.procedure,
            expected_observations=candidate.expected_observations,
            verification=candidate.verification,
        )

        result = self.sandbox.validate_skill(skill)
        return result.valid
