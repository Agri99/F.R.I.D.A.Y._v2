"""
scripts/phase6_voice_calibration.py

WHAT THIS IS FOR:
Reproducible calibration CLI for Phase 6 Speech Director & Chatterbox Turbo.
Generates controlled, deterministic audio samples for perceptual expression evaluation.

Usage:
    # Single sample generation
    python scripts/phase6_voice_calibration.py --expression happy --text-id H01 --blend-weight 0.65 --seed 1

    # Screening pass across all categories
    python scripts/phase6_voice_calibration.py --screening

    # Blend weight sweep for a specific expression
    python scripts/phase6_voice_calibration.py --expression dramatic --sweep

    # Stability pass (3 seeds) for an expression
    python scripts/phase6_voice_calibration.py --expression whispering --stability --blend-weight 0.70
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
from pathlib import Path
import subprocess
from typing import Any

import numpy as np
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phase6_voice_calibration")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROMPTS_PATH = PROJECT_ROOT / "data" / "phase6_calibration" / "prompts.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "phase6_calibration" / "raw"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "data" / "phase6_calibration" / "manifests" / "manifest.jsonl"

EXPRESSIONS_LIST = [
    "neutral",
    "happy",
    "dramatic",
    "whispering",
    "laugh",
    "chuckle",
    "sigh",
    "gasp",
    "sarcastic",
    "angry",
    "crying",
    "fear",
    "surprised",
]


def get_git_commit() -> str:
    """Retrieve current Git commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def load_prompts(prompts_file: Path) -> dict[str, list[dict[str, str]]]:
    """Load calibration prompts from YAML."""
    if not prompts_file.exists():
        raise FileNotFoundError(f"Prompts file not found: {prompts_file}")
    with open(prompts_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def resolve_condition_profile(expression: str) -> str:
    """Map calibration expression name to acoustic condition profile key."""
    canonical_map = {
        "neutral": "neutral",
        "happy": "happy",
        "dramatic": "dramatic",
        "whispering": "whispering",
        "laugh": "chuckle",
        "chuckle": "chuckle",
        "sigh": "sigh",
        "gasp": "surprised",
        "sarcastic": "sarcastic",
        "angry": "angry",
        "crying": "crying",
        "fear": "fear",
        "surprised": "surprised",
        "master": "master",
    }
    return canonical_map.get(expression.lower().strip(), "neutral")


def generate_sample(
    synth: Any,
    expression: str,
    text_id: str,
    text: str,
    blend_weight: float,
    seed: int,
    output_dir: Path,
    manifest_file: Path,
    git_commit: str,
    dry_run: bool = False,
) -> Path:
    """Generate a single calibration sample and record manifest metadata."""
    import torch

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)

    filename = f"{expression}__{text_id}__w{blend_weight:.2f}__s{seed:03d}.wav"
    output_path = output_dir / filename
    resolved_cond = resolve_condition_profile(expression)

    # Set seeds for deterministic synthesis
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)

    sample_rate = getattr(synth, "sample_rate", 24000)

    if dry_run:
        logger.info("[DRY RUN] Would generate: %s (cond=%s, w=%.2f, seed=%d)", filename, resolved_cond, blend_weight, seed)
    else:
        logger.info("Generating: %s (text=\"%s\")", filename, text[:40])
        # Inject tag if applicable to test tag tokenization along with condition profile
        synth_text = f"[{expression}] {text}" if expression not in ("neutral", "master") else text
        res = synth.speak(
            synth_text,
            save_path=output_path,
            play_audio=False,
            emotion=resolved_cond,
            blend_weight=blend_weight,
        )
        if not res.success:
            logger.error("Synthesis failed for %s: %s", filename, res.error)
            raise RuntimeError(f"Synthesis failed for {filename}: {res.error}")

    # Append to manifest
    manifest_entry = {
        "expression": expression,
        "text_id": text_id,
        "source_text": text,
        "requested_tag": expression,
        "resolved_condition": resolved_cond,
        "blend_weight": blend_weight,
        "seed": seed,
        "sample_rate": sample_rate,
        "output_path": str(output_path.relative_to(PROJECT_ROOT) if output_path.is_relative_to(PROJECT_ROOT) else output_path),
        "generation_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model_backend": "ChatterboxTurboTTS",
        "git_commit": git_commit,
    }

    with open(manifest_file, "a", encoding="utf-8") as mf:
        mf.write(json.dumps(manifest_entry) + "\n")

    return output_path


