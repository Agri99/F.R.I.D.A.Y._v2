#!/usr/bin/env python3
"""
scripts/validate_skills.py

WHAT THIS IS FOR:
Scans, validates, and audits all builtin, learned, and archived SKILL.md definitions (§28).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from friday.skills.loader import SkillLoader
from friday.skills.validator import SkillValidator


def validate_all_skills() -> bool:
    print("\n=== F.R.I.D.A.Y. Skills Audit & Validation ===\n")
    loader = SkillLoader()
    validator = SkillValidator()

    skill_dirs = [
        _ROOT / "skills" / "builtin",
        _ROOT / "skills" / "learned",
        _ROOT / "skills" / "archived",
    ]

    total_checked = 0
    total_valid = 0
    all_clean = True

    for s_dir in skill_dirs:
        if not s_dir.exists():
            continue

        skills = loader.load_from_directory(s_dir)
        print(f"[*] Checking directory: {s_dir.relative_to(_ROOT)} ({len(skills)} skills found)")
        
        for skill in skills:
            total_checked += 1
            res = validator.validate(skill)
            
            if res.valid:
                total_valid += 1
                status_tag = "[VALID]"
            else:
                all_clean = False
                status_tag = "[INVALID]"

            print(f"    {status_tag} {skill.name} (v{skill.version}, {skill.risk_profile})")
            for err in res.errors:
                print(f"        [!] Error: {err}")
            for warn in res.warnings:
                print(f"        [-] Warning: {warn}")

    print("\n----------------------------------------------")
    print(f"Summary: {total_valid}/{total_checked} skills valid.")
    print("==============================================\n")
    return all_clean


def main() -> None:
    success = validate_all_skills()
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
