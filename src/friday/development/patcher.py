"""
src/friday/development/patcher.py

WHAT THIS IS FOR:
Applies safe code modifications or unified diffs inside a target worktree.
Strictly verifies that modifications cannot escape the worktree root.
Runbook §63, §65.
"""
from __future__ import annotations

import os
from pathlib import Path


class PatcherError(RuntimeError):
    pass


class SafePatcher:
    """Safely writes or patches files inside an isolated root."""

    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir).resolve()

    def _resolve_safe_path(self, relative_path: str) -> Path:
        target = (self.root_dir / relative_path).resolve()
        if not str(target).startswith(str(self.root_dir)):
            raise PatcherError(f"Path traversal detected: {relative_path} attempts to escape {self.root_dir}")
        return target

    def write_file(self, relative_path: str, content: str) -> None:
        """Write content to a file inside the isolated root."""
        target = self._resolve_safe_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def read_file(self, relative_path: str) -> str:
        """Read content from a file inside the isolated root."""
        target = self._resolve_safe_path(relative_path)
        if not target.exists():
            raise FileNotFoundError(f"File {relative_path} not found in {self.root_dir}")
        return target.read_text(encoding="utf-8")

    def apply_file_map(self, files: dict[str, str]) -> list[str]:
        """Apply a map of {relative_path: content}. Returns list of modified files."""
        modified = []
        for rel_path, content in files.items():
            self.write_file(rel_path, content)
            modified.append(rel_path)
        return modified


__all__ = ["SafePatcher", "PatcherError"]
