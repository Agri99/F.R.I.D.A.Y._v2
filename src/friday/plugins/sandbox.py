"""Plugin candidate sandbox interface."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from friday.security.sandbox import PathValidator


@dataclass(frozen=True)
class SandboxResult:
    passed: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""


class PluginSandbox:
    """Runs plugin tests in a restricted subprocess without secrets or host privileges."""

    def __init__(self, workspace: str | Path, timeout_seconds: float = 60.0) -> None:
        self.workspace = Path(workspace).resolve()
        self.timeout_seconds = timeout_seconds
        self.path_validator = PathValidator(self.workspace)

    def run_tests(self, plugin_path: str | Path) -> SandboxResult:
        path = self.path_validator.validate_path(plugin_path, [self.workspace])
        test_path = path / "tests"
        if not test_path.exists():
            return SandboxResult(False, 2, stderr="Plugin tests directory is missing")
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


__all__ = ["PluginSandbox", "SandboxResult"]
