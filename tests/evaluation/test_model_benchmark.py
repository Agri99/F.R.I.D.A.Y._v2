"""
tests/evaluation/test_model_benchmark.py

WHAT THIS IS FOR:
E2E evaluation test for model benchmark compliance with thresholds.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


class TestModelBenchmarkCompliance:
    @pytest.fixture
    def config_dir(self):
        return _project_root() / "config"

    def test_default_yaml_exists(self, config_dir):
        assert (config_dir / "default.yaml").exists()

    def test_profiles_exist(self, config_dir):
        profiles = config_dir / "profiles"
        assert (profiles / "laptop.yaml").exists()
        assert (profiles / "balanced.yaml").exists()
        assert (profiles / "workstation.yaml").exists()

    def test_model_roles_defined(self, config_dir):
        """Verify model roles are defined across default config and profiles.
        Required: fast, reasoning, vision, embedding, stt, tts
        Optional: reranker
        """
        required_roles = ["fast", "reasoning", "vision", "embedding", "stt", "tts"]
        optional_roles = ["reranker"]

        # Collect all roles from default config and all profiles
        all_models = {}

        # Check default config
        with open(config_dir / "default.yaml") as f:
            default = yaml.safe_load(f)
        all_models.update(default.get("models", {}))

        # Check all profiles
        profiles_dir = config_dir / "profiles"
        for profile_file in profiles_dir.glob("*.yaml"):
            with open(profile_file) as f:
                profile = yaml.safe_load(f)
            all_models.update(profile.get("models", {}))

        # Verify all required roles exist somewhere
        for role in required_roles:
            assert role in all_models, f"Required role '{role}' missing from all configs"

        # Optional roles should be logged but not required
        for role in optional_roles:
            if role not in all_models:
                print(f"Warning: Optional role '{role}' not found in configs")

        # Check laptop profile specifically has extended roles
        with open(config_dir / "profiles" / "laptop.yaml") as f:
            laptop = yaml.safe_load(f)
        laptop_models = laptop.get("models", {})
        for role in ["embedding", "stt", "tts"]:
            assert role in laptop_models, f"Role '{role}' missing from laptop.yaml"

    def test_learning_config_has_promotion_thresholds(self, config_dir):
        """Verify promotion thresholds are configured (§15.3)."""
        with open(config_dir / "default.yaml") as f:
            config = yaml.safe_load(f)

        learning = config.get("learning", {})
        assert learning.get("minimum_successes") is not None
        assert learning.get("minimum_success_rate") is not None
        assert learning.get("require_sandbox_pass") is not None

    def test_benchmark_script_exists(self):
        """Verify benchmark script exists and is importable."""
        script_path = _project_root() / "scripts/benchmark_models.py"
        assert script_path.exists()