#!/usr/bin/env python3
"""
scripts/hardware_probe.py

Standalone hardware detection script.
"""
from __future__ import annotations
import json
import dataclasses

def main():
    try:
        from friday.models.hardware import detect_hardware
        hw = detect_hardware()
        print(json.dumps(dataclasses.asdict(hw), indent=2))
    except ImportError:
        print("Run from project root or ensure package is installed.")

if __name__ == "__main__":
    main()
