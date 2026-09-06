"""
src/friday/models/provisioning.py

WHAT THIS IS FOR:
Handles the full lifecycle of model provisioning:
  hardware profile -> role requirements -> model candidates ->
  compatibility check -> installed? -> load|download -> integrity ->
  benchmark -> health -> activate.

Runbook §45 (Runtime model provisioning).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from friday.models.registry import ModelEntry, ModelRegistry


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ProvisionResult:
    model_id: str
    success: bool
    message: str
    installed: bool = False
    integrity_ok: bool = False
    benchmark: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provisioner
# ---------------------------------------------------------------------------

class ModelProvisioner:
    """Provisions models for FRIDAY using the registry and installed providers.

    The provisioner follows the runbook flow:
      1. Check if the model is already available in the provider (e.g. Ollama).
      2. If not, attempt to pull it from the provider's hub.
      3. Run an integrity check if a SHA-256 is registered.
      4. Run a lightweight benchmark (time-to-first-token).
      5. Update the registry with results.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        registry_path: str | Path = "data/model_registry.json",
    ) -> None:
        self.registry = registry
        self.registry_path = Path(registry_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_role(self, role: str) -> ProvisionResult:
        """Ensure the best available model for ``role`` is installed and healthy.

        Returns a ProvisionResult indicating success/failure.
        """
        candidates = self.registry.by_role(role)
        if not candidates:
            return ProvisionResult(model_id="", success=False, message=f"No models registered for role '{role}'")

        for entry in candidates:
            result = self._try_provision(entry)
            if result.success:
                return result

        return ProvisionResult(
            model_id=candidates[0].id,
            success=False,
            message=f"All candidates for role '{role}' failed to provision",
        )

    def provision(self, model_id: str) -> ProvisionResult:
        """Provision a specific model by registry ID."""
        entry = self.registry.get(model_id)
        if entry is None:
            return ProvisionResult(model_id=model_id, success=False, message="Model not in registry")
        return self._try_provision(entry)

    def check_installed(self, entry: ModelEntry) -> bool:
        """Return True if the model is currently available in its provider."""
        if entry.provider == "ollama":
            return self._ollama_model_exists(entry.model)
        # For file-based providers, check the model path exists
        if entry.source_url and Path(entry.model).exists():
            return True
        return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _try_provision(self, entry: ModelEntry) -> ProvisionResult:
        installed = self.check_installed(entry)

        if not installed:
            installed = self._pull_model(entry)
            if not installed:
                return ProvisionResult(
                    model_id=entry.id,
                    success=False,
                    message=f"Could not install model '{entry.model}' via provider '{entry.provider}'",
                )

        # Integrity check (if checksum configured)
        integrity_ok = True
        if entry.sha256:
            from friday.models.integrity import verify_file
            # For Ollama the weights are managed internally — skip file check
            if entry.provider != "ollama":
                ir = verify_file(entry.model, entry.sha256)
                integrity_ok = ir.ok
                if not integrity_ok:
                    self.registry.update_health(entry.id, "UNHEALTHY")
                    return ProvisionResult(
                        model_id=entry.id,
                        success=False,
                        message=ir.message,
                        installed=True,
                        integrity_ok=False,
                    )

        # Quick benchmark
        benchmark = self._run_quick_benchmark(entry)

        self.registry.mark_installed(entry.id, True)
        self.registry.update_health(entry.id, "HEALTHY")
        self.registry.update_benchmark(entry.id, benchmark)
        self.registry.save(self.registry_path)

        return ProvisionResult(
            model_id=entry.id,
            success=True,
            message=f"Model '{entry.model}' provisioned OK",
            installed=True,
            integrity_ok=integrity_ok,
            benchmark=benchmark,
        )

    def _ollama_model_exists(self, model_name: str) -> bool:
        """Return True if the model is already listed in Ollama."""
        try:
            import ollama
            models = ollama.list()
            names = [m.model for m in getattr(models, "models", [])]
            # Accept exact match or prefix match (e.g. "qwen3:8b" matches "qwen3:8b-q4_k_m")
            return any(n == model_name or n.startswith(model_name.split(":")[0]) for n in names)
        except Exception:
            return False

    def _pull_model(self, entry: ModelEntry) -> bool:
        """Attempt to pull the model via its provider. Returns True on success."""
        if entry.provider == "ollama":
            try:
                import ollama
                print(f"[Provisioner] Pulling {entry.model} via Ollama...")
                ollama.pull(entry.model)
                return True
            except Exception as exc:
                print(f"[Provisioner] Pull failed for {entry.model}: {exc}")
                return False
        return False

    def _run_quick_benchmark(self, entry: ModelEntry) -> dict[str, Any]:
        """Run a minimal benchmark: time-to-first-token for a short prompt."""
        if entry.provider != "ollama":
            return {}
        try:
            import ollama
            start = time.perf_counter()
            resp = ollama.chat(
                model=entry.model,
                messages=[{"role": "user", "content": "Hi"}],
                stream=False,
                options={"num_predict": 1},
            )
            elapsed = time.perf_counter() - start
            return {
                "ttft_ms": round(elapsed * 1000, 1),
                "model": entry.model,
                "timestamp": time.time(),
            }
        except Exception as exc:
            return {"error": str(exc)}


__all__ = ["ModelProvisioner", "ProvisionResult"]
