"""
Skills subsystem for F.R.I.D.A.Y. v2.

WHAT THIS IS FOR:
Procedural skill lifecycle management (Runbook §26-27).

A skill is a reusable, verified procedure that FRIDAY can execute on demand.
Skills are learned from successful trajectories, validated in sandbox, benchmarked,
and promoted to production. They never grant additional capabilities.
"""

from friday.skills.loader import Skill, SkillLoader
from friday.skills.registry import SkillRegistry, SkillSummary
from friday.skills.runtime import SkillRuntime, SkillResult
from friday.skills.validator import SkillValidator, ValidationResult
from friday.skills.versioning import SkillVersionManager, SkillVersion
from friday.skills.learner import SkillLearner, SkillCandidate
from friday.skills.evaluator import SkillEvaluator, SkillEvaluation

__all__ = [
    # Core
    "Skill",
    "SkillLoader",
    "SkillRegistry",
    "SkillSummary",
    "SkillResult",
    "SkillRuntime",
    # Lifecycle
    "SkillValidator",
    "ValidationResult",
    "SkillVersionManager",
    "SkillVersion",
    "SkillLearner",
    "SkillCandidate",
    "SkillEvaluator",
    "SkillEvaluation",
]
