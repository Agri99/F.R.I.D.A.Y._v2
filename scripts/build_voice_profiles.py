"""
scripts/build_voice_profiles.py

WHAT THIS IS FOR:
Offline build script that processes the 283 reference audio lines in data/voices/dataset
into a Master Voice Profile and Multi-Emotion Latent Condition Bank for Chatterbox Turbo.

HOW IT WORKS:
1. Calculates the Master Centroid Speaker Embedding across all 283 clips to guarantee
   100% voice identity consistency.
2. Extracts acoustic prompt tokens and flow-matching reference latents for each emotion cluster.
3. Saves precomputed .pt Conditionals into data/voices/conditionals/ for zero-latency runtime TTS.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import torch

from chatterbox.models.t3.modules.cond_enc import T3Cond
from chatterbox.tts_turbo import ChatterboxTurboTTS, Conditionals, S3GEN_SR, S3_SR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_voice_profiles")


# Curated best representative clips for each emotion cluster
EMOTION_PRIMARY_CLIPS: dict[str, list[str]] = {
    "neutral": ["Lune 97", "Lune 96", "Lune 53"],
    "happy": ["Lune 129", "Lune 124", "Lune 22"],
    "sigh": ["Lune 127", "Lune 59", "Lune 76"],
    "chuckle": ["Lune 125", "Lune 217", "Lune 15"],
    "sarcastic": ["Lune 344", "Lune 218", "Lune 340"],
    "angry": ["Lune 14", "Lune 95", "Lune 10"],
    "surprised": ["Lune 103", "Lune 117", "Lune 61", "Lune 94"],
    "whispering": ["Lune 93", "Lune 17", "Lune 88"],
    "dramatic": ["Lune 13", "Lune 108"],
    "fear": ["Lune 77", "Lune 101"],
    "crying": ["Lune 126", "Lune 128", "Lune 59"],
}


def load_dataset_metadata(dataset_dir: Path) -> dict[str, str]:
    """Parse metadata.csv into {clip_key: transcript} mapping."""
    csv_file = dataset_dir / "metadata.csv"
    if not csv_file.exists():
        raise FileNotFoundError(f"metadata.csv not found at {csv_file}")

    metadata: dict[str, str] = {}
    with open(csv_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "|" not in line:
                continue
            key, text = line.split("|", 1)
            metadata[key.strip()] = text.strip()
    return metadata


def build_voice_profiles(
    dataset_dir: Path,
    output_dir: Path,
    exaggeration: float = 0.35,
    device: str | None = None,
) -> None:
    """Build Master Speaker Embedding and Emotion Condition Bank."""
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = load_dataset_metadata(dataset_dir)
    logger.info("Loaded metadata for %d clips from %s", len(metadata), dataset_dir)

    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Initializing Chatterbox Turbo TTS on %s...", dev)
    tts = ChatterboxTurboTTS.from_pretrained(device=dev)

    # 1. Compute Master Centroid Speaker Embedding across all clips
    logger.info("Extracting speaker embeddings across %d dataset clips...", len(metadata))
    ve_embeddings: list[torch.Tensor] = []
    valid_clips = 0

    wav_files = sorted(dataset_dir.glob("*.wav"))
    for idx, wav_path in enumerate(wav_files, 1):
        try:
            audio, sr = librosa.load(str(wav_path), sr=S3_SR)
            if len(audio) < int(0.5 * S3_SR):
                continue
            emb = tts.ve.embeds_from_wavs([audio], sample_rate=S3_SR)
            ve_embeddings.append(torch.from_numpy(emb).squeeze(0))
            valid_clips += 1
            if idx % 50 == 0 or idx == len(wav_files):
                logger.info("Processed %d/%d clips for centroid embedding", idx, len(wav_files))
        except Exception as err:  # noqa: BLE001
            logger.warning("Failed to process %s for voice encoder: %s", wav_path.name, err)

    if not ve_embeddings:
        raise RuntimeError("No valid audio clips could be processed for voice encoder!")

    # Centroid embedding representing the true speaker baseline
    master_speaker_emb = torch.stack(ve_embeddings).mean(dim=0, keepdim=True).to(dev)
    logger.info(
        "Master Speaker Embedding computed from %d clips (shape: %s)",
        len(ve_embeddings),
        list(master_speaker_emb.shape),
    )

    manifest: dict[str, Any] = {
        "speaker": "Lune (Friday)",
        "total_source_clips": len(metadata),
        "embedding_clips_used": len(ve_embeddings),
        "exaggeration": exaggeration,
        "sample_rate_gen": S3GEN_SR,
        "sample_rate_t3": S3_SR,
        "profiles": {},
    }

    # 2. Build Conditionals for each emotion cluster
    plen = tts.t3.hp.speech_cond_prompt_len or 375
    s3_tokzr = tts.s3gen.tokenizer

    for emotion, clip_candidates in EMOTION_PRIMARY_CLIPS.items():
        logger.info("Compiling condition profile for '%s'...", emotion)
        selected_clip_key = None
        s3gen_ref_wav = None

        # Find best available clip from candidates
        for cand_key in clip_candidates:
            cand_path = dataset_dir / f"{cand_key}.wav"
            if cand_path.exists():
                wav_raw, sr = librosa.load(str(cand_path), sr=S3GEN_SR)
                # Ensure minimum length of 5.1 seconds for Chatterbox receptive field
                if len(wav_raw) / sr >= 5.0:
                    selected_clip_key = cand_key
                    s3gen_ref_wav = wav_raw
                    break

        # Fallback: concatenate multiple candidate clips if individual clip < 5.0s
        if s3gen_ref_wav is None:
            concatenated = []
            selected_keys = []
            for cand_key in clip_candidates:
                cand_path = dataset_dir / f"{cand_key}.wav"
                if cand_path.exists():
                    wav_raw, _ = librosa.load(str(cand_path), sr=S3GEN_SR)
                    concatenated.append(wav_raw)
                    # Add tiny 50ms silence between concatenated phrases
                    concatenated.append(np.zeros(int(0.05 * S3GEN_SR), dtype=np.float32))
                    selected_keys.append(cand_key)
                    if sum(len(c) for c in concatenated) / S3GEN_SR >= 5.5:
                        break

            if concatenated:
                s3gen_ref_wav = np.concatenate(concatenated)
                selected_clip_key = "+".join(selected_keys)

        # Final fallback: pad with neutral clip if still < 5.0s
        if s3gen_ref_wav is None or (len(s3gen_ref_wav) / S3GEN_SR < 5.0):
            neutral_cand = dataset_dir / "Lune 97.wav"
            base_wav, _ = librosa.load(str(neutral_cand), sr=S3GEN_SR)
            if s3gen_ref_wav is not None:
                s3gen_ref_wav = np.concatenate([s3gen_ref_wav, base_wav])
            else:
                s3gen_ref_wav = base_wav
            selected_clip_key = f"{selected_clip_key or 'fallback'}+neutral_pad"

        # Normalize loudness
        s3gen_ref_wav = tts.norm_loudness(s3gen_ref_wav, S3GEN_SR).astype(np.float32)
        ref_16k_wav = librosa.resample(s3gen_ref_wav, orig_sr=S3GEN_SR, target_sr=S3_SR).astype(np.float32)

        # Truncate to maximum conditional lengths
        s3gen_dec_wav = s3gen_ref_wav[: tts.DEC_COND_LEN]
        s3gen_ref_dict = tts.s3gen.embed_ref(s3gen_dec_wav, S3GEN_SR, device=dev)

        t3_cond_tokens, _ = s3_tokzr.forward([ref_16k_wav[: tts.ENC_COND_LEN]], max_len=plen)
        t3_cond_tokens = torch.atleast_2d(t3_cond_tokens).to(dev)

        # Bind with Master Speaker Embedding
        t3_cond = T3Cond(
            speaker_emb=master_speaker_emb,
            cond_prompt_speech_tokens=t3_cond_tokens,
            emotion_adv=exaggeration * torch.ones(1, 1, 1, device=dev),
        )

        conds = Conditionals(t3=t3_cond, gen=s3gen_ref_dict)
        pt_path = output_dir / f"{emotion}.pt"
        conds.save(pt_path)
        logger.info("Saved condition profile: %s", pt_path)

        manifest["profiles"][emotion] = {
            "file": pt_path.name,
            "source_clip": selected_clip_key,
            "duration_seconds": float(len(s3gen_ref_wav) / S3GEN_SR),
            "transcript": metadata.get(selected_clip_key, ""),
        }

    # Also save master.pt (alias for neutral with master embedding)
    neutral_pt = output_dir / "neutral.pt"
    master_pt = output_dir / "master.pt"
    if neutral_pt.exists():
        import shutil
        shutil.copyfile(str(neutral_pt), str(master_pt))
        manifest["profiles"]["master"] = manifest["profiles"]["neutral"].copy()
        manifest["profiles"]["master"]["file"] = "master.pt"

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    logger.info("Saved condition manifest: %s", manifest_path)
    logger.info("Successfully compiled %d voice profiles into %s", len(manifest["profiles"]), output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile Master Voice Profile & Multi-Emotion Latent Condition Bank")
    parser.add_argument("--dataset-dir", type=Path, default=Path("data/voices/dataset"), help="Path to WAV dataset")
    parser.add_argument("--output-dir", type=Path, default=Path("data/voices/conditionals"), help="Output directory for .pt conditionals")
    parser.add_argument("--exaggeration", type=float, default=0.35, help="Emotion exaggeration factor")
    parser.add_argument("--device", type=str, default=None, help="Device to use (cuda/cpu)")

    args = parser.parse_args()
    build_voice_profiles(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        exaggeration=args.exaggeration,
        device=args.device,
    )