def run_screening(
    synth: Any,
    prompts: dict[str, list[dict[str, str]]],
    output_dir: Path,
    manifest_file: Path,
    git_commit: str,
    dry_run: bool = False,
) -> list[Path]:
    """Execute screening pass: 2 representative sentences per expression, 1 seed, w=0.65."""
    screening_dir = output_dir / "screening"
    generated: list[Path] = []
    default_weight = 0.65
    default_seed = 1

    for expr in EXPRESSIONS_LIST:
        category_prompts = prompts.get(expr) or prompts.get(
            {
                "laugh": "playful",
                "chuckle": "playful",
                "gasp": "surprise",
                "surprised": "surprise",
                "sigh": "empathy",
                "fear": "dramatic",
                "angry": "angry",
                "crying": "crying",
            }.get(expr, "neutral"),
            [],
        )
        if not category_prompts:
            category_prompts = [{"id": f"{expr[:1].upper()}01", "text": "Testing calibration delivery."}]

        for item in category_prompts[:2]:
            p = generate_sample(
                synth=synth,
                expression=expr,
                text_id=item["id"],
                text=item["text"],
                blend_weight=default_weight,
                seed=default_seed,
                output_dir=screening_dir,
                manifest_file=manifest_file,
                git_commit=git_commit,
                dry_run=dry_run,
            )
            generated.append(p)
    return generated


def run_sweep(
    synth: Any,
    expression: str,
    prompts: dict[str, list[dict[str, str]]],
    output_dir: Path,
    manifest_file: Path,
    git_commit: str,
    dry_run: bool = False,
) -> list[Path]:
    """Execute blend weight sweep: [0.35, 0.50, 0.65, 0.80] for expression."""
    sweep_dir = output_dir / "sweeps" / expression
    weights = [0.35, 0.50, 0.65, 0.80]
    seed = 1

    category_prompts = prompts.get(expression) or prompts.get(
        {"laugh": "playful", "chuckle": "playful", "gasp": "surprise"}.get(expression, "neutral"),
        [],
    )
    prompt = category_prompts[0] if category_prompts else {"id": f"{expression[:1].upper()}01", "text": "Testing blend weights."}

    generated: list[Path] = []
    for w in weights:
        p = generate_sample(
            synth=synth,
            expression=expression,
            text_id=prompt["id"],
            text=prompt["text"],
            blend_weight=w,
            seed=seed,
            output_dir=sweep_dir,
            manifest_file=manifest_file,
            git_commit=git_commit,
            dry_run=dry_run,
        )
        generated.append(p)
    return generated


def run_stability(
    synth: Any,
    expression: str,
    blend_weight: float,
    prompts: dict[str, list[dict[str, str]]],
    output_dir: Path,
    manifest_file: Path,
    git_commit: str,
    dry_run: bool = False,
) -> list[Path]:
    """Execute stability pass: 3 seeds [1, 2, 3] at specified blend weight."""
    stab_dir = output_dir / "stability" / expression
    seeds = [1, 2, 3]

    category_prompts = prompts.get(expression) or prompts.get(
        {"laugh": "playful", "chuckle": "playful", "gasp": "surprise"}.get(expression, "neutral"),
        [],
    )
    prompt = category_prompts[0] if category_prompts else {"id": f"{expression[:1].upper()}01", "text": "Testing stability."}

    generated: list[Path] = []
    for s in seeds:
        p = generate_sample(
            synth=synth,
            expression=expression,
            text_id=prompt["id"],
            text=prompt["text"],
            blend_weight=blend_weight,
            seed=s,
            output_dir=stab_dir,
            manifest_file=manifest_file,
            git_commit=git_commit,
            dry_run=dry_run,
        )
        generated.append(p)
    return generated


