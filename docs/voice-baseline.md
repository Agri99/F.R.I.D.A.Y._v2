# F.R.I.D.A.Y. Voice Baseline Documentation

**Generated:** 2026-09-16  
**Runbook Phase:** V0 — Baseline

## System Configuration

```text
Python: 3.11+
Audio: sounddevice (PortAudio)
STT: faster-whisper (int8 quantization)
TTS: Piper (ONNX)
VAD: Silero (ONNX) or RMS fallback
Wake Word: openwakeword
```

## Voice Pipeline Architecture

```
Windows Audio Input Device
        ↓
   AudioCapture (single owner)
        ↓
   Bounded Frame Bus
        ↓
   ┌───────┬───────┬───────┐
   ↓       ↓       ↓       ↓
Wake    VAD     STT    BargeIn
Word    Engine         Detector
   ↓       ↓       ↓       ↓
   └───────┴───────┴───────┘
           ↓
     Turn Detector
           ↓
   Streaming Transcriber
           ↓
   Conversation Manager
           ↓
     Model Router
           ↓
      ModelProvider.stream()
           ↓
      Text Delta Stream
           ↓
       Segmenter
           ↓
    Streaming Piper TTS
           ↓
     Audio Output Service
           ↓
        Speaker
```

## Latency Targets

| Metric | Target | Description |
|--------|--------|-------------|
| wake_latency | < 200ms | Wake word detection to listening state |
| speech_start_latency | < 100ms | VAD speech start detection |
| stt_partial_latency | < 500ms | First partial transcript while speaking |
| stt_final_latency | < 800ms | Final transcript after speech ends |
| llm_first_token_latency | < 300ms | First LLM token after transcript |
| tts_first_audio_latency | < 200ms | First audio after text segment ready |
| time_to_first_audio | < 1500ms | Speech end to first audio output |
| barge_in_latency | < 150ms | User speech to playback stop |
| turn_duration | variable | Full turn from start to end |

## Key Components

### AudioCapture (Phase V1)

Single persistent microphone owner with bounded frame bus.

```python
from friday.interaction import AudioCapture, AudioCaptureConfig

config = AudioCaptureConfig(
    sample_rate=16000,
    channels=1,
    block_ms=20,
    queue_max_size=128,
)
capture = AudioCapture(config)
capture.start()
```

### VAD (Phase V3)

Voice Activity Detection with Silero (preferred) or RMS fallback.

```python
from friday.interaction import SileroVoiceActivityDetector, RmsVoiceActivityDetector

# Silero (recommended)
vad = SileroVoiceActivityDetector(
    model_path="data/silero_vad.onnx",
    speech_threshold=0.5,
)

# RMS fallback
vad = RmsVoiceActivityDetector(rms_threshold=50.0)
```

### StreamingTranscriber (Phase V4)

Asynchronous streaming STT with generation IDs.

```python
from friday.interaction import StreamingTranscriber

transcriber = StreamingTranscriber(
    model_size="small",
    min_partial_interval_s=0.4,
    max_buffer_seconds=15.0,
)
transcriber.start_streaming(callback=None, turn_id="turn-123")
transcriber.submit_chunk(audio_data, timestamp=time.time())
events = transcriber.drain_events()
final_events = transcriber.finalize()
```

### TurnDetector (Phase V5)

Deterministic turn boundary detection.

```python
from friday.interaction import TurnDetector, TurnDetectorConfig

config = TurnDetectorConfig(
    silence_to_end_s=0.7,
    max_turn_seconds=30.0,
)
detector = TurnDetector(config)
detector.observe_vad(vad_event)
detector.observe_partial(transcript_event)
decision = detector.decide(now=time.time(), transcript=text)
```

### StreamingTts (Phase V7)

Sentence-level streaming TTS with generation-aware cancellation.

```python
from friday.interaction import StreamingTts, QueuedAudioSink

sink = QueuedAudioSink()
tts = StreamingTts(synth=synthesizer_callback, sink=sink)
gen_id = tts.start(turn_id="turn-123")
tts.feed("Hello, ")
tts.feed("how can I help?")
tts.finish()
chunks = sink.drain()
```

### InterruptionManager (Phase V9)

Generation-safe barge-in handling.

```python
from friday.interaction import InterruptionManager

im = InterruptionManager()
im.register("tts", lambda prev, new: tts.cancel())
im.register("llm", lambda prev, new: llm.cancel())

if barge_in_detected:
    new_gen = im.interrupt(reason="user_barge_in")
```

### AudioOutputService (Phase V8)

Reusable audio sink with generation-local cancellation.

```python
from friday.interaction import AudioOutputService, AudioOutputConfig

output = AudioOutputService(AudioOutputConfig())
output.start()
output.play(audio_bytes, sample_rate=22050, generation=gen_id)
output.flush_generation()  # Cancel current gen only, keep service alive
```

## Voice Session States

```text
IDLE → LISTENING_FOR_WAKE → WAKE_DETECTED → LISTENING → TRANSCRIBING → THINKING → SPEAKING → FOLLOWUP_LISTENING → (back to LISTENING or IDLE)

Any state → INTERRUPTED (on barge-in)
Any state → ERROR (on failure)
```

## Diagnostic Commands

Run system health check:
```bash
python scripts/doctor.py
```

Run voice pipeline diagnostics:
```bash
python scripts/doctor.py --voice
```

## Known Issues

1. **M2 Voice Pipeline**: Event-driven path stuck in LISTENING on live host. Use legacy path (flag in VoiceSession) as fallback.

2. **Silero VAD Model**: Must be downloaded separately to `data/silero_vad.onnx`.

3. **Wake Word Model**: Custom "hey_friday.onnx" model required for optimal performance.

## Configuration

Voice settings in `config.yaml`:

```yaml
voice:
  wake_word: "friday"
  tts_voice: "en_US-lessac-medium"
  vad:
    mode: auto  # auto, silero, rms
    threshold: 50.0  # for RMS mode
  followup_window_seconds: 5.0
  max_turn_seconds: 30.0
```

## Testing

Run voice-related tests:
```bash
pytest tests/interaction/ -v
```

Run voice integration tests:
```bash
pytest tests/interaction/test_event_driven_voice_integration.py -v
```
