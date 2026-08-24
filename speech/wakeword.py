from openwakeword.model import Model
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
FRAME_SIZE = 1280  # 80ms at 16kHz, openWakeWord's expected chunk size


class WakeWordListener:
    def __init__(self, model_path: str = "models/friday.onnx", threshold: float = 0.5):
        self.model = Model(wakeword_models=[model_path])
        self.threshold = threshold
        self.wakeword_name = "friday"  # matches the key openWakeWord returns

    def check_frame(self, stream, debug: bool = False) -> bool:
        """Read one frame from an already-open InputStream and check for the wake word."""
        audio_frame, overflowed = stream.read(FRAME_SIZE)
        if overflowed:
            return False  # discard a frame we know may be corrupted, rather than risk a bad read
        
        audio_frame = audio_frame.flatten()
        prediction = self.model.predict(audio_frame)
        score = prediction.get(self.wakeword_name, 0.0)

        if debug:
            print(f"[debug] wakeword score: {score:.3f} (threshold: {self.threshold})")

        return score > self.threshold

    def listen_for_wakeword(self) -> None:
        """Blocks until the wake word is detected, then returns."""
        print("Listening for wake word...")

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME_SIZE) as stream:
            warmup_frames = 5
            frame_count = 0

            while True:
                frame_count += 1
                if frame_count <= warmup_frames:
                    stream.read(FRAME_SIZE)
                    continue

                if self.check_frame(stream):
                    print("Wake word detected!")
                    return