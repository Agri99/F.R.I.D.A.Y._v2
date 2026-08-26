"""
Semantic memory (§13.1).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from friday.memory.database import MemoryDatabase
import re

@dataclass
class Fact:
    subject: str
    predicate: str
    value: str
    confidence: float
    source: str | None
    created_at: str

class SemanticMemory:
    """Manages semantic facts and knowledge."""
    
    def __init__(self, db: MemoryDatabase):
        self.db = db

    def store_fact(self, subject: str, predicate: str, value: str, source: str | None = None, confidence: float = 1.0) -> None:
        """Store a fact. Never persists secrets (§13.2)."""
        if self._is_secret(value) or self._is_secret(subject):
            raise ValueError("Refusing to store potential secret in semantic memory.")
            
        now = datetime.now().isoformat(timespec="seconds")
        with self.db.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO facts (subject, predicate, value, confidence, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (subject, predicate, value, confidence, source, now)
            )
            row_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO facts_fts (rowid, subject, predicate, value) VALUES (?, ?, ?, ?)",
                (row_id, subject, predicate, value)
            )

    def recall(self, query: str, limit: int = 5) -> list[Fact]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """SELECT f.subject, f.predicate, f.value, f.confidence, f.source, f.created_at
                   FROM facts_fts fts
                   JOIN facts f ON fts.rowid = f.id
                   WHERE facts_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit)
            ).fetchall()
            
        return [
            Fact(
                subject=r["subject"],
                predicate=r["predicate"],
                value=r["value"],
                confidence=r["confidence"],
                source=r["source"],
                created_at=r["created_at"]
            )
            for r in rows
        ]

    def _is_secret(self, text: str) -> bool:
        """Heuristic to avoid storing passwords, API keys, etc."""
        text = text.lower()
        if any(kw in text for kw in ("password", "secret", "api_key", "token", "credential")):
            return True
        # Look for high entropy strings like typical tokens
        if re.search(r'[A-Za-z0-9_\-]{32,}', text):
            return True
        return False
