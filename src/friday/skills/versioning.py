"""
Skill versioning (§14.4).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

@dataclass
class SkillVersion:
    version: str
    changes: str

class SkillVersionManager:
    """Manages skill semantic versioning."""
    
    def __init__(self):
        self._history: dict[str, list[SkillVersion]] = {}

    def create_version(self, skill: Any, changes: str) -> str:
        """Bump minor version and record changes."""
        current_v = skill.version
        match = re.match(r'v?(\d+)\.(\d+)', current_v)
        if match:
            major, minor = int(match.group(1)), int(match.group(2))
            new_v = f"{major}.{minor + 1}"
        else:
            new_v = "1.1"
            
        skill.version = new_v
        
        if skill.name not in self._history:
            self._history[skill.name] = []
            
        self._history[skill.name].append(SkillVersion(version=new_v, changes=changes))
        return new_v

    def rollback(self, skill_name: str, to_version: str) -> None:
        """Rollback skill to previous version."""
        pass

    def get_history(self, skill_name: str) -> list[SkillVersion]:
        return self._history.get(skill_name, [])
