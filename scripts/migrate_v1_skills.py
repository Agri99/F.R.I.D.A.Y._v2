"""
scripts/migrate_v1_skills.py

WHAT THIS IS FOR:
Migrates legacy skills from v1 skills.json to the new v2 SKILL.md format
under skills/learned/ per blueprint §32.1 and §34 Phase 10.
"""

from __future__ import annotations

import json
from pathlib import Path


def migrate_skills(
    source_path: str | Path = "skills.json",
    dest_dir: str | Path = "skills/learned",
) -> int:
    source = Path(source_path)
    if not source.exists():
        print(f"No {source_path} found. Nothing to migrate.")
        return 0

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    try:
        raw_data = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to parse {source_path}: {exc}")
        return 0

    migrated_count = 0
    for skill_name, steps in raw_data.items():
        doc = [f"# {skill_name}\n"]
        doc.append("## Purpose\nMigrated legacy workflow from F.R.I.D.A.Y. v1.\n")
        doc.append("## Trigger\n" + f'"{skill_name.replace("_", " ")}"\n')
        doc.append("## Risk Profile\nYELLOW\n")
        doc.append("## Prerequisites\n- Workspace directory available\n")
        doc.append("## Procedure")

        for idx, step in enumerate(steps, 1):
            tool = step.get("tool", "unknown_tool")
            args = step.get("arguments", {})
            doc.append(f"{idx}. Call `{tool}` with arguments `{json.dumps(args)}`")

        doc.append("\n## Verification\n- Action completed without errors\n")
        doc.append("## Failure Modes\n- Tool execution failure\n")
        doc.append("## Recovery\n- Notify user and halt\n")

        file_content = "\n".join(doc)
        output_file = dest / f"{skill_name}.md"
        output_file.write_text(file_content, encoding="utf-8")
        print(f"Migrated skill '{skill_name}' -> {output_file}")
        migrated_count += 1

    return migrated_count


if __name__ == "__main__":
    count = migrate_skills()
    print(f"Successfully migrated {count} skills.")

