"""
src/friday/interaction/gemini_live.py

WHAT THIS IS FOR:
Real-time, bidirectional voice conversation engine using Google Gemini Live API
(gemini-3.1-flash-live-preview) over WebSockets with Chatterbox Turbo neural TTS speech output.

KEY CAPABILITIES:
- Full-duplex conversational streaming (16kHz in, Chatterbox Turbo TTS speech out).
- Chatterbox Turbo Voice: Expressive, natural human-like neural TTS with emotion delivery and vocal sound effects.
- Server-side Gemini Voice Activity Detection (differentiates human voice from background noise).
- Real-time barge-in / interruption handling: cuts off TTS speech output instantly when the user speaks.
- Local Friday tool execution (mouse control, installed apps, system control, time, web search).
- 10-Second Post-Speech Follow-Up Window:
  Strict 10.0-second countdown begins ONLY AFTER Friday completely finishes speaking.
  If the user speaks within 10s, conversation continues seamlessly into the next turn.
  If 10s elapses without speech, automatically returns to wake word listening ("Friday").
"""

from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
import collections
from datetime import datetime
from typing import Any, Callable

import numpy as np

try:
    from google import genai
    from google.genai import types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]

from friday.interaction.segmenter import segment
from friday.interaction.session import SessionState
from friday.security.secrets import SecretsManager

SAMPLE_RATE_IN = 16000     # Gemini Live expects 16kHz PCM input
CHUNK_SIZE_IN = 1024       # ~64ms chunks for low-latency streaming


