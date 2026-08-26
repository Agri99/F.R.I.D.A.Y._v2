# F.R.I.D.A.Y. v2

A local-first, privacy-respecting personal AI computer assistant for Windows 11. Designed from the ground up to operate through typed tools, independent policy verification, and hardware-agnostic local models.

---

## Overview

F.R.I.D.A.Y. (Female Replacement Intelligent Digital Assistant Youth) runs entirely on-device:
- **Speech Recognition:** `faster-whisper` (running locally on CPU/GPU)
- **Wake Word Detection:** `openWakeWord` with real-time audio barge-in
- **Reasoning & Planning:** Local LLM via [Ollama](https://ollama.com) (default: `qwen3:8b`) with multi-step task planning
- **Vision Perception:** Local vision models via Ollama (`llava`, `gemma3`, `qwen3-vl`) + Tesseract OCR
- **Speech Synthesis:** Local `Piper` neural TTS (`en_GB-jenny_dioco-medium`)
- **Computer-Use Subsystem:** Native Windows mouse/keyboard control, UI Automation (UIA), and window management
- **Visual Presence:** Floating 3D WebGL orb overlay hosted in PySide6 / Three.js via an isolated WebSocket state server

---

## Security & Architecture Principles

FRIDAY separates intelligence from execution (Principle D) and fails closed (Principle G):

1. **Capability Scopes & Risk Tiers:**
   - Every tool declares fine-grained capability scopes (`filesystem.read`, `gmail.send`, `windows.interact`, etc.) and a risk tier:
     - 🟢 **GREEN:** Read-only operations (auto-approved).
     - 🟡 **YELLOW:** Reversible local operations.
     - 🟠 **ORANGE:** External or state-modifying actions (requires spoken voice confirmation).
     - 🔴 **RED:** Destructive or critical system operations (requires voice confirmation + SHA-256 passphrase).
2. **Independent Authorization & Sandbox:**
   - The LLM cannot authorize its own actions.
   - File operations are sandboxed to the `workspace/` directory with path-traversal prevention.
   - Confirmation requests are action-bound with a 60-second TTL.
3. **Observe $\rightarrow$ Act $\rightarrow$ Verify:**
   - Tools provide independent post-execution state verifiers to confirm that expected state changes actually occurred.
4. **Structured Audit Logging:**
   - All tool invocations and authorization events are logged to daily JSONL files in `data/audit/` with sensitive arguments (passwords, tokens) automatically redacted.

---

## Repository Structure

```
c:\Dev\F.R.I.D.A.Y._v2\
├── config/                     # Multi-environment YAML configurations (default, development, production)
├── data/                       # Local SQLite database (friday.db), audit logs, trajectories, voice refs
├── models/                     # Piper TTS voice models, openWakeWord models, SpeechBrain weights
├── scripts/                    # healthcheck.py, benchmark_models.py, migrate_v1_skills.py
├── secrets/                    # OAuth credentials (credentials.json)
├── skills/                     # Builtin and learned SKILL.md definitions
├── tests/                      # Unit, security invariant, and smoke test suites
├── workspace/                  # Sandboxed agent workspace
├── src/friday/
│   ├── app.py                  # Single application entrypoint
│   ├── config.py               # Pydantic configuration loader
│   ├── models/                 # ModelProvider ABC, OllamaProvider, CloudProvider, ModelRouter
│   ├── security/               # PolicyEngine, CapabilityRegistry, PathValidator, AuditLogger, VoiceAuth
│   ├── agent/                  # AgentOrchestrator, TaskStateMachine, Planner, Executor, Evaluator, FastPath
│   ├── tools/                  # 33 typed tools across system, files, apps, computer, web, gmail, calendar
│   ├── computer/               # WindowsComputerController, accessibility (UIA), screen perception
│   ├── browser/                # BrowserController with URL safety & clean content extraction
│   ├── interaction/            # Voice loop, STT, TTS, wake word, and session management
│   ├── ui/                     # WebSocket orb server & client
│   ├── memory/                 # SQLite FTS5 conversation, episodic, semantic, and preference stores
│   └── learning/               # Trajectory logging, pattern distillation, and skill auto-promotion
└── pyproject.toml              # Project packaging and dependency specification
```

---

## Tool Ecosystem (33 Tools)

- **`system.*`**: `get_status`, `get_time`, `lock`, `shutdown_friday`
- **`filesystem.*`**: `list`, `read`, `write`, `move`, `delete` (sandboxed with previews)
- **`applications.*`**: `open`, `close` (allowlisted desktop apps)
- **`computer.*`**: `capture`, `describe_screen`, `read_screen_text`, `click`, `type`, `press`, `scroll`, `wait`, `active_window`, `control_window`
- **`browser.*`**: `open`, `search`, `observe` (plain-text content extraction)
- **`gmail.*`**: `search`, `read`, `send` (Google OAuth 2.0)
- **`calendar.*`**: `list`, `create`, `update`, `delete` (Google Calendar API)
- **`audio.*`**: `set_volume`, `mute`, `get_volume`
- **`timer.*`**: `set`, `cancel`

---

## Getting Started

### Prerequisites
- **Operating System:** Windows 10/11
- **Python:** 3.11+
- **[Ollama](https://ollama.com):** Installed and running locally
- **Local Models:**
  ```bash
  ollama pull qwen3:8b
  ollama pull llava
  ```
- **(Optional) Tesseract OCR:** Installed for exact on-screen text reading (`read_screen_text`)
- **(Optional) Google Cloud Credentials:** Place `credentials.json` in `secrets/` for Gmail/Calendar tools

### Installation

1. Clone the repository and navigate into the folder:
   ```bash
   cd c:\Dev\F.R.I.D.A.Y._v2
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -e .
   ```

4. Configure your environment:
   ```bash
   cp .env.example .env
   ```

---

## Running FRIDAY

### 1. Text / CLI Smoke Test Mode
Run a quick, text-only test without starting the voice loop or UI:
```bash
python -m friday.app --text
```
or
```bash
python src/friday/app.py --text
```

### 2. Full Voice & 3D Orb Mode
Start the complete voice assistant with the visual orb:
```bash
python src/friday/app.py
```
- Say **"FRIDAY"** to wake the assistant.
- Speak your command (e.g. *"What time is it?"*, *"Open Notepad and type Hello World"*, *"Check my upcoming calendar events"*).

---

## Testing & Verification

Run the comprehensive test suite (unit tests, security invariants, and smoke scenarios):
```bash
pytest tests/ -v
```

Run the system health check:
```bash
python scripts/healthcheck.py
```

Migrate legacy v1 skills:
```bash
python scripts/migrate_v1_skills.py
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
