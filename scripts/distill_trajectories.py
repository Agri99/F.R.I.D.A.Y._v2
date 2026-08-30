#!/usr/bin/env python3
"""
scripts/distill_trajectories.py

WHAT THIS IS FOR:
CLI to run the PatternDistiller on all trajectory files and store candidates
in skills/learned/ for promotion review (§14).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from friday.learning.distiller import PatternDistiller


def main() -> None:
    traj_dir = _ROOT / "data" / "trajectories"
    learned_dir = _ROOT / "skills" / "learned"
    learned_dir.mkdir(parents=True, exist_ok=True)

    # NOTE: TrajectoryRecorder.finish() (learning/trajectory.py) writes files
    # as "{task_id}.jsonl", not ".json" - this glob used to only match
    # ".json" and would therefore NEVER find any trajectory file the real
    # recorder actually produces. The self-improvement pipeline (Phase 3)
    # was silently inert: this script would always print "No trajectory
    # files found" no matter how many tasks had actually run. Matching both
    # extensions so existing .json files (if any) and the real .jsonl
    # output both get picked up.
    trajectory_files = list(traj_dir.glob("*.json")) + list(traj_dir.glob("*.jsonl"))
    if not trajectory_files:
        print("[!] No trajectory files found in data/trajectories/")
        return

    trajectories = []
    for f in trajectory_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                trajectories.extend(data)
            else:
                trajectories.append(data)
        except Exception as e:
            print(f"[!] Failed to load {f}: {e}")

    print(f"[*] Loaded {len(trajectories)} trajectory records from {len(trajectory_files)} files")

    distiller = PatternDistiller()
    candidate = distiller.distill(trajectories)

    if not candidate:
        print("[!] No skill candidate could be distilled (need >= 2 successful runs)")
        return

    # Write candidate as SKILL.md
    skill_path = learned_dir / f"{candidate.name}.md"
    markdown = candidate.to_markdown() if hasattr(candidate, "to_markdown") else str(candidate.procedure)
    skill_path.write_text(markdown, encoding="utf-8")

    print(f"[+] Skill candidate created: {skill_path}")
    print(f"    Name: {candidate.name}")
    print(f"    Purpose: {candidate.purpose}")
    print(f"    Capabilities: {', '.join(candidate.required_capabilities)}")
    print(f"    Steps: {len(candidate.procedure)}")


if __name__ == "__main__":
    main()