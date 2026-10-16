"""
tests/unit/test_skill_lifecycle.py

Unit tests for Skill dataclass and SkillValidator logic.
"""
from __future__ import annotations

from friday.skills.loader import Skill
from friday.skills.validator import SkillValidator


def test_skill_validation_valid():
    validator = SkillValidator()
    skill = Skill(
        name="open_notes",
        purpose="Open notepad for taking notes",
        trigger="open notes",
        procedure="1. action: applications.open\n   args: {'app_id': 'notepad'}",
        risk_profile="GREEN",
        required_capabilities=["applications"],
    )
    res = validator.validate(skill)
    assert res.valid is True
    assert len(res.errors) == 0


def test_skill_validation_rejects_empty_name_or_procedure():
    validator = SkillValidator()
    invalid_skill = Skill(name="", procedure="")
    res = validator.validate(invalid_skill)
    assert res.valid is False
    assert any("name" in e.lower() for e in res.errors)
    assert any("procedure" in e.lower() for e in res.errors)


def test_skill_validation_security_privilege_mismatch():
    validator = SkillValidator()
    dangerous_skill = Skill(
        name="root_wipe",
        procedure="rm -rf / --no-preserve-root",
        risk_profile="GREEN",
        required_capabilities=["terminal"],
    )
    res = validator.validate(dangerous_skill)
    assert res.valid is False
    assert any("privileged capability" in e.lower() for e in res.errors)
