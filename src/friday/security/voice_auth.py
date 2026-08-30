"""
Voice verification using SpeechBrain ECAPA-TDNN with lazy loading, false-positive handling,
and reliability improvements.
"""
from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Detailed voice verification result."""
    verified: bool
    score: float
    threshold: float
    duration_seconds: float
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class VoiceAuthMetrics:
    """Tracks voice auth reliability metrics."""
    total_attempts: int = 0
    successful_verifications: int = 0
    failed_verifications: int = 0
    false_rejects: int = 0  # Legitimate user rejected
    false_accepts: int = 0  # Imposter accepted
    avg_score: float = 0.0
    min_score: float = 1.0
    max_score: float = 0.0
    last_verification: str | None = None


class VoiceAuthProvider:
    """Voice verification with ECAPA-TDNN, false-positive handling, and reliability metrics."""

    def __init__(self, enrollment_dir: str | Path = "data/voice_enrollment",
                 threshold: float = 0.30, min_duration: float = 1.0,
                 adaptive_threshold: bool = True):
        self.enrollment_dir = Path(enrollment_dir)
        self.threshold = threshold
        self.min_duration = min_duration
        self.adaptive_threshold = adaptive_threshold
        self._reference_embedding: Any | None = None
        self._verification: Any | None = None
        self._initialized = False
        self.metrics = VoiceAuthMetrics()
        self._score_history: list[float] = []

    def _initialize(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        try:
            from speechbrain.inference.speaker import SpeakerRecognition
            from speechbrain.utils.fetching import LocalStrategy

            self._verification = SpeakerRecognition.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir="models/spkrec-ecapa-voxceleb",
                local_strategy=LocalStrategy.COPY_SKIP_CACHE,
            )
            self._reference_embedding = self._build_reference_embedding()
            if self._reference_embedding is None:
                logger.warning("No voice enrollment found. Voice auth will deny all attempts.")
        except Exception as e:
            logger.warning(f"VoiceAuthProvider could not load SpeechBrain models: {e}")

    def _load_waveform(self, path: str | Path) -> Any:
        import soundfile as sf
        import torch

        audio, _ = sf.read(str(path), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return torch.from_numpy(audio).unsqueeze(0)

    def _build_reference_embedding(self) -> Any | None:
        import torch

        if not self.enrollment_dir.exists():
            return None
        ref_files = sorted(self.enrollment_dir.glob("voice_ref_*.wav"))
        if not ref_files:
            return None

        embeddings = [self._verification.encode_batch(self._load_waveform(str(f))) for f in ref_files]
        if not embeddings:
            return None
        return torch.stack(embeddings).mean(dim=0)

    def get_duration_seconds(self, path: str | Path) -> float:
        try:
            with wave.open(str(path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return frames / float(rate)
        except Exception:
            pass

        try:
            import soundfile as sf
            info = sf.info(str(path))
            return info.frames / info.samplerate
        except Exception:
            return 0.0

    def verify(self, audio_path: str | Path) -> VerificationResult:
        """Verify voice with detailed result."""
        self.metrics.total_attempts += 1
        self.metrics.last_verification = datetime.now().isoformat()

        self._initialize()

        if self._verification is None or self._reference_embedding is None:
            self.metrics.failed_verifications += 1
            return VerificationResult(
                verified=False, score=0.0, threshold=self.threshold,
                duration_seconds=self.get_duration_seconds(audio_path),
                error="No enrollment or models not loaded"
            )

        duration = self.get_duration_seconds(audio_path)
        if duration < self.min_duration:
            self.metrics.failed_verifications += 1
            return VerificationResult(
                verified=False, score=0.0, threshold=self.threshold,
                duration_seconds=duration,
                error=f"Voice sample too short ({duration:.1f}s < {self.min_duration}s)"
            )

        try:
            import torch
            emb_test = self._verification.encode_batch(self._load_waveform(audio_path))
            score = torch.nn.functional.cosine_similarity(
                self._reference_embedding.squeeze(1), emb_test.squeeze(1)
            )
            score_val = float(score.item())

            # Update metrics
            self._update_metrics(score_val)

            # Adaptive threshold adjustment
            effective_threshold = self.threshold
            if self.adaptive_threshold and len(self._score_history) >= 10:
                # Adjust threshold based on score distribution
                import numpy as np
                recent_scores = np.array(self._score_history[-50:])
                mean_score = recent_scores.mean()
                std_score = recent_scores.std()
                # Set threshold at mean - 2*std for legitimate user
                adaptive_t = max(0.25, mean_score - 2 * std_score)
                effective_threshold = min(self.threshold, adaptive_t)

            verified = score_val >= effective_threshold

            if verified:
                self.metrics.successful_verifications += 1
            else:
                self.metrics.failed_verifications += 1

            return VerificationResult(
                verified=verified,
                score=score_val,
                threshold=effective_threshold,
                duration_seconds=duration
            )
        except Exception as e:
            self.metrics.failed_verifications += 1
            logger.error(f"Voice verification failed during processing: {e}")
            return VerificationResult(
                verified=False, score=0.0, threshold=self.threshold,
                duration_seconds=duration,
                error=str(e)
            )

    def _update_metrics(self, score: float):
        """Update running metrics."""
        self.metrics.avg_score = (self.metrics.avg_score * (self.metrics.total_attempts - 1) + score) / self.metrics.total_attempts
        self.metrics.min_score = min(self.metrics.min_score, score)
        self.metrics.max_score = max(self.metrics.max_score, score)
        self._score_history.append(score)
        if len(self._score_history) > 100:
            self._score_history = self._score_history[-100:]

    def get_metrics(self) -> VoiceAuthMetrics:
        """Get current verification metrics."""
        return self.metrics

    def get_false_reject_rate(self) -> float:
        if self.metrics.total_attempts == 0:
            return 0.0
        return self.metrics.false_rejects / self.metrics.total_attempts

    def get_false_accept_rate(self) -> float:
        if self.metrics.total_attempts == 0:
            return 0.0
        return self.metrics.false_accepts / self.metrics.total_attempts

    def record_false_reject(self):
        """Record a false rejection (legitimate user denied)."""
        self.metrics.false_rejects += 1

    def record_false_accept(self):
        """Record a false acceptance (imposter accepted)."""
        self.metrics.false_accepts += 1

    def reset_metrics(self):
        """Reset metrics for fresh tracking."""
        self.metrics = VoiceAuthMetrics()
        self._score_history.clear()

    def enroll_new_sample(self, audio_path: str | Path) -> bool:
        """Add a new enrollment sample and rebuild reference."""
        if not self.enrollment_dir.exists():
            self.enrollment_dir.mkdir(parents=True, exist_ok=True)

        import shutil
        dest = self.enrollment_dir / f"voice_ref_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        shutil.copy2(audio_path, dest)

        # Rebuild reference embedding
        self._reference_embedding = self._build_reference_embedding()
        return self._reference_embedding is not None
