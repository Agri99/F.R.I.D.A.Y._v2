"""
tests/evaluation/test_memory_export_rebuild.py

WHAT THIS IS FOR:
E2E evaluation test for memory export to YAML and rebuild from YAML.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml


class TestMemoryExportRebuild:
    @pytest.fixture
    def db_path(self, tmp_path):
        return tmp_path / "friday.db"

    @pytest.fixture
    def export_dir(self, tmp_path):
        export_dir = tmp_path / "export"
        export_dir.mkdir()
        return export_dir

    @pytest.fixture(autouse=True)
    def setup_database(self, db_path, export_dir):
        """Create a minimal SQLite DB with the required schema."""
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
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
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY,
                content TEXT,
                category TEXT,
                confidence REAL,
                source TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                role TEXT,
                content TEXT,
                timestamp TEXT
            );
        """)
        cursor.execute("INSERT INTO identity (id, key, value, created_at) VALUES ('1', 'name', 'FRIDAY', '2026-08-28')")
        cursor.execute("INSERT INTO preferences (key, value) VALUES ('theme', 'dark')")
        cursor.execute("INSERT INTO facts (content, category, confidence, source) VALUES ('Python is great', 'knowledge', 0.95, 'user')")
        cursor.execute("INSERT INTO messages (role, content, timestamp) VALUES ('user', 'Hello', '2026-08-28')")
        conn.commit()
        conn.close()

        # Monkey-patch the DB path
        import scripts.export_memory as export_mod
        self._orig_db_path = export_mod._DB_PATH
        export_mod._DB_PATH = db_path
        self._orig_export_dir = export_mod._EXPORT_DIR
        export_mod._EXPORT_DIR = export_dir

        yield

        # Restore
        export_mod._DB_PATH = self._orig_db_path
        export_mod._EXPORT_DIR = self._orig_export_dir

    def test_export_produces_yaml_files(self, export_dir):
        from scripts.export_memory import export_all
        export_all()
        assert (export_dir / "identity.yaml").exists()
        assert (export_dir / "preferences.yaml").exists()
        assert (export_dir / "facts.yaml").exists()
        assert (export_dir / "messages.yaml").exists()

    def test_exported_yaml_is_valid(self, export_dir):
        from scripts.export_memory import export_all
        export_all()
        data = yaml.safe_load((export_dir / "identity.yaml").read_text())
        assert data["table"] == "identity"
        assert data["count"] == 1
        assert data["records"][0]["value"] == "FRIDAY"

        data = yaml.safe_load((export_dir / "facts.yaml").read_text())
        assert data["table"] == "facts"
        assert data["count"] == 1
        assert data["records"][0]["content"] == "Python is great"

    def test_round_trip_preserves_data(self, db_path, export_dir):
        """Exported data should be importable back into SQLite."""
        from scripts.export_memory import export_all, import_from_yaml
        export_all()

        # Create a fresh DB and import
        new_db = db_path.parent / "friday_rebuilt.db"
        conn = sqlite3.connect(str(new_db))
        cursor = conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS identity (id TEXT, key TEXT, value TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS preferences (id INTEGER, key TEXT, value TEXT);
            CREATE TABLE facts (id INTEGER, content TEXT, category TEXT, confidence REAL, source TEXT);
            CREATE TABLE messages (id INTEGER, role TEXT, content TEXT, timestamp TEXT);
        """)
        conn.commit()
        conn.close()

        import scripts.export_memory as export_mod
        export_mod._DB_PATH = new_db
        try:
            import_from_yaml(export_dir)
        finally:
            export_mod._DB_PATH = db_path

        # Verify imported data matches
        conn = sqlite3.connect(str(new_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM identity")
        identity_records = cursor.fetchall()
        assert len(identity_records) == 1
        assert identity_records[0]["value"] == "FRIDAY"

        cursor.execute("SELECT * FROM preferences")
        prefs = cursor.fetchall()
        assert len(prefs) == 1
        assert prefs[0]["key"] == "theme"
        conn.close()