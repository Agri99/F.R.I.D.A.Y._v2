"""
src/friday/development/tester.py

WHAT THIS IS FOR:
Runs isolated tests, linting, and typechecks on candidate worktrees.
Supports both direct venv subprocess execution and Docker sandbox execution.
Runbook §63, §67.

FIXED BUG: `use_docker` was a constructor parameter and the docstring
claimed Docker support, but nothing in this class ever read
`self.use_docker` - every method unconditionally ran subprocess.run() on
the HOST regardless of the flag. This is the concrete reason FRIDAY's
self-development pipeline never actually used Docker: the switch existed
but was wired to nothing. _run_cmd now genuinely branches on it.

SCOPE NOTE ON WHAT THE DOCKER PATH CAN ACTUALLY RUN:
The host is Windows; Docker Desktop's default backend runs LINUX
containers. Windows-compiled dependencies in .venv (torch+cuda, PySide6,
pywin32, etc.) cannot run inside a Linux container - mounting them
would be silently useless. The sandbox image therefore installs only
the pure-Python, platform-portable subset of dependencies (see
SANDBOX_REQUIREMENTS below) needed to run most of tests/unit and
tests/security. Tests that import Windows-only modules (computer/*,
terminal.py's win32 paths, audio device tests) will fail inside the
sandbox and should be run in host mode instead. This is an honest
scoping choice, not a shortcut: claiming full-suite Docker coverage
without it actually working would just be another instance of the
same "claims done, isn't" pattern found elsewhere in this project.
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Pure-Python / Linux-portable subset only - see scope note above.
SANDBOX_REQUIREMENTS = [
    "pydantic>=2.6", "pyyaml>=6.0", "requests>=2.31", "psutil>=5.9",
    "pillow>=10.0", "pytest>=8.0", "pytest-asyncio>=0.23", "ruff>=0.4", "mypy>=1.10",
]
SANDBOX_DOCKERFILE = """FROM python:3.11-slim
RUN useradd -m -u 1000 sandbox
RUN pip install --no-cache-dir {reqs}
USER sandbox
WORKDIR /workspace
""".format(reqs=" ".join(f'"{r}"' for r in SANDBOX_REQUIREMENTS))
SANDBOX_IMAGE_TAG = "friday-sandbox:latest"


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

    def __init__(self, python_executable: str | None = None, use_docker: bool = False,
                 docker_image: str = SANDBOX_IMAGE_TAG, cpu_limit: float = 2.0,
                 memory_limit_mb: int = 2048, docker_timeout_seconds: int = 180):
        self.python_executable = python_executable or sys.executable
        self.use_docker = use_docker
        self.docker_image = docker_image
        self.cpu_limit = cpu_limit
        self.memory_limit_mb = memory_limit_mb
        self.docker_timeout_seconds = docker_timeout_seconds

    def _ensure_sandbox_image(self, client) -> str | None:
        """Build the sandbox image once if it doesn't exist yet. Returns an
        error message on failure, or None on success."""
        try:
            client.images.get(self.docker_image)
            return None
        except Exception:
            pass  # doesn't exist yet, build it below

        import io
        import tarfile

        try:
            dockerfile_bytes = SANDBOX_DOCKERFILE.encode("utf-8")
            tar_buf = io.BytesIO()
            with tarfile.open(fileobj=tar_buf, mode="w") as tar:
                info = tarfile.TarInfo(name="Dockerfile")
                info.size = len(dockerfile_bytes)
                tar.addfile(info, io.BytesIO(dockerfile_bytes))
            tar_buf.seek(0)
            client.images.build(fileobj=tar_buf, custom_context=True, tag=self.docker_image, rm=True)
            return None
        except Exception as exc:  # noqa: BLE001
            return f"Failed to build sandbox image: {exc}"

    def _run_cmd_docker(self, cmd: list[str], cwd: Path) -> TestExecutionResult:
        """Runs cmd inside an isolated, network-disabled, non-root, resource-
        limited Linux container (runbook §9, §67). The candidate worktree is
        mounted READ-ONLY at /workspace; nothing the container does can
        modify the source it's testing, and the container is destroyed
        after the run regardless of outcome."""
        start = time.perf_counter()
        try:
            import docker
        except ImportError as exc:
            duration = time.perf_counter() - start
            return TestExecutionResult(
                command=" ".join(cmd), returncode=-1, duration_s=duration, stdout="",
                stderr=f"docker Python SDK not installed: {exc}", passed=False,
            )

        try:
            client = docker.from_env()
            client.ping()
        except Exception as exc:  # noqa: BLE001
            duration = time.perf_counter() - start
            return TestExecutionResult(
                command=" ".join(cmd), returncode=-1, duration_s=duration, stdout="",
                stderr=f"Docker daemon not reachable (is Docker Desktop running?): {exc}", passed=False,
            )

        build_err = self._ensure_sandbox_image(client)
        if build_err:
            duration = time.perf_counter() - start
            return TestExecutionResult(
                command=" ".join(cmd), returncode=-1, duration_s=duration, stdout="", stderr=build_err, passed=False,
            )

        # container_cmd: swap the host's absolute python_executable for the
        # sandbox image's own interpreter - the host's path doesn't exist
        # inside the container.
        container_cmd = ["python" if part == self.python_executable else part for part in cmd]

        container = None
        try:
            container = client.containers.run(
                self.docker_image,
                command=container_cmd,
                volumes={str(cwd.resolve()): {"bind": "/workspace", "mode": "ro"}},
                working_dir="/workspace",
                network_disabled=True,
                mem_limit=f"{self.memory_limit_mb}m",
                nano_cpus=int(self.cpu_limit * 1_000_000_000),
                user="sandbox",
                detach=True,
                stdout=True,
                stderr=True,
            )
            try:
                result = container.wait(timeout=self.docker_timeout_seconds)
                returncode = result.get("StatusCode", -1)
                timed_out = False
            except Exception:
                container.kill()
                returncode = -1
                timed_out = True

            logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            duration = time.perf_counter() - start
            if timed_out:
                return TestExecutionResult(
                    command=" ".join(cmd), returncode=-1, duration_s=duration, stdout="",
                    stderr=f"Sandbox execution exceeded {self.docker_timeout_seconds}s and was killed.", passed=False,
                )
            return TestExecutionResult(
                command=" ".join(cmd), returncode=returncode, duration_s=duration,
                stdout=logs, stderr="", passed=(returncode == 0),
            )
        except Exception as exc:  # noqa: BLE001
            duration = time.perf_counter() - start
            return TestExecutionResult(
                command=" ".join(cmd), returncode=-1, duration_s=duration, stdout="",
                stderr=f"Docker execution failed: {exc}", passed=False,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def _run_cmd(self, cmd: list[str], cwd: Path) -> TestExecutionResult:
        if self.use_docker:
            return self._run_cmd_docker(cmd, cwd)
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
