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

    def record_evidence(self, key: str, value: str) -> None:
        """Increments evidence_count, recalculates confidence."""
        with self.db.connection() as conn:
            row = conn.execute("SELECT confidence, evidence_count FROM preferences WHERE key = ?", (key,)).fetchone()
            now = datetime.now().isoformat(timespec="seconds")
            if row:
                confidence = float(row["confidence"])
                evidence_count = int(row.get("evidence_count", 1))
                evidence_count += 1
                confidence = min(0.95, confidence + (0.8 - confidence) * 0.3)
                conn.execute(
                    "UPDATE preferences SET value = ?, confidence = ?, evidence_count = ?, updated_at = ? WHERE key = ?",
                    (value, confidence, evidence_count, now, key)
                )
            else:
                conn.execute(
                    """INSERT INTO preferences (key, value, confidence, evidence_count, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (key, value, 0.3, 1, now, now)
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

    def get_confident(self, key: str, min_confidence: float = 0.7) -> str | None:
        """Return preference value if confidence is high enough."""
        pref = self.get_preference(key)
        if pref and pref.confidence >= min_confidence:
            return pref.value
        return None

    def list_preferences(self) -> list[Preference]:
        with self.db.connection() as conn:
            rows = conn.execute("SELECT key, value, confidence FROM preferences").fetchall()
        return [Preference(key=r["key"], value=r["value"], confidence=r["confidence"]) for r in rows]
