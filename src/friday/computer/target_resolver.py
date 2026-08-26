"""
src/friday/computer/target_resolver.py
WHAT THIS IS FOR: Resolve natural language target descriptions to UI elements.
"""
from __future__ import annotations

from enum import Enum
from typing import Any
from dataclasses import dataclass

class ResolutionMethod(Enum):
    ACCESSIBILITY_LABEL = 'accessibility_label'
    AUTOMATION_ID = 'automation_id'
    ROLE_AND_LABEL = 'role_and_label'
    BROWSER_LOCATOR = 'browser_locator'
    VISUAL_MATCH = 'visual_match'
    COORDINATE_FALLBACK = 'coordinate_fallback'

@dataclass
class ResolvedTarget:
    method: ResolutionMethod
    element: Any  # the resolved UI element or coordinates
    confidence: float
    description: str

class TargetResolver:
    def resolve(self, description: str, context: dict | None = None) -> ResolvedTarget | None:
        """Resolve a natural-language target description to a UI element."""
        # Try each method in priority order:
        # 1. accessibility label (UIAutomation)
        # 2. automation ID
        # 3. role + label
        # 4. browser locator (if browser context)
        # 5. visual match (screenshot + VLM)
        # 6. coordinate fallback
        
        # Stub implementation
        return ResolvedTarget(
            method=ResolutionMethod.ACCESSIBILITY_LABEL,
            element=None,
            confidence=0.8,
            description=f"Resolved '{description}'"
        )
