"""
Isolated skill execution environment.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]

@dataclass
class SkillExecutionResult:
    success: bool
    output: Any
    errors: list[str]

class SkillSandbox:
    def __init__(self, workspace_dir: Path, allowed_capabilities: list[str]):
        self.workspace_dir = workspace_dir
        self.allowed_capabilities = allowed_capabilities

    def execute(self, skill: Any, inputs: dict, tool_registry: Any, policy_engine: Any) -> SkillExecutionResult:
        """Execute a skill in isolation. Every tool call goes through policy."""
        # Key rule: Skills CANNOT lower their own risk level or bypass authorization.
        # This is a stub implementation representing the isolated execution logic.
        
        errors = []
        output = None
        success = True
        
        try:
            for step in skill.procedure:
                # In a real implementation we would build an ActionRequest and call policy_engine.authorize
                pass
        except Exception as e:
            success = False
            errors.append(str(e))
            
        return SkillExecutionResult(success=success, output=output, errors=errors)

    def validate_skill(self, skill: Any) -> ValidationResult:
        """Dry-run validation without actual execution."""
        errors = []
        if not hasattr(skill, "procedure"):
            errors.append("Skill missing procedure.")
        
        for cap in getattr(skill, "required_capabilities", []):
            if cap not in self.allowed_capabilities:
                errors.append(f"Capability {cap} not allowed in sandbox.")
                
        return ValidationResult(valid=len(errors) == 0, errors=errors)
