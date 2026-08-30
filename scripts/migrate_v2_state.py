#!/usr/bin/env python3
"""
scripts/migrate_v2_state.py

WHAT THIS IS FOR:
Applies database migrations from v2 to v3 schema, adding confidence and retention columns (§28).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _ROOT / "data" / "friday.db"


def migrate() -> None:
    if not _DB_PATH.exists():
        print(f"[*] Database {_DB_PATH} does not exist yet. No migration needed.")
        return

    print(f"[*] Checking database schema for {_DB_PATH}...")
    conn = sqlite3.connect(str(_DB_PATH))
    cursor = conn.cursor()

    # Migration for facts table
    try:
        cursor.execute("SELECT confidence FROM facts LIMIT 1")
    except sqlite3.OperationalError:
        print("    [+] Adding 'confidence' column to facts table...")
        cursor.execute("ALTER TABLE facts ADD COLUMN confidence REAL DEFAULT 1.0")

    try:
        cursor.execute("SELECT expires_at FROM facts LIMIT 1")
    except sqlite3.OperationalError:
        print("    [+] Adding 'expires_at' column to facts table...")
        cursor.execute("ALTER TABLE facts ADD COLUMN expires_at TEXT DEFAULT NULL")

    try:
        cursor.execute("SELECT source FROM facts LIMIT 1")
    except sqlite3.OperationalError:
        print("    [+] Adding 'source' column to facts table...")
        cursor.execute("ALTER TABLE facts ADD COLUMN source TEXT DEFAULT 'user'")

    # Migration for episodes table
    try:
        cursor.execute("SELECT retention_score FROM episodes LIMIT 1")
    except sqlite3.OperationalError:
        print("    [+] Adding 'retention_score' column to episodes table...")
        cursor.execute("ALTER TABLE episodes ADD COLUMN retention_score REAL DEFAULT 1.0")

    conn.commit()
    conn.close()
    print("[+] Database migration completed successfully.")


def main() -> None:
    migrate()


if __name__ == "__main__":
    main()
