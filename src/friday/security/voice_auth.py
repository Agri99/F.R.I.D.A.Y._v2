"""
Voice verification using SpeechBrain ECAPA-TDNN with lazy loading and standard library fallbacks.
"""
from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VoiceAuthProvider:
    def __init__(self, enrollment_dir: str | Path = "data/voice_enrollment", threshold: float = 0.30):
        self.enrollment_dir = Path(enrollment_dir)
        self.threshold = threshold
        self._reference_embedding: Any | None = None
        self._verification: Any | None = None
        self._initialized = False

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

    def verify(self, audio_path: str | Path) -> bool:
        self._initialize()
        if self._verification is None or self._reference_embedding is None:
            # Graceful degradation if no enrollment exists - we fail closed because voice auth was requested
            logger.warning("Voice auth requested but no enrollment exists or models not loaded. Denying.")
            return False

        if self.get_duration_seconds(audio_path) < 1.0:
            logger.warning("Voice sample too short. Minimum duration is 1.0s.")
            return False

        try:
            import torch
            emb_test = self._verification.encode_batch(self._load_waveform(audio_path))
            score = torch.nn.functional.cosine_similarity(
                self._reference_embedding.squeeze(1), emb_test.squeeze(1)
            )
            return bool(score.item() >= self.threshold)
        except Exception as e:
            logger.error(f"Voice verification failed during processing: {e}")
            return False