def main() -> None:
    parser = argparse.ArgumentParser(description="FRIDAY v2 Phase 6 Voice Calibration Tool")
    parser.add_argument("--expression", type=str, default="neutral", help="Expression name to calibrate")
    parser.add_argument("--text-id", type=str, default=None, help="Prompt text ID from prompts.yaml")
    parser.add_argument("--blend-weight", type=float, default=0.65, help="Latent blend weight (0.0 to 1.0)")
    parser.add_argument("--seed", type=int, default=1, help="Random seed for synthesis")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory for generated WAVs")
    parser.add_argument("--prompts-file", type=Path, default=DEFAULT_PROMPTS_PATH, help="Path to prompts.yaml")
    parser.add_argument("--manifest-file", type=Path, default=DEFAULT_MANIFEST_PATH, help="Path to manifest JSONL")
    parser.add_argument("--screening", action="store_true", help="Run screening pass across all expressions")
    parser.add_argument("--sweep", action="store_true", help="Run blend weight sweep for expression")
    parser.add_argument("--stability", action="store_true", help="Run 3-seed stability pass for expression")
    parser.add_argument("--all", action="store_true", help="Run full calibration matrix")
    parser.add_argument("--device", type=str, default=None, help="Inference device (cuda/cpu)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate generation without executing neural model")

    args = parser.parse_args()

    git_commit = get_git_commit()
    logger.info("FRIDAY Phase 6 Calibration (Git commit: %s)", git_commit)

    prompts = load_prompts(args.prompts_file)
    logger.info("Loaded prompts with categories: %s", ", ".join(prompts.keys()))

    synth = None
    if not args.dry_run:
        from friday.interaction.tts import ChatterboxTurboSynthesizer
        dev = args.device or ("cuda" if Path("models/chatterbox-turbo").exists() else "cpu")
        logger.info("Initializing ChatterboxTurboSynthesizer on %s...", dev)
        synth = ChatterboxTurboSynthesizer(device=dev)
    else:
        logger.info("Dry-run mode: skipping model initialization.")

    if args.screening:
        logger.info("Starting Phase 6 screening pass...")
        gen = run_screening(synth, prompts, args.output_dir, args.manifest_file, git_commit, dry_run=args.dry_run)
        logger.info("Screening complete: generated %d samples.", len(gen))
    elif args.sweep:
        logger.info("Starting blend weight sweep for %s...", args.expression)
        gen = run_sweep(synth, args.expression, prompts, args.output_dir, args.manifest_file, git_commit, dry_run=args.dry_run)
        logger.info("Sweep complete: generated %d samples.", len(gen))
    elif args.stability:
        logger.info("Starting stability pass for %s at w=%.2f...", args.expression, args.blend_weight)
        gen = run_stability(synth, args.expression, args.blend_weight, prompts, args.output_dir, args.manifest_file, git_commit, dry_run=args.dry_run)
        logger.info("Stability complete: generated %d samples.", len(gen))
    else:
        # Single prompt execution
        text_id = args.text_id or f"{args.expression[:1].upper()}01"
        cat_prompts = prompts.get(args.expression, [])
        match = next((p for p in cat_prompts if p["id"] == text_id), None)
        text = match["text"] if match else "Calibration sample text."

        p = generate_sample(
            synth=synth,
            expression=args.expression,
            text_id=text_id,
            text=text,
            blend_weight=args.blend_weight,
            seed=args.seed,
            output_dir=args.output_dir,
            manifest_file=args.manifest_file,
            git_commit=git_commit,
            dry_run=args.dry_run,
        )
        logger.info("Sample generated: %s", p)


if __name__ == "__main__":
    main()
