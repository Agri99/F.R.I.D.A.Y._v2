# F.R.I.D.A.Y.

A local-first, privacy-respecting personal AI computer assistant for Windows 11. Designed to operate through typed tools, independent policy verification, observation-aware replanning, hardware-agnostic local models, and self-improving skill distillation.

---

## Overview

F.R.I.D.A.Y. (Female Replacement Intelligent Digital Assistant Youth) runs entirely on-device:
- **Speech Recognition:** `faster-whisper` with pre-roll ring buffer and vocabulary biasing
- **Wake Word Detection:** `openWakeWord` with real-time audio barge-in
- **Reasoning & Planning:** Local LLM via [Ollama](https://ollama.com) (default: `qwen3:8b` / `qwen3:14b` / `qwen3:32b` by profile) with multi-step replanning
- **Vision Perception:** Local vision models (`qwen3-vl`, `llava`) + progressive screen perception + OCR
- **Speech Synthesis:** Local `Piper` neural TTS (`en_GB-jenny_dioco-medium`)
- **Computer-Use Subsystem:** Target resolver (UIA $\rightarrow$ Automation ID $\rightarrow$ DOM $\rightarrow$ Visual match $\rightarrow$ Coordinates), safety checks, and native Windows automation
- **Visual Presence:** Constellation 3D holographic orb overlay hosted in PySide6 / Three.js via an isolated WebSocket state server
- **Self-Improvement:** Trajectory logging, pattern distillation into reusable `SKILL.md` workflows, and isolated sandbox validation
- **Proactive Jobs:** Cron/event-driven job scheduler executing background tasks within strict policy limits
- **Hardware Portability:** Automatic CPU/GPU/VRAM hardware profiling (`laptop.yaml`, `balanced.yaml`, `workstation.yaml`)

---

## Security & Architecture Principles

FRIDAY separates intelligence from execution (Principle D) and fails closed (Principle G):

1. **Formal Action Contracts (`ActionRequest`):**
   - Every tool call constructs an immutable `ActionRequest` carrying capability scope, target, risk tier, requester, and context source.
   - SHA-256 confirmation hashes guarantee that spoken approvals bind strictly to the exact tool and parameters requested.
2. **Capability Scopes & Risk Tiers:**
   - 🟢 **GREEN:** Read-only local operations (auto-approved).
   - 🟡 **YELLOW:** Reversible local operations.
   - 🟠 **ORANGE:** External or state-modifying actions (requires spoken confirmation).
   - 🔴 **RED:** Destructive or critical system operations (requires voice confirmation + passphrase).
3. **Observe $\rightarrow$ Act $\rightarrow$ Verify $\rightarrow$ Replan:**
   - Actions are validated post-execution with independent verifiers. If verification fails, the recovery classifier diagnoses the failure and triggers an observation-aware replan.
4. **Context Priming & Retention:**
   - Relevant semantic memories, project knowledge, preferences, and skills are bundled before planning, preventing prompt clutter while scoring memory confidence from evidence.
5. **Structured Audit Logging:**
   - 20 lifecycle audit events are logged to daily JSONL files in `data/audit/` with sensitive arguments (passwords, tokens) automatically redacted.

---

## Repository Structure

```
.
├── config/                     # Multi-environment YAML configurations & hardware profiles
│   ├── default.yaml
│   ├── development.yaml
│   ├── production.yaml
│   └── profiles/               # laptop.yaml, balanced.yaml, workstation.yaml
├── data/                       # Local SQLite database (friday.db), audit logs, trajectories, voice refs
├── models/                     # Local model weights cache (managed by download_models.py)
├── scripts/                    # setup.py, hardware_probe.py, benchmark_models.py, download_models.py
├── secrets/                    # Isolated credentials store (credentials.json, tokens)
├── skills/                     # Builtin and learned SKILL.md definitions
├── tests/                      # 41 unit, security invariant, computer, memory, learning, and smoke tests
├── workspace/                  # Sandboxed agent workspace
├── src/friday/
│   ├── app.py                  # Single application entrypoint
│   ├── config.py               # Pydantic configuration loader
│   ├── agent/                  # Orchestrator, Planner (replanning), Executor, Evaluator, Recovery, Steering
│   ├── security/               # ActionRequest, PolicyEngine, Authorization, Confirmation, SecretsManager
│   ├── models/                 # ModelRouter (7 roles), OllamaBackend, CloudBackend, HardwareProbe, Benchmark
│   ├── tools/                  # System, filesystem, applications, computer, browser, gmail, calendar, terminal
│   ├── computer/               # Controller, TargetResolver, ScreenObserver, SafetyCheck, Verification
│   ├── browser/                # Controller, PageExtractor, BrowserNavigator, BrowserVerifier, BrowserSafety
│   ├── memory/                 # Database (FTS5), PrimingEngine, RetentionManager, Semantic, Preferences
│   ├── skills/                 # SkillLoader, SkillRegistry, SkillSandbox, SkillRuntime, SkillValidator
│   ├── learning/               # TrajectoryRecorder, PatternDistiller, SkillLearner, LearningScheduler
│   ├── jobs/                   # JobScheduler, JobRegistry, JobExecutor
│   ├── online/                 # NetworkMonitor, OnlineCapabilityGate, WebSearch, LiveData
│   ├── interaction/            # Voice session, faster-whisper STT, Piper TTS, openWakeWord
│   └── ui/                     # PySide6 transparent window & Three.js holographic orb
├── pyproject.toml              # Modern packaging specification with optional dependency groups
└── CHANGELOG.md                # Release history and milestone documentation
```

---

## Getting Started

### 1. Prerequisites
- **Operating System:** Windows 10/11
- **Python:** 3.11+
- **[Ollama](https://ollama.com):** Installed and running locally
  ```bash
  ollama pull qwen3:8b
  ollama pull qwen3-vl:8b
  ```

### 2. Installation & First-Run Setup
```bash
# 1. Clone the repository
git clone https://github.com/Agri99/F.R.I.D.A.Y._v2.git
cd F.R.I.D.A.Y._v2

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install in editable mode with development tools
pip install -e ".[all]"

# 4. Download local voice/vision model weights
python scripts/download_models.py --all

# 5. Run first-time hardware probe and setup wizard
python scripts/setup.py
```

---

## Running FRIDAY

### 1. CLI / Text Test Mode
```bash
python src/friday/app.py --text
```

### 2. Full Voice & Holographic Orb Mode
```bash
python src/friday/app.py
```
- Say **"FRIDAY"** to wake the assistant.
- Speak naturally:
  - *"Open Notepad and write project plan"*
  - *"Check my inbox"*
  - *"What's the system status?"*
  - *"Friday, use fast mode"*
  - *"Hide yourself"* / *"Come back"*
  - *"Goodbye Friday"* $\rightarrow$ *"Do you want me to go off?"* $\rightarrow$ *"Yes"*

---

## Testing & Verification

Run the full automated test suite:
```bash
pytest tests/ -v
```
All **41 automated tests** covering security invariants, ActionRequest contracts, replanning loops, target resolution, memory priming, skill distillation, and execution budgets pass consistently.
