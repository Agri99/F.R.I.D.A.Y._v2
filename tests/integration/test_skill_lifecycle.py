"""
tests/integration/test_skill_lifecycle.py

WHAT THIS IS FOR:
Integration test for the full skill lifecycle: detect -> validate -> evaluate -> version -> rollback.
"""

from __future__ import annotations

from friday.skills.learner import SkillLearner, SkillCandidate
from friday.skills.validator import SkillValidator
from friday.skills.evaluator import SkillEvaluator
from friday.skills.versioning import SkillVersionManager
from friday.learning.promotion import PromotionManager, PromotionDecision


def test_full_skill_lifecycle():
    learner = SkillLearner()
    validator = SkillValidator()
    evaluator = SkillEvaluator()
    versioner = SkillVersionManager()
    promoter = PromotionManager()

    # 1. Synthesize candidate from mock trajectory
    class MockTrajectory:
        goal = "prepare workspace"
        steps = [
            type("Step", (), {"action": "applications.open", "arguments": {"app_id": "notepad"}, "expected_observation": "opened"})(),
            type("Step", (), {"action": "audio.set_volume", "arguments": {"volume": 30}, "expected_observation": "set"})(),
        ]

    candidate = learner.generate_candidate(MockTrajectory())
    assert candidate.proposed_name == "prepare_workspace"
    assert "applications" in candidate.required_capabilities

    # 2. Validate candidate
    val_res = validator.validate(candidate)
    assert val_res.valid is True

    # 3. Check promotion decision
    decision = promoter.check_promotion_criteria(candidate)
    assert decision == PromotionDecision.APPROVED

    # 4. Promote to skill
    skill = promoter.promote(candidate, save_to_disk=False)
    assert skill.name == "prepare_workspace"

    # 5. Evaluate execution
    mock_result = type("Result", (), {"success": True, "duration": 1.2, "error": None})()
    eval_res = evaluator.evaluate_execution(skill, mock_result)
    assert eval_res.success is True
    assert skill.success_rate == 1.0

    # 6. Version bumping and rollback
    # Note: promoter.promote() already bumped version to 1.1, so this bumps to 1.2
    v2 = versioner.create_version(skill, "Added volume control")
    assert v2 == "1.2"
    assert skill.version == "1.2"

    rolled_back = versioner.rollback(skill)
    assert rolled_back is True

