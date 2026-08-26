"""
Skill validation (§14.5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

class SkillValidator:
    """Validates skills before execution or promotion."""
    
    def validate(self, skill: Any) -> ValidationResult:
        """Check if skill procedure is valid and permissions are bounded."""
        errors = []
        warnings = []
        
        if not skill.name:
            errors.append("Skill must have a name.")
            
        if not skill.procedure:
            errors.append("Skill must define a procedure.")
            
        # In a full implementation, we'd check if referenced tools exist in registry
        # and if the risk profile bounds the capabilities requested.
        
        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
