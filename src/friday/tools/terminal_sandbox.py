"""
src/friday/tools/terminal_sandbox.py

WHAT THIS IS FOR:
Secure terminal execution in an isolated sandbox (§20). Runs commands in a
subprocess restricted to the workspace/sandbox directory with a capability
allowlist from configuration.

Enhanced for Phase 9: Separate host ops from autonomous execution.
Sandbox for: generated code, dependency installs, builds, scripts, repo cloning, untrusted code testing.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import venv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from enum import Enum


class SandboxMode(Enum):
    """Sandbox execution mode."""
    AUTONOMOUS = "autonomous"    # Fully isolated, strict allowlist
    BUILD = "build"              # Build tools allowed (pip, npm, cargo, etc.)
    CLONE = "clone"              # Git clone allowed
    DEVELOPMENT = "development"  # Broader toolset for development


@dataclass
class TerminalResult:
    success: bool
    output: str
    exit_code: int
    error: Optional[str] = None
    mode: SandboxMode = SandboxMode.AUTONOMOUS


# Commands that are shell builtins on Windows
SHELL_BUILTINS = {"echo", "cd", "dir", "type", "cls", "copy", "del", "ren", "move", "md", "rd"}

# Default allowlists per mode
AUTONOMOUS_ALLOWLIST = [
    "git status", "git log", "git diff", "git branch", "git show",
    "pip list", "pip show", "pip --version",
    "python --version", "python -c", "python -m",
    "node --version", "npm --version", "npm list",
    "ollama list", "ollama --version",
    "cargo --version", "cargo build", "cargo test",
    "go version", "go build", "go test",
    "dotnet --version", "dotnet build",
    "make --version", "cmake --version",
    "echo",  # Shell builtin
]

BUILD_ALLOWLIST = AUTONOMOUS_ALLOWLIST + [
    "pip install", "pip uninstall", "pip freeze",
    "npm install", "npm ci", "npm run",
    "yarn install", "yarn add", "yarn build",
    "cargo build", "cargo test", "cargo install",
    "go build", "go test", "go mod",
    "dotnet build", "dotnet restore", "dotnet test",
    "make", "cmake", "msbuild",
    "pipx install", "pipx run",
    "uv pip install", "uv sync",
]

CLONE_ALLOWLIST = AUTONOMOUS_ALLOWLIST + [
    "git clone", "git fetch", "git pull", "git checkout", "git switch",
    "git submodule update", "git submodule init",
]

DEVELOPMENT_ALLOWLIST = BUILD_ALLOWLIST + CLONE_ALLOWLIST + [
    "git push", "git tag", "git merge", "git rebase",
    "pip install -e", "npm link",
    "pytest", "jest", "vitest",
    "docker build", "docker run", "docker compose",
    "kubectl", "helm",
]


class TerminalSandbox:
    """Sandboxed terminal executor with capability-based allowlist per mode."""

    def __init__(
        self,
        sandbox_dir: Path | str = "workspace/sandbox",
        mode: SandboxMode = SandboxMode.AUTONOMOUS,
        allowed_commands: Optional[list[str]] = None,
        timeout_seconds: int = 30,
        max_output_chars: int = 10000,
    ):
        self.sandbox_dir = Path(sandbox_dir).resolve()
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

        # Build combined allowlist
        if mode == SandboxMode.AUTONOMOUS:
            base_allowlist = AUTONOMOUS_ALLOWLIST
        elif mode == SandboxMode.BUILD:
            base_allowlist = BUILD_ALLOWLIST
        elif mode == SandboxMode.CLONE:
            base_allowlist = CLONE_ALLOWLIST
        elif mode == SandboxMode.DEVELOPMENT:
            base_allowlist = DEVELOPMENT_ALLOWLIST
        else:
            base_allowlist = AUTONOMOUS_ALLOWLIST

        self.allowed_commands = list(set(base_allowlist + (allowed_commands or [])))

        # Create virtual environment for build mode
        self._venv_path: Optional[Path] = None
        if mode in (SandboxMode.BUILD, SandboxMode.DEVELOPMENT):
            self._venv_path = self.sandbox_dir / ".venv"
            if not self._venv_path.exists():
                self._create_venv()

    def _create_venv(self) -> None:
        """Create a virtual environment in the sandbox."""
        try:
            venv.create(self._venv_path, with_pip=True)
        except Exception:
            self._venv_path = None

    def _get_venv_python(self) -> Optional[Path]:
        """Get the Python executable from the virtual environment."""
        if not self._venv_path or not self._venv_path.exists():
            return None
        if sys.platform == "win32":
            return self._venv_path / "Scripts" / "python.exe"
        return self._venv_path / "bin" / "python"

    def _get_environment(self) -> dict[str, str]:
        """Get environment for subprocess execution."""
        env = {**os.environ, "FRIDAY_SANDBOX": "true", "FRIDAY_SANDBOX_MODE": self.mode.value}
        if self._venv_path and self._venv_path.exists():
            if sys.platform == "win32":
                env["PATH"] = str(self._venv_path / "Scripts") + os.pathsep + env.get("PATH", "")
            else:
                env["PATH"] = str(self._venv_path / "bin") + os.pathsep + env.get("PATH", "")
            env["VIRTUAL_ENV"] = str(self._venv_path)
        return env

    def _check_allowed(self, command: str) -> tuple[bool, str]:
        """Verify the command (and its arguments) are permitted."""
        parts = shlex.split(command)
        if not parts:
            return False, "Empty command"

        cmd = parts[0]
        # Check if the base command is allowed
        for allowed in self.allowed_commands:
            allowed_parts = shlex.split(allowed)
            if allowed_parts and cmd == allowed_parts[0]:
                if len(allowed_parts) == 1:
                    return True, ""
                if len(parts) >= len(allowed_parts):
                    if parts[:len(allowed_parts)] == allowed_parts:
                        return True, ""
                else:
                    if parts == allowed_parts[:len(parts)]:
                        return True, ""

        return False, f"Command '{cmd}' is not in the allowed list for {self.mode.value} mode"

    def execute(self, command: str, cwd: Optional[Path] = None) -> TerminalResult:
        """Execute a command in the sandbox directory."""
        allowed, reason = self._check_allowed(command)
        if not allowed:
            return TerminalResult(success=False, output="", exit_code=1, error=reason, mode=self.mode)

        working_dir = (cwd or self.sandbox_dir).resolve()
        # Ensure the working directory is inside the sandbox
        if not str(working_dir).startswith(str(self.sandbox_dir)):
            return TerminalResult(
                success=False,
                output="",
                exit_code=1,
                error=f"Working directory {working_dir} is outside sandbox {self.sandbox_dir}",
                mode=self.mode,
            )

        # Determine if this is a shell builtin (needs shell=True on Windows)
        parts = shlex.split(command)
        cmd = parts[0].lower() if parts else ""
        use_shell = cmd in SHELL_BUILTINS or sys.platform == "win32"

        # Handle python commands - use venv python if available
        final_command = command
        if cmd in ("python", "python3", "python.exe") and self._venv_path:
            venv_python = self._get_venv_python()
            if venv_python and venv_python.exists():
                final_command = str(venv_python) + " " + " ".join(parts[1:])
                use_shell = False

        try:
            result = subprocess.run(
                final_command if use_shell else shlex.split(final_command),
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=self._get_environment(),
                shell=use_shell,
            )

            output = result.stdout + result.stderr
            if len(output) > self.max_output_chars:
                output = output[:self.max_output_chars] + f"\n...[TRUNCATED: {len(output)} total chars]"

            return TerminalResult(
                success=result.returncode == 0,
                output=output if output else "(no output)",
                exit_code=result.returncode,
                error=None if result.returncode == 0 else result.stderr,
                mode=self.mode,
            )
        except subprocess.TimeoutExpired:
            return TerminalResult(
                success=False,
                output="",
                exit_code=124,
                error=f"Command timed out after {self.timeout_seconds}s",
                mode=self.mode,
            )
        except Exception as exc:
            return TerminalResult(success=False, output="", exit_code=1, error=str(exc), mode=self.mode)

    def clone_repository(self, repo_url: str, target_dir: Optional[str] = None) -> TerminalResult:
        """Clone a git repository into the sandbox."""
        if self.mode not in (SandboxMode.CLONE, SandboxMode.DEVELOPMENT):
            return TerminalResult(
                success=False, output="", exit_code=1,
                error=f"Repository cloning requires CLONE or DEVELOPMENT mode, current: {self.mode.value}",
                mode=self.mode
            )

        target = self.sandbox_dir / (target_dir or Path(repo_url).stem.replace(".git", ""))
        if target.exists():
            return TerminalResult(
                success=False, output="", exit_code=1,
                error=f"Target directory {target} already exists",
                mode=self.mode
            )

        return self.execute(f"git clone {shlex.quote(repo_url)} {shlex.quote(str(target))}")

    def install_dependencies(self, req_file: Optional[str] = None, packages: Optional[list[str]] = None) -> TerminalResult:
        """Install Python dependencies in the sandbox venv."""
        if self.mode not in (SandboxMode.BUILD, SandboxMode.DEVELOPMENT):
            return TerminalResult(
                success=False, output="", exit_code=1,
                error=f"Dependency installation requires BUILD or DEVELOPMENT mode, current: {self.mode.value}",
                mode=self.mode
            )

        if req_file:
            return self.execute(f"pip install -r {shlex.quote(req_file)}")
        elif packages:
            return self.execute(f"pip install {' '.join(shlex.quote(p) for p in packages)}")
        else:
            return TerminalResult(success=False, output="", exit_code=1, error="No requirements file or packages specified", mode=self.mode)

    def run_tests(self, test_command: str = "pytest") -> TerminalResult:
        """Run tests in the sandbox."""
        if self.mode not in (SandboxMode.BUILD, SandboxMode.DEVELOPMENT):
            return TerminalResult(
                success=False, output="", exit_code=1,
                error=f"Test execution requires BUILD or DEVELOPMENT mode, current: {self.mode.value}",
                mode=self.mode
            )
        return self.execute(test_command)

    def build_project(self, build_command: str) -> TerminalResult:
        """Build a project in the sandbox."""
        if self.mode not in (SandboxMode.BUILD, SandboxMode.DEVELOPMENT):
            return TerminalResult(
                success=False, output="", exit_code=1,
                error=f"Build execution requires BUILD or DEVELOPMENT mode, current: {self.mode.value}",
                mode=self.mode
            )
        return self.execute(build_command)