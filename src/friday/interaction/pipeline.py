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
from typing import Any, Callable

from friday.interaction.audio_input import AudioInputStream
from friday.interaction.conversation import ConversationManager
from friday.interaction.interruption import InterruptionManager
from friday.interaction.streaming_tts import QueuedAudioSink, StreamingTts
from friday.interaction.turn_detector import TurnDetector
from friday.interaction.vad import RmsVoiceActivityDetector, VoiceActivityDetector


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

    @classmethod
    def from_speech_synthesizer(
        cls,
        speech_synthesizer: Any,
        speech_recognizer: Any,
        model_size: str = "small",
        sample_rate: int = 16000,
        rms_threshold: float = 400.0,
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
        sample_rate = int(getattr(speech_synthesizer.voice.config, "sample_rate", sample_rate))

        def synth(text: str) -> tuple[bytes, int] | None:
            try:
                audio = speech_synthesizer._build_audio(text)
            except Exception:
                return None
            if audio is None or len(audio) == 0:
                return None
            return audio.astype("<i2").tobytes(), sample_rate

        if transcriber is None:
            transcriber = StreamingTranscriber(model_size=model_size)
            if hasattr(speech_recognizer, "_model") and speech_recognizer._model is not None:
                transcriber._model = speech_recognizer._model

        return cls(
            audio_input=AudioInputStream(sample_rate=16000, channels=1, block_ms=20),
            vad=RmsVoiceActivityDetector(rms_threshold=rms_threshold),
            transcriber=transcriber,
            turn_detector=TurnDetector(),
            streaming_tts=StreamingTts(synth=synth, sink=sink),
            interruption=InterruptionManager(),
            conversation=ConversationManager(followup_window_seconds=followup_window_seconds),
            sink=sink,
        )


__all__ = ["VoicePipeline"]
