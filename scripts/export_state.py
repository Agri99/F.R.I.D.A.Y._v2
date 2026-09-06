#!/usr/bin/env python3
"""
scripts/export_state.py
Exports memory, identity, preferences, and knowledge to human-readable YAML. Runbook §82.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.export_memory import export_all

if __name__ == "__main__":
    export_all()
