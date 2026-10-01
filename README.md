# F.R.I.D.A.Y.

A local-first, privacy-respecting personal AI computer assistant for Windows 11. Designed to operate through typed tools, independent policy verification, observation-aware replanning, hardware-agnostic model routing, expressive neural speech synthesis, and real-time bidirectional voice conversation.

---

## Overview

F.R.I.D.A.Y. (Female Replacement Intelligent Digital Assistant Youth) runs on Windows with flexible local and cloud hybrid intelligence:

- **Speech Recognition & Multilingual Chain:** Real-time neural Silero VAD stream gating and `faster-whisper` with prioritized language comprehension hierarchy (English > Indonesian > Sundanese > Other languages), rolling pre-speech ring buffer preventing word-onset clipping, domain vocabulary biasing, and an English-first spoken response policy.
- **Wake Word Detection:** `openWakeWord` with real-time streaming audio detection and seamless re-arming.
- **Bidirectional Conversational Voice Engine:** Google Gemini Live API (`gemini-3.1-flash-live-preview`) over WebSockets with full-duplex conversational streaming, native tool calling, 100% local Chatterbox Turbo neural voice synthesis (Lune's voice), neural Silero VAD stream gating, pre-speech ring buffer, and acoustic echo suppression with barge-in interruption.
- **Reasoning & Planning:** Local LLM via [Ollama](https://ollama.com) (`qwen2.5:3b` standardized for low latency and ~5.5GB VRAM footprint) or Google Gemini Cloud (`gemini-3.8-flash`, `gemini-3.5-flash-lite`) with multi-step replanning, fast/deep reasoning preferences, and autonomous distillation feedback.
- **Speech Synthesis:** Resemble AI's `Chatterbox Turbo` neural TTS with custom speaker timbre cloning (`models/voice_reference.wav`), fine-tuned LoRA checkpoint support (`models/chatterbox-turbo`), automatic short-clip tiling, and expressive prosody.
- **Multi-Tier Online Search:** Privacy-respecting real-time retrieval combining self-hosted SearXNG (`http://127.0.0.1:8080`) as the primary general web search layer, with Wikipedia API (instant authoritative encyclopedic summaries) and Google News RSS (current affairs and breaking events) as specialized fallbacks.
- **Computer-Use Subsystem:** Target resolver (UIA -> Automation ID -> DOM -> Visual match -> Coordinates), foreground window validation, verified post-action state checking, safety checks, and native Windows automation.
- **Visual Presence:** Constellation 3D holographic orb overlay hosted in PySide6 / Three.js via an isolated WebSocket state server with state-matched speeds and color synchronization.
- **Self-Improvement:** Trajectory logging, pattern distillation into reusable `SKILL.md` workflows, skill benchmark auto-promotion, and isolated sandbox validation (Docker and subprocess).
- **Proactive Jobs:** Cron and event-driven job scheduler with triggers for idle state, network changes, resource conditions, system startup, application events, and calendar lead times.
- **Hardware Portability:** Automatic CPU/GPU/VRAM hardware profiling (`laptop.yaml`, `balanced.yaml`, `workstation.yaml`) with backup, restore, and state migration tools.

---

## Security & Architecture Principles

FRIDAY separates intelligence from execution and fails closed:

1. **Formal Action Contracts (`ActionRequest`):**
   - Every tool call constructs an immutable `ActionRequest` carrying capability scope, target, risk tier, requester, and context source.
   - SHA-256 confirmation hashes guarantee that spoken approvals bind strictly to the exact tool and parameters requested.
2. **Capability Scopes & Risk Tiers:**
   - **[GREEN]** Read-only local operations (auto-approved).
   - **[YELLOW]** Reversible local operations.
   - **[ORANGE]** External or state-modifying actions (requires spoken confirmation).
   - **[RED]** Destructive or critical system operations (requires voice confirmation and passphrase).
3. **Observe -> Act -> Verify -> Replan:**
   - Actions are validated post-execution with independent verifiers. If verification fails, the recovery classifier diagnoses the failure and triggers an observation-aware replan.
4. **Context Priming & Retention:**
   - Relevant semantic memories, project knowledge, user preferences, and skills are bundled before planning, preventing prompt clutter while scoring memory confidence from evidence.
5. **Structured Audit Logging:**
   - Lifecycle audit events are logged to daily JSONL files in `data/audit/` with sensitive arguments (passwords, tokens) automatically redacted.

---

## Configuration & Personalization

### 1. Customizing Personas (Owner vs. Guest)
FRIDAY adjusts her personality dynamically based on who is speaking. You can customize her responses in [`config/personas.yaml`](config/personas.yaml) without touching code:

```yaml
owner_persona: |
  You are speaking to your creator and primary user, Boss.
  Persona Rules:
  - Respond in a loyal, confident, concise, and natural tone. Address them as "Boss".
  - Never say robotic phrases like "I'm just a virtual assistant" or "As an AI model".
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
FRIDAY uses SpeechBrain neural speaker verification (ECAPA-TDNN) to distinguish your voice from others:
1. Run the interactive voice enrollment utility while wearing your headset / normal mic:
   ```powershell
   python scripts/enroll_voice.py
   ```
2. The tool records **3 short audio clips** (4 seconds each), saves them to `data/voice_enrollment/`, extracts your reference speaker embedding, and verifies cross-consistency.
3. When audio is received, FRIDAY compares the speaker embedding against these reference files to identify you as the **Owner** (or a **Guest**).

---

### 3. Setting Your Security Passphrase
For critical [RED] tier actions (such as file deletions, code self-upgrades, or system shutdowns), FRIDAY requires a spoken passphrase verified via SHA-256:
1. Run the security passphrase configuration utility:
   ```powershell
   python scripts/set_passphrase.py
   ```
2. Enter and confirm your secret phrase (e.g. `"omega override"` or `"jarvis protocol"`).
3. The utility hashes the phrase with SHA-256 and writes `PASSPHRASE_HASH=<hash>` to `.env`.
4. When prompted during critical actions, speak your passphrase aloud.

---

### 4. Neural Speech Synthesis (Chatterbox Turbo) & Expression Bank
FRIDAY uses Resemble AI's Chatterbox Turbo for expressive, natural voice output:
- **Consistent Lune Voice Model:** Generates 100% of spoken responses using local Chatterbox Turbo on CUDA (`models/voice_reference.wav`), providing zero network latency, zero cloud API limits, and a consistent vocal profile across all interactions.
- **Multilingual Comprehension & English Spoken Output:** Comprehends speech across a prioritized chain: **English > Indonesian > Sundanese > Other languages**. Whatever language is spoken to her, Friday formulates and delivers her spoken replies in English, maintaining her signature British wit and persona while addressing you as "Boss".
- **Neural Silero VAD Stream Gating & Pre-Speech Ring Buffer:** A rolling 3-chunk pre-speech ring buffer (~192ms) captures leading soft consonants ('th', 's', 'p', 'f', 'h') and flushes them to the recognition stream upon speech detection, while neural Silero VAD suppresses ambient room noise, fan hums, and keyboard clicks.
- **Anti-Interruption & Audio Queue Stability:** Pre-playback synthesis is protected from premature cancellation by ambient sounds, and asynchronous transcription race conditions are eliminated so generated responses reliably play through the speakers.
- **Master Centroid & 12 Precompiled Emotion Conditionals:** Uses `scripts/build_voice_profiles.py` to compile reference latents (`master.pt`, `neutral.pt`, `happy.pt`, `sigh.pt`, `chuckle.pt`, `sarcastic.pt`, `angry.pt`, `whispering.pt`, etc.) in `data/voices/conditionals/`.
- **Continuous Latent Blending:** Dynamically interpolates speaker embeddings and style conditioning with 0ms disk overhead.
- **Deterministic Speech Director:** A dedicated rule-based prosody director (`src/friday/interaction/speech_director.py`) injects calibrated vocal tags (`[sigh]`, `[gasp]`, `[chuckle]`) and selects emotional condition profiles.

---

### 5. Teaching Skills & Multi-Step Routines

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
You can say:
- *"Remember that my default project directory is C:\Dev\MyProject"*
- *"Remember that my favorite browser is Firefox"*
These facts are stored in SQLite semantic memory and recalled via Context Priming.

---

### 6. Local SearXNG Search Service
FRIDAY uses a local, self-hosted SearXNG container for privacy-respecting general web search:
1. Ensure Docker Desktop is running.
2. Start the local SearXNG service:
   ```powershell
   cd ops/searxng
   docker compose up -d
   ```
3. The instance is accessible at `http://127.0.0.1:8080` with JSON format enabled. Wikipedia and Google News remain active as specialized fallbacks.

---

## Holographic 3D Constellation Orb

The floating visualizer displays real-time system states:
- **Cyan (Pulsing):** Idle (waiting for wake word)
- **Emerald Green:** Listening (recording user speech)
- **Purple (Fast Rotation):** Thinking & Planning (LLM reasoning or tool execution)
- **Vivid Orange:** Speaking (neural TTS audio playback)
- **Gold:** Awaiting Confirmation (asking for user approval)
- **Red:** Blocked / Error (policy block or action failure)

*(You can click and drag the orb anywhere on your screen, or say "Hide yourself" / "Come back" to toggle visibility.)*

---

## Repository Structure

```
.
├── config/                     # Multi-environment YAML configurations & hardware profiles
│   ├── default.yaml            # Default system configuration
│   ├── gemini.yaml             # Gemini Live & Cloud configuration overlay
│   ├── personas.yaml           # Owner and Guest personality definitions
│   └── profiles/               # laptop.yaml, balanced.yaml, workstation.yaml
├── data/                       # Local SQLite database (friday.db), audit logs, trajectories, voice refs
├── models/                     # Model weights cache (chatterbox-turbo, openwakeword, voice references)
├── scripts/                    # setup.py, hardware_probe.py, benchmark_models.py, wipe_history.py
├── secrets/                    # Isolated credentials store (managed by SecretsManager)
├── skills/                     # Builtin and learned SKILL.md definitions
├── tests/                      # Automated unit, integration, and security test suites
├── workspace/                  # Sandboxed agent workspace
├── src/friday/
│   ├── __main__.py             # Module execution entrypoint
│   ├── app.py                  # Orchestrator assembly and boot runner
│   ├── config.py               # Pydantic configuration loader
│   ├── agent/                  # Orchestrator, Planner, Executor, Evaluator, Steering
│   ├── security/               # ActionRequest, PolicyEngine, Authorization, VoiceAuth, SecretsManager
│   ├── models/                 # ModelRouter, OllamaBackend, CloudBackend, GeminiBackend, HardwareProbe
│   ├── tools/                  # System, filesystem, applications, computer, browser, gmail, terminal
│   ├── computer/               # Controller, TargetResolver, ScreenObserver, SafetyCheck, Verification
│   ├── browser/                # Controller, PageExtractor, BrowserNavigator, BrowserVerifier
│   ├── online/                 # WebSearchProvider, CalendarClient, GmailClient, CapabilityGate
│   ├── memory/                 # Database (FTS5), PrimingEngine, RetentionManager, Semantic, Preferences
│   ├── skills/                 # SkillLoader, SkillRegistry, SkillSandbox, SkillRuntime
│   ├── learning/               # TrajectoryRecorder, PatternDistiller, SkillLearner, Scheduler
│   ├── jobs/                   # JobScheduler, JobRegistry, JobExecutor
│   ├── interaction/            # GeminiLiveSession, ChatterboxTurboSynthesizer, WakeWordListener, STT
│   └── ui/                     # PySide6 transparent window & Three.js holographic orb
├── pyproject.toml              # Packaging specification with dependencies and scripts
└── CHANGELOG.md                # Release history and milestone documentation
```

---

## Getting Started

### 1. Prerequisites
- **Operating System:** Windows 10/11
- **Python:** 3.11+ (Python 3.11-3.14 supported)
- **Audio:** Working microphone and speaker output
- **AI Backend:**
  - For Gemini Live mode: A Google Gemini API key
  - For Local mode: [Ollama](https://ollama.com) installed and running locally (`ollama pull qwen3:8b`)

### 2. Installation & First-Run Setup
```powershell
# 1. Clone the repository
git clone https://github.com/Agri99/F.R.I.D.A.Y._v2.git
cd F.R.I.D.A.Y._v2

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -e .

# 4. Configure Gemini API Key (if using Gemini Live mode)
python -c "from friday.security.secrets import SecretsManager; SecretsManager().set('gemini_api_key', 'YOUR_KEY_HERE')"

# 5. Run first-time setup wizard
python scripts/setup.py
```

---

## Running FRIDAY

### 1. Gemini Live Bidirectional Voice Mode (Recommended)
Connects directly to Google Gemini Live API for low-latency, real-time voice conversation, with speech synthesized through local Chatterbox Turbo neural voice:
```powershell
python -m friday --gemini
```
- FRIDAY boots up and speaks a natural, varied greeting (e.g. *"All systems operational, Boss. Ready when you are."*).
- Say **"FRIDAY"** to initiate conversation.
- Once active, FRIDAY maintains a 10-second post-speech follow-up window, allowing natural back-and-forth dialogue without repeating the wake word.
- Barge-in interruption allows cutting off speech naturally by speaking over playback.

### 2. Local Ollama Voice Mode
Runs fully on-device using local Ollama models (`qwen3:8b`) and local speech recognition:
```powershell
python -m friday
```

### 3. Text / CLI Smoke Test Mode
Runs in interactive terminal mode without opening audio streams:
```powershell
python -m friday --text
```

### 4. Database Maintenance
To clear conversation history and reset memory indices:
```powershell
python scripts/wipe_history.py
```

---

## Testing & Verification

Run the automated test suite:
```powershell
pytest tests/ -q
```
All core unit, interaction, security, and integration tests execute across the test matrix.
