"""
Enhanced SQLite database for all memory types.
"""
from __future__ import annotations

import sqlite3
import contextlib
from pathlib import Path
from typing import Iterator

class MemoryDatabase:
    """Low-level SQLite connection management."""
    
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
                    source TEXT,
                    created_at TEXT NOT NULL
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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Run Migrations
            self._migrate_table(conn, "episodes", [
                ("confidence", "REAL DEFAULT 0.5"),
                ("evidence_count", "INTEGER DEFAULT 1"),
                ("expiry", "TEXT")
            ])
            self._migrate_table(conn, "facts", [
                ("evidence_count", "INTEGER DEFAULT 1"),
                ("expiry", "TEXT")
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
