"""
Memory retention manager with confidence scoring, source tracking, and decay policies.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from friday.memory.database import MemoryDatabase


@dataclass
class MemoryCandidate:
    category: str       # 'fact' | 'preference' | 'project' | 'episode' | 'knowledge'
    content: str
    source: str          # 'conversation' | 'trajectory' | 'user_explicit' | 'inferred' | 'verified'
    confidence: float    # 0.0 to 1.0
    evidence_count: int  # how many interactions support this
    created_at: datetime
    updated_at: datetime
    expiry: datetime | None = None # None = permanent


@dataclass
class RetentionScore:
    value: float
    should_retain: bool
    reason: str = ""


@dataclass
class SourceAuthority:
    """Defines authority levels for different memory sources."""
    source: str
    authority: float  # 0.0 to 1.0
    description: str = ""


# Default source authority levels (higher = more trusted)
DEFAULT_SOURCE_AUTHORITIES = {
    "user_explicit": SourceAuthority("user_explicit", 1.0, "Directly stated by user"),
    "verified": SourceAuthority("verified", 0.95, "Confirmed through verification"),
    "trajectory": SourceAuthority("trajectory", 0.7, "From successful task execution"),
    "conversation": SourceAuthority("conversation", 0.5, "From conversation context"),
    "inferred": SourceAuthority("inferred", 0.3, "Derived/inferred by system"),
    "web": SourceAuthority("web", 0.2, "From web search (untrusted)"),
}


class MemoryRetentionEngine:
    """Evaluates whether memories should be retained based on confidence, evidence, and source authority."""

    def __init__(self):
        self.source_authorities = DEFAULT_SOURCE_AUTHORITIES.copy()

    def compute_retention(self, candidate: dict[str, Any]) -> RetentionScore:
        """Compute retention score for a memory candidate."""
        confidence = float(candidate.get("confidence", 0.0))
        evidence_count = int(candidate.get("evidence_count", 0))
        source = candidate.get("source", "inferred")
        expiry = candidate.get("expiry")
        created_at = candidate.get("created_at")

        # Check expiry
        if expiry:
            try:
                expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                if expiry_dt < datetime.now():
                    return RetentionScore(value=0.0, should_retain=False, reason="Expired")
            except Exception:
                pass

        # Source authority weighting
        source_auth = self.source_authorities.get(source, SourceAuthority(source, 0.3))
        effective_confidence = confidence * source_auth.authority + confidence * (1 - source_auth.authority) * 0.5

        # Low confidence threshold (adjusted by source authority)
        min_confidence = 0.3 * source_auth.authority + 0.1
        if effective_confidence < min_confidence:
            return RetentionScore(value=effective_confidence, should_retain=False, reason=f"Low confidence ({effective_confidence:.2f})")

        # Single evidence with low confidence
        if evidence_count < 2 and effective_confidence < 0.5:
            return RetentionScore(value=effective_confidence, should_retain=False, reason="Insufficient evidence")

        # Age-based decay
        age_penalty = 0.0
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_days = (datetime.now() - created_dt).days
                if age_days > 30:
                    age_penalty = min(0.2, age_days * 0.002)  # Max 20% penalty after ~100 days
            except Exception:
                pass

        final_score = max(0.0, effective_confidence - age_penalty + (evidence_count * 0.01))

        should_retain = final_score >= min_confidence
        return RetentionScore(value=min(0.95, final_score), should_retain=should_retain, reason="")

    def calculate_decay(self, confidence: float, source: str, age_days: int, evidence_count: int) -> float:
        """Calculate confidence decay over time."""
        source_auth = self.source_authorities.get(source, SourceAuthority(source, 0.3))
        base_authority = source_auth.authority

        # Higher authority sources decay slower
        daily_decay = 0.01 * (1.0 - base_authority * 0.5)  # 0.5% to 1% per day
        decay = daily_decay * age_days

        # Evidence reduces decay
        evidence_protection = min(0.005 * evidence_count, 0.03)  # Up to 3% protection

        return max(0.0, confidence - decay + evidence_protection)


class RetentionManager:
    """Manages memory lifecycle, retention, confidence scoring, and decay policies."""

    def __init__(self, db: MemoryDatabase):
        self.db = db
        self.engine = MemoryRetentionEngine()
        self._load_source_authorities()
        self._load_retention_policies()

    def _load_source_authorities(self) -> None:
        """Load source authorities from database or use defaults."""
        try:
            with self.db.connection() as conn:
                rows = conn.execute("SELECT source_name, authority_level, description FROM source_registry").fetchall()
                for row in rows:
                    self.engine.source_authorities[row["source_name"]] = SourceAuthority(
                        row["source_name"], row["authority_level"], row["description"]
                    )
        except Exception:
            pass  # Use defaults

    def _load_retention_policies(self) -> dict:
        """Load retention policies from database."""
        policies = {}
        try:
            with self.db.connection() as conn:
                rows = conn.execute("SELECT category, min_confidence, max_age_days, decay_rate, archive_threshold FROM retention_policies").fetchall()
                for row in rows:
                    policies[row["category"]] = dict(row)
        except Exception:
            pass
        return policies

    def should_retain(self, candidate: MemoryCandidate) -> bool:
        """Determines if a candidate memory is worth keeping."""
        score = self.engine.compute_retention({
            "confidence": candidate.confidence,
            "evidence_count": candidate.evidence_count,
            "source": candidate.source,
            "expiry": candidate.expiry.isoformat() if candidate.expiry else None,
            "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        })
        return score.should_retain

    def update_confidence(self, memory_id: str, category: str, new_evidence: bool, verification_passed: bool = True) -> float:
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
                f"SELECT confidence, evidence_count, source, created_at FROM {table} WHERE id = ?",
                (memory_id,)
            ).fetchone()

            if not row:
                return 0.0

            confidence = float(row["confidence"])
            evidence_count = int(row["evidence_count"])
            source = row["source"] if "source" in row.keys() else "inferred"
            created_at = row["created_at"] if "created_at" in row.keys() else None

            if new_evidence and verification_passed:
                evidence_count += 1
                # Bayesian update: increase confidence more for high-authority sources
                source_auth = self.engine.source_authorities.get(source, SourceAuthority(source, 0.3))
                confidence_boost = (0.8 - confidence) * 0.3 * source_auth.authority
                confidence = min(0.95, confidence + confidence_boost)
            elif not verification_passed:
                # Verification failed - reduce confidence
                confidence = max(0.0, confidence - 0.15)
            else:
                # Contradiction without verification failure
                confidence = max(0.0, confidence - 0.1)

            now = datetime.now().isoformat(timespec="seconds")
            update_sql = f"UPDATE {table} SET confidence = ?, evidence_count = ? WHERE id = ?"
            if table == "preferences":
                update_sql = f"UPDATE {table} SET confidence = ?, evidence_count = ?, updated_at = ? WHERE id = ?"
                conn.execute(update_sql, (confidence, evidence_count, now, memory_id))
            else:
                conn.execute(update_sql, (confidence, evidence_count, memory_id))

            return confidence

    def record_access(self, memory_type: str, memory_id: int, access_type: str = "read") -> None:
        """Record memory access for decay tracking."""
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO memory_access_log (memory_type, memory_id, access_type, accessed_at) VALUES (?, ?, ?, ?)",
                (memory_type, memory_id, access_type, datetime.now().isoformat())
            )

    def apply_decay(self) -> dict[str, int]:
        """Apply time-based decay to all memories. Returns count of decayed items per category."""
        decayed = {"facts": 0, "preferences": 0, "episodes": 0}
        policies = self._load_retention_policies()

        with self.db.connection() as conn:
            for category, table in [("fact", "facts"), ("preference", "preferences"), ("episode", "episodes")]:
                policy = policies.get(category, {})
                decay_rate = policy.get("decay_rate", 0.01)
                max_age_days = policy.get("max_age_days", 365)

                rows = conn.execute(
                    f"SELECT id, confidence, source, created_at, evidence_count FROM {table} WHERE confidence > 0.0"
                ).fetchall()

                for row in rows:
                    try:
                        created_dt = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                        age_days = (datetime.now() - created_dt).days

                        if age_days > max_age_days:
                            # Archive old memories instead of deleting
                            conn.execute(f"UPDATE {table} SET confidence = 0.0 WHERE id = ?", (row["id"],))
                            decayed[table] += 1
                            continue

                        new_confidence = self.engine.calculate_decay(
                            row["confidence"], row["source"], age_days, row["evidence_count"]
                        )

                        if new_confidence != row["confidence"]:
                            conn.execute(f"UPDATE {table} SET confidence = ? WHERE id = ?", (new_confidence, row["id"]))
                            if new_confidence < 0.1:
                                decayed[table] += 1
                    except Exception:
                        continue

        return decayed

    def expire_stale(self) -> int:
        """Soft delete expired memories by marking confidence=0."""
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

    def merge_duplicates(self, category: str = "facts", similarity_threshold: float = 0.9) -> int:
        """Merges duplicate memories using text similarity."""
        # Placeholder - would use embeddings or text similarity
        return 0

    def get_memory_stats(self) -> dict:
        """Get statistics about memory health."""
        stats = {}
        with self.db.connection() as conn:
            for table in ["facts", "preferences", "episodes"]:
                total = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()["c"]
                active = conn.execute(f"SELECT COUNT(*) as c FROM {table} WHERE confidence > 0.0").fetchone()["c"]
                avg_conf = conn.execute(f"SELECT AVG(confidence) as avg FROM {table} WHERE confidence > 0.0").fetchone()["avg"] or 0
                stats[table] = {"total": total, "active": active, "avg_confidence": round(avg_conf, 3)}
        return stats