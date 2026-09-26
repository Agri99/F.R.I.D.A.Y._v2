"""
src/friday/learning/distiller.py

WHAT THIS IS FOR:
Pattern detection -> structured skill candidate distillation (§14 of Blueprint).
Extracts repeatable multi-step workflows from successful trajectory records.
"""

from __future__ import annotations

import json
import re
from typing import Any


from friday.skills.learner import SkillCandidate

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
        variables: list[dict] = []
        for n in norm_steps:
            merged_steps.extend(n["steps"])
            variables.extend(n["variables"])
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

        return SkillCandidate(
            proposed_name=safe_name,
            purpose=f"Distilled workflow for '{primary_goal}'",
            triggers=[primary_goal.lower(), f"execute {safe_name}"],
            prerequisites=["System online"],
            required_capabilities=[step["action"].split(".")[0] for step in unique_steps],
            risk_profile="YELLOW" if any(cap in ("filesystem", "terminal", "computer") for cap in [step["action"].split(".")[0] for step in unique_steps]) else "GREEN",
            procedure="",
            procedure_steps=unique_steps,
            expected_observations=[f"Step {i+1} completed" for i in range(len(unique_steps))],
            verification="",
            verification_rules=[{"check": f"{step['action']} succeeded"} for step in unique_steps],
            failure_recovery=[{"action": "retry", "args": {}} for _ in unique_steps],
            variables=variables,
            examples=[{
                "input": primary_goal,
                "output": "Success"
            }]
        )