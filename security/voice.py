import soundfile as sf
import torch
from pathlib import Path
from speechbrain.inference.speaker import SpeakerRecognition
from speechbrain.utils.fetching import LocalStrategy

_verification = SpeakerRecognition.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="models/spkrec-ecapa-voxceleb",
    local_strategy=LocalStrategy.COPY_SKIP_CACHE,
)


def _load_waveform(path: str) -> torch.Tensor:
    audio, _ = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return torch.from_numpy(audio).unsqueeze(0)


def _build_reference_embedding() -> torch.Tensor:
    ref_files = sorted(Path(".").glob("voice_ref_*.wav")) or [Path("voice_reference.wav")]
    embeddings = [_verification.encode_batch(_load_waveform(str(f))) for f in ref_files]
    return torch.stack(embeddings).mean(dim=0)


_reference_embedding = _build_reference_embedding()


def get_duration_seconds(path: str) -> float:
    info = sf.info(path)
    return info.frames / info.samplerate


def is_authorized_voice(audio_path: str, threshold: float = 0.30) -> bool:
    emb_test = _verification.encode_batch(_load_waveform(audio_path))
    score = torch.nn.functional.cosine_similarity(
        _reference_embedding.squeeze(1), emb_test.squeeze(1)
    )
    return score.item() >= threshold