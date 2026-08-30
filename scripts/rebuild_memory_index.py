#!/usr/bin/env python3
"""
scripts/rebuild_memory_index.py

WHAT THIS IS FOR:
Rebuilds and re-indexes SQLite FTS5 search tables from stored raw memory records (§28).
Can also import from YAML exports if the database is missing or corrupted.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _ROOT / "data" / "friday.db"
_EXPORT_DIR = _ROOT / "data" / "export"


def rebuild_fts5_indexes() -> None:
    if not _DB_PATH.exists():
        print(f"[!] Database file {_DB_PATH} not found.")
        # Try to import from YAML exports if available
        if _EXPORT_DIR.exists():
            print(f"[*] Attempting to import from YAML exports in {_EXPORT_DIR}...")
            import_from_yaml()
            if not _DB_PATH.exists():
                print("[!] Import did not create database. Run setup.py first.")
            return
        else:
            print("[!] No YAML exports found. Run setup.py first.")
        return

    print(f"[*] Rebuilding FTS5 full-text search indexes in {_DB_PATH}...")
    conn = sqlite3.connect(str(_DB_PATH))
    cursor = conn.cursor()

    try:
        # Check if facts_fts exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='facts_fts'")
        if cursor.fetchone():
            print("    [+] Rebuilding facts_fts index...")
            cursor.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")

        # Check if messages_fts exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'")
        if cursor.fetchone():
            print("    [+] Rebuilding messages_fts index...")
            cursor.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")

        conn.commit()
        print("[+] All memory FTS5 indexes successfully rebuilt.")
    except Exception as exc:
        print(f"[!] Error rebuilding FTS5 index: {exc}")
    finally:
        conn.close()


def import_from_yaml(export_dir: Path = None) -> None:
    """Import YAML exports back into SQLite."""
    export_dir = export_dir or _EXPORT_DIR

    if not export_dir.exists():
        print(f"[!] Export directory {export_dir} not found.")
        return

    if not _DB_PATH.exists():
        print(f"[!] Database file {_DB_PATH} not found.")
        return

    print(f"[*] Importing memory from {export_dir} to {_DB_PATH}...")
    conn = sqlite3.connect(str(_DB_PATH))
    cursor = conn.cursor()

    try:
        import yaml
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
    if len(sys.argv) > 1 and sys.argv[1] == "import":
        import_from_yaml()
    else:
        rebuild_fts5_indexes()


if __name__ == "__main__":
    main()
