"""
tests/interaction/test_condition_bank.py

Unit tests for the Multi-Emotion Latent Condition Bank:
1. Profile files and manifest integrity.
2. Deserialization of compiled Conditionals and speaker embedding tensor shapes.
3. ChatterboxTurboSynthesizer dynamic condition switching and zero-latency restoration.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
import torch

from friday.interaction.tts import ChatterboxTurboSynthesizer, blend_conditionals


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COND_DIR = PROJECT_ROOT / "data" / "voices" / "conditionals"


def test_manifest_and_profiles_exist():
    assert COND_DIR.exists(), f"Conditionals directory not found at {COND_DIR}"
    manifest_path = COND_DIR / "manifest.json"
    assert manifest_path.exists(), "manifest.json not found in conditionals directory"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["total_source_clips"] == 283
    assert manifest["embedding_clips_used"] == 283
    assert "profiles" in manifest

    # Check each profile in manifest corresponds to a real .pt file on disk
    for key, pinfo in manifest["profiles"].items():
        pt_path = COND_DIR / pinfo["file"]
        assert pt_path.exists(), f"Missing condition profile file for {key}: {pt_path}"

    # Also verify master.pt centroid profile exists
    assert (COND_DIR / "master.pt").exists(), "Missing master centroid condition profile master.pt"


def test_compiled_conditionals_shapes_and_speaker_identity():
    """Verify precompiled .pt files load and share the exact centroid speaker embedding."""
    try:
        from chatterbox.tts_turbo import Conditionals
    except ImportError:
        pytest.skip("chatterbox-tts not installed in environment")

    master_path = COND_DIR / "master.pt"
    if not master_path.exists():
        pytest.skip("master.pt does not exist")

    master_cond = Conditionals.load(str(master_path), map_location="cpu")
    assert hasattr(master_cond, "t3"), "Conditionals missing t3"
    assert hasattr(master_cond, "gen"), "Conditionals missing gen"
    assert master_cond.t3.speaker_emb.shape == (1, 256), f"Unexpected shape {master_cond.t3.speaker_emb.shape}"

    # Sample a couple of emotions to verify speaker embedding equivalence
    for emo in ["happy", "sigh", "chuckle"]:
        emo_path = COND_DIR / f"{emo}.pt"
        if emo_path.exists():
            emo_cond = Conditionals.load(str(emo_path), map_location="cpu")
            diff = torch.norm(master_cond.t3.speaker_emb - emo_cond.t3.speaker_emb).item()
            assert diff < 1e-4, f"Speaker embedding for {emo} deviates from centroid by {diff}"


def test_synthesizer_dynamic_condition_switching_explicit_arg():
    """Verify that passing emotion='happy' activates continuous condition blending during generation and restores original."""
    synth = ChatterboxTurboSynthesizer(device="cpu")
    synth._ensure_model = MagicMock()

    mock_master = MagicMock(name="master_cond")
    mock_happy = MagicMock(name="happy_cond")
    mock_sigh = MagicMock(name="sigh_cond")

    synth._conditionals_bank = {
        "master": mock_master,
        "happy": mock_happy,
        "sigh": mock_sigh,
    }

    mock_model = MagicMock()
    mock_model.conds = mock_master
    observed_conds_during_gen = []

    def fake_generate(text, audio_prompt_path=None, exaggeration=0.5):
        observed_conds_during_gen.append(mock_model.conds)
        return torch.zeros((1, 24000), dtype=torch.float32)

    mock_model.generate.side_effect = fake_generate
    synth.model = mock_model

    # Run synthesis with emotion="happy" and default blend weight (0.65)
    audio = synth._build_audio("This is a great day!", emotion="happy")
    assert isinstance(audio, np.ndarray)
    assert len(observed_conds_during_gen) == 1
    # Check that blended condition took tokens from target (w=0.65 >= 0.5)
    assert observed_conds_during_gen[0].t3.cond_prompt_speech_tokens is mock_happy.t3.cond_prompt_speech_tokens
    # Check that model.conds was restored to mock_master
    assert mock_model.conds is mock_master

    # Test explicit blend_weight=1.0 (pure target emotion)
    synth._build_audio("Pure joy!", emotion="happy", blend_weight=1.0)
    assert observed_conds_during_gen[-1] is mock_happy
    assert mock_model.conds is mock_master

    # Test explicit blend_weight=0.0 (pure master baseline)
    synth._build_audio("Subtle delivery", emotion="happy", blend_weight=0.0)
    assert observed_conds_during_gen[-1] is mock_master
    assert mock_model.conds is mock_master


def test_synthesizer_dynamic_condition_switching_from_text_tag():
    """Verify that bracket emotion tags in text resolve to the correct profile key with continuous blending."""
    synth = ChatterboxTurboSynthesizer(device="cpu")
    synth._ensure_model = MagicMock()

    mock_master = MagicMock(name="master_cond")
    mock_happy = MagicMock(name="happy_cond")
    mock_chuckle = MagicMock(name="chuckle_cond")

    synth._conditionals_bank = {
        "master": mock_master,
        "happy": mock_happy,
        "chuckle": mock_chuckle,
    }

    mock_model = MagicMock()
    mock_model.conds = mock_master
    observed_conds_during_gen = []

    def fake_generate(text, audio_prompt_path=None, exaggeration=0.5):
        observed_conds_during_gen.append(mock_model.conds)
        return torch.zeros((1, 24000), dtype=torch.float32)

    mock_model.generate.side_effect = fake_generate
    synth.model = mock_model

    # [laugh] maps to "chuckle" profile with blend weight 0.65
    synth._build_audio("[laugh] That was brilliant!")
    assert observed_conds_during_gen[-1].t3.cond_prompt_speech_tokens is mock_chuckle.t3.cond_prompt_speech_tokens
    assert mock_model.conds is mock_master

    # [happy] maps to "happy" profile with blend weight 0.65
    synth._build_audio("[happy] All systems are optimal.")
    assert observed_conds_during_gen[-1].t3.cond_prompt_speech_tokens is mock_happy.t3.cond_prompt_speech_tokens
    assert mock_model.conds is mock_master

    # Untagged text defaults to master
    synth._build_audio("Standard factual readout.")
    assert observed_conds_during_gen[-1] is mock_master
    assert mock_model.conds is mock_master


def test_synthesizer_restores_condition_on_generate_failure():
    """Verify exception safety: model.conds is restored even if generate() raises an error."""
    synth = ChatterboxTurboSynthesizer(device="cpu")
    synth._ensure_model = MagicMock()

    mock_master = MagicMock(name="master_cond")
    mock_happy = MagicMock(name="happy_cond")

    synth._conditionals_bank = {
        "master": mock_master,
        "happy": mock_happy,
    }

    mock_model = MagicMock()
    mock_model.conds = mock_master

    def failing_generate(text, audio_prompt_path=None, exaggeration=0.5):
        raise RuntimeError("Inference crash simulation")

    mock_model.generate.side_effect = failing_generate
    synth.model = mock_model

    with pytest.raises(RuntimeError, match="Inference crash simulation"):
        synth._build_audio("Testing failure recovery", emotion="happy")

    # model.conds MUST be restored back to master
    assert mock_model.conds is mock_master


def test_blend_conditionals():
    """Verify continuous latent condition blending across boundary and intermediate weights."""
    mock_base = MagicMock(name="base_cond")
    mock_target = MagicMock(name="target_cond")

    # Boundary tests
    assert blend_conditionals(mock_base, mock_target, 0.0) is mock_base
    assert blend_conditionals(mock_base, mock_target, 1.0) is mock_target
    assert blend_conditionals(mock_base, mock_base, 0.5) is mock_base
    assert blend_conditionals(None, mock_target, 0.5) is mock_target
    assert blend_conditionals(mock_base, None, 0.5) is mock_base

    try:
        from chatterbox.models.t3.modules.cond_enc import T3Cond
        from chatterbox.tts_turbo import Conditionals
    except ImportError:
        pytest.skip("chatterbox-tts not installed in environment")

    # Construct real Conditionals objects with known tensors
    spk_base = torch.zeros((1, 256), dtype=torch.float32)
    spk_target = torch.ones((1, 256), dtype=torch.float32)

    adv_base = torch.zeros((1, 1), dtype=torch.float32)
    adv_target = torch.ones((1, 1), dtype=torch.float32)

    tok_base = torch.tensor([1, 2, 3], dtype=torch.long)
    tok_target = torch.tensor([4, 5, 6], dtype=torch.long)

    real_base = Conditionals(
        t3=T3Cond(speaker_emb=spk_base, cond_prompt_speech_tokens=tok_base, emotion_adv=adv_base),
        gen={"mel": torch.zeros((1, 80, 50), dtype=torch.float32), "discrete_meta": 10},
    )
    real_target = Conditionals(
        t3=T3Cond(speaker_emb=spk_target, cond_prompt_speech_tokens=tok_target, emotion_adv=adv_target),
        gen={"mel": torch.ones((1, 80, 50), dtype=torch.float32), "discrete_meta": 20},
    )

    # Blend with default weight 0.65
    blended = blend_conditionals(real_base, real_target, weight=0.65)
    assert isinstance(blended, Conditionals)
    # Check speaker_emb interpolation: (1 - 0.65)*0 + 0.65*1 = 0.65
    assert torch.allclose(blended.t3.speaker_emb, torch.full((1, 256), 0.65))
    # Check emotion_adv interpolation: 0.65
    assert torch.allclose(blended.t3.emotion_adv, torch.full((1, 1), 0.65))
    # Tokens switch to target when w >= 0.5
    assert torch.equal(blended.t3.cond_prompt_speech_tokens, tok_target)
    # Generator float tensor interpolated
    assert torch.allclose(blended.gen["mel"], torch.full((1, 80, 50), 0.65))
    # Generator non-tensor discrete meta takes target when w >= 0.5
    assert blended.gen["discrete_meta"] == 20

    # Blend with weight 0.35 (< 0.5)
    blended_low = blend_conditionals(real_base, real_target, weight=0.35)
    assert torch.allclose(blended_low.t3.speaker_emb, torch.full((1, 256), 0.35))
    assert torch.equal(blended_low.t3.cond_prompt_speech_tokens, tok_base)
    assert blended_low.gen["discrete_meta"] == 10

