#!/usr/bin/env python3
"""
scripts/export_memory.py

WHAT THIS IS FOR:
Exports all durable memory classes (identity, preferences, projects, knowledge, episodes)
to human-readable YAML files for backup, review, and migration (§12.1).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _ROOT / "data" / "friday.db"
_EXPORT_DIR = _ROOT / "data" / "export"


def export_all() -> None:
    _EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    if not _DB_PATH.exists():
        print(f"[!] Database file {_DB_PATH} not found.")
        return

    print(f"[*] Exporting memory from {_DB_PATH} to {_EXPORT_DIR}...")
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Export identity
        export_table(cursor, "identity", _EXPORT_DIR / "identity.yaml")

        # Export preferences
        export_table(cursor, "preferences", _EXPORT_DIR / "preferences.yaml")

        # Export projects
        export_table(cursor, "projects", _EXPORT_DIR / "projects.yaml")

        # Export knowledge (semantic facts) - export as facts.yaml to match table name
        export_table(cursor, "facts", _EXPORT_DIR / "facts.yaml")

        # Export episodes (episodic memory)
        export_table(cursor, "episodes", _EXPORT_DIR / "episodes.yaml")

        # Export conversation messages (recent)
        export_messages(cursor, _EXPORT_DIR / "messages.yaml")

        print("[+] Memory export completed successfully.")
    except Exception as exc:
        print(f"[!] Error exporting memory: {exc}")
    finally:
        conn.close()


def export_table(cursor: sqlite3.Cursor, table: str, out_path: Path) -> None:
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if not cursor.fetchone():
        print(f"    [-] Table '{table}' does not exist, skipping.")
        return

    cursor.execute(f"SELECT * FROM {table}")
    rows = [dict(row) for row in cursor.fetchall()]

    data = {
        "table": table,
        "exported_at": datetime.now().isoformat(),
        "count": len(rows),
        "records": rows,
    }

    out_path.write_text(yaml.dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"    [+] Exported {len(rows)} records to {out_path.name}")


def export_messages(cursor: sqlite3.Cursor, out_path: Path) -> None:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
    if not cursor.fetchone():
        print("    [-] Messages table does not exist, skipping.")
        return

    cursor.execute("SELECT * FROM messages ORDER BY timestamp DESC LIMIT 100")
    rows = [dict(row) for row in cursor.fetchall()]

    data = {
        "table": "messages",
        "exported_at": datetime.now().isoformat(),
        "count": len(rows),
        "records": rows,
    }

    out_path.write_text(yaml.dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"    [+] Exported {len(rows)} messages to {out_path.name}")


def import_from_yaml(export_dir: Path | str = None) -> None:
    """Import YAML exports back into SQLite (used by rebuild_memory_index.py)."""
    export_dir = Path(export_dir) if export_dir else _EXPORT_DIR

    if not export_dir.exists():
        print(f"[!] Export directory {export_dir} not found.")
        return

    if not _DB_PATH.exists():
        print(f"[!] Database file {_DB_PATH} not found.")
        return

    print(f"[*] Importing memory from {export_dir} to {_DB_PATH}...")
    conn = sqlite3.connect(str(_DB_PATH))
    cursor = conn.cursor()

    # Ensure tables exist
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS identity (
            id TEXT PRIMARY KEY,
            key TEXT,
            value TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS preferences (
            id INTEGER PRIMARY KEY,
            key TEXT,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY,
            name TEXT,
            path TEXT,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY,
            content TEXT,
            category TEXT,
            confidence REAL,
            source TEXT
        );
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY,
            content TEXT,
            category TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            role TEXT,
            content TEXT,
            timestamp TEXT
        );
    """)

    try:
        for yaml_file in export_dir.glob("*.yaml"):
            table_name = yaml_file.stem
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            records = data.get("records", [])

            if not records:
                continue

            # Build insert statement
            columns = list(records[0].keys())
            placeholders = ", ".join(["?" for _ in columns])
            col_str = ", ".join(columns)

            for record in records:
                values = [record.get(c) for c in columns]
                cursor.execute(
                    f"INSERT OR REPLACE INTO {table_name} ({col_str}) VALUES ({placeholders})",
                    values,
                )

            print(f"    [+] Imported {len(records)} records into {table_name}")

        conn.commit()
        print("[+] Memory import completed.")
    except Exception as exc:
        print(f"[!] Error importing memory: {exc}")
    finally:
        conn.close()


def main() -> None:
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "import":
        import_from_yaml()
    else:
        export_all()


if __name__ == "__main__":
    main()