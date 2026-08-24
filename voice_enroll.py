# voice_enroll.py
from speechbrain.inference.speaker import SpeakerRecognition
from speechbrain.utils.fetching import LocalStrategy
from speech.microphone import record_until_silence

verification = SpeakerRecognition.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="models/spkrec-ecapa-voxceleb",
    local_strategy=LocalStrategy.COPY_SKIP_CACHE,
)

print("We'll record 3 samples. Speak a full sentence each time.")
for i in range(3):
    input(f"Press ENTER, then speak sample {i + 1}/3...")
    record_until_silence(path=f"voice_ref_{i}.wav")

print("Done — voice_ref_0.wav, voice_ref_1.wav, voice_ref_2.wav saved.")