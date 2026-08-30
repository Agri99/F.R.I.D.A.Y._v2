"""
src/friday/skills/validator.py

WHAT THIS IS FOR:
Skill structural validation and capability boundedness checks (§14.5 of Blueprint).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_RISK_PROFILES: set[str] = {"GREEN", "YELLOW", "ORANGE", "RED"}
VALID_CAPABILITIES: set[str] = {
    "system",
    "filesystem",
    "applications",
    "computer",
    "browser",
    "gmail",
    "calendar",
    "scheduling",
    "audio",
    "terminal",
    "network",
}


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SkillValidator:
    """Validates skills before execution, promotion, or registration."""

    def validate(self, skill: Any) -> ValidationResult:
        """Validate structure, permissions, and procedure clarity."""
        errors: list[str] = []
        warnings: list[str] = []

        name = getattr(skill, "name", None) or getattr(skill, "proposed_name", "")
        if not name or not isinstance(name, str):

            errors.append("Skill must have a non-empty string name.")
        elif not name.replace("_", "").replace("-", "").isalnum():
            warnings.append(f"Skill name '{name}' contains special characters; recommend alphanumeric with underscores.")

        procedure = getattr(skill, "procedure", "")
        if not procedure or not isinstance(procedure, str):
            errors.append("Skill must define an executable procedure.")
        elif len(procedure.strip()) < 5:
            errors.append("Procedure content is too short to be executable.")

        risk = getattr(skill, "risk_profile", "GREEN")
        if risk not in VALID_RISK_PROFILES:
            errors.append(f"Invalid risk profile '{risk}'. Must be one of {VALID_RISK_PROFILES}.")

        caps = getattr(skill, "required_capabilities", [])
        for cap in caps:
            if cap not in VALID_CAPABILITIES:
                warnings.append(f"Unrecognized capability domain '{cap}'.")

        # Security check: high-risk tools cannot masquerade as GREEN
        if risk == "GREEN":
            if any(c in caps for c in ("terminal", "system.shutdown")):
                errors.append(f"Skill requires privileged capability {caps} but claims risk_profile GREEN.")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
