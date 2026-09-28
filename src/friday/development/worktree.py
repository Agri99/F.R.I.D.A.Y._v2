"""
src/friday/development/worktree.py

WHAT THIS IS FOR:
Manages isolated git worktrees for self-development upgrades.
FRIDAY must never modify the production tree directly.
Runbook §63, §64, §65.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class WorktreeError(RuntimeError):
    pass


class WorktreeManager:
    """Manages isolated git worktrees or shadow isolated directories."""

    def __init__(self, repo_root: str | Path = ".", base_worktree_dir: str | Path = "workspace/self_development/worktrees"):
        self.repo_root = Path(repo_root).resolve()
        self.base_worktree_dir = Path(base_worktree_dir).resolve()
        self.base_worktree_dir.mkdir(parents=True, exist_ok=True)

    def get_current_commit(self) -> str:
        """Return the current HEAD commit hash."""
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return res.stdout.strip()
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            return "unknown-commit"

    def create_worktree(self, upgrade_id: str) -> Path:
        """Create a new branch and git worktree for the given upgrade_id."""
        worktree_path = self.base_worktree_dir / upgrade_id
        if worktree_path.exists():
            self.remove_worktree(worktree_path)

        branch_name = f"upgrade/{upgrade_id}"
        try:
            # Try git worktree add
            res = subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
                check=False, cwd=self.repo_root,
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                # Fallback: if branch exists, try without -b or checkout existing
                res2 = subprocess.run(
                    ["git", "worktree", "add", str(worktree_path), branch_name],
                    check=False, cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                )
                if res2.returncode != 0:
                    # Final fallback: shallow directory copy
                    shutil.copytree(self.repo_root, worktree_path, ignore=shutil.ignore_patterns(".git", ".venv", "workspace"))
            return worktree_path
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            # Copytree fallback
            try:
                shutil.copytree(self.repo_root, worktree_path, ignore=shutil.ignore_patterns(".git", ".venv", "workspace"))
                return worktree_path
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as copy_err:
                raise WorktreeError(f"Failed to create worktree {upgrade_id}: {copy_err}") from copy_err

    def remove_worktree(self, worktree_path: str | Path) -> None:
        """Prune and remove the worktree."""
        path = Path(worktree_path).resolve()
        if not path.exists():
            return
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(path)],
                check=False, cwd=self.repo_root,
                capture_output=True,
                text=True,
            )
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            pass
        if path.exists():
            try:
                shutil.rmtree(path, ignore_errors=True)
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                pass

    def commit_changes(self, worktree_path: str | Path, message: str) -> str:
        """Stage and commit all changes in worktree. Returns commit hash."""
        path = Path(worktree_path).resolve()
        subprocess.run(["git", "add", "-A"], check=False, cwd=path, capture_output=True, text=True)
        subprocess.run(
            ["git", "commit", "-m", message],
            check=False, cwd=path,
            capture_output=True,
            text=True,
        )
        rev = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False, cwd=path,
            capture_output=True,
            text=True,
        )
        return rev.stdout.strip() if rev.returncode == 0 else ""

    def get_diff(self, worktree_path: str | Path, base_commit: str | None = None) -> str:
        """Get git diff of the worktree against base or working tree."""
        path = Path(worktree_path).resolve()
        cmd = ["git", "diff"]
        if base_commit:
            cmd.append(base_commit)
        res = subprocess.run(cmd, check=False, cwd=path, capture_output=True, text=True)
        return res.stdout if res.returncode == 0 else ""


__all__ = ["WorktreeManager", "WorktreeError"]
