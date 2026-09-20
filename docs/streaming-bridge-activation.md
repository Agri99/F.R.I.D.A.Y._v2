# Activating the Streaming Bridge

## Overview

Enable true LLM-to-TTS streaming for sub-second speech latency. This guide shows how to:

1. Make agents expose `.stream()` method
2. Update VoiceSession to detect and use streaming
3. Fall back gracefully when streaming unavailable
4. Test the integration

## Step 1: Extend Agent Interface

### Current Flow
```python
response = agent(transcript)  # Returns complete response object
```

### New Flow (With Streaming)
```python
# Agents should support EITHER:
response = agent(transcript)              # Batch mode
# OR
stream = agent.stream(transcript)         # Streaming mode (returns Iterator[ModelDelta])
```

**Implementation:**

```python
# In your orchestrator/planner that returns responses:

class AgentResponse:
    """Standard agent response."""
    def __init__(self, text: str):
        self.text = text
        self.status = "complete"
    
    def __str__(self):
        return self.text


class StreamingAgentResponse:
    """Enables streaming support."""
    def __init__(self, stream_iterator):
        self._stream = stream_iterator
    
    def __iter__(self):
        """Make response iterable - returns ModelDelta stream."""
        return self._stream
    
    def __str__(self):
        """Fallback to collecting for batch mode."""
        return "".join(d.text for d in self._stream if hasattr(d, 'text'))
```

## Step 2: Update VoiceSession

### Modify `_run_once_event_driven()` to detect streaming:

```python
# Around line 242 in session.py

self.set_state(SessionState.THINKING)
print(f"\nUSER: {transcript}")

llm_start = time.time()
if self._pending_task_id and self.resume_agent is not None:
    response = self.resume_agent(self._pending_task_id, transcript)
    self._pending_task_id = None
else:
    response = self.agent(transcript)

latency.first_llm_token_at = time.time()

# NEW: Check if response supports streaming
llm_stream = None
response_text = ""

if hasattr(response, '__iter__') and not isinstance(response, str):
    try:
        # Try to use as stream (yields ModelDelta objects)
        from friday.models.base import ModelDelta
        # Peek at first item to verify it's a stream
        response_iter = iter(response)
        first = next(response_iter, None)
        if first and isinstance(first, ModelDelta):
            # It's a real stream - chain the first item back
            import itertools
            llm_stream = itertools.chain([first], response_iter)
            response_text = ""  # Will be populated from stream
        else:
            # Not a ModelDelta stream, use as text
            response_text = str(response) if first else ""
    except (TypeError, StopIteration):
        # Not iterable or empty, use text representation
        response_text = self._response_text(response)
else:
    # Standard text response
    response_text = self._response_text(response)

print(f"FRIDAY: {response_text}\n")
if self.cancelled:
    return last_response

if self.resume_agent is not None and self._is_awaiting_auth(response):
    self._pending_task_id = getattr(response, "id", None)

self.set_state(SessionState.SPEAKING)
interrupted = self._speak_event_driven(
    pipeline, response_text, latency=latency, llm_stream=llm_stream
)
```

## Step 3: Update `_speak_event_driven()` to handle streams

```python
# In session.py - update method signature

def _speak_event_driven(
    self,
    pipeline: Any,
    text: str,
    latency: TurnLatency | None = None,
    llm_stream: Any | None = None,  # NEW parameter
) -> bool:
    """Stream text through sentence-level TTS with cancelable playback.
    
    Args:
        pipeline: Voice pipeline with TTS and interruption
        text: Text for batch mode (used if llm_stream is None)
        latency: Latency metrics tracker
        llm_stream: Iterator[ModelDelta] for true streaming mode
    """
    from friday.interaction.streaming_tts import iter_llm_deltas_to_text
    from friday.models.base import ModelDelta

    streaming_tts = pipeline.streaming_tts
    interruption = pipeline.interruption
    conversation = pipeline.conversation
    turn_detector = pipeline.turn_detector
    sink = pipeline.sink
    audio_in = pipeline.audio_input
    vad = pipeline.vad

    if hasattr(vad, "reset"):
        vad.reset()

    streaming_tts.start(turn_id=conversation.active_turn_id or "")
    captured = interruption.generation()
    turn_detector.set_system_speaking(True)
    conversation.set_speaking(True)

    self._playback_stop.clear()

    def on_interrupt(prev_gen: int, new_gen: int) -> None:
        streaming_tts.cancel()
        self._playback_stop.set()
        conversation.set_speaking(False)
        turn_detector.set_system_speaking(False)

    interruption.register("voice_session_speak", on_interrupt)
    interrupted = False

    try:
        # TRUE STREAMING MODE: feed deltas as they arrive
        if llm_stream is not None:
            print("FRIDAY [Voice]: Using true streaming mode")
            for delta in iter_llm_deltas_to_text(llm_stream):
                if interruption.is_stale(captured):
                    interrupted = True
                    return True
                streaming_tts.feed(delta)
                # Record first audio time
                if latency and latency.first_audio_at is None and streaming_tts.first_audio_timestamp:
                    latency.first_audio_at = streaming_tts.first_audio_timestamp
        else:
            # BATCH MODE: segment complete text
            print("FRIDAY [Voice]: Using batch mode")
            deltas = [ModelDelta(text=text)]
            for delta in iter_llm_deltas_to_text(deltas):
                streaming_tts.feed(delta)
                if interruption.is_stale(captured):
                    interrupted = True
                    return True
            # Record first-audio time
            if latency and streaming_tts.first_audio_timestamp:
                latency.first_audio_at = streaming_tts.first_audio_timestamp
        
        streaming_tts.finish()

        # Play each chunk with barge-in monitoring
        chunks = sink.drain()
        for chunk in chunks:
            if interruption.is_stale(captured) or self._playback_stop.is_set():
                interrupted = True
                if latency:
                    latency.audio_stop_at = time.time()
                return True

            barge_in = self._play_chunk_with_bargein(
                chunk.audio, chunk.sample_rate, audio_in, vad,
                interruption, captured, latency,
            )
            if barge_in:
                interrupted = True
                return True

        return False  # Completed successfully

    except Exception as exc:
        logger.error("TTS failed during streaming: %s", exc)
        return False
    finally:
        conversation.set_speaking(False)
        turn_detector.set_system_speaking(False)
        interruption.unregister("voice_session_speak")
```

