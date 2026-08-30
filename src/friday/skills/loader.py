"""
src/friday/skills/loader.py

WHAT THIS IS FOR:
Parses and loads structured SKILL.md files into typed Skill dataclass instances (§13, §14).
Enhanced with full procedural skill metadata for lifecycle management (Phase 5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Skill:
    # Core identity
    name: str
    purpose: str = ""
    trigger: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    risk_profile: str = "GREEN"

    # Procedural metadata (Phase 5)
    prerequisites: list[str] = field(default_factory=list)
    context_requirements: list[str] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)  # {name: {type, description, default, required}}
    permissions: list[str] = field(default_factory=list)
    expected_observations: list[str] = field(default_factory=list)
    verification_rules: list[dict] = field(default_factory=list)  # [{check, expected, tolerance}]
    failure_recovery: list[dict] = field(default_factory=list)  # [{on_failure, action, max_attempts}]
    failure_modes: list[str] = field(default_factory=list)
    examples: list[dict] = field(default_factory=list)  # [{input, expected_output, description}]

    # Procedure can be string (markdown) or list of steps
    procedure: str = ""
    procedure_steps: list[dict] = field(default_factory=list)  # Parsed steps: {action, args, intent, expected}

    # Versioning & metrics
    version: str = "1.0"
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    avg_execution_time_ms: float = 0.0
    verification_rate: float = 0.0
    user_corrections: int = 0
    failure_causes: list[str] = field(default_factory=list)
    last_validated: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def success_rate(self) -> float:
        if self.attempts == 0:
            return 0.0
        return self.successes / self.attempts

    @property
    def verification(self) -> str:
        if not self.verification_rules:
            return ""
        return "\n".join(r.get("check", "") for r in self.verification_rules)

    @property
    def recovery(self) -> str:
        if not self.failure_recovery:
            return ""
        return "\n".join(r.get("on_failure", "") for r in self.failure_recovery)


class SkillLoader:
    """Loads and parses skills from markdown files."""

    def load_from_directory(self, path: str | Path) -> list[Skill]:
        p = Path(path)
        if not p.exists() or not p.is_dir():
            return []

        return [self.load_skill(f) for f in p.glob("*.md")]

    def load_skill(self, path: str | Path) -> Skill:
        """Parse full SKILL.md format."""
        file_path = Path(path)
        content = file_path.read_text(encoding="utf-8")

        skill = Skill(name=file_path.stem)

        # Name / Title
        title_match = re.search(r"^#\s+(.*?)$", content, re.MULTILINE)
        if title_match:
            skill.name = title_match.group(1).strip()

        # Section helper
        def extract_section(header_pattern: str) -> str:
            match = re.search(rf"##\s+(?:{header_pattern})\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL | re.IGNORECASE)
            if match and match.group(1):
                return match.group(1).strip()
            return ""


        # Purpose
        skill.purpose = extract_section("Purpose") or skill.purpose

        # Trigger
        skill.trigger = extract_section("Trigger|Triggers")

        # Risk Profile
        risk = extract_section("Risk Profile|Risk")
        if risk:
            skill.risk_profile = risk.split()[0].upper()

        # Procedure
        skill.procedure = extract_section("Procedure|Steps")

        # Verification
        skill_verification = extract_section("Verification")
        if skill_verification:
            # Only append if we aren't handling Verification Rules later
            pass

        # Recovery
        skill_recovery = extract_section("Recovery")
        if skill_recovery:
            pass

        # Prerequisites
        prereqs = extract_section("Prerequisites")
        if prereqs:
            skill.prerequisites = [line.strip("- *").strip() for line in prereqs.splitlines() if line.strip("- *")]

        # Capabilities
        caps = extract_section("Capabilities|Required Capabilities")
        if caps:
            skill.required_capabilities = [c.strip() for c in re.split(r"[,;\n]+", caps) if c.strip()]

        # Failure Modes
        failures = extract_section("Failure Modes|Failures")
        if failures:
            skill.failure_modes = [line.strip("- *").strip() for line in failures.splitlines() if line.strip("- *")]

        # Context Requirements
        context = extract_section("Context Requirements|Context")
        if context:
            skill.context_requirements = [line.strip("- *").strip() for line in context.splitlines() if line.strip("- *")]

        # Variables
        vars_section = extract_section("Variables|Inputs")
        if vars_section:
            for line in vars_section.splitlines():
                line = line.strip("- *").strip()
                if ":" in line:
                    parts = line.split(":", 1)
                    skill.variables[parts[0].strip()] = {"description": parts[1].strip(), "required": True}

        # Permissions
        perms = extract_section("Permissions")
        if perms:
            skill.permissions = [line.strip("- *").strip() for line in perms.splitlines() if line.strip("- *")]

        # Verification Rules
        ver = extract_section("Verification Rules|Verification")
        if ver:
            for line in ver.splitlines():
                line = line.strip("- *").strip()
                if line:
                    skill.verification_rules.append({"check": line, "expected": "", "tolerance": "auto"})

        # Failure Recovery
        recovery = extract_section("Failure Recovery|Recovery")
        if recovery:
            for line in recovery.splitlines():
                line = line.strip("- *").strip()
                if line:
                    skill.failure_recovery.append({"on_failure": line, "action": "retry", "max_attempts": 2})

        # Examples
        ex = extract_section("Examples")
        if ex:
            for line in ex.splitlines():
                line = line.strip("- *").strip()
                if line:
                    skill.examples.append({"description": line, "input": {}, "expected_output": {}})

        # Parse procedure steps from markdown if present
        proc = extract_section("Procedure|Steps")
        if proc:
            skill.procedure = proc
            # Try to parse numbered steps: "1. action: `foo`\n   args: `{...}`"
            step_pattern = re.compile(r"^\d+\.\s*action:\s*`([^`]+)`\s*\n\s*args:\s*`([^`]*)`", re.MULTILINE)
            for match in step_pattern.finditer(proc):
                skill.procedure_steps.append({
                    "action": match.group(1),
                    "args": match.group(2),
                    "intent": "",
                    "expected": ""
                })

        return skill
