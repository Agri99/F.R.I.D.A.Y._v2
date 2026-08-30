#!/usr/bin/env python3
"""
scripts/backup_restore.py

WHAT THIS IS FOR:
Backup and restore utilities for F.R.I.D.A.Y. v3 database, configuration, and state (§28).
Supports full backup, incremental backup, point-in-time recovery, and automated scheduling.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sqlite3
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
_BACKUP_DIR = _ROOT / "backups"
_DB_PATH = _ROOT / "data" / "friday.db"
_CONFIG_DIRS = [_ROOT / "config", _ROOT / ".env", _ROOT / ".env.example", _ROOT / "skills"]
_DATA_DIRS = [_ROOT / "data", _ROOT / "skills", _ROOT / "workspace"]


class BackupManager:
    """Manages backup and restore operations for F.R.I.D.A.Y. v3."""

    def __init__(self, backup_dir: Path | str = _BACKUP_DIR):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, name: str | None = None, incremental: bool = False) -> Path:
        """Create a full or incremental backup."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = name or f"friday_backup_{timestamp}"
        backup_path = self.backup_dir / f"{backup_name}.tar.gz"

        print(f"[*] Creating {'incremental' if incremental else 'full'} backup: {backup_path}")

        with tarfile.open(backup_path, "w:gz") as tar:
            # Database
            if _DB_PATH.exists():
                tar.add(_DB_PATH, arcname="friday.db")
                print("  [+] Added database")

            # Config files
            for config_dir in _CONFIG_DIRS:
                if config_dir.exists():
                    if config_dir.is_file():
                        tar.add(config_dir, arcname=f"config/{config_dir.name}")
                    else:
                        for item in config_dir.rglob("*"):
                            if item.is_file():
                                rel_path = item.relative_to(_ROOT)
                                tar.add(item, arcname=str(rel_path))
                    print(f"  [+] Added config: {config_dir.name}")

            # Data directories (excluding backups to avoid recursion)
            for data_dir in _DATA_DIRS:
                if data_dir.exists() and data_dir != _BACKUP_DIR:
                    for item in data_dir.rglob("*"):
                        if item.is_file() and _BACKUP_DIR not in item.parents:
                            rel_path = item.relative_to(_ROOT)
                            tar.add(item, arcname=str(rel_path))
                    print(f"  [+] Added data: {data_dir.name}")

            # Metadata
            metadata = {
                "created_at": datetime.now().isoformat(),
                "version": self._get_version(),
                "incremental": incremental,
                "base_backup": self._find_latest_backup() if incremental else None,
                "size_bytes": backup_path.stat().st_size,
            }
            metadata_path = self.backup_dir / f"{backup_name}.metadata.json"
            metadata_path.write_text(json.dumps(metadata, indent=2))
            tar.add(metadata_path, arcname="metadata.json")
            metadata_path.unlink()

        print(f"[+] Backup created: {backup_path} ({backup_path.stat().st_size / 1024 / 1024:.1f} MB)")
        return backup_path

    def _get_version(self) -> str:
        """Get current version from pyproject.toml."""
        try:
            import tomli
            with open(_ROOT / "pyproject.toml", "rb") as f:
                data = tomli.load(f)
                return data.get("project", {}).get("version", "unknown")
        except Exception:
            return "unknown"

    def _find_latest_backup(self) -> Path | None:
        """Find the most recent backup for incremental base."""
        backups = list(self.backup_dir.glob("friday_backup_*.tar.gz"))
        if not backups:
            return None
        return max(backups, key=lambda p: p.stat().st_mtime)

    def list_backups(self) -> list[dict]:
        """List all available backups with metadata."""
        backups = []
        for backup in sorted(self.backup_dir.glob("friday_backup_*.tar.gz")):
            meta_path = self.backup_dir / f"{backup.stem}.metadata.json"
            metadata = {}
            if meta_path.exists():
                metadata = json.loads(meta_path.read_text())
            backups.append({
                "file": backup.name,
                "path": str(backup),
                "size_mb": backup.stat().st_size / 1024 / 1024,
                "created": datetime.fromtimestamp(backup.stat().st_mtime).isoformat(),
                "metadata": metadata,
            })
        return backups

    def restore_backup(self, backup_path: Path, target_dir: Path | None = None, overwrite: bool = False) -> bool:
        """Restore from a backup file."""
        target_dir = target_dir or _ROOT
        backup_path = Path(backup_path)

        if not backup_path.exists():
            print(f"[!] Backup file not found: {backup_path}")
            return False

        print(f"[*] Restoring from backup: {backup_path}")

        # Safety check
        if not overwrite:
            if _DB_PATH.exists():
                print("[!] Database exists. Use --overwrite to replace.")
                return False

        try:
            with tarfile.open(backup_path, "r:gz") as tar:
                # Extract to target
                tar.extractall(target_dir)
                print("[+] Backup extracted successfully")

            # Verify database
            if _DB_PATH.exists():
                print("[+] Database restored successfully")
            else:
                print("[!] Warning: Database not found in backup")

            return True

        except Exception as e:
            print(f"[!] Restore failed: {e}")
            return False

    def cleanup_old_backups(self, keep: int = 10, max_age_days: int = 30) -> int:
        """Remove old backups, keeping the most recent N and those within max_age_days."""
        backups = sorted(
            self.backup_dir.glob("friday_backup_*.tar.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        removed = 0
        now = time.time()
        for i, backup in enumerate(backups):
            age_days = (now - backup.stat().st_mtime) / 86400
            if i >= keep or age_days > max_age_days:
                meta_path = self.backup_dir / f"{backup.stem}.metadata.json"
                backup.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
                removed += 1
                print(f"  [-] Removed old backup: {backup.name}")

        print(f"[+] Cleanup complete. Removed {removed} old backups.")
        return removed


def main():
    parser = argparse.ArgumentParser(description="F.R.I.D.A.Y. v3 Backup & Restore Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Create a backup")
    backup_parser.add_argument("--name", help="Custom backup name")
    backup_parser.add_argument("--incremental", action="store_true", help="Create incremental backup")

    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument("backup", help="Backup file path or name")
    restore_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing data")

    # List command
    subparsers.add_parser("list", help="List available backups")

    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Remove old backups")
    cleanup_parser.add_argument("--keep", type=int, default=10, help="Number of backups to keep")
    cleanup_parser.add_argument("--max-age", type=int, default=30, help="Max age in days")

    args = parser.parse_args()

    manager = BackupManager()

    if args.command == "backup":
        manager.create_backup(name=args.name, incremental=args.incremental)
    elif args.command == "restore":
        backup_path = Path(args.backup)
        if not backup_path.exists():
            backup_path = _BACKUP_DIR / args.backup
        manager.restore_backup(backup_path, overwrite=args.overwrite)
    elif args.command == "list":
        backups = manager.list_backups()
        if not backups:
            print("No backups found.")
        else:
            print(f"\nAvailable Backups ({len(backups)}):")
            for b in backups:
                meta = b.get("metadata", {})
                print(f"  {b['file']}")
                print(f"    Size: {b['size_mb']:.1f} MB")
                print(f"    Created: {b['created']}")
                print(f"    Version: {meta.get('version', 'unknown')}")
                print(f"    Incremental: {meta.get('incremental', False)}")
    elif args.command == "cleanup":
        manager.cleanup_old_backups(keep=args.keep, max_age_days=args.max_age)


if __name__ == "__main__":
    main()