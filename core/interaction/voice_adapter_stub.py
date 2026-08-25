"""
core/interaction/voice_adapter_stub.py

WHAT THIS IS FOR:
This is where your EXISTING v1 voice loop plugs in as Process B.
It is a STUB — the wake-word / Whisper / Piper calls below are
placeholders for the real functions from your v1 project. Copy
this file into your v1 voice code's repo (or vice versa), and
replace the three marked functions with your real implementations.

WHAT IT DOES:
Runs as its own process. Loop: wait for wake word -> record -> STT ->
send recognized text (TEXT ONLY, per Section 23) to Core over the
/voice WebSocket channel -> get task result back -> TTS the reply.

Core never sees a raw audio stream and never controls the mic - this
process owns that entirely, exactly like your v1 architecture already
does. You are not rewriting your voice pipeline, just changing what
it hands its output to (a WebSocket call instead of an in-process
function call).
"""

from __future__ import annotations

import asyncio
import json
import uuid

import websockets

CORE_VOICE_URL = "ws://localhost:8765/voice"


# --- REPLACE THESE THREE WITH YOUR REAL v1 IMPLEMENTATIONS -----------------

def wait_for_wake_word() -> dict:
    """Blocks until openWakeWord fires. Return whatever metadata you already capture."""
    raise NotImplementedError("plug in your v1 openWakeWord loop here")


def record_and_transcribe() -> str:
    """Record until silence, run faster-whisper, return the text."""
    raise NotImplementedError("plug in your v1 faster-whisper call here")


def speak(text: str) -> None:
    """Run Piper TTS on `text` and play it, with your existing barge-in handling."""
    raise NotImplementedError("plug in your v1 Piper call here")

# -----------------------------------------------------------------------------


async def voice_loop(session_id: str | None = None) -> None:
    session_id = session_id or str(uuid.uuid4())[:8]
    async with websockets.connect(CORE_VOICE_URL) as ws:
        while True:
            wake_meta = wait_for_wake_word()
            recognized_text = record_and_transcribe()

            await ws.send(json.dumps({
                "recognized_text": recognized_text,
                "session_id": session_id,
                "wake_word_meta": wake_meta,
                # audio_path_for_authorization only needed when a RED-tier
                # action requires voiceprint + passphrase second factor
            }))

            reply_raw = await ws.recv()
            result = json.loads(reply_raw)
            # result["history"] holds the full state trail if you want to
            # speak intermediate states ("thinking...") later; v1 parity
            # just speaks the final outcome for now.
            speak(f"Task ended in state {result['state']}")


if __name__ == "__main__":
    asyncio.run(voice_loop())
