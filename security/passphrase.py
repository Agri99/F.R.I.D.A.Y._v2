import hashlib
import os


def _hash(text: str) -> str:
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def verify_passphrase(user_text: str) -> bool:
    stored_hash = os.environ.get("PASSPHRASE_HASH", "")
    if not stored_hash:
        return False  # fail closed: no passphrase set means critical actions can never proceed
    return _hash(user_text) == stored_hash