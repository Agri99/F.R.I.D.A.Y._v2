"""
src/friday/learning/distiller.py

WHAT THIS IS FOR:
Pattern detection -> structured skill candidate distillation (§14 of Blueprint).
Extracts repeatable multi-step workflows from successful trajectory records.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillCandidate:
    proposed_name: str = ""
    name: str = ""
    purpose: str = ""
    triggers: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    risk_profile: str = "GREEN"
    inputs: list[dict] = field(default_factory=list)        # {name, type, description, required}
    procedure: list[dict] = field(default_factory=list)     # ordered action steps
    expected_observations: list[str] = field(default_factory=list)
    verification: list[dict] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    recovery: list[dict] = field(default_factory=list)
    source_trajectory_ids: list[str] = field(default_factory=list)
    procedure_steps: list[dict] = field(default_factory=list)  # {action, args, intent, expected}
    verification_rules: list[dict] = field(default_factory=list)
    failure_recovery: list[dict] = field(default_factory=list)
    variables: dict = field(default_factory=dict)
    prerequisites: list[str] = field(default_factory=list)
    context_requirements: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    examples: list[dict] = field(default_factory=list)
    version: str = "1.0"
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    failure_causes: list[str] = field(default_factory=list)
    avg_execution_time_ms: float = 0.0
    verification_rate: float = 0.0
    user_corrections: int = 0
    regression_history: list[dict] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if self.proposed_name and not self.name:
            self.name = self.proposed_name
        elif self.name and not self.proposed_name:
            self.proposed_name = self.name

    @property
    def success_rate(self) -> float:
        if self.attempts > 0:
            return self.successes / self.attempts
        return 0.0

    def to_markdown(self) -> str:
        """Render skill candidate into valid SKILL.md format."""
        procedure_lines = []
        for i, step in enumerate(self.procedure, 1):
            action = step.get("action", "unknown")
            args = step.get("arguments", {})
            procedure_lines.append(f"{i}. **action:** `{action}`\n   **args:** `{args}`")

        caps_str = ", ".join(self.required_capabilities) or "none"
        obs_str = "\n".join(f"- {o}" for o in self.expected_observations) or "- Action completed successfully"
        ver_str = "\n".join(f"- {v}" for v in self.verification) or "- Check status == 'DONE'"
        fail_str = "\n".join(f"- {f}" for f in self.failure_modes) or "- Tool execution timeout"
        rec_str = "\n".join(f"- {r}" for r in self.recovery) or "- Retry with max 2 attempts"
        prereq_str = "\n".join(f"- {p}" for p in self.prerequisites) or "- System online"

        return f"""# {self.name}

## Purpose
{self.purpose}

## Triggers
{chr(10).join(f"- \"{t}\"" for t in self.triggers)}

## Prerequisites
{prereq_str}

## Capabilities
{caps_str}

## Risk Profile
{self.risk_profile}

## Inputs
{chr(10).join(f"- {inp}" for inp in self.inputs) if self.inputs else "none"}

## Procedure
{chr(10).join(procedure_lines)}

## Expected Observations
{obs_str}

## Verification
{ver_str}

## Failure Modes
{fail_str}

