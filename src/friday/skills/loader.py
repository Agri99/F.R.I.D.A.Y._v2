"""
Skill loader.
"""
from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class Skill:
    name: str
    purpose: str = ""
    trigger: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    risk_profile: str = "GREEN"
    prerequisites: list[str] = field(default_factory=list)
    procedure: str = ""
    expected_observations: list[str] = field(default_factory=list)
    verification: str = ""
    failure_modes: list[str] = field(default_factory=list)
    recovery: str = ""
    examples: str = ""
    version: str = "1.0"
    success_stats: dict = field(default_factory=dict)
    last_validated: str = ""

class SkillLoader:
    """Loads skills from markdown files."""
    
    def load_from_directory(self, path: str | Path) -> list[Skill]:
        p = Path(path)
        if not p.exists() or not p.is_dir():
            return []
            
        return [self.load_skill(f) for f in p.glob("*.md")]

    def load_skill(self, path: str | Path) -> Skill:
        """Parse SKILL.md format."""
        content = Path(path).read_text(encoding="utf-8")
        
        # Simple markdown parsing (Regex-based extraction)
        skill = Skill(name=Path(path).stem)
        
        purpose_match = re.search(r'# \s*(.*?)\n', content)
        if purpose_match:
            skill.purpose = purpose_match.group(1).strip()
            
        trigger_match = re.search(r'## Trigger\s*\n(.*?)(?=\n##|$)', content, re.DOTALL)
        if trigger_match:
            skill.trigger = trigger_match.group(1).strip()
            
        # Extrapolate other fields...
        
        return skill
