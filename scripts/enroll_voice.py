"""
scripts/enroll_voice.py

Speaker Enrollment Tool for F.R.I.D.A.Y.
Records 3 clean voice samples of the owner, extracts neural speaker embeddings
using SpeechBrain ECAPA-TDNN, and establishes your biometric voiceprint.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import numpy as np
import sounddevice as sd
import soundfile as sf

ENROLLMENT_DIR = _ROOT / "data" / "voice_enrollment"
SAMPLE_RATE = 16000
DURATION_SECONDS = 4.0

SAMPLE_PROMPTS = [
    "Hello Friday, this is my primary voice authorizing access.",
    "All systems online, standing by for my instructions, Friday.",
    "Verify my voice biometrics and initialize Friday's neural core.",
]


def record_sample(prompt: str, index: int) -> Path:
    print(f"\n[{index + 1}/3] Please prepare to speak clearly into your microphone / headset:")
    print(f'     Prompt to read: "{prompt}"')
    input("     Press [Enter] when ready to start recording...")

    print("     >>> RECORDING NOW... (Speak naturally)")
    frames_needed = int(SAMPLE_RATE * DURATION_SECONDS)
    audio = sd.rec(frames_needed, samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    print("     >>> RECORDING COMPLETE.")

    # Calculate RMS to ensure mic is actually capturing audio
    audio_flat = audio.flatten()
    rms = float(np.sqrt(np.mean(np.square(audio_flat))))
    if rms < 0.005:
        print("     [!] Warning: Audio level is very low. Please check your microphone input volume.")

    ENROLLMENT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = ENROLLMENT_DIR / f"voice_ref_{index}.wav"
    sf.write(str(out_file), audio_flat, SAMPLE_RATE, subtype="PCM_16")
    print(f"     Saved sample to: {out_file.relative_to(_ROOT)}")
    return out_file


def main() -> None:
    print("=======================================================")
    print("         F.R.I.D.A.Y. Speaker Voice Enrollment         ")
    print("=======================================================")
    print("This utility records 3 voice clips to identify you as the")
    print("authorized Owner of F.R.I.D.A.Y.")
    print("Make sure you are wearing your headset or in your normal")
    print("speaking posture with your primary microphone.\n")

    files = []
    for i, prompt in enumerate(SAMPLE_PROMPTS):
        out_file = record_sample(prompt, i)
        files.append(out_file)
        time.sleep(0.5)

    print("\n[*] Processing voice samples through SpeechBrain ECAPA-TDNN...")
    try:
        from friday.security.voice_auth import VoiceAuthProvider

        auth_provider = VoiceAuthProvider(enrollment_dir=ENROLLMENT_DIR)
        auth_provider._initialize()

        if auth_provider._reference_embedding is None:
            print("[-] Error: Reference embedding could not be generated.")
            return

        print("[+] Voiceprint successfully generated and saved!")
        print(f"    Reference embedding shape: {auth_provider._reference_embedding.shape}")

        # Self-verification check across the 3 files
        print("\n[*] Running cross-consistency verification:")
        for f in files:
            res = auth_provider.verify(f)
            status = "MATCH" if res.verified else "LOW"
            print(f"    - {f.name}: {status} (Cosine Score: {res.score:.3f} | Threshold: {res.threshold:.2f})")

        print("\n[+] Speaker enrollment completed successfully!")
        print("    F.R.I.D.A.Y. now recognizes your voice.")
    except Exception as exc:  # noqa: BLE001
        print(f"[!] Warning during neural processing: {exc}")
        print("    Audio files are saved and ready for offline embedding extraction.")


if __name__ == "__main__":
    main()
