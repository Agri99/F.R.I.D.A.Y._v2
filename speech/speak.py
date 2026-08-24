from piper import PiperVoice
import sounddevice as sd
import numpy as np
import re
import time

def _strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)             # **bold**
    text = re.sub(r'\*(.*?)\*', r'\1', text)                 # *italic*
    text = re.sub(r'`(.*?)`', r'\1', text)                   # `code`
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)   # # headers
    text = re.sub(r'^[-*]\s+', '', text, flags=re.MULTILINE) # - bullets
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE) # 1. numbered lists
    return text

class SpeechSynthesizer:
    def __init__(self, model_path: str = "models/en_GB-jenny_dioco-medium.onnx"):
        self.voice = PiperVoice.load(model_path)

    def _build_audio(self, text: str) -> np.ndarray:
        text = _strip_markdown(text)
        audio_chunks = [np.frombuffer(c.audio_int16_bytes, dtype=np.int16) for c in self.voice.synthesize(text)]
        audio = np.concatenate(audio_chunks)
        padding = np.zeros(int(0.15 * self.voice.config.sample_rate), dtype=np.int16)
        return np.concatenate([padding, audio])

    def speak(self, text: str) -> None:
        audio = self._build_audio(text)
        sd.play(audio, samplerate=self.voice.config.sample_rate)
        sd.wait()

    def speak_interruptible(self, text: str, wakeword_listener, playback_gain: float = 0.6) -> bool:
        audio = self._build_audio(text)
        audio = (audio.astype(np.float32) * playback_gain).astype(np.int16)
        duration = len(audio) / self.voice.config.sample_rate

        wakeword_listener.model.reset()  # clear stale scoring buffer from the last real detection

        sd.play(audio, samplerate=self.voice.config.sample_rate)
        start_time = time.time()
        interrupted = False

        with sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=1280) as stream:
            warmup_frames = 5
            frame_count = 0

            while time.time() - start_time < duration:
                frame_count += 1
                if frame_count <= warmup_frames:
                    stream.read(1280)
                    continue

                if wakeword_listener.check_frame(stream, debug=True):
                    sd.stop()
                    interrupted = True
                    break

        if not interrupted:
            sd.wait()  # confirm playback actually finished, not just that estimated time elapsed

        return interrupted