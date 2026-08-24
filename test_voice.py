from orb.state_server import start_server_in_background, set_state
import tools.power

start_server_in_background()

import time
from speech.wakeword import WakeWordListener
from speech.microphone import record_until_silence, listen_for_followup
from speech.listen import SpeechRecognizer
from speech.speak import SpeechSynthesizer
from llm import Assistant
from tools.timers import set_notify_callback

wakeword = WakeWordListener()
recognizer = SpeechRecognizer()
synthesizer = SpeechSynthesizer()
assistant = Assistant(on_notice=synthesizer.speak)
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

    reply = assistant.ask(text, audio_path=audio_path)
    print(f"FRIDAY: {reply}")

    synthesizer.speak_interruptible(reply, wakeword)
    if tools.power.SHUTDOWN_REQUESTED:
        break
    need_wakeword = False
    time.sleep(0.2)