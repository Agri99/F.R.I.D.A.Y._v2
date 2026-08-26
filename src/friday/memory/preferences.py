"""
Preference memory (§13.1).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from friday.memory.database import MemoryDatabase

@dataclass
class Preference:
    key: str
    value: str
    confidence: float

class PreferenceMemory:
    """Stores user preferences."""
    
    def __init__(self, db: MemoryDatabase):
        self.db = db

    def record_preference(self, key: str, value: str, confidence: float = 1.0) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.db.connection() as conn:
            conn.execute(
                """INSERT INTO preferences (key, value, confidence, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                   value=excluded.value,
                   confidence=excluded.confidence,
                   updated_at=excluded.updated_at""",
                (key, value, confidence, now, now)
            )

    def get_preference(self, key: str) -> Preference | None:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT key, value, confidence FROM preferences WHERE key = ?",
                (key,)
            ).fetchone()
            
        if not row:
            return None
        return Preference(key=row["key"], value=row["value"], confidence=row["confidence"])

    def list_preferences() -> list[Preference]:
        # Implementation would read all preferences
        return []
