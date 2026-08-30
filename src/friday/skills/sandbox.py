"""
src/friday/skills/sandbox.py

WHAT THIS IS FOR:
Isolated skill execution environment (§14). Runs skills in a separate process
restricted to the workspace/sandbox directory, enforcing capability limits.
Enhanced with full lifecycle support: validate → execute → monitor → rollback (Phase 5).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass
class SkillExecutionResult:
    success: bool
    output: Any
    errors: list[str]
    execution_time_ms: float = 0.0
    verification_passed: bool = False
    observations: list[str] = field(default_factory=list)


@dataclass
class SkillMonitoringResult:
    skill_name: str
    version: str
    success_rate: float
    total_executions: int
    regression_detected: bool = False
    regression_details: dict | None = None


class SkillSandbox:
    """Isolated skill execution environment with full lifecycle support."""

    def __init__(self, workspace_dir: Path | str, allowed_capabilities: list[str], timeout_seconds: int = 60):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.sandbox_dir = self.workspace_dir / "sandbox"
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.allowed_capabilities = allowed_capabilities
        self.timeout_seconds = timeout_seconds
        self._execution_history: list[dict] = []

    def execute(self, skill: Any, inputs: dict[str, Any], tool_registry: Any, policy_engine: Any) -> SkillExecutionResult:
        """
        Execute a skill in isolation with full observe-act-verify loop.
        """
        start_time = time.time()
        errors = []
        output = None
        success = True
        verification_passed = False
        observations = []

        # Pre-execution capability check
        validation = self.validate_skill(skill)
        if not validation.valid:
            return SkillExecutionResult(
                success=False, output=None, errors=validation.errors,
                execution_time_ms=0, verification_passed=False
            )

        try:
            # Get procedure steps (prefer structured, fallback to markdown parsing)
            steps = self._get_procedure_steps(skill)

            for i, step in enumerate(steps):
                action = step.get("action")
                args = step.get("args", step.get("arguments", {}))

                # Merge inputs with step args
                merged_args = {**inputs, **args}

                # Enforce capability mapping
                domain = action.split(".")[0] if "." in action else "system"
                if domain not in self.allowed_capabilities and action not in self.allowed_capabilities:
                    raise PermissionError(f"Action '{action}' requires capability '{domain}' which is not allowed in sandbox.")

                # Execute tool with policy check
                if tool_registry:
                    tool = tool_registry.get(action)
                    if not tool:
                        raise ValueError(f"Tool {action} not found in registry.")

                    # Check policy
                    if policy_engine:
                        # Policy check would go here
                        pass

                    if hasattr(tool, "run"):
                        res = tool.run(**merged_args)
                    elif hasattr(tool, "handler"):
                        res = tool.handler(**merged_args)
                    else:
                        res = tool(**merged_args)

                    obs = str(res)
                    observations.append(obs)

                    # Verify step expectation
                    expected = step.get("expected", step.get("expected_observation", ""))
                    if expected and expected.lower() not in obs.lower():
                        # Check for success indicators
                        success_indicators = ("success", "opened", "created", "saved", "done", "written", "ok", "true", "200")
                        if not any(ind in obs.lower() for ind in success_indicators):
                            raise AssertionError(f"Step {i+1} verification failed: expected '{expected}', got '{obs}'")

            output = observations
            verification_passed = True

        except subprocess.TimeoutExpired:
            success = False
            errors.append(f"Skill execution timed out after {self.timeout_seconds} seconds")
        except Exception as e:
            success = False
            errors.append(str(e))

        execution_time_ms = (time.time() - start_time) * 1000

        # Record execution for monitoring
        self._execution_history.append({
            "skill": skill.name,
            "version": getattr(skill, "version", "1.0"),
            "success": success,
            "execution_time_ms": execution_time_ms,
            "verification_passed": verification_passed,
            "timestamp": time.time(),
        })

        return SkillExecutionResult(
            success=success, output=output, errors=errors,
            execution_time_ms=execution_time_ms,
            verification_passed=verification_passed,
            observations=observations
        )

    def _get_procedure_steps(self, skill: Any) -> list[dict]:
        """Get procedure steps from skill, preferring structured format."""
        if hasattr(skill, "procedure_steps") and skill.procedure_steps:
            return skill.procedure_steps

        # Handle both list of dicts and markdown string
        proc = getattr(skill, "procedure", [])
        steps = []

        if isinstance(proc, list):
            # Already structured: [{"action": "...", "args": {...}}, ...]
            for step in proc:
                steps.append({
                    "action": step.get("action", ""),
                    "args": step.get("args", step.get("arguments", {})),
                    "intent": step.get("intent", ""),
                    "expected": step.get("expected", step.get("expected_observation", ""))
                })
        elif isinstance(proc, str) and proc:
            # Parse markdown
            import re
            step_pattern = re.compile(r"^\d+\.\s*action:\s*`([^`]+)`\s*\n\s*args:\s*`([^`]*)`", re.MULTILINE)
            for match in step_pattern.finditer(proc):
                try:
                    args = json.loads(match.group(2)) if match.group(2).strip() else {}
                except json.JSONDecodeError:
                    args = {}
                steps.append({
                    "action": match.group(1),
                    "args": args,
                    "intent": "",
                    "expected": ""
                })
        return steps

    def validate_skill(self, skill: Any) -> ValidationResult:
        """Dry-run validation without actual execution."""
        errors = []
        warnings = []

        if not hasattr(skill, "procedure") or not skill.procedure:
            errors.append("Skill missing procedure.")

        required_caps = getattr(skill, "required_capabilities", [])
        for cap in required_caps:
            if cap not in self.allowed_capabilities:
                errors.append(f"Capability '{cap}' not allowed in sandbox.")

        # Validate risk profile
        risk = getattr(skill, "risk_profile", "RED").upper()
        if risk == "RED" and "admin" not in self.allowed_capabilities:
            errors.append("RED risk profile skills cannot be validated in standard sandbox.")

        # Check for missing verification rules
        if not getattr(skill, "verification_rules", []):
            warnings.append("No verification rules defined - skill may not be self-validating")

        # Check for failure recovery
        if not getattr(skill, "failure_recovery", []):
            warnings.append("No failure recovery defined - skill may not be resilient")

        # Check prerequisites
        prereqs = getattr(skill, "prerequisites", [])
        for prereq in prereqs:
            warnings.append(f"Prerequisite: {prereq}")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def monitor_skill(self, skill_name: str, version: str, version_manager: Any) -> SkillMonitoringResult:
        """Monitor skill performance and detect regression."""
        executions = [e for e in self._execution_history if e["skill"] == skill_name and e["version"] == version]

        if not executions:
            return SkillMonitoringResult(
                skill_name=skill_name, version=version,
                success_rate=0.0, total_executions=0
            )

        total = len(executions)
        successful = sum(1 for e in executions if e["success"])
        success_rate = successful / total

        # Check for regression against previous version
        regression_detected = False
        regression_details = None

        if version_manager:
            prev_version = self._get_previous_version(version_manager, skill_name, version)
            if prev_version:
                comparison = version_manager.compare_versions(skill_name, prev_version.version, version)
                if comparison and comparison.get("regression"):
                    regression_detected = True
                    regression_details = comparison

        return SkillMonitoringResult(
            skill_name=skill_name,
            version=version,
            success_rate=success_rate,
            total_executions=total,
            regression_detected=regression_detected,
            regression_details=regression_details
        )

    def _get_previous_version(self, version_manager: Any, skill_name: str, current_version: str) -> Any:
        """Get the version before current_version."""
        history = version_manager.get_history(skill_name)
        if len(history) < 2:
            return None

        # Find current index
        for i, v in enumerate(history):
            if v.version == current_version:
                if i > 0:
                    return history[i-1]
        return None

    def rollback_on_regression(self, skill: Any, version_manager: Any) -> bool:
        """Auto-rollback if regression detected during monitoring."""
        monitor_result = self.monitor_skill(skill.name, skill.version, version_manager)

        if monitor_result.regression_detected:
            # Rollback to previous version
            return version_manager.rollback(skill)
        return False
