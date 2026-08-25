"""
run_friday_v2.py

WHAT THIS IS FOR:
The new entry point that replaces test_voice.py's use of llm.Assistant with
the new friday_v2 AgentOrchestrator (config-driven models, policy engine,
typed tools, task state machine). Everything else - wake word, recording,
transcription, TTS, barge-in, the orb connection - is your existing,
working v1 code, untouched.

WHY THIS FILE EXISTS SEPARATELY FROM test_voice.py:
So you can A/B it against the old assistant without deleting anything.
Once you're happy with it, this can replace test_voice.py's role in
run_friday.py.

ORB STATES: unchanged from v1 (idle / listening / thinking / speaking).
No new IPC, no new port - state_server.py on 127.0.0.1:8765 keeps doing
exactly what it already does.
"""

import sys
import time
from pathlib import Path

# speech/, orb/, tools/, llm.py etc. live at the project root; friday_v2/
# is the new architecture. Both need to be importable from this script.
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "friday_v2"))

from orb.state_server import start_server_in_background, set_state
import tools.power

from speech.wakeword import WakeWordListener
from speech.microphone import record_until_silence, listen_for_followup
from speech.listen import SpeechRecognizer
from speech.speak import SpeechSynthesizer
from tools.timers import set_notify_callback

from main import build_orchestrator  # friday_v2/main.py


def reply_text_for_task(task) -> str:
    """Pull something speakable out of the task's final state.
    DONE stores the model's text (or a tool result) as the last history reason.
    FAILED/BLOCKED store why, which is also fine to say aloud for now."""
    if task.history:
        _, reason = task.history[-1]
        if reason:
            return reason
    return f"Task ended in state {task.state.value}."


def main():
    start_server_in_background()

    orch = build_orchestrator(str(PROJECT_ROOT / "friday_v2" / "config" / "default.yaml"))
    reasoning = orch.models.get("reasoning")
    if not reasoning.is_available():
        print("Ollama not reachable at localhost:11434 - start Ollama and pull the model first.")
        return

    wakeword = WakeWordListener()
    recognizer = SpeechRecognizer()
    synthesizer = SpeechSynthesizer()
    set_notify_callback(synthesizer.speak)

    FOLLOWUP_WINDOW_SECONDS = 5.0
    need_wakeword = True

    while True:
        set_state("idle")
        if need_wakeword:
            wakeword.listen_for_wakeword()
            set_state("listening")
            audio_path = record_until_silence()
        else:
            set_state("listening")
            audio_path = listen_for_followup(timeout_seconds=FOLLOWUP_WINDOW_SECONDS)
            if audio_path is None:
                need_wakeword = True
                continue

        text = recognizer.transcribe(audio_path)
        print(f"You said: {text}")

        set_state("thinking")
        task = orch.run(text)
        reply = reply_text_for_task(task)
        print(f"FRIDAY [{task.state.value}]: {reply}")

        set_state("speaking")
        synthesizer.speak_interruptible(reply, wakeword)

        if tools.power.SHUTDOWN_REQUESTED:
            break
        need_wakeword = False
        time.sleep(0.2)


if __name__ == "__main__":
    main()
