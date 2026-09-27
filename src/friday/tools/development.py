"""
src/friday/tools/development.py

WHAT THIS IS FOR:
Bridges FRIDAY's self-development pipeline (src/friday/development/) to
the tool registry, so it's actually reachable from conversation.

WHY THIS FILE DIDN'T EXIST UNTIL NOW:
The entire development/ subsystem (manager, generator, worktree, patcher,
tester with its Docker sandbox execution, simulator, reviewer,
benchmarker, canary, rollback) was real, substantial code - but nothing
registered it as a tool, and build_orchestrator() in app.py never called
a register_development_tools(). FRIDAY had no path from conversation into
self-development or Docker at all, regardless of whether the internal
logic worked. This file closes that gap.

SAFETY MODEL:
- RED tier + critical=True: requires voice confirmation AND the
  passphrase, same as any other irreversible/high-impact action.
- The pipeline NEVER merges into the real codebase. It creates a
  throwaway git worktree, applies the proposed change there, runs
  static review + tests + simulation + benchmarking, and always
  deletes the worktree afterward (see WorktreeManager.remove_worktree,
  called unconditionally in a finally block). The tool's output is a
  validated diff + report for a human to review and apply manually -
  not an autonomous merge. Auto-promotion to the live codebase is
  deliberately NOT exposed as a tool here; that would need a separate,
  even-higher-bar mechanism this project doesn't have yet.
- proposed_files must be supplied by the model as a name->content map
  (there is no separate code-generation step in generator.py - the
  caller provides the actual file contents).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from friday.tools.registry import Tool, VerificationResult


def _propose_and_validate_upgrade(goal: str, proposed_files: dict, use_docker: bool = True) -> dict:
    from friday.development.manager import SelfDevelopmentManager
    from friday.development.generator import ProposalGenerator
    from friday.development.worktree import WorktreeManager
    from friday.development.tester import IsolatedTester

    if not proposed_files:
        return {"status": "error", "message": "No proposed_files given - nothing to validate."}

    manager = SelfDevelopmentManager(repo_root=".")
    # manager's own default (IsolatedTester()) always runs on the host;
    # swap in one that actually honors use_docker (see development/tester.py).
    manager.tester = IsolatedTester(use_docker=use_docker)

    generator = ProposalGenerator()
    worktree_mgr = WorktreeManager(".")
    base_commit = worktree_mgr.get_current_commit()

    candidate = generator.create_candidate(
        goal=goal, base_commit=base_commit, files=proposed_files, risk_tier="RED",
    )

    report = manager.execute_upgrade_proposal(candidate)

    return {
        "status": "ok" if report.passed else "rejected",
        "upgrade_id": report.upgrade_id,
        "stage": report.stage,
        "passed": report.passed,
        "error": report.error,
        "review_passed": report.review_report.get("passed") if report.review_report else None,
        "test_summary": report.test_report.get("summary") if report.test_report else None,
        "diff_preview": (report.diff or "")[:2000],
        "note": (
            "This only VALIDATED the proposed change in an isolated, disposable "
            "worktree - nothing was merged into the real codebase. Review the diff "
            "and apply it manually if it passed."
        ),
    }


def _preview_propose_upgrade(goal: str, proposed_files: dict, use_docker: bool = True) -> dict:
    file_list = ", ".join(proposed_files.keys()) if proposed_files else "(no files)"
    sandbox = "Docker sandbox" if use_docker else "host subprocess"
    return {
        "found": True,
        "path": f"self-development proposal '{goal}' touching: {file_list} (validated via {sandbox})",
        "size_bytes": 0,
    }


def _verify_propose_upgrade(args: dict, result: Any) -> VerificationResult:
    """Confirms the pipeline actually ran and produced a real report - not
    that the proposed code itself is good (the pipeline's own review/test/
    simulation/benchmark stages already judge that; this just checks the
    tool didn't silently no-op)."""
    if not isinstance(result, dict):
        return VerificationResult(False, "no structured result returned")
    if result.get("status") == "error":
        return VerificationResult(False, result.get("message", "propose_and_validate_upgrade errored"))
    if "upgrade_id" not in result:
        return VerificationResult(False, "pipeline did not produce an upgrade_id - it may not have run at all")
    return VerificationResult(True, f"pipeline completed, stage={result.get('stage')}, passed={result.get('passed')}")


def _list_recent_reports(limit: int = 5) -> dict:
    reports_dir = Path("workspace/self_development/reports")
    if not reports_dir.exists():
        return {"status": "ok", "reports": []}
    files = sorted(reports_dir.glob("*_report.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    reports = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            reports.append({
                "upgrade_id": data.get("upgrade_id"),
                "stage": data.get("stage"),
                "passed": data.get("passed"),
                "error": data.get("error"),
            })
        except Exception:  # noqa: BLE001
            continue
    return {"status": "ok", "reports": reports}


def register_all_tools(registry: Any) -> None:
    registry.register(Tool(
        name="development.propose_and_validate_upgrade",
        description=(
            "Propose a code change to FRIDAY's own source and validate it end-to-end in an "
            "isolated, disposable git worktree: static security review, automated tests, "
            "scenario simulation, and benchmarking - by default inside a network-disabled "
            "Docker sandbox. Nothing is ever merged into the real codebase; this only "
            "produces a validated diff and report for the user to review and apply manually. "
            "Requires the passphrase, since this is self-modifying code."
        ),
        tier="RED",
        capability_scope="development.self_modify",
        input_schema={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "What this change is meant to accomplish"},
                "proposed_files": {
                    "type": "object",
                    "description": "Map of relative file path to full new file content for every file this change touches",
                },
                "use_docker": {
                    "type": "boolean",
                    "description": "Run tests inside an isolated Docker sandbox (default true) instead of directly on the host",
                },
            },
            "required": ["goal", "proposed_files"],
        },
        handler=lambda goal, proposed_files, use_docker=True: _propose_and_validate_upgrade(goal, proposed_files, use_docker),
        preview=_preview_propose_upgrade,
        verify=_verify_propose_upgrade,
        critical=True,
    ))

    registry.register(Tool(
        name="development.list_recent_reports",
        description="List FRIDAY's most recent self-development upgrade validation reports (read-only).",
        tier="GREEN",
        capability_scope="development.read",
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max reports to return (default 5)"}},
        },
        handler=lambda limit=5: _list_recent_reports(limit),
    ))


__all__ = ["register_all_tools"]
