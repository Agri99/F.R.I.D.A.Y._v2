#!/usr/bin/env python3
"""
scripts/restore_state.py
Restores FRIDAY state, database, configuration, and skills from a backup archive. Runbook §82.
"""
import sys
import argparse
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.backup_restore import BackupManager

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Restore FRIDAY state from backup archive")
    parser.add_argument("backup_file", nargs="?", help="Path to backup tar.gz file")
    args = parser.parse_args()

    mgr = BackupManager()
    if args.backup_file:
        path = Path(args.backup_file)
    else:
        # Find latest
        backups = sorted(mgr.backup_dir.glob("friday_backup_*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not backups:
            print("[-] No backups found in backups/ directory.")
            sys.exit(1)
        path = backups[0]

    print(f"[*] Restoring from: {path}")
    mgr.restore_backup(path)
    print("[+] State restoration completed.")
