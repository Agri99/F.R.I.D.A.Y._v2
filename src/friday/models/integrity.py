"""
src/friday/models/integrity.py

WHAT THIS IS FOR:
Verifies downloaded model artifacts against their expected SHA-256 checksum.
Runbook §46 (Model integrity).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class IntegrityResult:
    ok: bool
    actual_sha256: str
    expected_sha256: str
    message: str


def compute_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute the SHA-256 hex digest of a file, reading in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_file(
    path: str | Path,
    expected_sha256: str,
    expected_size_bytes: int | None = None,
) -> IntegrityResult:
    """Verify a model artifact's SHA-256 and optionally its file size.

    Returns an IntegrityResult where ``ok`` is True only if all checks pass.
    """
    path = Path(path)

    if not path.exists():
        return IntegrityResult(
            ok=False,
            actual_sha256="",
            expected_sha256=expected_sha256,
            message=f"File not found: {path}",
        )

    if expected_size_bytes is not None:
        actual_size = path.stat().st_size
        if actual_size != expected_size_bytes:
            return IntegrityResult(
                ok=False,
                actual_sha256="",
                expected_sha256=expected_sha256,
                message=f"Size mismatch: expected {expected_size_bytes} bytes, got {actual_size}",
            )

    if not expected_sha256:
        # No checksum configured — skip verification but note it.
        return IntegrityResult(
            ok=True,
            actual_sha256="",
            expected_sha256="",
            message="No expected checksum configured; skipping verification",
        )

    actual = compute_sha256(path)
    if actual.lower() == expected_sha256.lower():
        return IntegrityResult(
            ok=True,
            actual_sha256=actual,
            expected_sha256=expected_sha256,
            message="Checksum verified OK",
        )

    return IntegrityResult(
        ok=False,
        actual_sha256=actual,
        expected_sha256=expected_sha256,
        message=f"Checksum mismatch: expected {expected_sha256[:16]}… got {actual[:16]}…",
    )


__all__ = ["IntegrityResult", "compute_sha256", "verify_file"]
