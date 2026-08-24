# speech/microphone.py
import numpy as np
import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 16000
CHUNK_DURATION = 0.1       # seconds analyzed per step
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)
SILENCE_THRESHOLD = 500    # RMS level below which audio counts as "quiet" — needs tuning
SILENCE_DURATION = 1.5     # seconds of continuous quiet before stopping
MAX_DURATION = 15          # hard cap so a stuck mic can't record forever


def record_until_silence(path: str = "audio.wav") -> str:
    print("Recording... (speak now)")
    frames = []
    silence_chunks = 0
    silence_chunks_needed = int(SILENCE_DURATION / CHUNK_DURATION)
    max_chunks = int(MAX_DURATION / CHUNK_DURATION)
    speech_started = False

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        for _ in range(max_chunks):
            chunk, _ = stream.read(CHUNK_SIZE)
            frames.append(chunk)

            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))

            if rms >= SILENCE_THRESHOLD:
                speech_started = True
                silence_chunks = 0
            elif speech_started:
                silence_chunks += 1
                if silence_chunks >= silence_chunks_needed:
                    break

    audio = np.concatenate(frames)
    sf.write(path, audio, SAMPLE_RATE)
    print("Done recording.")
    return path

def listen_for_followup(path: str = "audio.wav", timeout_seconds: float = 5.0) -> str | None:
    """Listen for speech starting within timeout_seconds. If speech begins,
    record until natural silence (same as record_until_silence) and return
    the file path. If nothing is said in time, return None."""
    print(f"Listening for a follow-up ({timeout_seconds:.0f}s)...")
    frames = []
    silence_chunks = 0
    silence_chunks_needed = int(SILENCE_DURATION / CHUNK_DURATION)
    max_chunks = int(MAX_DURATION / CHUNK_DURATION)
    timeout_chunks = int(timeout_seconds / CHUNK_DURATION)
    speech_started = False
    chunks_waited = 0

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        for _ in range(max_chunks):
            chunk, _ = stream.read(CHUNK_SIZE)
            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))

            if not speech_started:
                chunks_waited += 1
                if chunks_waited > timeout_chunks:
                    return None  # nobody spoke in time
                if rms < SILENCE_THRESHOLD:
                    continue  # still waiting for speech to actually begin

            frames.append(chunk)

            if rms >= SILENCE_THRESHOLD:
                speech_started = True
                silence_chunks = 0
            elif speech_started:
                silence_chunks += 1
                if silence_chunks >= silence_chunks_needed:
                    break

    if not speech_started:
        return None

    audio = np.concatenate(frames)
    sf.write(path, audio, SAMPLE_RATE)
    print("Done recording.")
    return path