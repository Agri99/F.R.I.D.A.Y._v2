from faster_whisper import WhisperModel


class SpeechRecognizer:
    def __init__(self, model_size: str = "small"):
        self.model = WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
    )

    # def transcribe(self, audio_file: str) -> str:
    #     segments, _ = self.model.transcribe(audio_file)
    #     return " ".join(segment.text for segment in segments).strip()

    def transcribe(self, audio_file: str) -> str:
        segments, _ = self.model.transcribe(audio_file, language="en")
        return " ".join(segment.text for segment in segments).strip()