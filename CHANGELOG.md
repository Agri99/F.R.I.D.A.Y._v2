# Changelog

All notable changes to this project will be documented in this file.

## [2.1.0] — 2026-08-27

### Added
- **v3 Blueprint upgrade** — formal ActionRequest contracts, observation-aware replanning, context priming, proactive jobs, hardware profiling, and productionization.
- `security/action_request.py` — typed ActionRequest object for all tool invocations.
- `agent/steering.py` — voice control commands (go offline, fast mode, deep reasoning, stop, pause).
- `computer/target_resolver.py` — accessibility → visual fallback resolution chain.
- `computer/safety.py` — pre-action safety checks.
- `browser/` expansion — extractor, navigation, verification, safety modules.
- `tools/terminal.py` — sandboxed and bounded host terminal access.
- `memory/priming.py` — task-specific context priming engine.
- `memory/retention.py` — confidence-based memory retention with evidence scoring.
- `skills/sandbox.py` — isolated skill execution environment.
- `skills/runtime.py` — skill execution engine with policy re-authorization.
- `learning/scheduler.py` — background learning job scheduling.
- `jobs/` subsystem — proactive scheduled task execution.
- `models/hardware.py` — CPU/GPU/VRAM hardware capability detection.
- `models/benchmark.py` — model performance benchmarking harness.
- Hardware profiles: `config/profiles/laptop.yaml`, `balanced.yaml`, `workstation.yaml`.
- `scripts/download_models.py` — model download-on-demand mechanism.
- `scripts/setup.py` — first-run bootstrap wizard.
- `.github/workflows/ci.yml` — GitHub Actions CI pipeline.
- Expanded test suites: integration, computer, memory, learning, evaluation.

### Changed
- `pyproject.toml` — all dependencies from requirements.txt, organized into optional groups (voice, browser, google, vision, dev).
- Agent orchestrator — full PLAN → EXECUTE → OBSERVE → VERIFY → RECOVER → REPLAN loop.
- Planner — observation-aware replanning with plan versioning.
- Executor — ActionRequest construction, step-level budgets, observation capture.
- Evaluator — structured EvaluationResult with pass/fail/uncertain.
- Recovery — full failure classifier with evidence-driven retry.
- Memory database — confidence, evidence_count, expiry columns.
- Model router — expanded to 6+ roles (fast, reasoning, vision, embedding, stt, tts).
- Audit logger — full task lifecycle events (20 event types).
- Learning distiller — real pattern extraction replacing placeholder stub.

### Removed
- `requirements.txt` — superseded by pyproject.toml.
- `spinning.html`, `spin.html` — reference files no longer needed.
- `scripts/migrate_v1_skills.py` — v1 migration complete.

## [2.0.0] — 2026-08-26

### Added
- Complete v2 architecture: agent orchestrator, typed tool engine, security policy, holographic 3D orb UI.
- 33 typed tools across system, filesystem, applications, computer, browser, Gmail, Calendar, audio, timer.
- Local-first Ollama model routing (fast/reasoning/vision).
- Wake word detection, faster-whisper STT, Piper TTS.
- PySide6 + Three.js holographic orb visualizer.
- SQLite FTS5 memory with conversation, episodic, semantic, preference layers.
- Security: 4-tier risk policy, capability scopes, action-bound TTL confirmations, voice auth, passphrase.

