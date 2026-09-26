"""
src/friday/interaction/vad.py

WHAT THIS IS FOR:
Voice activity detection (VAD) abstraction.

Runbook §19 — keep VAD replaceable so the conversation engine doesn't bind to
one library. The protocol returns ``VadEvent`` so callers can do state-machine
work without coupling to RMS or to Silero / WebRTC / webrtcvad internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

import numpy as np


class VadEventKind(str, Enum):
    """Voice activity events emitted by a VAD over a stream of audio chunks."""
    SPEECH_STARTED = "speech_started"
    SPEECH_CONTINUED = "speech_continued"
    SPEECH_ENDED = "speech_ended"
    NO_SPEECH = "no_speech"


@dataclass(frozen=True)
class VadEvent:
    """A single VAD decision for a chunk of audio."""
    kind: VadEventKind
    confidence: float
    timestamp: float


@runtime_checkable
class VoiceActivityDetector(Protocol):
    """Process a chunk of int16 mono PCM and return a VadEvent."""

    def process(self, audio_chunk: np.ndarray, timestamp: float) -> VadEvent: ...


class RmsVoiceActivityDetector:
    """Energy-threshold VAD.

    This is the same fallback already used inside ``record_until_silence``; we
    keep it as a deterministic, dependency-free baseline that always works on
    any host and as a regression reference.
    """

    def __init__(
        self,
        rms_threshold: float = 50.0,
        silence_chunks_to_end: int = 3,
        speech_chunks_to_start: int = 2,
    ) -> None:
        if rms_threshold < 0:
            raise ValueError("rms_threshold must be non-negative")
        if silence_chunks_to_end < 1:
            raise ValueError("silence_chunks_to_end must be >= 1")
        if speech_chunks_to_start < 1:
            raise ValueError("speech_chunks_to_start must be >= 1")
        self.rms_threshold = float(rms_threshold)
        self.silence_chunks_to_end = int(silence_chunks_to_end)
        self.speech_chunks_to_start = int(speech_chunks_to_start)
        self._speech_streak = 0
        self._silence_streak = 0
        self._speaking = False

    def reset(self) -> None:
        self._speech_streak = 0
        self._silence_streak = 0
        self._speaking = False

    def _rms(self, chunk: np.ndarray) -> float:
        if chunk.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

    def process(self, audio_chunk: np.ndarray, timestamp: float) -> VadEvent:
        rms = self._rms(audio_chunk)
        # Debug: print RMS every 50 frames so user can see their mic level
        if not hasattr(self, "_debug_counter"):
            self._debug_counter = 0
        self._debug_counter += 1
        if self._debug_counter % 50 == 0:
            print(f"FRIDAY [VAD]: rms={rms:.1f} threshold={self.rms_threshold}")
        is_speech = rms >= self.rms_threshold

        if is_speech:
            self._speech_streak += 1
            self._silence_streak = 0
        else:
            self._silence_streak += 1
            self._speech_streak = 0

        if not self._speaking and self._speech_streak >= self.speech_chunks_to_start:
            self._speaking = True
            self._silence_streak = 0
            return VadEvent(VadEventKind.SPEECH_STARTED, confidence=min(1.0, rms / (self.rms_threshold * 2)), timestamp=timestamp)

        if self._speaking and self._silence_streak >= self.silence_chunks_to_end:
            self._speaking = False
            self._speech_streak = 0
            return VadEvent(VadEventKind.SPEECH_ENDED, confidence=1.0, timestamp=timestamp)

        if self._speaking:
            return VadEvent(VadEventKind.SPEECH_CONTINUED, confidence=min(1.0, rms / (self.rms_threshold * 2)), timestamp=timestamp)
        return VadEvent(VadEventKind.NO_SPEECH, confidence=1.0 - min(1.0, rms / self.rms_threshold) if self.rms_threshold > 0 else 0.0, timestamp=timestamp)


class CompositeVad:
    """Combine multiple VADs by majority vote over the SPEECH/NO_SPEECH decision.

    Useful when layering a fast RMS detector with a slower but more accurate
    Silero / WebRTC detector. The first detector in the list is the primary;
    the others serve as confirmations.
    """

    def __init__(self, detectors: list[VoiceActivityDetector]) -> None:
        if not detectors:
            raise ValueError("CompositeVad requires at least one detector")
        self.detectors = detectors

    def process(self, audio_chunk: np.ndarray, timestamp: float) -> VadEvent:
        events = [d.process(audio_chunk, timestamp) for d in self.detectors]
        speech_votes = sum(1 for e in events if e.kind in (VadEventKind.SPEECH_STARTED, VadEventKind.SPEECH_CONTINUED, VadEventKind.SPEECH_ENDED))
        any_started = any(e.kind == VadEventKind.SPEECH_STARTED for e in events)
        any_ended = any(e.kind == VadEventKind.SPEECH_ENDED for e in events)
        majority_speech = speech_votes > len(events) / 2
        avg_conf = sum(e.confidence for e in events) / len(events)

        if any_ended:
            return VadEvent(VadEventKind.SPEECH_ENDED, confidence=avg_conf, timestamp=timestamp)
        if any_started and majority_speech:
            return VadEvent(VadEventKind.SPEECH_STARTED, confidence=avg_conf, timestamp=timestamp)
        if majority_speech:
            return VadEvent(VadEventKind.SPEECH_CONTINUED, confidence=avg_conf, timestamp=timestamp)
        return VadEvent(VadEventKind.NO_SPEECH, confidence=avg_conf, timestamp=timestamp)


class SileroVoiceActivityDetector:
    """Neural VAD using Silero (ONNX).
    
    Extremely robust against background noise, typing, and fans. Only triggers
    on actual human speech.
    """

    def __init__(
        self,
        model_path: str = "data/silero_vad.onnx",
        speech_threshold: float = 0.35,
        silence_chunks_to_end: int = 15,   # ~480ms at 512 frames/chunk
        speech_chunks_to_start: int = 2,   # ~64ms
        rms_fallback_threshold: float = 60.0,
    ) -> None:
        import onnxruntime as ort
        import os
        
        self.speech_threshold = speech_threshold
        self.silence_chunks_to_end = silence_chunks_to_end
        self.speech_chunks_to_start = speech_chunks_to_start
        self.rms_fallback_threshold = rms_fallback_threshold
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Silero VAD model not found at {model_path}. Please download it.")
            
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.reset()
        
    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._buffer = np.array([], dtype=np.float32)
        self._speech_streak = 0
        self._silence_streak = 0
        self._speaking = False
        self._last_event = VadEvent(VadEventKind.NO_SPEECH, 0.0, 0.0)
        
    def process(self, audio_chunk: np.ndarray, timestamp: float) -> VadEvent:
        if audio_chunk.size == 0:
            return self._last_event
            
        # Convert to float32 [-1.0, 1.0]
        chunk_f32 = audio_chunk.astype(np.float32) / 32768.0
        self._buffer = np.concatenate((self._buffer, chunk_f32))
        
        # We need 512 frames for Silero at 16kHz
        while self._buffer.size >= 512:
            frame = self._buffer[:512]
            self._buffer = self._buffer[512:]
            
            # Run inference
            inputs = {
                'input': frame.reshape(1, 512),
                'sr': np.array(16000, dtype=np.int64),
                'state': self._state
            }
            out, self._state = self.session.run(None, inputs)
            prob = float(out[0][0])
            frame_rms = float(np.sqrt(np.mean(frame ** 2)) * 32768.0)
            
            # Speech detected if model probability is confident OR borderline with sufficient RMS energy
            is_speech = (prob >= self.speech_threshold) or (prob >= 0.20 and frame_rms >= self.rms_fallback_threshold)
            
            if is_speech:
                self._speech_streak += 1
                self._silence_streak = 0
            else:
                self._silence_streak += 1
                self._speech_streak = 0
                
            if not self._speaking and self._speech_streak >= self.speech_chunks_to_start:
                self._speaking = True
                self._silence_streak = 0
                self._last_event = VadEvent(VadEventKind.SPEECH_STARTED, prob, timestamp)
            elif self._speaking and self._silence_streak >= self.silence_chunks_to_end:
                self._speaking = False
                self._speech_streak = 0
                self._last_event = VadEvent(VadEventKind.SPEECH_ENDED, 1.0 - prob, timestamp)
            elif self._speaking:
                self._last_event = VadEvent(VadEventKind.SPEECH_CONTINUED, prob, timestamp)
            else:
                self._last_event = VadEvent(VadEventKind.NO_SPEECH, 1.0 - prob, timestamp)
                
            # Optional debug print (uncomment to trace probabilities)
            # print(f"Silero prob: {prob:.3f} | speaking={self._speaking}")
            
        return self._last_event


__all__ = [
    "VadEvent",
    "VadEventKind",
    "VoiceActivityDetector",
    "RmsVoiceActivityDetector",
    "SileroVoiceActivityDetector",
    "CompositeVad",
]
