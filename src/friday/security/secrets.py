"""
Isolated secrets store.
Never exposes raw credential values to model context.
"""
from __future__ import annotations

import os
from pathlib import Path

class SecretsManager:
    def __init__(self, secrets_dir: str | Path = "secrets"):
        self.secrets_dir = Path(secrets_dir)
        
    def _get_secret_path(self, key: str) -> Path:
        # namespaces 'google/client_id' -> 'secrets/google/client_id'
        clean_key = os.path.normpath(key)
        if clean_key.startswith("..") or os.path.isabs(clean_key):
            raise ValueError(f"Invalid secret key: {key}")
        return self.secrets_dir / clean_key

    def get(self, key: str) -> str | None:
        path = self._get_secret_path(key)
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8").strip()
        return None

    def exists(self, key: str) -> bool:
        path = self._get_secret_path(key)
        return path.exists() and path.is_file()
