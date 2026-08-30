"""
Enhanced SQLite database for all memory types with confidence, source tracking, and retention.
"""
from __future__ import annotations

import sqlite3
import contextlib
from pathlib import Path
from typing import Iterator

class MemoryDatabase:
    """Low-level SQLite connection management with memory lifecycle support."""

    def __init__(self, db_path: str | Path = "data/friday.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            # Conversations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)")

            # Episodes
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    steps TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    duration REAL,
                    confidence REAL DEFAULT 0.5,
                    evidence_count INTEGER DEFAULT 1,
                    expiry TEXT,
                    source TEXT DEFAULT 'trajectory',
                    created_at TEXT NOT NULL
                )
            """)
            # FTS for episodes
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                    goal, steps, outcome, content='episodes', content_rowid='id'
                )
            """)

            # Semantic Facts
            conn.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_count INTEGER DEFAULT 1,
                    expiry TEXT,
                    source TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # FTS for facts
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                    subject, predicate, value, content='facts', content_rowid='id'
                )
            """)

            # Preferences
            conn.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_count INTEGER DEFAULT 1,
                    expiry TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Source of truth registry - tracks authoritative sources
            conn.execute("""
                CREATE TABLE IF NOT EXISTS source_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL UNIQUE,
                    source_type TEXT NOT NULL,  -- 'user_explicit', 'trajectory', 'inferred', 'verified'
                    authority_level REAL DEFAULT 0.5,  -- 0.0 to 1.0
                    created_at TEXT NOT NULL
                )
            """)

            # Retention policy configuration
            conn.execute("""
                CREATE TABLE IF NOT EXISTS retention_policies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL UNIQUE,  -- 'fact', 'preference', 'episode'
                    min_confidence REAL DEFAULT 0.3,
                    max_age_days INTEGER DEFAULT 365,
                    decay_rate REAL DEFAULT 0.01,  -- per day
                    archive_threshold REAL DEFAULT 0.1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Insert default retention policies
            conn.execute("""
                INSERT OR IGNORE INTO retention_policies (category, min_confidence, max_age_days, decay_rate, archive_threshold, created_at, updated_at)
                VALUES
                    ('fact', 0.3, 365, 0.01, 0.1, datetime('now'), datetime('now')),
                    ('preference', 0.4, 730, 0.005, 0.15, datetime('now'), datetime('now')),
                    ('episode', 0.2, 180, 0.02, 0.05, datetime('now'), datetime('now'))
            """)

            # Memory access log for decay calculation
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_access_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_type TEXT NOT NULL,  -- 'fact', 'preference', 'episode'
                    memory_id INTEGER NOT NULL,
                    access_type TEXT NOT NULL,  -- 'read', 'write', 'verification'
                    accessed_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_access_log_lookup ON memory_access_log(memory_type, memory_id)")

            # Run Migrations for existing tables
            self._migrate_table(conn, "episodes", [
                ("confidence", "REAL DEFAULT 0.5"),
                ("evidence_count", "INTEGER DEFAULT 1"),
                ("expiry", "TEXT"),
                ("source", "TEXT DEFAULT 'trajectory'")
            ])
            self._migrate_table(conn, "facts", [
                ("evidence_count", "INTEGER DEFAULT 1"),
                ("expiry", "TEXT"),
                ("updated_at", "TEXT")
            ])
            self._migrate_table(conn, "preferences", [
                ("evidence_count", "INTEGER DEFAULT 1"),
                ("expiry", "TEXT")
            ])

    def _migrate_table(self, conn: sqlite3.Connection, table: str, columns: list[tuple[str, str]]) -> None:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        existing_cols = {row["name"] for row in cursor.fetchall()}
        for col_name, col_type in columns:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")

    def rebuild_index(self) -> None:
        """Rebuild FTS5 indexes."""
        with self.connection() as conn:
            conn.execute("INSERT INTO episodes_fts(episodes_fts) VALUES('rebuild')")
            conn.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")

    @contextlib.contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
