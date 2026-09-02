"""Debug wake word detection with real mic input."""
import numpy as np
import sounddevice as sd
from openwakeword.model import Model

SAMPLE_RATE = 16000
FRAME_SIZE = 1280

model = Model(wakeword_models=['models/friday.onnx'])

print("Say 'FRIDAY' loudly...")
with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16', blocksize=FRAME_SIZE) as stream:
    for i in range(100):  # 100 frames ~ 8 seconds
        audio_frame, overflowed = stream.read(FRAME_SIZE)
        if overflowed:
            continue
        audio_frame = audio_frame.flatten()
        prediction = model.predict(audio_frame)
        score = prediction.get('friday', 0.0)
        if score > 0.1:
            print(f"Frame {i}: score={score:.3f} ***")
        else:
            print(f"Frame {i}: score={score:.3f}")
        if score > 0.5:
            print("WAKE WORD DETECTED!")
            break