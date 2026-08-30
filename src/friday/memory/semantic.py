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
                "INSERT INTO facts (subject, predicate, value, confidence, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (subject, predicate, value, confidence, source, now, now)
            )
            row_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO facts_fts (rowid, subject, predicate, value) VALUES (?, ?, ?, ?)",
                (row_id, subject, predicate, value)
            )

    def store_project_knowledge(self, project: str, knowledge: str, source: str) -> None:
        """Store project specific knowledge."""
        self.store_fact(subject=f"project:{project}", predicate="has_knowledge", value=knowledge, source=source)

    def recall(self, query: str, limit: int = 5) -> list[Fact]:
        """Recall facts matching query. Escapes FTS5 special characters."""
        # Escape FTS5 special characters to prevent syntax errors
        escaped_query = self._escape_fts5_query(query)

        with self.db.connection() as conn:
            rows = conn.execute(
                """SELECT f.subject, f.predicate, f.value, f.confidence, f.source, f.created_at
                   FROM facts_fts fts
                   JOIN facts f ON fts.rowid = f.id
                   WHERE facts_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (escaped_query, limit)
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

    def _escape_fts5_query(self, query: str) -> str:
        """Escape FTS5 special characters in query string.

        FTS5 uses a different escaping mechanism - we need to quote the query
        and escape any double quotes inside it. Special characters in FTS5
        include: " + - * ( ) : < > = ! @ $ % . , ; ? [ ] { } | ^ ~ \
        """
        # First escape any existing double quotes
        escaped = query.replace('"', '""')

        # Wrap the entire query in double quotes to treat as a phrase
        # This prevents special characters from being interpreted as operators
        return f'"{escaped}"'

    def search_by_relevance(self, query: str, limit: int = 5) -> list[dict]:
        """Search facts with confidence weighting."""
        facts = self.recall(query, limit=limit * 2) # Fetch more to sort
        facts.sort(key=lambda f: f.confidence, reverse=True)
        return [
            {
                "subject": f.subject,
                "predicate": f.predicate,
                "value": f.value,
                "confidence": f.confidence,
                "source": f.source
            }
            for f in facts[:limit]
        ]

    def export(self, format: str = "json") -> str:
        """Human-readable export format."""
        import json
        with self.db.connection() as conn:
            rows = conn.execute("SELECT * FROM facts").fetchall()
        
        data = [dict(r) for r in rows]
        if format == "json":
            return json.dumps(data, indent=2)
        elif format == "yaml":
            import yaml
            return yaml.dump(data)
        return str(data)

    def _is_secret(self, text: str) -> bool:
        """Heuristic to avoid storing passwords, API keys, etc."""
        text = text.lower()
        if any(kw in text for kw in ("password", "secret", "api_key", "token", "credential")):
            return True
        # Look for high entropy strings like typical tokens
        if re.search(r'[A-Za-z0-9_\-]{32,}', text):
            return True
        return False
