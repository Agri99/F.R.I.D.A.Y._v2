"""
tests/tools/test_terminal_sandbox.py

WHAT THIS IS FOR:
Unit tests for terminal sandbox isolation and allowlist enforcement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from friday.tools.terminal_sandbox import TerminalSandbox, TerminalResult


class TestTerminalSandbox:
    @pytest.fixture
    def sandbox(self, tmp_path):
        return TerminalSandbox(
            sandbox_dir=tmp_path / "sandbox",
            allowed_commands=["git status", "git log", "python --version", "echo"],
            timeout_seconds=10,
        )

    def test_allowed_command_succeeds(self, sandbox):
        """Commands in allowlist should execute successfully."""
        result = sandbox.execute("echo hello")
        assert result.success is True
        assert "hello" in result.output

    def test_disallowed_command_rejected(self, sandbox):
        """Commands not in allowlist should be rejected."""
        result = sandbox.execute("rm -rf /")
        assert result.success is False
        assert "not in the allowed list" in result.error

    def test_partial_prefix_allowed(self, sandbox):
        """Commands matching allowed prefix should work."""
        result = sandbox.execute("echo test")
        assert result.success is True
        assert "test" in result.output

    def test_working_dir_stays_in_sandbox(self, sandbox, tmp_path):
        """Working directory must be inside sandbox."""
        result = sandbox.execute("echo test", cwd=tmp_path)
        assert result.success is False
        assert "outside sandbox" in result.error

    def test_timeout_enforced(self, sandbox):
        """Commands exceeding timeout should be killed."""
        # Create a sandbox with very short timeout
        # Use Python's time.sleep which works cross-platform
        quick_sandbox = TerminalSandbox(
            sandbox_dir=sandbox.sandbox_dir,
            allowed_commands=["python"],
            timeout_seconds=1,
        )
        result = quick_sandbox.execute("python -c \"import time; time.sleep(10)\"")
        assert result.success is False
        assert "timed out" in (result.error or "").lower() or result.exit_code == 124

    def test_sandbox_creates_directory(self, tmp_path):
        """Sandbox should create its directory on initialization."""
        sandbox_dir = tmp_path / "custom_sandbox"
        sandbox = TerminalSandbox(sandbox_dir, ["echo"])
        assert sandbox.sandbox_dir.exists()
        assert sandbox.sandbox_dir.is_dir()


class TestTerminalSandboxIntegration:
    """Integration tests with the tool registry."""

    def test_terminal_run_sandbox_uses_sandbox_class(self, tmp_path):
        """terminal.run_sandbox tool should use TerminalSandbox internally."""
        from friday.tools.terminal import _run_sandbox

        # This will fail if git not available, but should not error
        result = _run_sandbox("echo test", mode="autonomous")
        assert result["success"] is True
        assert "test" in result["stdout"]

    def test_terminal_run_host_allowlist(self):
        """terminal.run_host should enforce allowlist."""
        from friday.tools.terminal import _run_host

        result = _run_host("git status", allowlist=["git status"])
        # git may not exist in test env, but allowlist check passes
        assert "allowlist" not in (result.get("stderr") or "")

        result = _run_host("rm -rf /", allowlist=["git status"])
        assert result["success"] is False
        assert "allowlist" in result["stderr"]