"""
src/friday/interaction/stt.py

WHAT THIS IS FOR:
Speech-to-text transcription via faster-whisper with domain vocabulary prompting,
pre-roll audio buffer to prevent leading consonant clipping, and Silero VAD filtering (blueprint §23).
"""

from __future__ import annotations

import os
from collections import deque
from pathlib import Path
import numpy as np
import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 16000
CHUNK_DURATION = 0.1  # 100ms
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)
SILENCE_THRESHOLD = 400  # RMS threshold for speech activity
SILENCE_DURATION = 1.2   # Silence needed to end recording (seconds)
MAX_DURATION = 15
PREROLL_CHUNKS = 4       # Keep 400ms before speech detection to prevent clipping initial syllables

# Vocabulary biasing prompt for faster-whisper
WHISPER_INITIAL_PROMPT = (
    "FRIDAY, an AI personal computer assistant on Windows. "
    "Voice commands: Open Notepad, Calculator, VS Code, Terminal, Explorer, "
    "check my inbox, send email, list calendar events, what time is it, "
    "mute audio, volume up, lock computer, hide yourself, goodbye Friday, shut down."
)


def record_until_silence(path: str = "data/audio.wav") -> str:
    """Record audio from microphone until silence is detected with pre-roll buffer."""
    dest_path = Path(path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    print("Recording... (speak now)")
    preroll = deque(maxlen=PREROLL_CHUNKS)
    recorded_frames = []
    silence_chunks = 0
    silence_chunks_needed = int(SILENCE_DURATION / CHUNK_DURATION)
    max_chunks = int(MAX_DURATION / CHUNK_DURATION)
    speech_started = False

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        for _ in range(max_chunks):
            chunk, _ = stream.read(CHUNK_SIZE)
            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))

            if not speech_started:
                preroll.append(chunk)
                if rms >= SILENCE_THRESHOLD:
                    speech_started = True
                    # Flush pre-roll buffer into recorded frames
                    recorded_frames.extend(list(preroll))
                    silence_chunks = 0
            else:
                recorded_frames.append(chunk)
                if rms >= SILENCE_THRESHOLD:
                    silence_chunks = 0
                else:
                    silence_chunks += 1
                    if silence_chunks >= silence_chunks_needed:
                        break

    if not recorded_frames and preroll:
        recorded_frames = list(preroll)

    audio = np.concatenate(recorded_frames) if recorded_frames else np.zeros((CHUNK_SIZE,), dtype=np.int16)
    sf.write(str(dest_path), audio, SAMPLE_RATE)
    print("Done recording.")
    return str(dest_path)


def listen_for_followup(timeout_seconds: float = 5.0, path: str = "data/audio.wav") -> str | None:
    """Listen for speech starting within a timeout window with pre-roll buffering."""
    dest_path = Path(path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Listening for a follow-up ({timeout_seconds:.0f}s)...")
    preroll = deque(maxlen=PREROLL_CHUNKS)
    recorded_frames = []
    silence_chunks = 0
    silence_chunks_needed = int(SILENCE_DURATION / CHUNK_DURATION)
    max_chunks = int(MAX_DURATION / CHUNK_DURATION)
    timeout_chunks = int(timeout_seconds / CHUNK_DURATION)
    speech_started = False
    chunks_waited = 0

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        for _ in range(max_chunks):
            chunk, _ = stream.read(CHUNK_SIZE)
            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))

            if not speech_started:
                preroll.append(chunk)
                chunks_waited += 1
                if chunks_waited > timeout_chunks:
                    return None
                if rms >= SILENCE_THRESHOLD:
                    speech_started = True
                    recorded_frames.extend(list(preroll))
                    silence_chunks = 0
            else:
                recorded_frames.append(chunk)
                if rms >= SILENCE_THRESHOLD:
                    silence_chunks = 0
                else:
                    silence_chunks += 1
                    if silence_chunks >= silence_chunks_needed:
                        break

    if not speech_started:
        return None

    audio = np.concatenate(recorded_frames)
    sf.write(str(dest_path), audio, SAMPLE_RATE)
    print("Done recording.")
    return str(dest_path)


class SpeechRecognizer:
    """Handles speech recognition using faster-whisper with domain vocabulary biasing."""

    def __init__(self, model_size: str = "small"):
        self.model_size = model_size
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
            )
        return self._model

    def transcribe(self, audio_file: str) -> str:
        """Transcribe an audio file to text using initial prompt and beam search."""
        try:
            segments, _ = self.model.transcribe(
                audio_file,
                language="en",
                initial_prompt=WHISPER_INITIAL_PROMPT,
                beam_size=5,
                temperature=0.0,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400),
            )
            text = " ".join(segment.text for segment in segments).strip()
            return text
        except Exception:
            # Fallback to standard transcribe if VAD or options encounter issue
            segments, _ = self.model.transcribe(audio_file, language="en")
            return " ".join(segment.text for segment in segments).strip()

    def record_until_silence(self, path: str = "data/audio.wav") -> str:
        return record_until_silence(path)

    def listen_for_followup(self, timeout_seconds: float = 5.0, path: str = "data/audio.wav") -> str | None:
        return listen_for_followup(timeout_seconds=timeout_seconds, path=path)


__all__ = [
    "SpeechRecognizer",
    "record_until_silence",
    "listen_for_followup",
]
