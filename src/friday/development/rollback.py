"""
src/friday/development/rollback.py

WHAT THIS IS FOR:
Handles atomic rollback of candidates or broken upgrades.
Runbook §63, §65, §84.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class RollbackError(RuntimeError):
    pass


class UpgradeRollback:
    """Executes atomic rollbacks of failed upgrades."""

    def __init__(self, repo_root: str | Path = "."):
        self.repo_root = Path(repo_root).resolve()

    def rollback_to_commit(self, target_commit: str) -> bool:
        """Reset the working branch to a known good target commit."""
        if not target_commit:
            raise RollbackError("Target commit cannot be empty")

        res = subprocess.run(
            ["git", "reset", "--hard", target_commit],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        return res.returncode == 0

    def cleanup_upgrade_branch(self, upgrade_id: str) -> bool:
        """Delete candidate upgrade branch."""
        branch_name = f"upgrade/{upgrade_id}"
        res = subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        return res.returncode == 0


__all__ = ["UpgradeRollback", "RollbackError"]
