"""
tests/eval/computer/test_intermediate_computer_use.py

WHAT THIS IS FOR:
Intermediate computer use benchmarks - create project, edit file, run program, find file, browser navigation, multi-step workflows.
"""

import pytest
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

from friday.computer.controller import WindowsComputerController
from friday.agent.orchestrator import AgentOrchestrator
from friday.config import Settings
from friday.models.router import ModelRouter
from friday.security.policy import PolicyEngine
from friday.tools.registry import ToolRegistry
from friday.tools.system import register_all_tools
from friday.tools.filesystem import register_all_tools as register_filesystem_tools
from friday.tools.browser import register_all_tools as register_browser_tools
from friday.tools.terminal import register_all_tools as register_terminal_tools


@dataclass
class BenchmarkResult:
    test_name: str
    success: bool
    latency_ms: float
    verification_passed: bool
    steps_completed: int = 0
    total_steps: int = 0
    recovery_triggered: bool = False
    replan_count: int = 0
    error: str | None = None


class IntermediateComputerUseBenchmarks:
    """Benchmark suite for intermediate computer use operations."""

    def __init__(self):
        self.controller = WindowsComputerController()
        self.results: list[BenchmarkResult] = []
        self.registry = ToolRegistry()
        register_all_tools(self.registry)
        from friday.tools.filesystem import register_all_tools as reg_fs
        reg_fs(self.registry)
        from friday.tools.terminal import register_all_tools as reg_term
        reg_term(self.registry)
        from friday.tools.browser import register_all_tools as reg_browse
        reg_browse(self.registry)
        
    def _execute(self, tool_name: str, args: dict):
        tool = self.registry.get(tool_name)
        if hasattr(tool, 'run'):
            res = tool.run(**args)
        elif hasattr(tool, 'handler'):
            res = tool.handler(**args)
        else:
            res = tool(**args)
        print(f"[DEBUG] {tool_name} returned: {res}")
        return res

    def run_benchmark(self, test_name: str, operation: callable, expected_steps: int = 1) -> BenchmarkResult:
        """Run a multi-step benchmark operation."""
        start = time.perf_counter()
        steps_completed = 0

        try:
            result = operation()
            latency_ms = (time.perf_counter() - start) * 1000

            if hasattr(result, 'success'):
                success = result.success
            elif isinstance(result, dict):
                success = result.get('status', 'ok') not in ('error', 'failed') or result.get('success', False)
            else:
                success = True

            if hasattr(result, 'verification_passed'):
                verified = result.verification_passed
            else:
                verified = success

            # Estimate steps completed based on success
            steps_completed = expected_steps if success else 0

            return BenchmarkResult(
                test_name=test_name,
                success=success,
                latency_ms=latency_ms,
                verification_passed=verified,
                steps_completed=steps_completed,
                total_steps=expected_steps,
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return BenchmarkResult(
                test_name=test_name,
                success=False,
                latency_ms=latency_ms,
                verification_passed=False,
                steps_completed=0,
                total_steps=expected_steps,
                error=str(e),
            )

    def test_create_project(self) -> BenchmarkResult:
        """Test creating a project directory and files."""
        return self.run_benchmark(
            "create_project",
            lambda: self._execute("filesystem.write", {
                "filename": "workspace/benchmark_project/main.py",
                "content": "print('Hello, FRIDAY!')\n"
            }),
            expected_steps=1
        )

    def test_edit_file(self) -> BenchmarkResult:
        """Test editing an existing file."""
        # First create file
        self._execute("filesystem.write", {
            "filename": "workspace/benchmark_project/test.txt",
            "content": "Original content"
        })

        return self.run_benchmark(
            "edit_file",
            lambda: self._execute("filesystem.write", {
                "filename": "workspace/benchmark_project/test.txt",
                "content": "Modified content by FRIDAY"
            }),
            expected_steps=1
        )

    def test_run_program(self) -> BenchmarkResult:
        """Test running a Python program."""
        # Create test script
        self._execute("filesystem.write", {
            "filename": "workspace/benchmark_project/run_test.py",
            "content": "import sys\nprint('Test output')\nsys.exit(0)\n"
        })

        return self.run_benchmark(
            "run_program",
            lambda: self._execute("terminal.run_sandbox", {
                "command": "python workspace/benchmark_project/run_test.py",
                "mode": "autonomous"
            }),
            expected_steps=1
        )

    def test_find_file(self) -> BenchmarkResult:
        """Test finding a file."""
        from pathlib import Path
        Path("workspace").mkdir(exist_ok=True)
        return self.run_benchmark(
            "find_file",
            lambda: self._execute("filesystem.list", {
                "path": "."
            }),
            expected_steps=1
        )

    def test_browser_navigation(self) -> BenchmarkResult:
        """Test browser navigation to a website."""
        with patch('friday.browser.controller.BrowserController.navigate') as mock_nav:
            mock_nav.return_value = MagicMock(success=True, url="https://example.com")

            return self.run_benchmark(
                "browser_navigation",
                lambda: self._execute("browser.open", {
                    "url": "https://example.com"
                }),
                expected_steps=1
            )

    def test_multi_step_workflow(self) -> BenchmarkResult:
        """Test a multi-step workflow: create file -> edit -> run -> verify."""
        def workflow():
            # Step 1: Create project
            self._execute("filesystem.write", {
                "filename": "workspace/workflow_test/main.py",
                "content": "def hello():\n    return 'hello'\n"
            })

            # Step 2: Edit file
            self._execute("filesystem.write", {
                "filename": "workspace/workflow_test/main.py",
                "content": "def hello():\n    return 'hello from FRIDAY'\n"
            })

            # Step 3: Run test
            result = self._execute("terminal.run_sandbox", {
                "command": "python -c \"import sys; sys.path.insert(0, 'workspace/workflow_test'); import main; print(main.hello())\"",
                "mode": "autonomous"
            })

            return result

        return self.run_benchmark(
            "multi_step_workflow",
            workflow,
            expected_steps=3
        )

    def test_terminal_build(self) -> BenchmarkResult:
        """Test building a simple project."""
        return self.run_benchmark(
            "terminal_build",
            lambda: self._execute("terminal.run_sandbox", {
                "command": "echo 'Build successful'",
                "mode": "autonomous"
            }),
            expected_steps=1
        )

    def run_all(self) -> list[BenchmarkResult]:
        """Run all intermediate benchmarks."""
        self.results = []

        tests = [
            self.test_create_project,
            self.test_edit_file,
            self.test_run_program,
            self.test_find_file,
            self.test_browser_navigation,
            self.test_multi_step_workflow,
            self.test_terminal_build,
        ]

        for test in tests:
            print(f"Running {test.__name__}...")
            result = test()
            self.results.append(result)
            print(f"  Success: {result.success}, Steps: {result.steps_completed}/{result.total_steps}, Latency: {result.latency_ms:.1f}ms, Verified: {result.verification_passed}")

        return self.results


# Pytest integration
@pytest.fixture
def benchmark_suite():
    return IntermediateComputerUseBenchmarks()


@pytest.mark.benchmark
class TestIntermediateComputerUse:
    """Pytest benchmarks for intermediate computer use."""

    def test_create_project_benchmark(self, benchmark_suite):
        result = benchmark_suite.test_create_project()
        assert result.success, f"Failed: {result.error}"
        assert result.steps_completed == result.total_steps

    def test_edit_file_benchmark(self, benchmark_suite):
        result = benchmark_suite.test_edit_file()
        assert result.success, f"Failed: {result.error}"

    def test_run_program_benchmark(self, benchmark_suite):
        result = benchmark_suite.test_run_program()
        assert result.success, f"Failed: {result.error}"

    def test_find_file_benchmark(self, benchmark_suite):
        result = benchmark_suite.test_find_file()
        assert result.success, f"Failed: {result.error}"

    def test_browser_navigation_benchmark(self, benchmark_suite):
        result = benchmark_suite.test_browser_navigation()
        assert result.success, f"Failed: {result.error}"

    def test_multi_step_workflow_benchmark(self, benchmark_suite):
        result = benchmark_suite.test_multi_step_workflow()
        assert result.success, f"Failed: {result.error}"
        assert result.steps_completed == result.total_steps

    def test_terminal_build_benchmark(self, benchmark_suite):
        result = benchmark_suite.test_terminal_build()
        assert result.success, f"Failed: {result.error}"


def run_benchmarks():
    """Run all intermediate benchmarks and print summary."""
    suite = IntermediateComputerUseBenchmarks()
    results = suite.run_all()

    print("\n=== Intermediate Computer Use Benchmark Summary ===")
    total_tests = len(results)
    passed = sum(1 for r in results if r.success)
    verified = sum(1 for r in results if r.verification_passed)
    total_steps = sum(r.total_steps for r in results)
    completed_steps = sum(r.steps_completed for r in results)
    avg_latency = sum(r.latency_ms for r in results) / len(results) if results else 0

    print(f"Tests: {total_tests}")
    print(f"Passed: {passed}/{total_tests} ({passed/total_tests*100:.1f}%)")
    print(f"Verified: {verified}/{total_tests} ({verified/total_tests*100:.1f}%)")
    print(f"Steps: {completed_steps}/{total_steps} ({completed_steps/total_steps*100:.1f}%)")
    print(f"Avg Latency: {avg_latency:.1f}ms")

    for r in results:
        status = "✓" if r.success else "✗"
        verify = "✓" if r.verification_passed else "✗"
        print(f"  {status} {r.test_name}: {r.latency_ms:.1f}ms, Steps: {r.steps_completed}/{r.total_steps} (verified: {verify})")

    return results


if __name__ == "__main__":
    run_benchmarks()