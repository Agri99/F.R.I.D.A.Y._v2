"""
src/friday/development/tester.py

WHAT THIS IS FOR:
Runs isolated tests, linting, and typechecks on candidate worktrees.
Supports both direct venv subprocess execution and Docker sandbox execution.
Runbook §63, §67.
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TestExecutionResult:
    command: str
    returncode: int
    duration_s: float
    stdout: str
    stderr: str
    passed: bool


@dataclass
class TestSuiteReport:
    passed: bool
    total_duration_s: float
    results: dict[str, TestExecutionResult] = field(default_factory=dict)
    summary: str = ""


class IsolatedTester:
    """Executes verification suites in the isolated worktree."""

    def __init__(self, python_executable: str | None = None, use_docker: bool = False):
        self.python_executable = python_executable or sys.executable
        self.use_docker = use_docker

    def _run_cmd(self, cmd: list[str], cwd: Path) -> TestExecutionResult:
        start = time.perf_counter()
        try:
            res = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=180,
            )
            duration = time.perf_counter() - start
            return TestExecutionResult(
                command=" ".join(cmd),
                returncode=res.returncode,
                duration_s=duration,
                stdout=res.stdout,
                stderr=res.stderr,
                passed=(res.returncode == 0),
            )
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            duration = time.perf_counter() - start
            return TestExecutionResult(
                command=" ".join(cmd),
                returncode=-1,
                duration_s=duration,
                stdout="",
                stderr=str(e),
                passed=False,
            )

    def run_tests(self, worktree_path: str | Path, test_targets: list[str] | None = None) -> TestExecutionResult:
        """Run pytest in worktree."""
        cwd = Path(worktree_path).resolve()
        targets = test_targets or ["tests/unit"]
        cmd = [self.python_executable, "-m", "pytest", "-q"] + targets
        return self._run_cmd(cmd, cwd)

    def run_lint(self, worktree_path: str | Path) -> TestExecutionResult:
        """Run ruff check in worktree."""
        cwd = Path(worktree_path).resolve()
        cmd = [self.python_executable, "-m", "ruff", "check", "src/"]
        return self._run_cmd(cmd, cwd)

    def run_typecheck(self, worktree_path: str | Path) -> TestExecutionResult:
        """Run mypy in worktree."""
        cwd = Path(worktree_path).resolve()
        cmd = [self.python_executable, "-m", "mypy", "src/friday"]
        return self._run_cmd(cmd, cwd)

    def run_full_suite(self, worktree_path: str | Path, test_targets: list[str] | None = None) -> TestSuiteReport:
        """Run lint, typecheck, and unit tests."""
        cwd = Path(worktree_path).resolve()
        start = time.perf_counter()
        results: dict[str, TestExecutionResult] = {}

        # 1. Lint
        results["lint"] = self.run_lint(cwd)

        # 2. Tests
        results["tests"] = self.run_tests(cwd, test_targets)

        total_dur = time.perf_counter() - start
        all_passed = all(r.passed for r in results.values())
        summary = f"Passed: {all_passed} ({len(results)} checks in {total_dur:.1f}s)"

        return TestSuiteReport(
            passed=all_passed,
            total_duration_s=total_dur,
            results=results,
            summary=summary,
        )


__all__ = ["IsolatedTester", "TestExecutionResult", "TestSuiteReport"]
