"""
scripts/download_models.py

Download required model weights on first run.
Replaces storing large binaries in the Git repository.

Usage:
    python scripts/download_models.py [--all | --tts | --wakeword | --voiceauth]
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

MODELS = {
    "tts": {
        "description": "Chatterbox Turbo neural TTS (ResembleAI/chatterbox-turbo)",
        "files": {},
        "dest": MODELS_DIR,
        "note": "Chatterbox Turbo weights are automatically downloaded and cached by Hugging Face on first use.",
    },
    "wakeword": {
        "description": "OpenWakeWord custom FRIDAY model",
        "files": {},  # Custom trained — user must supply or train
        "dest": MODELS_DIR,
        "note": "Custom wake word model (friday.onnx) must be trained locally or supplied manually.",
    },
    "voiceauth": {
        "description": "SpeechBrain ECAPA-TDNN speaker verification",
        "files": {},  # Downloaded automatically by speechbrain on first use
        "dest": MODELS_DIR / "spkrec-ecapa-voxceleb",
        "note": "SpeechBrain downloads this automatically on first use via HuggingFace Hub.",
    },
}


def download_file(url: str, dest: Path) -> None:
    """Download a file with progress reporting."""
    if dest.exists():
        print(f"  ✓ Already exists: {dest.name}")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ↓ Downloading: {dest.name} ...")

    try:
        urllib.request.urlretrieve(url, str(dest))
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  ✓ Downloaded: {dest.name} ({size_mb:.1f} MB)")
    except Exception as e:
        print(f"  ✗ Failed: {dest.name} — {e}")
        if dest.exists():
            dest.unlink()


def download_group(group_name: str) -> None:
    """Download all files in a model group."""
    group = MODELS[group_name]
    print(f"\n── {group['description']} ──")

    if not group["files"]:
        note = group.get("note", "No automated download available.")
        print(f"  ℹ {note}")
        return

    for filename, url in group["files"].items():
        dest = group["dest"] / filename
        download_file(url, dest)


def main():
    parser = argparse.ArgumentParser(description="Download FRIDAY model weights")
    parser.add_argument("--all", action="store_true", help="Download all model groups")
    parser.add_argument("--tts", action="store_true", help="Pre-cache Chatterbox Turbo TTS weights")
    parser.add_argument("--wakeword", action="store_true", help="Info about wake word model")
    parser.add_argument("--voiceauth", action="store_true", help="Info about voice auth model")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if args.tts:
        print("\n── Pre-caching Chatterbox Turbo model weights ──")
        try:
            import torch
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"  ↓ Loading/caching ChatterboxTurboTTS on {dev.upper()}...")
            ChatterboxTurboTTS.from_pretrained(device=dev)
            print("  ✓ Chatterbox Turbo cached successfully.")
        except Exception as e:
            print(f"  ✗ Failed to pre-cache Chatterbox Turbo: {e}")

    if args.all or not any([args.tts, args.wakeword, args.voiceauth]):
        for name in MODELS:
            download_group(name)
    else:
        if args.wakeword:
            download_group("wakeword")
        if args.voiceauth:
            download_group("voiceauth")

    print("\n✓ Model download complete.")


if __name__ == "__main__":
    main()

