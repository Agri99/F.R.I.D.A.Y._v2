"""
Interaction subsystem for F.R.I.D.A.Y. v2.

WHAT THIS IS FOR:
Voice interaction pipeline including audio capture, VAD, STT, TTS,
turn detection, interruption handling, and session management.

Runbook §5-12: Complete voice pipeline infrastructure.
"""
from __future__ import annotations

from friday.interaction.wakeword import WakeWordListener
from friday.interaction.stt import (
    SpeechRecognizer,
    StreamingTranscriber,
    TranscriptEvent,
    VoiceState,
    record_until_silence,
    listen_for_followup,
)
from friday.interaction.tts import SpeechSynthesizer
from friday.interaction.streaming_tts import (
    StreamingTts,
    TtsAudioChunk,
    AudioSink,
    QueuedAudioSink,
    StreamingAudioConsumer,
)
from friday.interaction.session import VoiceSession, SessionState, TurnLatency
from friday.interaction.audio_input import (
    AudioChunk,
    BoundedAudioQueue,
    RingAudioBuffer,
    AudioInputStream,
)
from friday.interaction.audio_output import (
    AudioOutputService,
    AudioOutputConfig,
    AudioOutputAdapter,
)
from friday.interaction.audio_capture import AudioCapture, AudioCaptureConfig, FrameQueue
from friday.interaction.vad import (
    VadEvent,
    VadEventKind,
    VoiceActivityDetector,
    RmsVoiceActivityDetector,
    SileroVoiceActivityDetector,
    CompositeVad,
)
from friday.interaction.turn_detector import (
    TurnAction,
    TurnDecision,
    TurnDetector,
    TurnDetectorConfig,
)
from friday.interaction.conversation import (
    ConversationManager,
    ConversationSnapshot,
    ConnectivityState,
    ModePreference,
)
from friday.interaction.interruption import InterruptionManager, InterruptionEvent
from friday.interaction.pipeline import VoicePipeline
from friday.interaction.diagnostics import VoiceDiagnostics, run_diagnostics
from friday.interaction.llm_streaming import (
    LlmStreamToTts,
    StreamingConfig,
    StreamingMetrics,
    stream_llm_to_tts,
)
from friday.interaction.echo_suppression import (
    EchoSuppressionConfig,
    SimpleSpectrumMatcher,
    EchoSuppressingBargeInDetector,
)
from friday.interaction.online_offline_gate import (
    OnlineOfflineGate,
    NetworkRequirement,
    NetworkStatus,
    get_online_offline_gate,
)

__all__ = [
    # Wakeword
    "WakeWordListener",
    # STT
    "SpeechRecognizer",
    "StreamingTranscriber",
    "TranscriptEvent",
    "VoiceState",
    "record_until_silence",
    "listen_for_followup",
    # TTS
    "SpeechSynthesizer",
    "StreamingTts",
    "TtsAudioChunk",
    "AudioSink",
    "QueuedAudioSink",
    "StreamingAudioConsumer",
    # Session
    "VoiceSession",
    "SessionState",
    "TurnLatency",
    # Audio I/O
    "AudioChunk",
    "BoundedAudioQueue",
    "RingAudioBuffer",
    "AudioInputStream",
    "AudioCapture",
    "AudioCaptureConfig",
    "FrameQueue",
    "AudioOutputService",
    "AudioOutputConfig",
    "AudioOutputAdapter",
    # VAD
    "VadEvent",
    "VadEventKind",
    "VoiceActivityDetector",
    "RmsVoiceActivityDetector",
    "SileroVoiceActivityDetector",
    "CompositeVad",
    # Turn Detection
    "TurnAction",
    "TurnDecision",
    "TurnDetector",
    "TurnDetectorConfig",
    # Conversation
    "ConversationManager",
    "ConversationSnapshot",
    "ConnectivityState",
    "ModePreference",
    # Interruption
    "InterruptionManager",
    "InterruptionEvent",
    # Pipeline
    "VoicePipeline",
    # Diagnostics
    "VoiceDiagnostics",
    "run_diagnostics",
    # Streaming & Echo Suppression
    "LlmStreamToTts",
    "StreamingConfig",
    "StreamingMetrics",
    "stream_llm_to_tts",
    "EchoSuppressionConfig",
    "SimpleSpectrumMatcher",
    "EchoSuppressingBargeInDetector",
    "OnlineOfflineGate",
    "NetworkRequirement",
    "NetworkStatus",
    "get_online_offline_gate",
]
