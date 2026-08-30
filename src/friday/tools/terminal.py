"""
src/friday/tools/terminal.py

WHAT THIS IS FOR:
Sandboxed and bounded terminal execution tools (Blueprint §9, §19).
Constrains autonomous shell executions to `workspace/` and enforces strict allowlists for host tools.

Phase 9: Separate host ops from autonomous execution.
- Sandbox modes: AUTONOMOUS (strict), BUILD (pip/npm/cargo), CLONE (git clone), DEVELOPMENT (full)
- Sandbox for: generated code, dependency installs, builds, scripts, repo cloning, untrusted code testing
- Avoid unrestricted PowerShell for autonomous tasks
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from friday.tools.terminal_sandbox import TerminalSandbox, SandboxMode

WORKSPACE_DIR = Path("workspace")


def _get_sandbox(mode: SandboxMode = SandboxMode.AUTONOMOUS, timeout: int = 30) -> TerminalSandbox:
    """Get a configured sandbox instance."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    return TerminalSandbox(
        sandbox_dir=WORKSPACE_DIR / "sandbox",
        mode=mode,
        timeout_seconds=timeout,
    )


def _run_sandbox(command: str, mode: str = "autonomous", timeout: int = 30) -> dict[str, Any]:
    """Run command in isolated workspace directory with mode-specific allowlist."""
    sandbox_mode = SandboxMode(mode.lower())
    sandbox = _get_sandbox(sandbox_mode, timeout)
    result = sandbox.execute(command)

    return {
        "exit_code": result.exit_code,
        "stdout": result.output[:4000],
        "stderr": (result.error or "")[:2000],
        "success": result.success,
        "mode": result.mode.value,
    }


def _run_host(command: str, allowlist: list[str] | None = None) -> dict[str, Any]:
    """Run bounded host command. Only allows specific whitelisted commands."""
    default_allowlist = [
        "git status",
        "git log",
        "git diff",
        "git branch",
        "pip list",
        "pip show",
        "python --version",
        "ollama list",
        "ollama --version",
    ]
    active_allowlist = allowlist or default_allowlist

    cmd_stripped = command.strip().lower()
    if not any(cmd_stripped.startswith(allowed.lower()) for allowed in active_allowlist):
        return {
            "exit_code": 1,
            "stdout": "",
            "stderr": f"Command '{command}' is not in the host execution allowlist.",
            "success": False,
        }

    try:
        proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[:4000],
            "stderr": proc.stderr[:2000],
            "success": proc.returncode == 0,
        }
    except Exception as exc:
        return {"exit_code": 1, "stdout": "", "stderr": str(exc), "success": False}


def _clone_repo(repo_url: str, target_dir: str | None = None) -> dict[str, Any]:
    """Clone a git repository into the sandbox (CLONE or DEVELOPMENT mode)."""
    sandbox = _get_sandbox(SandboxMode.CLONE)
    result = sandbox.clone_repository(repo_url, target_dir)
    return {
        "exit_code": result.exit_code,
        "stdout": result.output[:4000],
        "stderr": (result.error or "")[:2000],
        "success": result.success,
    }


def _install_deps(req_file: str | None = None, packages: list[str] | None = None) -> dict[str, Any]:
    """Install Python dependencies in sandbox venv (BUILD or DEVELOPMENT mode)."""
    sandbox = _get_sandbox(SandboxMode.BUILD)
    result = sandbox.install_dependencies(req_file=req_file, packages=packages)
    return {
        "exit_code": result.exit_code,
        "stdout": result.output[:4000],
        "stderr": (result.error or "")[:2000],
        "success": result.success,
    }


def _run_tests(test_command: str = "pytest") -> dict[str, Any]:
    """Run tests in sandbox (BUILD or DEVELOPMENT mode)."""
    sandbox = _get_sandbox(SandboxMode.BUILD)
    result = sandbox.run_tests(test_command)
    return {
        "exit_code": result.exit_code,
        "stdout": result.output[:4000],
        "stderr": (result.error or "")[:2000],
        "success": result.success,
    }


def _build_project(build_command: str) -> dict[str, Any]:
    """Build a project in sandbox (BUILD or DEVELOPMENT mode)."""
    sandbox = _get_sandbox(SandboxMode.BUILD)
    result = sandbox.build_project(build_command)
    return {
        "exit_code": result.exit_code,
        "stdout": result.output[:4000],
        "stderr": (result.error or "")[:2000],
        "success": result.success,
    }


def register_all_tools(registry: Any) -> None:
    """Register terminal execution tools with capability scope definitions."""
    if hasattr(registry, "register"):
        registry.register(
            name="terminal.run_sandbox",
            description="Execute a shell command inside the sandboxed workspace directory. Mode determines allowlist: autonomous (strict), build (pip/npm/cargo), clone (git clone), development (full).",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "mode": {"type": "string", "description": "Sandbox mode: autonomous, build, clone, development (default: autonomous)"},
                    "timeout": {"type": "integer", "description": "Execution timeout in seconds (default 30)"},
                },
                "required": ["command"],
            },
            handler=lambda command, mode="autonomous", timeout=30: _run_sandbox(command=command, mode=mode, timeout=timeout),
            capability_scope="terminal.sandbox",
            tier="GREEN",
        )

        registry.register(
            name="terminal.run_host",
            description="Execute safe diagnostic host commands from the allowlist (git status, pip list, ollama list). Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Allowlisted host command"},
                },
                "required": ["command"],
            },
            handler=lambda command: _run_host(command=command),
            capability_scope="terminal.host",
            tier="ORANGE",
        )

        registry.register(
            name="terminal.clone_repo",
            description="Clone a git repository into the isolated sandbox (requires CLONE or DEVELOPMENT mode).",
            parameters={
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string", "description": "Git repository URL to clone"},
                    "target_dir": {"type": "string", "description": "Optional target directory name"},
                },
                "required": ["repo_url"],
            },
            handler=lambda repo_url, target_dir=None: _clone_repo(repo_url=repo_url, target_dir=target_dir),
            capability_scope="terminal.clone",
            tier="YELLOW",
        )

        registry.register(
            name="terminal.install_deps",
            description="Install Python dependencies in sandbox virtual environment (requires BUILD or DEVELOPMENT mode).",
            parameters={
                "type": "object",
                "properties": {
                    "req_file": {"type": "string", "description": "Path to requirements.txt file"},
                    "packages": {"type": "array", "items": {"type": "string"}, "description": "List of package names to install"},
                },
            },
            handler=lambda req_file=None, packages=None: _install_deps(req_file=req_file, packages=packages),
            capability_scope="terminal.build",
            tier="YELLOW",
        )

        registry.register(
            name="terminal.run_tests",
            description="Run tests in sandbox (requires BUILD or DEVELOPMENT mode).",
            parameters={
                "type": "object",
                "properties": {
                    "test_command": {"type": "string", "description": "Test command to run (default: pytest)"},
                },
            },
            handler=lambda test_command="pytest": _run_tests(test_command=test_command),
            capability_scope="terminal.build",
            tier="YELLOW",
        )

        registry.register(
            name="terminal.build",
            description="Build a project in sandbox (requires BUILD or DEVELOPMENT mode).",
            parameters={
                "type": "object",
                "properties": {
                    "build_command": {"type": "string", "description": "Build command to execute"},
                },
                "required": ["build_command"],
            },
            handler=lambda build_command: _build_project(build_command=build_command),
            capability_scope="terminal.build",
            tier="YELLOW",
        )