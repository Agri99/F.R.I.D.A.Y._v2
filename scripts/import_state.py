#!/usr/bin/env python3
"""
scripts/import_state.py
Imports memory, identity, preferences, and knowledge from exported YAML into SQLite database. Runbook §82.
"""
import sqlite3
from pathlib import Path
import yaml

_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _ROOT / "data" / "friday.db"
_EXPORT_DIR = _ROOT / "data" / "export"


def import_table(cursor: sqlite3.Cursor, table_name: str, yaml_path: Path):
    if not yaml_path.exists():
        return
    with open(yaml_path, "r", encoding="utf-8") as f:
        rows = yaml.safe_load(f) or []
    if not rows:
        return

    count = 0
    for row in rows:
        cols = list(row.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})"
        try:
            cursor.execute(sql, list(row.values()))
            count += 1
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            pass
    print(f"  [+] Imported {count} rows into {table_name}")


def import_all():
    if not _EXPORT_DIR.exists():
        print(f"[-] Export directory {_EXPORT_DIR} does not exist.")
        return

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    cursor = conn.cursor()

    print(f"[*] Importing state from {_EXPORT_DIR} into {_DB_PATH}...")
    try:
        import_table(cursor, "identity", _EXPORT_DIR / "identity.yaml")
        import_table(cursor, "preferences", _EXPORT_DIR / "preferences.yaml")
        import_table(cursor, "projects", _EXPORT_DIR / "projects.yaml")
        import_table(cursor, "facts", _EXPORT_DIR / "facts.yaml")
        import_table(cursor, "episodes", _EXPORT_DIR / "episodes.yaml")
        conn.commit()
        print("[+] State import completed successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    import_all()
