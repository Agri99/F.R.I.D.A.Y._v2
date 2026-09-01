"""
Skill registry (§14) for managing available skills.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SkillSummary:
    name: str
    purpose: str
    trigger: str
    version: str

class SkillRegistry:
    """Manages loaded skills."""
    
    def __init__(self):
        self._skills: dict[str, Any] = {}

    def register(self, skill: Any) -> None:
        """Register a new skill."""
        self._skills[skill.name.lower()] = skill

    def get(self, name: str) -> Any | None:
        """Retrieve a skill by name."""
        return self._skills.get(name.lower())

    def list_all(self) -> list[SkillSummary]:
        """List all registered skills."""
        return [
            SkillSummary(
                name=s.name, 
                purpose=s.purpose, 
                trigger=s.trigger,
                version=s.version
            ) for s in self._skills.values()
        ]

    def search_skills(self, context: str) -> list[dict[str, Any]]:
        """Return serializable, trigger-ranked skills for context priming."""
        query = context.lower()
        matches = []
        for skill in self._skills.values():
            triggers = list(getattr(skill, "triggers", []) or [])
            trigger = getattr(skill, "trigger", "")
            if trigger:
                triggers.append(trigger)
            purpose = str(getattr(skill, "purpose", ""))
            if not any(term and term.lower() in query for term in triggers) and not (
                purpose and purpose.lower() in query
            ):
                continue
            matches.append({
                "name": skill.name,
                "purpose": purpose,
                "triggers": triggers,
                "required_capabilities": list(getattr(skill, "required_capabilities", []) or []),
                "risk_profile": getattr(skill, "risk_profile", "GREEN"),
                "version": getattr(skill, "version", "1.0.0"),
                "trigger_match": True,
            })
        return matches

    def list_by_trigger(self, context: str) -> list[Any]:
        """Find skills relevant to the context."""
        # Simple string matching for now
        context = context.lower()
        return [
            s for s in self._skills.values() 
            if s.trigger and s.trigger.lower() in context
        ]
