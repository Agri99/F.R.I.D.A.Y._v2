"""
src/friday/development/__init__.py

WHAT THIS IS FOR:
Exports the self-development subsystem classes and utilities.
Runbook §63, §64, §85.
"""
from __future__ import annotations

from friday.development.benchmarker import BenchmarkComparison, UpgradeBenchmarker
from friday.development.canary import CanaryState, UpgradeStage
from friday.development.generator import ProposalGenerator, UpgradeCandidate
from friday.development.manager import SelfDevelopmentManager, UpgradeExecutionReport
from friday.development.patcher import PatcherError, SafePatcher
from friday.development.reviewer import CodeReviewer, ReviewFinding, ReviewReport
from friday.development.rollback import RollbackError, UpgradeRollback
from friday.development.simulator import ScenarioSimulator, SimulationResult, SimulationScenario
from friday.development.tester import IsolatedTester, TestExecutionResult, TestSuiteReport
from friday.development.worktree import WorktreeError, WorktreeManager

__all__ = [
    "BenchmarkComparison",
    "CanaryState",
    "CodeReviewer",
    "IsolatedTester",
    "PatcherError",
    "ProposalGenerator",
    "ReviewFinding",
    "ReviewReport",
    "RollbackError",
    "SafePatcher",
    "ScenarioSimulator",
    "SelfDevelopmentManager",
    "SimulationResult",
    "SimulationScenario",
    "TestExecutionResult",
    "TestSuiteReport",
    "UpgradeBenchmarker",
    "UpgradeCandidate",
    "UpgradeExecutionReport",
    "UpgradeRollback",
    "UpgradeStage",
    "WorktreeError",
    "WorktreeManager",
]