class GeminiLiveSession:
    """Manages a real-time Gemini Live WebSocket session with Chatterbox Turbo neural TTS output,

    Friday tool execution, and an accurate 10-second post-speech follow-up window.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-3.1-flash-live-preview",
        voice_name: str = "Aoede",
        system_prompt: str | None = None,
        tool_registry: Any = None,
        wakeword_listener: Any = None,
        speech_synthesizer: Any = None,
        speech_director: Any = None,
        followup_timeout: float = 10.0,
        on_state_change: Callable[[SessionState], None] | None = None,
        episodic_memory: Any = None,
        barge_in_rms: float = 1200.0,
        bargein_min_frames: int = 3,
        barge_in_vad_threshold: float = 0.65,
    ) -> None:
        if not _GENAI_AVAILABLE:
            raise RuntimeError("The google-genai library is not installed.")

        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            try:
                self.api_key = SecretsManager().get("gemini_api_key")
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                pass

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")

        self.api_key = self.api_key.strip()
        self.client = genai.Client(api_key=self.api_key)
        self.model = model
        self.voice_name = voice_name
        self.speech_synthesizer = speech_synthesizer
        self.speech_director = speech_director
        self.barge_in_rms = float(barge_in_rms)
        self.bargein_min_frames = max(2, int(bargein_min_frames))
        self.barge_in_vad_threshold = float(barge_in_vad_threshold)
        self._last_user_text = ""

        base_prompt = system_prompt or "You are FRIDAY, an elite personal AI assistant."
        operational_rules = (
            "\n\nIMPORTANT OPERATIONAL INSTRUCTIONS:\n"
            "1. When the user asks for the current time, call system_get_time without arguments to retrieve their local workstation time. "
            "Never specify timezone='UTC' unless the user explicitly asked for UTC or a specific foreign city. "
            "When stating the time, format it cleanly with proper colon punctuation (e.g. 'It is 2:01 PM, Boss.' or 'It's two oh one PM, Boss.'), never unpunctuated numbers like '2 01 PM'.\n"
            "2. When answering, speak naturally with warmth, personality, and emotion as Friday. "
            "Keep responses conversational and expressive — our speech engine handles vocal expression automatically.\n"
            "3. If the user asks to control the mouse (move, click, right click, double click, scroll), use computer_mouse_move, computer_mouse_click, or computer_mouse_scroll.\n"
            "4. If the user asks to open an application, use applications_open. Whitelisted utilities (notepad, calculator, vscode, terminal, explorer) open directly. All other installed applications are Orange-tier and require user confirmation before opening.\n"
            "5. Call system_shutdown_friday ONLY when the user explicitly commands you to shut down, turn off, or says goodbye (e.g. 'shut down', 'goodbye', 'turn off'). "
            "NEVER call system_shutdown_friday when the user interrupts, says 'actually', 'wait', 'hold on', or during ongoing conversations.\n"
            "6. For queries about recent events, modern games (e.g. Expedition 33, Clair Obscur, recent sequels), awards (such as Game of the Year 2024/2025/2026), current news, or specific factual details beyond your baseline training, ALWAYS call the online_search tool immediately to fetch live, verified facts before formulating your answer. Never say you don't know without searching first.\n"
            "7. Punctuation and human cadence: Speak with natural, fluid prosody just like a human conversationalist. "
            "Use commas for natural breathing pauses in longer sentences. Use em-dashes ('—') for smooth conversational transitions or slight hesitations. "
            "When pondering or checking, use ellipses ('...'). "
            "When tone authentically calls for emotional expression, you may naturally prefix sentences with supported vocal tags: "
            "[chuckle] (for light amusement or witty banter), [sigh] (for genuine empathy or thoughtful pause), [whispering] (for confidential or quiet observations), or [sarcastic] (for dry humor). "
            "Never use tags during critical errors, confirmations, or routine factual readouts. Use at most one tag per sentence.\n"
            "8. Multilingual Language Recognition and Persona Consistency: "
            "You fluently comprehend and transcribe speech in any language, following the priority order: English > Indonesian > Sundanese > Any other languages. "
            "CRITICAL LANGUAGE RESPONSE DIRECTIVE: Regardless of what language the user speaks to you in (whether English, Indonesian, Sundanese, or any other language), you must ALWAYS formulate and speak your response exclusively in ENGLISH. "
            "You understand everything the user says in their language with complete nuance, but your spoken replies are always in English. "
            "CRITICAL PERSONA AND MANNERISM RULES: "
            "Never sound like a generic customer-service agent, corporate robot, or reading a script. "
            "Always embody Friday: sophisticated, refined, loyal, poised, and quietly witty, addressing the user warmly as 'Boss'."
        )
        self.system_prompt = base_prompt + operational_rules
        self.tool_registry = tool_registry
        self.wakeword_listener = wakeword_listener
        self.followup_timeout = float(followup_timeout)
        self.on_state_change = on_state_change
        self.episodic_memory = episodic_memory

        self.state = SessionState.IDLE
        self._stop_requested = False
        self._shutdown_pending = False
        self._interrupted = threading.Event()
        self._user_spoke_in_turn = asyncio.Event()

    @property
    def effective_system_prompt(self) -> str:
        """Dynamically attach current date and time to the system prompt."""
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M %p")
        year_str = str(now.year)
        temporal_preamble = (
            f"TEMPORAL REAL-TIME CONTEXT:\n"
            f"- Today's Date: {date_str}\n"
            f"- Current Year: {year_str}\n"
            f"- Local Time: {time_str}\n\n"
        )
        return temporal_preamble + self.system_prompt


    def set_state(self, new_state: SessionState) -> None:
        self.state = new_state
        if self.on_state_change:
            self.on_state_change(new_state)

    def request_shutdown(self) -> None:
        self._stop_requested = True

    def _build_tools_declaration(self) -> list[Any] | None:
        """Translate Friday tool registry schemas into Gemini Live function declarations."""
        if not self.tool_registry:
            return None

        declarations = []
        try:
            schemas = self.tool_registry.all_schemas()
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            return None

        for schema in schemas:
            func = schema.get("function", schema)
            raw_name = func.get("name", "")
            # Gemini function names must be alphanumeric and underscore only
            safe_name = raw_name.replace(".", "_")
            desc = func.get("description", "")
            params = func.get("parameters") or {"type": "object", "properties": {}}

            declarations.append(
                types.FunctionDeclaration(
                    name=safe_name,
                    description=desc,
                    parameters_json_schema=params,
                )
            )

        if not declarations:
            return None
        return [types.Tool(function_declarations=declarations)]

    def _execute_local_tool(self, call_name: str, call_args: dict[str, Any]) -> Any:
        """Lookup and execute a tool from Friday's tool registry."""
        if not self.tool_registry:
            return {"error": "No tool registry available"}

        tool = self.tool_registry.get(call_name)
        if tool is None and "_" in call_name:
            dotted_name = call_name.replace("_", ".", 1)
            tool = self.tool_registry.get(dotted_name)
            if tool is None:
                dotted_name_full = call_name.replace("_", ".")
                tool = self.tool_registry.get(dotted_name_full)

        if tool is None:
            return {"error": f"Tool '{call_name}' not found."}

        try:
            print(f"FRIDAY [Live Tool]: Executing {call_name}({call_args})...")
            if "shutdown" in call_name:
                user_text_lower = (self._last_user_text or "").lower()
                shutdown_triggers = {
                    "shut down", "shutdown", "goodbye", "turn off", "power down",
                    "exit", "quit", "go to sleep", "sleep now", "bye friday", "bye",
                }
                if not any(trigger in user_text_lower for trigger in shutdown_triggers):
                    print(f"FRIDAY [Live Tool]: Intercepted hallucinated shutdown. User said '{self._last_user_text}', not a shutdown command.")
                    return {
                        "status": "cancelled",
                        "message": (
                            f"Shutdown cancelled: user did not request shutdown (user said: '{self._last_user_text}'). "
                            "Do not power down. Continue the conversation and respond to the user's actual statement."
                        ),
                    }
                self._shutdown_pending = True
            result = tool.run(**call_args)
            print(f"FRIDAY [Live Tool]: Result -> {result}")

            if self.episodic_memory is not None and hasattr(self.episodic_memory, "record_episode"):
                try:
                    import uuid
                    task_id = f"gemini_{uuid.uuid4().hex[:8]}"
                    goal = self._last_user_text or f"Execute {call_name}"
                    steps = [{"action": call_name, "arguments": call_args, "result": result}]
                    self.episodic_memory.record_episode(task_id, goal, steps, "SUCCESS", duration=0.1)
                except Exception:  # noqa: BLE001
                    pass

            return result
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
            print(f"FRIDAY [Live Tool]: Execution error: {exc}")
            return {"error": str(exc)}

    async def _live_conversation_loop(self) -> None:
        """Single live session loop over WebSockets until 10s silence or shutdown."""
        import sounddevice as sd

        self._interrupted.clear()
        self._user_spoke_in_turn.clear()

        tools = self._build_tools_declaration()

        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice_name)
            )
        )

        # Connect with AUDIO response modality (required by gemini-3.1-flash-live-preview)
        # and output_audio_transcription. Gemini's cloud audio chunks are discarded, and
        # the real-time transcription is synthesized into speech using Chatterbox Turbo.
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            speech_config=speech_config,
            system_instruction=types.Content(parts=[types.Part(text=self.effective_system_prompt)]),
            tools=tools,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

        audio_in_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=30)
        tts_queue: queue.Queue[tuple[str, str | None, float | None] | tuple[str, str | None] | str | None] = queue.Queue()
        audio_play_queue: queue.Queue[tuple[np.ndarray, int] | None] = queue.Queue(maxsize=10)
        loop = asyncio.get_running_loop()

        playback_active = threading.Event()
        playback_active.set()
        is_playing_audio = threading.Event()
        pending_count = [0]
        tts_lock = threading.Lock()

        def drain_tts_and_audio() -> None:
            """Discard all pending synthesis requests and queued audio buffers immediately."""
            with tts_lock:
                while not tts_queue.empty():
                    try:
                        tts_queue.get_nowait()
                    except queue.Empty:
                        break
                while not audio_play_queue.empty():
                    try:
                        audio_play_queue.get_nowait()
                    except queue.Empty:
                        break
                pending_count[0] = 0

        # Pipelined Stage 1: Synthesizes text to audio on GPU in the background
        def synth_worker():
            while playback_active.is_set():
                try:
                    queue_item = tts_queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                if queue_item is None:
                    audio_play_queue.put(None)
                    break

                if isinstance(queue_item, tuple):
                    if len(queue_item) >= 3:
                        sentence, emotion, intensity = queue_item[0], queue_item[1], queue_item[2]
                    else:
                        sentence, emotion = queue_item[0], queue_item[1]
                        intensity = None
                else:
                    sentence, emotion, intensity = queue_item, None, None

                if self._interrupted.is_set():
                    with tts_lock:
                        pending_count[0] = max(0, pending_count[0] - 1)
                    continue

                if not self.speech_synthesizer:
                    # Simulation in headless/test environments
                    time.sleep(min(1.0, max(0.1, len(sentence) * 0.03)))
                    with tts_lock:
                        pending_count[0] = max(0, pending_count[0] - 1)
                    continue

                try:
                    if self._interrupted.is_set():
                        with tts_lock:
                            pending_count[0] = max(0, pending_count[0] - 1)
                        continue
                    if hasattr(self.speech_synthesizer, "reset_interrupt"):
                        self.speech_synthesizer.reset_interrupt()

                    # Synthesize audio on GPU with continuous latent blending
                    try:
                        audio = self.speech_synthesizer._build_audio(sentence, emotion=emotion, blend_weight=intensity)
                    except TypeError:
                        if emotion is not None:
                            try:
                                audio = self.speech_synthesizer._build_audio(sentence, emotion=emotion)
                            except TypeError:
                                audio = self.speech_synthesizer._build_audio(sentence)
                        else:
                            audio = self.speech_synthesizer._build_audio(sentence)
                    sr = getattr(self.speech_synthesizer, "sample_rate", 24000)

                    if self._interrupted.is_set():
                        with tts_lock:
                            pending_count[0] = max(0, pending_count[0] - 1)
                        continue

                    if len(audio) > 0:
                        audio_play_queue.put((audio, sr))
                    else:
                        with tts_lock:
                            pending_count[0] = max(0, pending_count[0] - 1)
                except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as synth_err:
                    print(f"FRIDAY [Voice]: TTS synthesis error: {synth_err}")
                    with tts_lock:
                        pending_count[0] = max(0, pending_count[0] - 1)

        # Pipelined Stage 2: Continuously plays synthesized audio chunks with zero inter-sentence silence gap
        def playback_worker():
            while playback_active.is_set():
                try:
                    item = audio_play_queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                if item is None:
                    break

                audio, sr = item
                if self._interrupted.is_set():
                    with tts_lock:
                        pending_count[0] = max(0, pending_count[0] - 1)
                    continue

                try:
                    playback_started_at[0] = time.time()
                    is_playing_audio.set()
                    sd.play(audio, samplerate=sr)
                    sd.wait()
                except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as play_err:
                    print(f"FRIDAY [Voice]: TTS playback error: {play_err}")
                finally:
                    is_playing_audio.clear()
                    last_playback_ended_at[0] = time.time()
                    with tts_lock:
                        pending_count[0] = max(0, pending_count[0] - 1)

        synth_thread = threading.Thread(target=synth_worker, daemon=True)
        synth_thread.start()
        playback_thread = threading.Thread(target=playback_worker, daemon=True)
        playback_thread.start()

        session_closed_event = asyncio.Event()
        followup_deadline: list[float | None] = [None]
        initial_deadline: list[float | None] = [time.time() + 15.0]
        sentence_buffer = ""
        turn_in_progress = [False]
        playback_started_at = [0.0]
        last_playback_ended_at = [0.0]

        BARGE_IN_RMS_THRESHOLD = getattr(self, "barge_in_rms", 1200.0)
        BARGE_IN_GRACE_PERIOD_S = 0.25
        BARGE_IN_MIN_STREAK = max(2, int(getattr(self, "bargein_min_frames", 3)))

        def enqueue_audio_chunk(chunk: bytes) -> None:
            if audio_in_q.full():
                try:
                    audio_in_q.get_nowait()
                except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                    pass
            try:
                audio_in_q.put_nowait(chunk)
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                pass

        # Neural Silero VAD for intelligent voice activity detection & barge-in:
        # Detects real human vocal cords while completely ignoring keyboard typing,
        # mouse clicks, chair squeaks, and environmental room noise.
        silero_vad = None
        try:
            from friday.interaction.vad import SileroVoiceActivityDetector, VadEventKind
            silero_vad = SileroVoiceActivityDetector(
                model_path="data/silero_vad.onnx",
                speech_threshold=0.38,  # Sensitive to soft human speech while rejecting fan/typing noise
                speech_chunks_to_start=2,
            )
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            silero_vad = None

        vocal_streak = [0]
        speech_hangover = [0]
        # Pre-speech ring buffer (stores last 3 chunks ≈ 192ms)
        # Ensures initial soft consonants ('f', 's', 'th', 'p') are never cut off when speech starts
        pre_speech_ring: collections.deque[bytes] = collections.deque(maxlen=3)

        # Input audio callback (from microphone)
        def mic_callback(indata, frames, time_info, status):
            if status:
                pass
            chunk_bytes = indata.tobytes()
            raw_int16 = np.frombuffer(chunk_bytes, dtype=np.int16)
            audio_data = raw_int16.astype(np.float32)
            rms = float(np.sqrt(np.mean(np.square(audio_data))))
            now = time.time()

            is_active_playback = is_playing_audio.is_set()
            is_recent_tail = (now - last_playback_ended_at[0]) < 0.20

            # Run neural Silero VAD on microphone chunk
            is_human_speech = False
            vad_confidence = 0.0
            if silero_vad is not None:
                try:
                    vad_event = silero_vad.process(raw_int16, now)
                    is_human_speech = vad_event.kind in (VadEventKind.SPEECH_STARTED, VadEventKind.SPEECH_CONTINUED)
                    vad_confidence = getattr(vad_event, "confidence", 0.0)
                except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                    is_human_speech = rms >= 300.0
            else:
                is_human_speech = rms >= 300.0
                vad_confidence = 1.0 if is_human_speech else 0.0

            # 1. If Friday is physically outputting sound through speakers:
            if is_active_playback or is_recent_tail:
                is_barge_in = False
                in_grace_period = (now - playback_started_at[0]) < BARGE_IN_GRACE_PERIOD_S

                # Barge-in requires deliberate human speech louder than speaker bleed and outside grace period
                if not in_grace_period and rms >= BARGE_IN_RMS_THRESHOLD:
                    if silero_vad is not None:
                        if is_human_speech and vad_confidence >= getattr(self, "barge_in_vad_threshold", 0.65):
                            vocal_streak[0] += 1
                            if vocal_streak[0] >= BARGE_IN_MIN_STREAK:
                                is_barge_in = True
                        else:
                            vocal_streak[0] = max(0, vocal_streak[0] - 1)
                    else:
                        vocal_streak[0] += 1
                        if vocal_streak[0] >= BARGE_IN_MIN_STREAK:
                            is_barge_in = True
                else:
                    vocal_streak[0] = 0

                if is_barge_in:
                    vocal_streak[0] = 0
                    print("\n[FRIDAY: Barge-in detected, cutting off speech]")
                    self._interrupted.set()
                    sd.stop()
                    if self.speech_synthesizer and hasattr(self.speech_synthesizer, "cancel"):
                        self.speech_synthesizer.cancel()
                    drain_tts_and_audio()
                    is_playing_audio.clear()
                    self.set_state(SessionState.LISTENING)
                    # Forward user speech chunk to Gemini
                    loop.call_soon_threadsafe(enqueue_audio_chunk, chunk_bytes)
                    return
                else:
                    # Echo suppression: send silence chunk so Gemini cloud does not hear speaker bleed
                    silence_chunk = b"\x00" * len(chunk_bytes)
                    loop.call_soon_threadsafe(enqueue_audio_chunk, silence_chunk)
                    return
            else:
                # 2. Friday is NOT playing sound (idle, listening, or synthesizing in background)
                # If Friday is synthesizing/queued and user deliberately speaks loud & clear:
                # ONLY interrupt if Silero VAD confirms real human speech (never ambient room noise or fan hum!)
                if pending_count[0] > 0 or not tts_queue.empty() or not audio_play_queue.empty():
                    if is_human_speech and rms >= 800.0:
                        vocal_streak[0] += 1
                        if vocal_streak[0] >= 3:
                            vocal_streak[0] = 0
                            print("\n[FRIDAY: Interrupted before audio playback started]")
                            self._interrupted.set()
                            if self.speech_synthesizer and hasattr(self.speech_synthesizer, "cancel"):
                                self.speech_synthesizer.cancel()
                            drain_tts_and_audio()
                            is_playing_audio.clear()
                            self.set_state(SessionState.LISTENING)
                    else:
                        vocal_streak[0] = 0
                else:
                    vocal_streak[0] = 0

            # 3. Stream audio to Gemini Live using neural Silero VAD & pre-speech buffer:
            # - Real speech detected: flush pre-speech buffer (saving word starts) and stream audio
            # - Hangover (8 frames ≈ 512ms): smoothly bridges natural pauses between words
            # - Idle / Room noise: stream clean silence so fans and keyboard clicks do not trigger false turns
            if is_human_speech or rms >= 550.0:
                if speech_hangover[0] == 0:
                    while pre_speech_ring:
                        lead_chunk = pre_speech_ring.popleft()
                        loop.call_soon_threadsafe(enqueue_audio_chunk, lead_chunk)
                speech_hangover[0] = 8
                loop.call_soon_threadsafe(enqueue_audio_chunk, chunk_bytes)
                if followup_deadline[0] is not None:
                    followup_deadline[0] = max(followup_deadline[0], time.time() + 3.0)
            elif speech_hangover[0] > 0:
                speech_hangover[0] -= 1
                loop.call_soon_threadsafe(enqueue_audio_chunk, chunk_bytes)
            else:
                pre_speech_ring.append(chunk_bytes)
                silence_chunk = b"\x00" * len(chunk_bytes)
                loop.call_soon_threadsafe(enqueue_audio_chunk, silence_chunk)

        # Start microphone stream
        time.sleep(0.1)
        mic_stream = sd.InputStream(
            samplerate=SAMPLE_RATE_IN,
            channels=1,
            dtype="int16",
            blocksize=CHUNK_SIZE_IN,
            callback=mic_callback,
        )
        mic_stream.start()

        print(f"FRIDAY [Voice]: Connected to Gemini Live ({self.model}) with Chatterbox Turbo TTS. Listening...")
        self.set_state(SessionState.LISTENING)

        try:
            async with self.client.aio.live.connect(model=self.model, config=config) as session:

                # Sender Task: Streams microphone PCM to Gemini Live
                async def send_audio_task():
                    try:
                        while not session_closed_event.is_set() and not self._stop_requested:
                            try:
                                chunk = await asyncio.wait_for(audio_in_q.get(), timeout=0.1)
                                await session.send_realtime_input(
                                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                                )
                            except asyncio.TimeoutError:
                                continue
                    except asyncio.CancelledError:
                        pass
                    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                        pass

                # Receiver Task: Handles returned text, interruptions, and tool calls across all turns
                async def receive_task():
                    nonlocal sentence_buffer
                    try:
                        while not session_closed_event.is_set() and not self._stop_requested:
                            async for response in session.receive():
                                if session_closed_event.is_set() or self._stop_requested:
                                    break

                                # 1. Handle tool calls
                                if response.tool_call:
                                    turn_in_progress[0] = True
                                    followup_deadline[0] = None
                                    initial_deadline[0] = None
                                    self.set_state(SessionState.THINKING)
                                    tool_responses = []
                                    for fc in response.tool_call.function_calls:
                                        call_id = fc.id
                                        call_name = fc.name
                                        call_args = dict(fc.args) if fc.args else {}
                                        result = self._execute_local_tool(call_name, call_args)
                                        tool_responses.append(
                                            types.FunctionResponse(
                                                name=call_name,
                                                id=call_id,
                                                response={"result": result},
                                            )
                                        )
                                    if tool_responses:
                                        await session.send_tool_response(function_responses=tool_responses)
                                    continue

                                server_content = response.server_content
                                if not server_content:
                                    continue

                                # 2. Interruption signal (user spoke while Friday was speaking)
                                if getattr(server_content, "interrupted", False):
                                    turn_in_progress[0] = False
                                    self._interrupted.set()
                                    sd.stop()
                                    if self.speech_synthesizer and hasattr(self.speech_synthesizer, "cancel"):
                                        self.speech_synthesizer.cancel()
                                    drain_tts_and_audio()
                                    is_playing_audio.clear()
                                    sentence_buffer = ""
                                    print("\n[FRIDAY interrupted by Boss]")
                                    self.set_state(SessionState.LISTENING)
                                    followup_deadline[0] = None
                                    initial_deadline[0] = None
                                    continue

                                # 3. User speech transcript
                                if getattr(server_content, "input_transcription", None):
                                    text = server_content.input_transcription.text
                                    if text:
                                        self._last_user_text = text
                                        print(f"\n[Boss]: {text}")
                                        followup_deadline[0] = None
                                        initial_deadline[0] = None
                                        self.set_state(SessionState.LISTENING)

                                        # Turn-level language routing:
                                        # Decide engine immediately from Boss's transcribed speech!
                                        # English -> Chatterbox Turbo (Lune's voice)
                                        # Non-English (Indonesian, etc.) -> Gemini Voice
                                        if self.speech_synthesizer and hasattr(self.speech_synthesizer, "set_turn_language"):
                                            from friday.interaction.tts import detect_language
                                            user_lang = detect_language(text)
                                            self.speech_synthesizer.set_turn_language(user_lang)

                                        # If Friday was still physically playing audio from an earlier turn, cut speaker output
                                        if is_playing_audio.is_set():
                                            sd.stop()
                                            is_playing_audio.clear()
                                        if hasattr(self.speech_synthesizer, "reset_interrupt"):
                                            self.speech_synthesizer.reset_interrupt()

                                # 4. Model output transcription -> streamed into Chatterbox Turbo TTS
                                # Note: Gemini's inline audio chunks in model_turn.parts are intentionally
                                # NOT played, so Friday exclusively speaks using Chatterbox Turbo TTS.
                                transcription_text = ""
                                if getattr(server_content, "output_transcription", None):
                                    transcription_text = getattr(server_content.output_transcription, "text", "") or ""

                                # Fallback if text part is present in model_turn
                                if not transcription_text and getattr(server_content, "model_turn", None):
                                    for part in server_content.model_turn.parts:
                                        if getattr(part, "text", None):
                                            transcription_text += part.text

                                if transcription_text:
                                    turn_in_progress[0] = True
                                    self._interrupted.clear()
                                    if hasattr(self.speech_synthesizer, "reset_interrupt"):
                                        self.speech_synthesizer.reset_interrupt()
                                    followup_deadline[0] = None
                                    initial_deadline[0] = None
                                    if self.state != SessionState.SPEAKING:
                                        print("\n[FRIDAY]: ", end="", flush=True)
                                    self.set_state(SessionState.SPEAKING)

                                    print(transcription_text, end="", flush=True)
                                    sentence_buffer += transcription_text
                                    sentences = segment(sentence_buffer)
                                    if sentences:
                                        *ready, sentence_buffer = sentences
                                        for s in ready:
                                            tts_text = s
                                            emotion_key = None
                                            blend_weight = None
                                            if self.speech_director is not None:
                                                from friday.interaction.speech_director import SpeechContext
                                                ctx = SpeechContext(user_text=self._last_user_text)
                                                decision = self.speech_director.decide(s, ctx)
                                                emotion_key = self.speech_director.get_condition_key(decision)
                                                blend_weight = self.speech_director.get_blend_weight(decision) if hasattr(self.speech_director, "get_blend_weight") else getattr(decision, "intensity", None)
                                                tts_text = self.speech_director.render(s, ctx)
                                            with tts_lock:
                                                pending_count[0] += 1
                                            tts_queue.put((tts_text, emotion_key, blend_weight))

                                # 5. Turn Complete (Gemini finished emitting tokens for this turn)
                                if getattr(server_content, "turn_complete", False):
                                    print()
                                    turn_in_progress[0] = False
                                    leftover = sentence_buffer.strip()
                                    sentence_buffer = ""
                                    if leftover:
                                        tts_text = leftover
                                        emotion_key = None
                                        blend_weight = None
                                        if self.speech_director is not None:
                                            from friday.interaction.speech_director import SpeechContext
                                            ctx = SpeechContext(user_text=self._last_user_text)
                                            decision = self.speech_director.decide(leftover, ctx)
                                            emotion_key = self.speech_director.get_condition_key(decision)
                                            blend_weight = self.speech_director.get_blend_weight(decision) if hasattr(self.speech_director, "get_blend_weight") else getattr(decision, "intensity", None)
                                            tts_text = self.speech_director.render(leftover, ctx)
                                        with tts_lock:
                                            pending_count[0] += 1
                                        tts_queue.put((tts_text, emotion_key, blend_weight))

                                    if self._shutdown_pending:
                                        # Allow farewell speech to finish playing completely before closing session
                                        print("\nFRIDAY [Voice]: Completing farewell speech before shutdown...")
                                        wait_start = time.time()
                                        while (pending_count[0] > 0 or is_playing_audio.is_set()) and time.time() - wait_start < 15.0:
                                            await asyncio.sleep(0.1)
                                        self._stop_requested = True
                                        self.set_state(SessionState.IDLE)
                                        session_closed_event.set()
                                        break

                    except asyncio.CancelledError:
                        pass
                    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
                        if not session_closed_event.is_set() and not self._stop_requested:
                            if "1000" not in str(exc):
                                print(f"FRIDAY [Voice]: receive error: {exc}")
                        session_closed_event.set()

                # Timer Task: 10-second countdown strictly AFTER Friday finishes speaking
                async def countdown_timer_task():
                    was_speaking = False
                    try:
                        while not session_closed_event.is_set() and not self._stop_requested:
                            await asyncio.sleep(0.05)

                            is_speaking = is_playing_audio.is_set() or pending_count[0] > 0 or turn_in_progress[0]
                            if is_speaking:
                                was_speaking = True
                                followup_deadline[0] = None
                                initial_deadline[0] = None
                                continue

                            # Friday finished speaking all responses and audio playback completed
                            if was_speaking:
                                was_speaking = False
                                followup_deadline[0] = time.time() + self.followup_timeout
                                initial_deadline[0] = None
                                self.set_state(SessionState.FOLLOWUP_LISTENING)

                            # Check if the follow-up window expired
                            if followup_deadline[0] is not None:
                                if time.time() >= followup_deadline[0]:
                                    print(f"\nFRIDAY [Voice]: Follow-up window expired ({self.followup_timeout:.0f}s). Re-arming wake word...")
                                    self.set_state(SessionState.IDLE)
                                    session_closed_event.set()
                                    break

                            # Check if initial silence after wake word expired without any interaction
                            if initial_deadline[0] is not None:
                                if time.time() >= initial_deadline[0]:
                                    print("\nFRIDAY [Voice]: Initial silence timeout (15s). Re-arming wake word...")
                                    self.set_state(SessionState.IDLE)
                                    session_closed_event.set()
                                    break
                    except asyncio.CancelledError:
                        pass

                sender = asyncio.create_task(send_audio_task())
                receiver = asyncio.create_task(receive_task())
                timer = asyncio.create_task(countdown_timer_task())
                closed_waiter = asyncio.create_task(session_closed_event.wait())

                done, pending = await asyncio.wait(
                    [closed_waiter, receiver, timer],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                session_closed_event.set()
                for t in [sender, receiver, timer, closed_waiter]:
                    if not t.done():
                        t.cancel()
                await asyncio.gather(sender, receiver, timer, closed_waiter, return_exceptions=True)

        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
            print(f"FRIDAY [Voice]: Live session disconnected: {exc}")
        finally:
            if self._stop_requested:
                # Wait for any in-flight farewell speech to finish before cleaning up
                drain_start = time.time()
                while (is_playing_audio.is_set() or pending_count[0] > 0) and time.time() - drain_start < 8.0:
                    time.sleep(0.1)
            session_closed_event.set()
            playback_active.clear()
            tts_queue.put(None)
            audio_play_queue.put(None)
            if not self._stop_requested and self.speech_synthesizer and hasattr(self.speech_synthesizer, "cancel"):
                self.speech_synthesizer.cancel()
            try:
                mic_stream.stop()
                mic_stream.close()
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                pass

    def run_loop(self) -> None:
        """Main loop: listens for wake word, launches Live conversation, then returns to wake word on 10s silence."""
        import friday.tools.system as sys_tools

        print("FRIDAY [Voice]: Gemini Live Conversation loop starting.")

        while not self._stop_requested and not sys_tools.SHUTDOWN_REQUESTED:
            # 1. Listen for wake word
            self.set_state(SessionState.LISTENING_FOR_WAKE)
            print("\nFRIDAY [Voice]: Listening for wake word ('Friday')...")
            if self.wakeword_listener:
                detected = self.wakeword_listener.listen_for_wakeword()
                if not detected:
                    continue
            else:
                pass

            self.set_state(SessionState.WAKE_DETECTED)
            print("FRIDAY [Voice]: Wake word detected! Starting Gemini Live session...")

            # 2. Run Live Conversation until 10s inactivity or shutdown
            try:
                asyncio.run(self._live_conversation_loop())
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
                print(f"FRIDAY [Voice]: Live session error: {e}")

            if self._stop_requested or sys_tools.SHUTDOWN_REQUESTED:
                break

        self.set_state(SessionState.IDLE)
        print("FRIDAY [Voice]: Gemini Live session exited.")


__all__ = ["GeminiLiveSession"]
