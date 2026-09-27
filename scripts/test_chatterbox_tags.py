"""
scripts/test_chatterbox_tags.py

Chatterbox Turbo paralinguistic tag calibration harness.
Generates baseline vs tagged audio samples to empirically verify which
bracket tags produce distinguishable audible effects on the installed runtime.

Usage:
    python scripts/test_chatterbox_tags.py [--device cuda|cpu] [--output-dir PATH]
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

# Ensure repository root is on PYTHONPATH
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from friday.interaction.tts import (
    CHATTERBOX_EVENT_TAGS,
    CHATTERBOX_EXPERIMENTAL_EMOTION_TAGS,
    SpeechSynthesizer,
)

logger = logging.getLogger(__name__)

BASELINE_TEXT = "I understand. We can work through this together."

TEST_EVENT_TAGS = [
    "sigh",
    "gasp",
    "chuckle",
    "laugh",
]

TEST_EXPERIMENTAL_TAGS = [
    "happy",
    "sarcastic",
    "whispering",
    "angry",
    "surprised",
    "dramatic",
    "fear",
    "crying",
]


def run_tag_calibration(
    output_dir: Path,
    device: str = "cpu",
    test_experimental: bool = True,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Initializing SpeechSynthesizer (device={device})...")
    synthesizer = SpeechSynthesizer(engine="chatterbox_turbo", device=device)

    # 1. Baseline
    print(f"\n--- Synthesizing baseline: '{BASELINE_TEXT}' ---")
    baseline_wav = output_dir / "00_baseline.wav"
    try:
        res = synthesizer.speak(BASELINE_TEXT, save_path=str(baseline_wav))
        if res.success:
            print(f"  [OK] Saved: {baseline_wav}")
        else:
            print(f"  [ERROR] Baseline failed: {res.error}")
            return
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
        print(f"  [EXCEPTION] Baseline generation failed: {exc}")
        return

    # 2. Event Tags
    print("\n--- Testing Verified Event Tags ---")
    for tag in TEST_EVENT_TAGS:
        if tag not in CHATTERBOX_EVENT_TAGS:
            continue
        tagged_text = f"[{tag}] {BASELINE_TEXT}"
        out_file = output_dir / f"event_{tag.replace(' ', '_')}.wav"
        print(f"Synthesizing [{tag}]...")
        try:
            res = synthesizer.speak(tagged_text, save_path=str(out_file))
            if res.success:
                print(f"  [OK] Saved: {out_file}")
            else:
                print(f"  [ERROR] Tag [{tag}] failed: {res.error}")
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
            print(f"  [EXCEPTION] Tag [{tag}] failed: {exc}")

    # 3. Experimental Emotion Tags
    if test_experimental:
        print("\n--- Testing Experimental Emotion Tags ---")
        for tag in TEST_EXPERIMENTAL_TAGS:
            if tag not in CHATTERBOX_EXPERIMENTAL_EMOTION_TAGS:
                continue
            tagged_text = f"[{tag}] {BASELINE_TEXT}"
            out_file = output_dir / f"experimental_{tag}.wav"
            print(f"Synthesizing [{tag}]...")
            try:
                res = synthesizer.speak(tagged_text, save_path=str(out_file))
                if res.success:
                    print(f"  [OK] Saved: {out_file}")
                else:
                    print(f"  [ERROR] Experimental tag [{tag}] failed: {res.error}")
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
                print(f"  [EXCEPTION] Experimental tag [{tag}] failed: {exc}")

    print(f"\nCalibration complete. Compare WAV files in: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate Chatterbox Turbo vocal tags")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "data" / "eval" / "chatterbox_tag_test",
        help="Directory to save generated WAV samples",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        choices=["cpu", "cuda"],
        help="Inference device (cpu or cuda)",
    )
    parser.add_argument(
        "--skip-experimental",
        action="store_true",
        help="Skip testing experimental emotion tags",
    )

    args = parser.parse_args()
    run_tag_calibration(
        output_dir=args.output_dir,
        device=args.device,
        test_experimental=not args.skip_experimental,
    )


if __name__ == "__main__":
    main()
