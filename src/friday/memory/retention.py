"""
Memory retention manager with confidence scoring.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from friday.memory.database import MemoryDatabase

@dataclass
class MemoryCandidate:
    category: str       # 'fact' | 'preference' | 'project' | 'episode' | 'knowledge'
    content: str
    source: str          # 'conversation' | 'trajectory' | 'user_explicit' | 'inferred'
    confidence: float    # 0.0 to 1.0
    evidence_count: int  # how many interactions support this
    created_at: datetime
    updated_at: datetime
    expiry: datetime | None = None # None = permanent

class RetentionManager:
    """Manages memory lifecycle, retention, and confidence scoring."""
    
    def __init__(self, db: MemoryDatabase):
        self.db = db

    def should_retain(self, candidate: MemoryCandidate) -> bool:
        """Determines if a candidate memory is worth keeping."""
        # Single mention -> 0.3, so any initial thought might be retained if confidence >= 0.3
        # Or explicit -> 0.9.
        if candidate.source == "user_explicit" and candidate.confidence >= 0.9:
            return True
        if candidate.confidence >= 0.3:
            return True
        return False

    def update_confidence(self, memory_id: str, category: str, new_evidence: bool) -> float:
        """Update confidence based on new evidence (True) or contradiction (False)."""
        table_map = {
            "fact": "facts",
            "preference": "preferences",
            "episode": "episodes"
        }
        table = table_map.get(category)
        if not table:
            return 0.0

        with self.db.connection() as conn:
            row = conn.execute(
                f"SELECT confidence, evidence_count FROM {table} WHERE id = ?",
                (memory_id,)
            ).fetchone()
            
            if not row:
                return 0.0
                
            confidence = float(row["confidence"])
            evidence_count = int(row["evidence_count"])

            if new_evidence:
                evidence_count += 1
                # Bump toward 0.8 or higher
                confidence = min(0.95, confidence + (0.8 - confidence) * 0.3)
            else:
                # Contradicted
                confidence = max(0.0, confidence - 0.2)

            now = datetime.now().isoformat(timespec="seconds")
            # If preference, update updated_at. Others don't have updated_at in schema.
            update_sql = f"UPDATE {table} SET confidence = ?, evidence_count = ? WHERE id = ?"
            if table == "preferences":
                update_sql = f"UPDATE {table} SET confidence = ?, evidence_count = ?, updated_at = ? WHERE id = ?"
                conn.execute(update_sql, (confidence, evidence_count, now, memory_id))
            else:
                conn.execute(update_sql, (confidence, evidence_count, memory_id))
                
            return confidence

    def expire_stale(self) -> int:
        """Soft delete expired memories by marking them."""
        # For our purposes, we'll assume expiry is a datetime string and we check if it's passed.
        # But wait, soft delete means marking. If we don't have a soft_delete column, maybe we set confidence to 0?
        # Let's set confidence to 0.0 for expired ones.
        now = datetime.now().isoformat()
        expired_count = 0
        tables = ["facts", "preferences", "episodes"]
        with self.db.connection() as conn:
            for table in tables:
                cursor = conn.execute(
                    f"UPDATE {table} SET confidence = 0.0 WHERE expiry IS NOT NULL AND expiry < ? AND confidence > 0.0",
                    (now,)
                )
                expired_count += cursor.rowcount
        return expired_count

    def merge_duplicates(self) -> int:
        """Merges duplicate memories. Returns count of merged memories."""
        # Placeholder for complex deduplication logic
        return 0
