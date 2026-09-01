"""
src/friday/learning/promotion.py

WHAT THIS IS FOR:
Skill promotion gating, policy validation, and lifecycle persistence (§14.5 of Blueprint).
Ensures newly learned skills cannot grant themselves unearned privileges or bypass security.
Enhanced with performance metrics tracking and regression detection for measured self-improvement (Phase 4).
"""

from __future__ import annotations

import enum
from pathlib import Path

from friday.learning.optimizer import SkillOptimizer
from friday.skills.learner import SkillCandidate
from friday.skills.loader import Skill
from friday.skills.versioning import SkillVersionManager


class PromotionDecision(enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REGRESSION_DETECTED = "REGRESSION_DETECTED"


class PromotionManager:
    """Manages evaluation and promotion of candidate skills into active registry."""

    def __init__(self, learned_skills_dir: Path | str = "skills/learned") -> None:
        self.learned_skills_dir = Path(learned_skills_dir)
        self.learned_skills_dir.mkdir(parents=True, exist_ok=True)
        self._rejections: list[dict[str, str]] = []
        self.optimizer = SkillOptimizer()
        self.version_manager = SkillVersionManager()

    def check_promotion_criteria(self, candidate: SkillCandidate) -> PromotionDecision:
        """
        Evaluate candidate eligibility:
        - Must have a valid name and non-empty procedure
        - Red tier / destructive operations (e.g. format, delete, shutdown) require explicit user review
        - Cannot grant itself unrestricted authority
        - Check for regression if previous version exists
        """
        if not candidate.procedure or not candidate.proposed_name:
            return PromotionDecision.REJECTED

        caps = getattr(candidate, "required_capabilities", [])
        risk = getattr(candidate, "risk_profile", "GREEN")

        # Prohibit auto-promotion of destructive capabilities
        if any(c in caps for c in ("filesystem.delete", "terminal.sudo", "system.shutdown")):
            return PromotionDecision.NEEDS_REVIEW

        if risk == "RED":
            return PromotionDecision.NEEDS_REVIEW

        # Check for regression against existing skill
        existing_skill = self._get_existing_skill(candidate.proposed_name)
        if existing_skill:
            regression = self.optimizer.detect_regression(candidate, existing_skill)
            if regression:
                candidate.record_regression(
                    from_version=existing_skill.version,
                    to_version=candidate.version,
                    metric_drop=regression["drop"]
                )
                return PromotionDecision.REGRESSION_DETECTED

        return PromotionDecision.APPROVED

    def _get_existing_skill(self, name: str) -> SkillCandidate | None:
        """Load existing skill metrics from disk."""
        try:
            skill_path = self.learned_skills_dir / f"{name}.md"
            if not skill_path.exists():
                return None
            from friday.skills.loader import SkillLoader
            loader = SkillLoader()
            loaded = loader.load_skill(skill_path)
            candidate = SkillCandidate(
                proposed_name=loaded.name,
                purpose=loaded.purpose,
                triggers=[loaded.trigger] if loaded.trigger else ["run"],
                procedure=loaded.procedure,
                required_capabilities=loaded.required_capabilities,
                risk_profile=loaded.risk_profile,
            )
            candidate.version = loaded.version
            candidate.attempts = loaded.attempts
            candidate.successes = loaded.successes
            candidate.failures = loaded.failures
            candidate.avg_execution_time_ms = loaded.avg_execution_time_ms
            candidate.verification_rate = loaded.verification_rate
            candidate.user_corrections = loaded.user_corrections
            return candidate
        except Exception:
            return None

    def promote(self, candidate: SkillCandidate, save_to_disk: bool = True) -> Skill:
        """Promote candidate into a production Skill object and optionally persist to skills/learned/."""
        # Bump version
        new_version = self.version_manager.create_version(candidate, f"Promoted from {candidate.version}")

        skill = Skill(
            name=candidate.proposed_name,
            purpose=getattr(candidate, "purpose", f"Automated {candidate.proposed_name}"),
            procedure=candidate.procedure,
            trigger=candidate.triggers[0] if candidate.triggers else "",
            required_capabilities=candidate.required_capabilities,
            risk_profile=candidate.risk_profile,
            expected_observations=getattr(candidate, "expected_observations", []),
            verification_rules=getattr(candidate, "verification_rules", []),
            version=new_version,
        )

        # Attach metrics to skill for future regression detection
        skill.attempts = candidate.attempts
        skill.successes = candidate.successes
        skill.failures = candidate.failures
        skill.failure_causes = candidate.failure_causes.copy()
        skill.avg_execution_time_ms = candidate.avg_execution_time_ms
        skill.verification_rate = candidate.verification_rate
        skill.user_corrections = candidate.user_corrections
        skill.regression_history = candidate.regression_history.copy()

        if save_to_disk:
            try:
                skill_path = self.learned_skills_dir / f"{candidate.proposed_name}.md"
                md_content = candidate.to_markdown() if hasattr(candidate, "to_markdown") else candidate.procedure
                skill_path.write_text(md_content, encoding="utf-8")
            except Exception:
                pass

        return skill

    def reject(self, candidate: SkillCandidate, reason: str) -> None:
        """Log rejection reason for auditing."""
        self._rejections.append({
            "candidate": candidate.proposed_name,
            "reason": reason,
        })
