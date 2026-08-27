"""
src/friday/interaction/wakeword.py

WHAT THIS IS FOR:
Wake word detection using openWakeWord (ONNX runtime) with audio frame streaming.
"""

from __future__ import annotations

import logging
import typing
import numpy as np
import sounddevice as sd

if typing.TYPE_CHECKING:
    from typing import Any

# Filter out the benign openwakeword tflite warning (since we intentionally use ONNX)
class _TFLiteWarningFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "tflite runtime" not in record.getMessage()

logging.getLogger().addFilter(_TFLiteWarningFilter())

SAMPLE_RATE = 16000
FRAME_SIZE = 1280


class WakeWordListener:
    """Listens for the 'friday' wake word using openWakeWord."""

    def __init__(self, model_path: str = "models/friday.onnx", threshold: float = 0.5):
        from openwakeword.model import Model
        self.model = Model(wakeword_models=[model_path])
        self.threshold = threshold
        self.wakeword_name = "friday"

    def check_frame(self, stream: Any, debug: bool = False) -> bool:
        """Check a single audio frame for the wake word."""
        audio_frame, overflowed = stream.read(FRAME_SIZE)
        if overflowed:
            return False

        audio_frame = audio_frame.flatten()
        prediction = self.model.predict(audio_frame)
        score = prediction.get(self.wakeword_name, 0.0)

        if debug:
            print(f"[debug] wakeword score: {score:.3f} (threshold: {self.threshold})")

        return score > self.threshold

    def listen_for_wakeword(self) -> None:
        """Block until the wake word is detected."""
        print("Listening for wake word...")
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME_SIZE) as stream:
            warmup_frames = 5
            frame_count = 0

            while True:
                frame_count += 1
                if frame_count <= warmup_frames:
                    stream.read(FRAME_SIZE)
                    continue

                if self.check_frame(stream):
                    print("Wake word detected!")
                    return
