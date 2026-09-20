"""
src/friday/interaction/echo_suppression.py

WHAT THIS IS FOR:
Echo resistance for barge-in detection (Runbook §24 — Phase V9).

Problem: FRIDAY's own audio output can trigger barge-in detection,
causing infinite interrupt loops.

Solution: Output reference suppression using frequency comparison.
When audio is playing through the speaker, suppress high-similarity
audio from the microphone.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class EchoSuppressionConfig:
    """Configuration for echo suppression."""
    similarity_threshold: float = 0.85  # How similar before suppressing
    reference_window_ms: int = 500  # How long to keep reference audio
    sample_rate: int = 16000


class SimpleSpectrumMatcher:
    """Simple spectrum-based echo detection.

    Compares frequency content of incoming audio with reference (output)
    audio. If they're too similar, likely echo/output bleed.
    """

    def __init__(self, config: EchoSuppressionConfig | None = None):
        self.config = config or EchoSuppressionConfig()
        self._reference_buffer: list[np.ndarray] = []
        self._reference_spectrum: Optional[np.ndarray] = None

    def add_reference_audio(self, audio: np.ndarray) -> None:
        """Add output audio as a reference.

        Args:
            audio: int16 PCM audio from the speaker
        """
        self._reference_buffer.append(audio.copy())

        # Keep buffer bounded
        buffer_samples = int(self.config.sample_rate * self.config.reference_window_ms / 1000)
        total_samples = sum(len(a) for a in self._reference_buffer)

        while total_samples > buffer_samples and self._reference_buffer:
            removed = self._reference_buffer.pop(0)
            total_samples -= len(removed)

        # Update reference spectrum
        if self._reference_buffer:
            combined = np.concatenate(self._reference_buffer)
            self._reference_spectrum = self._get_spectrum(combined)

    def is_likely_echo(self, audio: np.ndarray) -> bool:
        """Check if incoming audio is likely echo.

        Args:
            audio: int16 PCM audio from the microphone

        Returns:
            True if audio appears to be echo of reference
        """
        if self._reference_spectrum is None or len(self._reference_buffer) == 0:
            return False

        # Get spectrum of incoming audio
        incoming_spectrum = self._get_spectrum(audio)

        # Compare spectra
        similarity = self._spectrum_similarity(incoming_spectrum, self._reference_spectrum)

        return similarity > self.config.similarity_threshold

    def _get_spectrum(self, audio: np.ndarray) -> np.ndarray:
        """Get magnitude spectrum of audio."""
        if audio.size < 512:
            return np.zeros(257)  # Return zeros if too short

        # Simple FFT
        fft = np.fft.rfft(audio[:512])  # Use first 512 samples
        spectrum = np.abs(fft) / 256  # Normalize

        return spectrum

    def _spectrum_similarity(
        self,
        spec1: np.ndarray,
        spec2: np.ndarray,
    ) -> float:
        """Compute cosine similarity between spectra.

        Args:
            spec1: First spectrum
            spec2: Second spectrum

        Returns:
            Similarity score from 0 to 1
        """
        if spec1.size == 0 or spec2.size == 0:
            return 0.0

        # Pad to same length
        max_len = max(len(spec1), len(spec2))
        s1 = np.pad(spec1, (0, max_len - len(spec1)))
        s2 = np.pad(spec2, (0, max_len - len(spec2)))

        # Normalize
        s1_norm = s1 / (np.linalg.norm(s1) + 1e-8)
        s2_norm = s2 / (np.linalg.norm(s2) + 1e-8)

        # Cosine similarity
        similarity = float(np.dot(s1_norm, s2_norm))

        return max(0.0, min(1.0, similarity))

    def clear_reference(self) -> None:
        """Clear the reference buffer."""
        self._reference_buffer = []
        self._reference_spectrum = None


class EchoSuppressingBargeInDetector:
    """Barge-in detector with echo suppression.

    Wraps a VAD detector and applies echo suppression:
      1. Monitor output audio via add_output_audio()
      2. Check incoming microphone audio with is_speech_barge_in()
      3. Returns True only for non-echo speech
    """

    def __init__(
        self,
        base_vad: any,
        config: EchoSuppressionConfig | None = None,
    ):
        self.vad = base_vad
        self.config = config or EchoSuppressionConfig()
        self._echo_detector = SimpleSpectrumMatcher(config)

    def add_output_audio(self, audio: np.ndarray) -> None:
        """Register output audio for echo suppression.

        Call this when FRIDAY is speaking, passing the audio chunk.

        Args:
            audio: int16 PCM audio from the speaker
        """
        self._echo_detector.add_reference_audio(audio)

    def is_speech_barge_in(self, audio: np.ndarray, timestamp: float) -> bool:
        """Check if audio is user speech (not echo).

        Args:
            audio: int16 PCM audio from the microphone
            timestamp: Timestamp of the audio chunk

        Returns:
            True if speech detected and not echo
        """
        # First check: does VAD detect speech?
        vad_event = self.vad.process(audio, timestamp)

        is_speech = vad_event.kind in (
            "speech_started",
            "speech_continued",
        )

        if not is_speech:
            return False

        # Second check: is it echo?
        is_echo = self._echo_detector.is_likely_echo(audio)

        if is_echo:
            return False

        # It's real speech, not echo
        return True

    def reset(self) -> None:
        """Reset detector state."""
        if hasattr(self.vad, "reset"):
            self.vad.reset()
        self._echo_detector.clear_reference()


__all__ = [
    "EchoSuppressionConfig",
    "SimpleSpectrumMatcher",
    "EchoSuppressingBargeInDetector",
]
