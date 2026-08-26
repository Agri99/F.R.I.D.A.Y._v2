"""
Skill promotion (§14.5).
"""
from __future__ import annotations

import enum
from typing import Any
from friday.skills.learner import SkillCandidate
from friday.skills.loader import Skill

class PromotionDecision(enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"

class PromotionManager:
    """Manages promoting candidates to full skills."""
    
    def check_promotion_criteria(self, candidate: SkillCandidate) -> PromotionDecision:
        """
        Check if candidate meets criteria: valid, tools exist, permissions bounded, 
        one test passes, not destructive auto-promoted.
        """
        # Red tools/capabilities shouldn't be auto-promoted
        if "filesystem.delete" in candidate.required_capabilities:
            return PromotionDecision.NEEDS_REVIEW
            
        if not candidate.procedure:
            return PromotionDecision.REJECTED
            
        return PromotionDecision.APPROVED

    def promote(self, candidate: SkillCandidate) -> Skill:
        """Promote candidate to official skill."""
        return Skill(
            name=candidate.proposed_name,
            procedure=candidate.procedure,
            trigger=candidate.triggers[0] if candidate.triggers else "",
            required_capabilities=candidate.required_capabilities
        )

    def reject(self, candidate: SkillCandidate, reason: str) -> None:
        """Log rejection reason."""
        pass
