"""
src/friday/sandbox/docker_sandbox.py

WHAT THIS IS FOR:
Docker sandbox for untrusted plugins and skills (Runbook §30 — Phase D1).

Provides network isolation, resource limits, filesystem isolation, and timeout
enforcement for plugins that cannot be trusted with direct host access.
"""

from __future__ import annotations

import subprocess
import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SandboxConfig:
    """Docker sandbox configuration."""
    image: str = "python:3.11-slim"
    memory_limit_mb: int = 512
    cpus: float = 0.5
    timeout_seconds: int = 30
    network_mode: str = "none"  # Isolation: no network access
    readonly_root: bool = True
    user: str = "nobody"


class DockerSandbox:
    """Executes code in an isolated Docker container."""

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self._verify_docker_available()

    def _verify_docker_available(self) -> None:
        """Check if Docker daemon is running."""
        try:
            subprocess.run(
                ["docker", "ps"],
                capture_output=True,
                timeout=5,
                check=True,
            )
        except Exception as e:
            raise RuntimeError(f"Docker not available: {e}")

    def execute(
        self,
        code: str,
        input_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute Python code in a sandboxed container.

        Args:
            code: Python code to execute
            input_data: Data to pass to the code via stdin

        Returns:
            Dict with 'output', 'error', 'return_code', 'duration_ms'
        """
        start_time = time.time()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write code to file
            code_path = Path(tmpdir) / "run.py"
            code_path.write_text(code)

            # Build docker run command
            cmd = [
                "docker",
                "run",
                "--rm",
                "-i",
                f"--memory={self.config.memory_limit_mb}m",
                f"--cpus={self.config.cpus}",
                f"--network={self.config.network_mode}",
                f"--user={self.config.user}",
                "--read-only" if self.config.readonly_root else "",
                "--tmpfs=/tmp:size=100m",  # Small tmpdir
                f"-v={code_path}:/app/run.py:ro",
                self.config.image,
                "python",
                "/app/run.py",
            ]
            cmd = [c for c in cmd if c]  # Remove empty strings

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.config.timeout_seconds,
                    input=json.dumps(input_data) if input_data else None,
                )

                duration_ms = (time.time() - start_time) * 1000

                return {
                    "output": result.stdout,
                    "error": result.stderr,
                    "return_code": result.returncode,
                    "duration_ms": round(duration_ms, 2),
                    "timeout": False,
                }

            except subprocess.TimeoutExpired:
                duration_ms = (time.time() - start_time) * 1000
                return {
                    "output": "",
                    "error": f"Execution timeout after {self.config.timeout_seconds}s",
                    "return_code": -1,
                    "duration_ms": round(duration_ms, 2),
                    "timeout": True,
                }
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                return {
                    "output": "",
                    "error": str(e),
                    "return_code": -1,
                    "duration_ms": round(duration_ms, 2),
                    "timeout": False,
                }


class SandboxedPlugin:
    """Wraps a plugin to run in sandbox."""

    def __init__(
        self,
        plugin_name: str,
        plugin_code: str,
        sandbox: DockerSandbox | None = None,
    ):
        self.name = plugin_name
        self.code = plugin_code
        self.sandbox = sandbox or DockerSandbox()

    def execute(self, function: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a function from the plugin.

        Args:
            function: Function name in the plugin code
            args: Arguments to pass

        Returns:
            Result from the sandboxed execution
        """
        # Wrap the plugin code to call the specific function
        wrapper = f"""
import json
import sys

# Plugin code
{self.code}

# Call the function
try:
    result = {function}(**json.loads(sys.stdin.read()))
    print(json.dumps({{"success": True, "result": result}}))
except Exception as e:
    print(json.dumps({{"success": False, "error": str(e)}}))
    sys.exit(1)
"""
        result = self.sandbox.execute(wrapper, input_data=args)

        if result["return_code"] == 0:
            try:
                output = json.loads(result["output"])
                return output
            except json.JSONDecodeError:
                return {"success": False, "error": "Invalid JSON output"}
        else:
            try:
                output = json.loads(result["output"])
                return output
            except Exception:
                return {
                    "success": False,
                    "error": result.get("error") or result.get("output") or "Execution failed",
                }


__all__ = [
    "SandboxConfig",
    "DockerSandbox",
    "SandboxedPlugin",
]
