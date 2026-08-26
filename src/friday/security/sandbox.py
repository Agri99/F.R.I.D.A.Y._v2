"""
Filesystem security and path validation (Principle B and G).
"""
from __future__ import annotations

from pathlib import Path


class PathValidator:
    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None

    def validate_path(self, target_path: str | Path, allowed_roots: list[str | Path]) -> Path:
        """
        Validates and resolves a path against allowed roots.
        Prevents path traversal attacks.
        Returns canonical path or raises ValueError.
        """
        resolved_path = Path(target_path).resolve()
        
        # Check against workspace sandbox if configured
        if self.workspace_root:
            try:
                resolved_path.relative_to(self.workspace_root)
            except ValueError:
                raise ValueError(f"Path {resolved_path} is outside the workspace root {self.workspace_root}")

        # Check against allowed roots
        is_allowed = False
        allowed_resolved = [Path(root).resolve() for root in allowed_roots]
        
        for root in allowed_resolved:
            try:
                resolved_path.relative_to(root)
                is_allowed = True
                break
            except ValueError:
                continue
                
        if not is_allowed and allowed_roots:
            raise ValueError(f"Path {resolved_path} is not within any allowed roots.")
            
        return resolved_path
