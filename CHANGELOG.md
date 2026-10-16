# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] — Blueprint hardening pass

### Added
- **Local FastPath Bypass in Gemini Live.** Direct workstation actions (window management, volume control, app launching) execute locally within ~5ms without cloud turn overhead, suppressing redundant cloud responses while preserving Friday's personality and voice.
- **SearXNG Search Integration.** Self-hosted SearXNG container deployment (`ops/searxng`) replacing direct DuckDuckGo API/Lite scraping as primary web search, while retaining Wikipedia API and Google News RSS as specialized fallbacks.
- **Rule-Based Speech Director.** Dedicated deterministic `SpeechDirector` (`src/friday/interaction/speech_director.py`) evaluating emotional prosody and injecting validated Chatterbox Turbo vocal tags (`[sigh]`, `[gasp]`, `[chuckle]`) at the TTS boundary across legacy voice, event-driven pipeline, and Gemini Live sessions.
- **Chatterbox Tag Calibration Harness.** `scripts/test_chatterbox_tags.py` for empirical audio evaluation of verified event tags versus experimental emotion tags.
- **`models/llamacpp_backend.py`** — GGUF/Q4_K_M/Q5_K_M/Q6_K/FP16/BF16 provider implementing the existing `ModelProvider` interface.
- **`learning/benchmark.py`** — `SkillBenchmarkRunner` runs configurable benchmark suites; `AutoPromotionManager` evaluates criteria + benchmark before auto-promotion.
- **`jobs/triggers.py`** — `TriggerMonitor` watches for idle, network change, resource conditions, startup, application event, calendar lead time; triggers registered jobs (`TriggerType` enum extended).
- **`skills/runtime.py`** & **`skills/registry.py`** — Structured skill execution engine with ActionRequest policy validation and trigger-ranked search summaries.
- **`plugins/loader.py`** & **`plugins/sandbox.py`** — Non-Docker isolated plugin execution environment with verified health probe lifecycle.
- **`security/audit.py`** — `log_event` helper for non-tool events (steering, transitions).
- **Unit and Integration Test Suites.** Comprehensive tests across `tests/unit/`, `tests/interaction/`, and `tests/online/`.

### Changed
- `src/friday/interaction/gemini_live.py` — Local FastPath router integration with speech context enqueue helper deduplicating speech synthesis flow.
- `src/friday/interaction/session.py` — Live voice state machine with barge-in cancellation, bounded follow-up window, deduplicated TTS rendering, and dead legacy method pruning.
- `src/friday/computer/controller.py` — Cached controller tool registry singleton preventing costly multi-module re-registration on every action; removed unverified UI tree call.
- `src/friday/computer/windows.py` — Dynamic app paths via `LOCALAPPDATA` env var; verified window management with state assertions.
- `src/friday/browser/session.py` — Proper context initialization on launch.
- `src/friday/tools/audio.py` & `src/friday/agent/fastpath.py` — Consistent volume schema handling (`level` and `volume`).
- `src/friday/agent/orchestrator.py` — Removed orphaned expressions, deduplicated budget checks, and streamlined action request bindings.
- `src/friday/app.py` — Extracted `_play_boot_greeting` helper across pipeline modes; pruned unreachable controls dict.
- `src/friday/models/router.py` — Hardware-aware role selection with lazy hardware loading and explicit compatibility checks.
- `src/friday/ui/static/index.html` — Particle texture opacity restored, `followup_listening` state, state speeds: listening 5x, speaking 3x, thinking 7x.
- `src/friday/memory/retention.py` & `src/friday/memory/priming.py` — Cleaned dead expressions; additive migrations adding `evidence_count`, `source`, and `last_confirmed`.

### Fixed
- **False-success guard.** `Evaluator` no longer reports success on bare tool returns; missing expected observation now sets `needs_replan=True` instead of silently marking a step complete. `Executor` no longer lies about `verification_passed=True` when no controller verified the outcome.
- **Authoritative routing.** `ModelRouter` raises `ModelRoutingError` when every configured provider is unhealthy instead of returning an unreliable one.
- **Recovery/pause wiring.** `AgentOrchestrator._trigger_replan` and `_pause_execution` now record audit events instead of being empty stubs; the task state machine captures every transition.
- **Loop completion message.** Final `task.last_message` is built from the last *verified* step's result rather than falling back to "Done." when step indices advance past plan length.
- **Job executor honesty.** `JobExecutor` without an orchestrator reports `success=False` instead of pretending to verify a simulated run.
- **Inconsistent confirmation.** Voice controls now speak acknowledgements ("I'm offline now", "I'll use fast mode"); pending authorization resumes on follow-up instead of creating new tasks.
- **Shutdown flow.** Fastpath shutdown now RED tier (requires voice confirmation); execution verified before marking complete.
- **Typing/window verification.** `computer.type` validates foreground window; `computer.control_window` returns verified `(success, message)` tuples with post-action state checking; window focus now matches running process windows instead of desktop.
- **Nonsense transcripts.** STT confidence filtering via `avg_logprob`/`no_speech_prob`/`compression_ratio`; returns `""` on low-confidence/garbled audio.
- **Orb idle during follow-up.** `FOLLOWUP_LISTENING` state now uses listening color/speed (5x) instead of idle.

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

