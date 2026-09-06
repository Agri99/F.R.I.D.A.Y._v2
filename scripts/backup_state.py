#!/usr/bin/env python3
"""
scripts/backup_state.py
Creates an archive of FRIDAY state, database, configuration, and skills. Runbook §82.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.backup_restore import BackupManager

if __name__ == "__main__":
    mgr = BackupManager()
    archive = mgr.create_backup()
    print(f"[+] State successfully backed up to: {archive}")
