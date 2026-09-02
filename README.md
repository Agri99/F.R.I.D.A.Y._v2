# F.R.I.D.A.Y.

A local-first, privacy-respecting personal AI computer assistant for Windows 11. Designed to operate through typed tools, independent policy verification, observation-aware replanning, hardware-agnostic local models, and self-improving skill distillation.

---

## Overview

F.R.I.D.A.Y. (Female Replacement Intelligent Digital Assistant Youth) runs entirely on-device:
- **Speech Recognition:** `faster-whisper` with pre-roll ring buffer, domain vocabulary biasing, and **confidence filtering** (avg_logprob, no_speech_prob, compression_ratio) to reject nonsense transcripts
- **Wake Word Detection:** `openWakeWord` with real-time audio barge-in
- **Reasoning & Planning:** Local LLM via [Ollama](https://ollama.com) (`qwen3:8b` / `qwen3:14b` / `qwen3:32b` by profile) with multi-step replanning, **fast/deep reasoning preference**, and hardware-aware model routing
- **Vision Perception:** Local vision models (`llava`, `qwen3-vl`) + progressive screen perception + OCR
- **Speech Synthesis:** Local `Piper` neural TTS (`en_GB-jenny_dioco-medium`) with **interruptible streaming**, barge-in cancellation, and **spoken acknowledgements** for mode changes
- **Computer-Use Subsystem:** Target resolver (UIA $\rightarrow$ Automation ID $\rightarrow$ DOM $\rightarrow$ Visual match $\rightarrow$ Coordinates), **foreground window validation**, **verified post-action state checking**, safety checks, and native Windows automation
- **Visual Presence:** Constellation 3D holographic orb overlay hosted in PySide6 / Three.js via an isolated WebSocket state server — **opaque particle texture**, **state-matched speeds** (listening 5x, speaking 3x, thinking 7x, follow-up 5x), state-color sync
- **Self-Improvement:** Trajectory logging, pattern distillation into reusable `SKILL.md` workflows, **skill benchmark auto-promotion** (configurable success rate, execution time, verification rate thresholds), and isolated sandbox validation (Docker + subprocess)
- **Proactive Jobs:** Cron/event-driven job scheduler with **idle, network change, resource condition, startup, application event, calendar lead time** triggers; strict policy enforcement
- **Hardware Portability:** Automatic CPU/GPU/VRAM hardware profiling (`laptop.yaml`, `balanced.yaml`, `workstation.yaml`), **backup/restore/migration** round-trip

---

## Security & Architecture Principles

FRIDAY separates intelligence from execution and fails closed:

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

## Configuration & Personalization

### 1. Customizing Personas (Owner vs. Guest)
FRIDAY adjusts her personality dynamically based on who is speaking. You can customize her responses in [`config/personas.yaml`](config/personas.yaml) without touching code:

```yaml
owner_persona: |
  You are speaking to your creator and primary user, Boss.
  Persona Rules:
  - Respond in a loyal, confident, concise, and natural tone. Address them as "Boss".
  - NEVER say robotic phrases like "I'm just a virtual assistant" or "As an AI model".
  - When asked conversational questions like "How are you?", respond naturally and in-character.
  - When executing commands, do so crisply and efficiently without unnecessary filler.

guest_persona: |
  You are speaking to an unauthorized Guest.
  Persona Rules:
  - Respond politely, formally, and concisely.
  - Do not reveal private personal facts, search histories, or private files.
  - If the guest asks you to execute computer commands, state: "I'm sorry, I am only authorized to perform computer actions for my primary user."
```

---

### 2. Voice Biometrics (Speaker Recognition)
FRIDAY uses SpeechBrain neural speaker verification to distinguish your voice from others:
1. Ensure the folder `data/voice_enrollment/` exists.
2. Record **3 short audio clips** (3–5 seconds each) of yourself speaking naturally (e.g. *"Hello Friday, this is my voice"*).
3. Save them inside `data/voice_enrollment/` as:
   - `voice_ref_0.wav`
   - `voice_ref_1.wav`
   - `voice_ref_2.wav`
4. When audio is received, FRIDAY compares the speaker's embedding against these reference files to identify you as the **Owner** (or a **Guest**).

---

### 3. Setting Your Security Passphrase
For critical 🔴 RED tier actions (e.g. file deletions), FRIDAY requires a spoken passphrase verified via SHA-256:
1. Generate the SHA-256 hash of your secret phrase (e.g. `"jarvis protocol"`):
   ```powershell
   python -c "import hashlib; print(hashlib.sha256('jarvis protocol'.encode()).hexdigest())"
   ```
2. Add the hash to your `.env` file:
   ```env
   PASSPHRASE_HASH=<your_sha256_hash_here>
   ```
3. When prompted during critical actions, simply speak your passphrase aloud.

---

### 4. Teaching Skills & Multi-Step Routines

#### A. Custom Skill Recipes (`skills/builtin/`)
Create a markdown recipe in `skills/builtin/` (e.g. `skills/builtin/dev-setup.md`):
```markdown
# Dev Setup Routine

## Triggers
- "start dev environment"
- "prep my workspace"

## Procedure
1. action: applications.open
   args: {"app_id": "vscode"}
2. action: applications.open
   args: {"app_id": "terminal"}
3. action: audio.set_volume
   args: {"volume": 35}
```

#### B. Automatic Habit Learning
If you execute the same sequence of actions 3 times during daily use, the **Pattern Distiller** (`src/friday/learning/distiller.py`) automatically extracts the pattern into a candidate skill in `skills/learned/`.

#### C. Declarative Preferences
You can simply say:
- *"Remember that my default project directory is C:\Dev\MyProject"*
- *"Remember that my favorite browser is Firefox"*
These facts are stored in SQLite semantic memory and recalled via Context Priming.

---

## Holographic 3D Constellation Orb

The floating visualizer displays real-time system states:
- 🔵 **Cyan (Pulsing):** `Idle` (waiting for wake word)
- 🟢 **Emerald Green:** `Listening` (recording your speech)
- 🟣 **Purple (Fast Rotation):** `Thinking & Planning` (Ollama LLM reasoning)
- 🟠 **Vivid Orange:** `Speaking` (Piper TTS active speech)
- 🟡 **Gold:** `Awaiting Confirmation` (asking for approval)
- 🔴 **Red:** `Blocked / Error` (policy block or failure)

*(You can click and drag the orb anywhere on your screen, or say "Hide yourself" / "Come back" to toggle visibility.)*

---

## Repository Structure

```
.
├── config/                     # Multi-environment YAML configurations & hardware profiles
│   ├── default.yaml
│   ├── personas.yaml           # Owner and Guest personality definitions
│   └── profiles/               # laptop.yaml, balanced.yaml, workstation.yaml
├── data/                       # Local SQLite database (friday.db), audit logs, trajectories, voice refs
├── models/                     # Local model weights cache (managed by download_models.py)
├── scripts/                    # setup.py, hardware_probe.py, benchmark_models.py, wipe_history.py
├── secrets/                    # Isolated credentials store (credentials.json, tokens)
├── skills/                     # Builtin and learned SKILL.md definitions
├── tests/                      # 41 unit, security invariant, computer, memory, and learning tests
├── workspace/                  # Sandboxed agent workspace
├── src/friday/
│   ├── app.py                  # Single application entrypoint & boot greeting
│   ├── config.py               # Pydantic configuration loader
│   ├── agent/                  # Orchestrator, Planner (replanning), Executor, Evaluator, Steering
│   ├── security/               # ActionRequest, PolicyEngine, Authorization, VoiceAuth, SecretsManager
│   ├── models/                 # ModelRouter (7 roles), OllamaBackend, CloudBackend, HardwareProbe
│   ├── tools/                  # System, filesystem, applications, computer, browser, gmail, terminal
│   ├── computer/               # Controller, TargetResolver, ScreenObserver, SafetyCheck, Verification
│   ├── browser/                # Controller, PageExtractor, BrowserNavigator, BrowserVerifier
│   ├── memory/                 # Database (FTS5), PrimingEngine, RetentionManager, Semantic, Preferences
│   ├── skills/                 # SkillLoader, SkillRegistry, SkillSandbox, SkillRuntime
│   ├── learning/               # TrajectoryRecorder, PatternDistiller, SkillLearner, Scheduler
│   ├── jobs/                   # JobScheduler, JobRegistry, JobExecutor
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
  ollama pull llava
  ```

### 2. Installation & First-Run Setup
```bash
# 1. Clone the repository
git clone https://github.com/Agri99/F.R.I.D.A.Y._v2.git
cd F.R.I.D.A.Y._v2

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install in editable mode with all dependencies
pip install -e ".[all]"

# 4. Download local voice model weights
python scripts/download_models.py --all

# 5. Run first-time setup wizard
python scripts/setup.py
```

---

## Running FRIDAY

### 1. Full Voice & Holographic Orb Mode
```bash
python src/friday/app.py
```
- FRIDAY will boot up and speak a dynamic, time-aware greeting (*"Good morning, Boss. All systems online and ready."*).
- Say **"FRIDAY"** to wake the assistant.
- Speak naturally:
  - *"How are you today?"*
  - *"Open Notepad and write a project summary"*
  - *"What's the system status?"*
  - *"Friday, use fast mode"*
  - *"Hide yourself"* / *"Come back"*
  - *"Goodbye Friday"* $\rightarrow$ *"Do you want me to go off?"* $\rightarrow$ *"Yes"*

### 2. Text / CLI Smoke Test Mode
```bash
python src/friday/app.py --text
```

### 3. Database Maintenance
To wipe conversation turns and start with a fresh memory database:
```bash
python scripts/wipe_history.py
```

---

## Testing & Verification

Run the full automated test suite:
```bash
pytest tests/ -v
```
All **276 automated tests** pass cleanly (unit, integration, security, evaluation, smoke, computer, browser, skills, tools, memory, learning).