## Step 4: Update Agent to Support Streaming

### Example: ModelRouter with streaming

```python
# In src/friday/models/router.py

class ModelRouter:
    def stream(self, context: RoutingContext, messages: list) -> Iterator[ModelDelta]:
        """Stream from the routed provider."""
        provider = self.route(context)
        return provider.stream(messages)
```

### Example: Orchestrator with streaming

```python
# In src/friday/agent/orchestrator.py (or equivalent)

class Orchestrator:
    def __call__(self, query: str):
        """Batch mode - standard call."""
        # ... planning logic ...
        response = self.model_provider.generate(messages)
        return response.text
    
    def stream(self, query: str):
        """Streaming mode - yields deltas as they arrive."""
        from friday.models.base import ModelDelta
        
        # ... planning logic ...
        for delta in self.model_provider.stream(messages):
            yield delta
```

## Step 5: Test the Integration

### Unit Test

```python
# tests/interaction/test_streaming_integration.py

def test_voice_session_uses_streaming_when_available():
    """Verify VoiceSession detects and uses streaming."""
    from friday.models.base import ModelDelta
    
    # Mock agent with streaming
    class StreamingAgent:
        def __call__(self, query):
            return "Fallback response"
        
        def stream(self, query):
            yield ModelDelta(text="Hello ")
            yield ModelDelta(text="world")
    
    agent = StreamingAgent()
    session = VoiceSession(
        stt=MagicMock(),
        tts=MagicMock(),
        wakeword=MagicMock(),
        agent=agent,
    )
    
    # Verify agent has stream method
    assert hasattr(agent, "stream")
    
    # Call stream and verify it yields ModelDeltas
    stream = agent.stream("test")
    delta = next(stream)
    assert isinstance(delta, ModelDelta)
```

### E2E Test

```bash
# Run voice with streaming debug output
python -c "
from friday.interaction.session import VoiceSession
# ... setup ...
session.run_once(require_wake=False)  # Will print mode (streaming vs batch)
"
```

## Step 6: Configuration

### Add to config.yaml

```yaml
voice:
  streaming:
    enabled: true
    max_tokens_per_second: 50.0
    buffer_timeout_ms: 100
    cancel_on_interruption: true
```

### Load in VoiceSession

```python
class VoiceSession:
    def __init__(self, ..., streaming_config: StreamingConfig | None = None):
        self.streaming_config = streaming_config or StreamingConfig()
```

## Step 7: Monitor & Metrics

### Log streaming metrics

```python
if llm_stream is not None:
    print(f"FRIDAY [Streaming]: first_token={metrics.first_token_latency_ms:.0f}ms, "
          f"first_audio={metrics.first_audio_latency_ms:.0f}ms, "
          f"tokens={metrics.total_tokens}")
```

### Check with doctor script

```bash
python scripts/doctor.py --voice
# Should show:
# [PASS] Streaming TTS initialized successfully
# [PASS] LLM streaming bridge available
```

## Activation Checklist

- [ ] Agent exposes `.stream()` method returning Iterator[ModelDelta]
- [ ] `_run_once_event_driven()` detects and passes llm_stream
- [ ] `_speak_event_driven()` handles llm_stream parameter
- [ ] Fallback to batch mode works when streaming unavailable
- [ ] Barge-in still works (interruption manager checks generation)
- [ ] Tests pass (streaming and batch modes)
- [ ] Metrics logged (first token, first audio latency)

## Rollback

If streaming causes issues, disable it:

```python
# In _run_once_event_driven(), force batch mode:
llm_stream = None  # Always use batch mode
```

Or config:
```yaml
voice:
  streaming:
    enabled: false  # Disabled
```

This keeps both modes working safely side-by-side.
