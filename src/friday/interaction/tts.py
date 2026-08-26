"""Text-to-speech module using Piper."""
from __future__ import annotations
import re
import time
import numpy as np
import sounddevice as sd
from typing import Any

def _strip_markdown(text: str) -> str:
    """Removes common markdown formatting for TTS reading."""
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    return text

class SpeechSynthesizer:
    """Synthesizes speech from text using Piper."""
    
    def __init__(self, model_path: str = "models/en_GB-jenny_dioco-medium.onnx"):
        from piper import PiperVoice
        self.voice = PiperVoice.load(model_path)
        
    def _build_audio(self, text: str) -> np.ndarray:
        text = _strip_markdown(text)
        audio_chunks = [np.frombuffer(c.audio_int16_bytes, dtype=np.int16) for c in self.voice.synthesize(text)]
        if not audio_chunks:
            return np.zeros(0, dtype=np.int16)
        audio = np.concatenate(audio_chunks)
        padding = np.zeros(int(0.15 * self.voice.config.sample_rate), dtype=np.int16)
        return np.concatenate([padding, audio])
        
    def speak(self, text: str) -> None:
        """Speak text synchronously."""
        audio = self._build_audio(text)
        if len(audio) == 0:
            return
        sd.play(audio, samplerate=self.voice.config.sample_rate)
        sd.wait()
        
    def speak_interruptible(self, text: str, wakeword_listener: Any, playback_gain: float = 0.6) -> bool:
        """Speak text allowing for wake word barge-in interruption."""
        audio = self._build_audio(text)
        if len(audio) == 0:
            return False
            
        audio = (audio.astype(np.float32) * playback_gain).astype(np.int16)
        duration = len(audio) / self.voice.config.sample_rate
        
        wakeword_listener.model.reset()
        
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
            sd.wait()
            
        return interrupted
