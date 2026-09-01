"""Plugin candidate sandbox interface."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from friday.security.sandbox import PathValidator


@dataclass(frozen=True)
class SandboxResult:
    passed: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""


class PluginSandbox:
    """Runs plugin tests in a restricted subprocess without secrets or host privileges."""

    def __init__(
        self,
        workspace: str | Path,
        timeout_seconds: float = 60.0,
        use_docker: bool = False,
        docker_image: str = "python:3.11-slim",
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.timeout_seconds = timeout_seconds
        self.path_validator = PathValidator(self.workspace)
        self.use_docker = use_docker
        self.docker_image = docker_image
        self._docker_client = None

    def _get_docker_client(self):
        """Lazy docker client initialization."""
        if self._docker_client is None and self.use_docker:
            try:
                import docker
                self._docker_client = docker.from_env()
            except (ImportError, Exception):
                self.use_docker = False
        return self._docker_client

    def run_tests(self, plugin_path: str | Path) -> SandboxResult:
        path = self.path_validator.validate_path(plugin_path, [self.workspace])
        test_path = path / "tests"
        if not test_path.exists():
            return SandboxResult(False, 2, stderr="Plugin tests directory is missing")

        if self.use_docker:
            return self._run_tests_docker(path, test_path)
        else:
            return self._run_tests_subprocess(path, test_path)

    def _run_tests_subprocess(self, path: Path, test_path: Path) -> SandboxResult:
        sanitized_env = {
            "PATH": "",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(self.workspace),
            "TMP": str(self.workspace),
            "TMPDIR": str(self.workspace),
            "FRIDAY_SANDBOX": "1",
        }
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_path), "-q"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=sanitized_env,
            )
            return SandboxResult(result.returncode == 0, result.returncode, result.stdout, result.stderr)
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(False, 124, exc.stdout or "", exc.stderr or "Timed out")

    def _run_tests_docker(self, path: Path, test_path: Path) -> SandboxResult:
        """Run tests in an isolated Docker container."""
        client = self._get_docker_client()
        if client is None:
            return SandboxResult(False, 1, stderr="Docker client unavailable")

        # Create a temporary directory with the plugin code
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            # Copy only the plugin directory (not tests outside)
            plugin_copy = tmp_path / "plugin"
            shutil.copytree(path, plugin_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "venv", ".venv", "env", ".env"))

            try:
                # Run pytest inside container
                container = client.containers.run(
                    self.docker_image,
                    command=["python", "-m", "pytest", "/plugin/tests", "-q"],
                    volumes={
                        str(plugin_copy): {"bind": "/plugin", "mode": "ro"},
                    },
                    working_dir="/plugin",
                    environment={
                        "PYTHONNOUSERSITE": "1",
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "FRIDAY_SANDBOX": "1",
                    },
                    mem_limit="512m",
                    cpu_count=1,
                    network_mode="none",  # No network access
                    user="nobody",
                    detach=False,
                    remove=True,
                    timeout=int(self.timeout_seconds),
                )
                stdout = container.decode("utf-8") if isinstance(container, bytes) else str(container)
                return SandboxResult(True, 0, stdout=stdout)
            except Exception as exc:
                return SandboxResult(False, 1, stderr=str(exc))


__all__ = ["PluginSandbox", "SandboxResult"]