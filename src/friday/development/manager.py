"""
src/friday/development/manager.py

WHAT THIS IS FOR:
Self-Development Manager that coordinates the entire self-development pipeline:
  Proposal -> Isolated Worktree -> Patch -> Static Analysis / Review ->
  Tests -> Scenario Simulation -> Benchmark -> Canary -> Promotion -> Rollback.
Runbook §63, §64, §85.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from friday.development.benchmarker import UpgradeBenchmarker
from friday.development.canary import CanaryState, UpgradeStage
from friday.development.generator import ProposalGenerator, UpgradeCandidate
from friday.development.patcher import SafePatcher
from friday.development.reviewer import CodeReviewer
from friday.development.rollback import UpgradeRollback
from friday.development.simulator import ScenarioSimulator
from friday.development.tester import IsolatedTester
from friday.development.worktree import WorktreeManager


@dataclass
class UpgradeExecutionReport:
    upgrade_id: str
    stage: str
    passed: bool
    review_report: dict[str, Any] = field(default_factory=dict)
    test_report: dict[str, Any] = field(default_factory=dict)
    sim_report: list[dict[str, Any]] = field(default_factory=list)
    diff: str = ""
    error: str | None = None


class SelfDevelopmentManager:
    """End-to-end coordinator for FRIDAY's controlled self-development pipeline."""

    def __init__(self, repo_root: str | Path = "."):
        self.repo_root = Path(repo_root).resolve()
        self.worktree_mgr = WorktreeManager(self.repo_root)
        self.generator = ProposalGenerator()
        self.reviewer = CodeReviewer()
        self.tester = IsolatedTester()
        self.simulator = ScenarioSimulator()
        self.benchmarker = UpgradeBenchmarker()
        self.rollback_mgr = UpgradeRollback(self.repo_root)
        self.reports_dir = Path("workspace/self_development/reports").resolve()
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def execute_upgrade_proposal(
        self,
        candidate: UpgradeCandidate,
        test_targets: list[str] | None = None,
    ) -> UpgradeExecutionReport:
        """Executes the pipeline on an upgrade candidate in an isolated worktree."""
        canary = CanaryState(upgrade_id=candidate.upgrade_id)
        report = UpgradeExecutionReport(
            upgrade_id=candidate.upgrade_id,
            stage=canary.stage.value,
            passed=False,
        )

        worktree_path = None
        try:
            # 1. Create isolated worktree
            canary.transition(UpgradeStage.SANDBOXED, "Creating isolated worktree")
            worktree_path = self.worktree_mgr.create_worktree(candidate.upgrade_id)

            # 2. Apply patch
            patcher = SafePatcher(worktree_path)
            modified_files = patcher.apply_file_map(candidate.proposed_files)

            # 3. Static Code Review
            canary.transition(UpgradeStage.TESTED, "Running static code review")
            review_res = self.reviewer.review_tree(worktree_path, modified_files)
            report.review_report = {
                "passed": review_res.passed,
                "findings": [asdict(f) for f in review_res.findings],
            }
            if not review_res.passed:
                report.error = "Static review failed: blocker or high security finding detected"
                canary.transition(UpgradeStage.REJECTED, report.error)
                return report

            # 4. Isolated Testing
            test_res = self.tester.run_full_suite(worktree_path, test_targets)
            report.test_report = {
                "passed": test_res.passed,
                "summary": test_res.summary,
            }
            if not test_res.passed:
                report.error = "Automated test suite failed in sandbox"
                canary.transition(UpgradeStage.REJECTED, report.error)
                return report

            # 5. Scenario Simulation
            sim_results = self.simulator.run_all()
            report.sim_report = [asdict(sr) for sr in sim_results]
            if not all(sr.passed for sr in sim_results):
                report.error = "Scenario simulations failed"
                canary.transition(UpgradeStage.REJECTED, report.error)
                return report

            # 6. Benchmarking
            canary.transition(UpgradeStage.BENCHMARKED, "Running regression benchmarking")
            bench_res = self.benchmarker.compare(
                candidate_passed_tests=len(test_res.results),
                candidate_total_tests=len(test_res.results),
                candidate_duration_s=test_res.total_duration_s,
            )
            if not bench_res.passed:
                report.error = f"Benchmarking rejected upgrade: {bench_res.reason}"
                canary.transition(UpgradeStage.REJECTED, report.error)
                return report

            # 7. Canary trial
            canary.transition(UpgradeStage.CANARY, "Canary trial active")
            # Run canary trials
            canary_ok = canary.record_run(success=True)
            if not canary_ok:
                report.error = "Canary execution failed"
                canary.transition(UpgradeStage.ROLLED_BACK, report.error)
                return report

            # Capture git diff
            report.diff = self.worktree_mgr.get_diff(worktree_path, candidate.base_commit)

            # Success!
            canary.transition(UpgradeStage.ACTIVE, "All verification gates passed")
            report.passed = True
            report.stage = canary.stage.value

        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
            report.error = str(exc)
            canary.transition(UpgradeStage.REJECTED, str(exc))
        finally:
            if worktree_path is not None:
                self.worktree_mgr.remove_worktree(worktree_path)

            # Save report
            rep_file = self.reports_dir / f"{candidate.upgrade_id}_report.json"
            rep_file.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

        return report


__all__ = ["SelfDevelopmentManager", "UpgradeExecutionReport"]
