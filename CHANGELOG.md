# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] — Blueprint hardening pass

### Fixed
- **False-success guard.** `Evaluator` no longer reports success on bare tool returns; missing expected observation now sets `needs_replan=True` instead of silently marking a step complete. `Executor` no longer lies about `verification_passed=True` when no controller verified the outcome.
- **Authoritative routing.** `ModelRouter` raises `ModelRoutingError` when every configured provider is unhealthy instead of returning an unreliable one.
- **Recovery/pause wiring.** `AgentOrchestrator._trigger_replan` and `_pause_execution` now record audit events instead of being empty stubs; the task state machine captures every transition.
- **Loop completion message.** Final `task.last_message` is built from the last *verified* step's result rather than falling back to "Done." when step indices advance past plan length.
- **Job executor honesty.** `JobExecutor` without an orchestrator reports `success=False` instead of pretending to verify a simulated run.
- **Inconsistent confirmation.** Voice controls now speak acknowledgements ("I'm offline now", "I'll use fast mode"); pending authorization resumes on follow-up instead of creating new tasks.
- **Shutdown flow.** Fastpath shutdown now RED tier (requires voice confirmation); execution verified before marking complete.
- **Typing/window verification.** `computer.type` validates foreground window; `computer.control_window` returns verified `(success, message)` tuples with post-action state checking.
- **Nonsense transcripts.** STT confidence filtering via `avg_logprob`/`no_speech_prob`/`compression_ratio`; returns `""` on low-confidence/garbled audio.
- **Orb idle during follow-up.** `FOLLOWUP_LISTENING` state now uses listening color/speed (5x) instead of idle.

### Added
- **`learning/benchmark.py`** — `SkillBenchmarkRunner` runs configurable benchmark suites; `AutoPromotionManager` evaluates criteria + benchmark before auto-promotion.
- **`jobs/triggers.py`** — `TriggerMonitor` watches for idle, network change, resource conditions, startup, idle, network change, resource condition, application event, calendar lead time; triggers registered jobs.
- **`jobs/triggers.py`** — `TriggerType` enum extended: `STARTUP`, `IDLE`, `NETWORK_CHANGE`, `RESOURCE_CONDITION`, `APPLICATION_EVENT`, `CALENDAR_LEAD_TIME`.
- **`tests/unit/test_skill_benchmark.py`** — benchmark config, result validation, auto-promotion approval/rejection logic.
- **`tests/unit/test_job_triggers.py`** — idle, network change, resource condition trigger coverage.
- **`tests/unit/test_skill_benchmark.py`** — benchmark config, result validation, auto-promotion approval/rejection logic.
- **`tests/unit/test_window_control.py`** — verified window control contracts.

### Changed
- `src/friday/app.py` — voice controls with spoken announcements, resume path for authorization, mode/model preference routing.
- `src/friday/interaction/session.py` — `VoiceSession` accepts `announce` callback, resumes pending auth tasks on follow-up.
- `src/friday/interaction/stt.py` — transcript confidence filtering using faster-whisper segment metadata.
- `src/friday/models/router.py` — `set_reasoning_preference()` for fast/deep mode routing.
- `src/friday/computer/controller.py` — foreground window validation before typing.
- `src/friday/computer/windows.py` — `WindowManager` methods return verified `(success, message)` tuples with post-action state checking.
- `src/friday/tools/computer.py` — window control tool uses verified results.
- `src/friday/ui/static/index.html` — particle texture opacity restored, `followup_listening` state, state speeds: listening 5x, speaking 3x, thinking 7x.
- `src/friday/jobs/scheduler.py` — `TriggerType` enum extended; `parse_trigger` handles all blueprint trigger types.
- `src/friday/jobs/triggers.py` — new `TriggerMonitor` with idle, network change, resource condition, startup, idle, network change, resource condition, application event, calendar lead time monitoring.
- `src/friday/agent/fastpath.py` — shutdown fastpath now RED tier.
- `src/friday/agent/orchestrator.py` — fastpath tier binding, reasoning preference wiring.
- `src/friday/learning/benchmark.py` — `SkillBenchmarkRunner` + `AutoPromotionManager` for skill auto-promotion.
- `src/friday/learning/promotion.py` — `promote()` accepts optional `benchmark_result`.

Tests: 225 passed, 0 failures. Healthcheck: 100% green.

### Added
- **`models/llamacpp_backend.py`** — GGUF/Q4_K_M/Q5_K_M/Q6_K/FP16/BF16 provider implementing the existing `ModelProvider` interface.
- **`interaction/session.py`** — live voice state machine (`IDLE` → `LISTENING_FOR_WAKE` → `WAKE_DETECTED` → `LISTENING` → `TRANSCRIBING` → `THINKING` → `SPEAKING` → `INTERRUPTED` → `FOLLOWUP_LISTENING` → `ERROR`) with barge-in cancellation, bounded follow-up window, and runtime controls (`stop`, `pause`, `go offline`, `use fast/deep reasoning`, `safer mode`, `explain`).
- **`memory/priming.py`** — `ContextPrimingEngine` now consumes `ContextBudget` + `ContextSelector`, with episodic-failure and skill-registry sources, ranking, and confidence weighting.
- **`skills/runtime.py`** — real execution engine: per-step `ActionRequest` construction, policy evaluation, argument interpolation, observation verification, structured results.
- **`skills/registry.py`** — `search_skills` produces serializable, trigger-ranked skill summaries for the priming engine.
- **`learning/promotion.py`** — parses persisted candidate metrics for regression comparison instead of returning `None`.
- **`plugins/loader.py`** — only transitions `SANDBOXED`/`TESTED`/`CANARY`/`ACTIVE` after actual sandbox tests and a real canary health probe; hot-swap restores the prior plugin on activation failure.
- **`plugins/sandbox.py`** — non-Docker isolation: restricted filesystem, sanitized env, no inherited secrets.
- **`learning/upgrade_logging.py`** — atomic JSON+Markdown write, fsync, then notify via the configured editor.
- **`security/audit.py`** — `log_event` helper for non-tool events (steering, transitions).
- **`memory/database.py`** — additive migrations add `evidence_count`, `source`, and `last_confirmed` to facts, episodes, and preferences.
- New tests: `tests/unit/test_voice_session.py`, `tests/unit/test_skill_runtime.py`, `tests/unit/test_model_router.py`, plus behavioral coverage for the strict evaluator and priming engine.

### Changed
- `app.py` — `run_voice` drives `VoiceSession` and routes transcripts through the same orchestrator path typed input uses; persona loading simplified.
- `agent/orchestrator.py` — eager `ActionRequest` binding; transition/replan/pause callbacks audit; loop completion formatter honors verified steps.
- `models/router.py` — hardware-aware role selection, lazy `HardwareManager` import to break a circular import, explicit compatibility checks (online, vision, prefer_local).
- `jobs/scheduler.py` — `mark_completed` honors `max_retries` and applies backoff; `DISABLE` policy actually disables after threshold.
- `jobs/executor.py` — surfaces thread exceptions, requires an orchestrator for verified execution.
- `context/` — `primer`/`__init__` use lazy `__getattr__` re-exports to keep `friday.context` importable without dragging in the memory layer.
- Ruff auto-fixes applied across the touched files (68 fixes); remaining lint debt is pre-existing in untouched legacy modules.

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

