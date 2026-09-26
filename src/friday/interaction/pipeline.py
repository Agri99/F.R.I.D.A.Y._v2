"""
src/friday/interaction/pipeline.py

WHAT THIS IS FOR:
Glue object that holds the event-driven voice pipeline components and the
adapter from the legacy ``SpeechSynthesizer`` (Piper) into the streaming
TTS synth callback.

The default usage:

    pipeline = VoicePipeline.from_speech_synthesizer(speech_synthesizer)
    session = VoiceSession(stt=..., tts=..., wakeword=..., agent=...,
                           voice_pipeline=pipeline)

The pipeline is the single thing you swap into ``VoiceSession`` to flip
between legacy and event-driven behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

from friday.interaction.audio_input import AudioInputStream
from friday.interaction.conversation import ConversationManager
from friday.interaction.interruption import InterruptionManager
from friday.interaction.streaming_tts import QueuedAudioSink, StreamingAudioConsumer, StreamingTts
from friday.interaction.turn_detector import TurnDetector
from friday.interaction.vad import SileroVoiceActivityDetector, VoiceActivityDetector


@dataclass
class VoicePipeline:
    """Container for the event-driven voice pipeline components."""

    audio_input: AudioInputStream
    vad: VoiceActivityDetector
    transcriber: Any  # StreamingTranscriber — typed as Any to avoid import cycles
    turn_detector: TurnDetector
    streaming_tts: StreamingTts
    interruption: InterruptionManager
    conversation: ConversationManager
    sink: QueuedAudioSink
    audio_consumer: StreamingAudioConsumer | None = None

    @classmethod
    def from_speech_synthesizer(
        cls,
        speech_synthesizer: Any,
        speech_recognizer: Any,
        model_size: str = "small",
        sample_rate: int = 16000,
        rms_threshold: float = 50.0,
        followup_window_seconds: float = 5.0,
        sink: QueuedAudioSink | None = None,
        transcriber: Any = None,
    ) -> "VoicePipeline":
        """Build a default pipeline wired to existing Piper speech synthesis
        and a faster-whisper ``SpeechRecognizer``:

            pipeline = VoicePipeline.from_speech_synthesizer(
                speech_synthesizer, speech_recognizer
            )
            # pipeline.transcriber is a real StreamingTranscriber.

        The host may pass its own pre-built ``transcriber`` to override the
        lazily-created default.
        """
        from friday.interaction.stt import StreamingTranscriber

        sink = sink or QueuedAudioSink()
        sr = getattr(speech_synthesizer, "sample_rate", None)
        if sr is None:
            voice = getattr(speech_synthesizer, "voice", None)
            config = getattr(voice, "config", None) if voice else None
            sr = getattr(config, "sample_rate", sample_rate) if config else sample_rate
        sample_rate = int(sr)

        def synth(text: str) -> tuple[bytes, int] | None:
            try:
                audio = speech_synthesizer._build_audio(text)
            except Exception as synth_exc:
                logger.warning("Pipeline TTS synthesis failed for '%s': %s", text, synth_exc)
                return None
            if audio is None or len(audio) == 0:
                return None
            if np.issubdtype(audio.dtype, np.floating):
                audio = np.clip(audio, -1.0, 1.0)
                audio_i16 = (audio * 32767).astype(np.int16)
            else:
                audio_i16 = audio.astype(np.int16)
            return audio_i16.tobytes(), sample_rate

        if transcriber is None:
            transcriber = StreamingTranscriber(model_size=model_size)
            if hasattr(speech_recognizer, "_model") and speech_recognizer._model is not None:
                transcriber._model = speech_recognizer._model

        return cls(
            audio_input=AudioInputStream(sample_rate=16000, channels=1, block_ms=20),
            vad=SileroVoiceActivityDetector(),
            transcriber=transcriber,
            turn_detector=TurnDetector(),
            streaming_tts=StreamingTts(synth=synth, sink=sink),
            interruption=InterruptionManager(),
            conversation=ConversationManager(followup_window_seconds=followup_window_seconds),
            sink=sink,
        )


__all__ = ["VoicePipeline"]
