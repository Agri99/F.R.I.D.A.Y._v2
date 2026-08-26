"""
src/friday/tools/terminal.py
WHAT THIS IS FOR: Sandboxed and bounded terminal access.
"""
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Any

def _run_sandbox(command: str, cwd: str | None = None, timeout: int = 30) -> dict:
    """Run command in isolated workspace directory."""
    return {"exit_code": 0, "stdout": "stub sandbox output", "stderr": ""}

def _run_host(command: str, allowlist: list[str] | None = None) -> dict:
    """Run bounded host command. Only allows specific whitelisted commands."""
    default_allowlist = ['git status', 'git log', 'git diff', 'pip list', 'pip show', 'python --version', 'ollama list']
    active_allowlist = allowlist or default_allowlist
    
    if not any(command.startswith(allowed) for allowed in active_allowlist):
        return {"exit_code": 1, "stdout": "", "stderr": "Command not allowed."}
        
    return {"exit_code": 0, "stdout": "stub host output", "stderr": ""}

def register_all_tools(registry: Any) -> None:
    """Register terminal tools to registry."""
    # terminal.sandbox - GREEN/YELLOW tier
    # terminal.host - RED tier, allowlisted commands only
    pass