## Recovery
{rec_str}
"""


class PatternDistiller:
    def __init__(self, model_provider: Any = None):
        self.model_provider = model_provider

    def _normalize_trajectory(self, trajectory: dict) -> list[dict]:
        """Strip timestamps, remove duplicate consecutive actions, and canonicalize args."""
        # Handle both dict-like and object-like trajectories
        if hasattr(trajectory, "get"):
            steps = trajectory.get("steps", [])
        else:
            steps = getattr(trajectory, "steps", [])

        normalized: list[dict] = []
        prev: dict | None = None
        for s in steps:
            # Convert step to dict if it's an object
            if hasattr(s, "items"):
                step = {k: v for k, v in s.items() if k not in ("timestamp", "observation_time")}
            else:
                step = {k: getattr(s, k, None) for k in ("action", "arguments", "expected_observation", "result") if hasattr(s, k)}
            # Collapse consecutive identical actions (action + args)
            if prev and prev.get("action") == step.get("action") and prev.get("arguments") == step.get("arguments"):
                continue
            normalized.append(step)
            prev = step
        return normalized

    def _remove_noise(self, steps: list[dict]) -> list[dict]:
        """Fuzzy‑match arguments to ignore non‑deterministic values (e.g., temp file names)."""
        cleaned: list[dict] = []
        for step in steps:
            args = step.get("arguments", {})
            # Replace any full path with placeholder
            for k, v in list(args.items()):
                if isinstance(v, str) and ("/" in v or "\\" in v):
                    args[k] = "{path}"
                elif isinstance(v, str) and re.fullmatch(r"[a-f0-9]{32}", v):
                    args[k] = "{hash}"
            cleaned.append({"action": step.get("action"), "arguments": args})
        return cleaned

    def _extract_variables(self, steps: list[dict]) -> tuple[list[dict], list[dict]]:
        """Detect variable placeholders in arguments and return (template_steps, variables)."""
        variables: list[dict] = []
        template_steps: list[dict] = []
        var_counter = 0
        for step in steps:
            args = step.get("arguments", {})
            tmpl_args = {}
            for k, v in args.items():
                if isinstance(v, str) and ("{" in v and "}" in v):
                    tmpl_args[k] = v
                elif isinstance(v, str) and ("/" in v or "\\" in v):
                    placeholder = f"{{var{var_counter}}}"
                    tmpl_args[k] = placeholder
                    variables.append({"name": placeholder, "example": v})
                    var_counter += 1
                else:
                    tmpl_args[k] = v
            template_steps.append({"action": step.get("action"), "arguments": tmpl_args})
        return template_steps, variables

    def distill(self, trajectories: list[dict]) -> SkillCandidate | None:
        """Extract a reusable skill from successful trajectories.
        Steps:
        1️⃣ Normalize each trajectory (remove timestamps, collapse dupes)
        2️⃣ Remove noisy arguments (paths, hashes)
        3️⃣ Extract variables (paths, URLs) with placeholders
        4️⃣ Group by goal similarity (simple string equality for now)
        5️⃣ Use the reasoning model to draft a markdown skill description.
        """
        if not trajectories:
            return None

        # Filter successful trajectories
        def _get_attr(obj, key, default=None):
            """Get attribute from dict-like or object with attributes."""
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # Filter successful trajectories
        successes = [t for t in trajectories if str(_get_attr(t, "outcome")).lower() in ("success", "done", "ok")]
        if len(successes) < 2:
            return None

        # Normalize and clean steps for each trajectory
        norm_steps = []
        for traj in successes:
            steps = self._normalize_trajectory(traj)
            steps = self._remove_noise(steps)
            tmpl, vars_ = self._extract_variables(steps)
            norm_steps.append({"steps": tmpl, "variables": vars_, "goal": _get_attr(traj, "goal", "")})

        # Simple grouping: pick the most common goal string
        goal_counts = {}
        for n in norm_steps:
            goal = n["goal"]
            goal_counts[goal] = goal_counts.get(goal, 0) + 1
        primary_goal = max(goal_counts, key=goal_counts.get) if goal_counts else "distilled_skill"

        # Merge steps from all trajectories (naïve union for now)
        merged_steps: list[dict] = []
        for n in norm_steps:
            merged_steps.extend(n["steps"])
        # Deduplicate by (action, arguments) tuple
        seen = set()
        unique_steps = []
        for s in merged_steps:
            key = (s.get("action"), json.dumps(s.get("arguments", {}), sort_keys=True))
            if key not in seen:
                seen.add(key)
                unique_steps.append(s)

        # Build SkillCandidate structure
        safe_name = primary_goal.lower().replace(" ", "_").replace("-", "_")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")[:32] or "distilled_skill"

        # For verification we just assert that each step succeeded (placeholder)
        verification = [{"check": f"{step['action']} succeeded"} for step in unique_steps]

        return SkillCandidate(
            name=safe_name,
            purpose=f"Distilled workflow for '{primary_goal}'",
            triggers=[primary_goal.lower(), f"execute {safe_name}"],
            prerequisites=["System online"],
            required_capabilities=[step["action"].split(".")[0] for step in unique_steps],
            risk_profile="YELLOW" if any(cap in ("filesystem", "terminal", "computer") for cap in [step["action"].split(".")[0] for step in unique_steps]) else "GREEN",
            inputs=[],
            procedure=unique_steps,
            expected_observations=[f"Step {i+1} completed" for i in range(len(unique_steps))],
            verification=[{"check": f"{step['action']} succeeded"} for step in unique_steps],
            failure_modes=["Tool execution timeout", "Target not found"],
            recovery=[{"on_failure": "retry", "max_attempts": 2}],
            source_trajectory_ids=[str(_get_attr(t, "id")) for t in successes]
        )