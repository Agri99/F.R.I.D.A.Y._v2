"""
Passphrase management and verification.
"""
from __future__ import annotations

import hashlib
import os


def _hash(text: str) -> str:
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def verify_passphrase(text: str) -> bool:
    """Verifies a passphrase against the environment variable."""
    stored_hash = os.environ.get("PASSPHRASE_HASH", "")
    if not stored_hash:
        return False  # fail closed: no passphrase set means critical actions can never proceed
    return _hash(text) == stored_hash


def set_passphrase(text: str) -> str:
    """Hashes a new passphrase to be stored in .env."""
    return _hash(text)
