"""
tests/unit/test_path_validator.py

Unit tests for PathValidator: path traversal prevention and allowlist enforcement.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from friday.security.sandbox import PathValidator


def test_path_traversal_prevention(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    validator = PathValidator(workspace_root=root)

    outside_path = root / ".." / "secrets.txt"
    with pytest.raises(ValueError, match="outside the workspace root"):
        validator.validate_path(outside_path, [root])


def test_path_allowlist_enforcement(tmp_path: Path):
    root1 = tmp_path / "allowed1"
    root2 = tmp_path / "allowed2"
    disallowed = tmp_path / "forbidden"
    root1.mkdir()
    root2.mkdir()
    disallowed.mkdir()

    validator = PathValidator()
    # Allowed path resolves cleanly
    resolved = validator.validate_path(root1 / "file.txt", [root1, root2])
    assert resolved == (root1 / "file.txt").resolve()

    # Disallowed root raises ValueError
    with pytest.raises(ValueError, match="not within any allowed roots"):
        validator.validate_path(disallowed / "file.txt", [root1, root2])
