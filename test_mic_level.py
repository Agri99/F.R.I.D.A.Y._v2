"""Test mic audio levels."""
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
FRAME_SIZE = 1280

print("Say 'FRIDAY' loudly...")
with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16', blocksize=FRAME_SIZE) as stream:
    for i in range(50):
        audio_frame, overflowed = stream.read(FRAME_SIZE)
        if overflowed:
            continue
        audio_frame = audio_frame.flatten()
        rms = np.sqrt(np.mean(audio_frame.astype(np.float32) ** 2))
        peak = np.max(np.abs(audio_frame))
        print(f"Frame {i}: RMS={rms:.1f} Peak={peak}")