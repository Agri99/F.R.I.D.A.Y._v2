# F.R.I.D.A.Y.

A local-first, voice-controlled AI assistant for Windows. Runs entirely on-device — speech recognition, the language model, and text-to-speech all execute locally, with no cloud dependency for the core assistant loop.

## Overview

FRIDAY listens for a wake word, transcribes speech locally, reasons with a local LLM through Ollama, and speaks its replies back using local text-to-speech. It can control local applications, read and describe the screen, manage files in a sandboxed workspace, and interact with Gmail and Google Calendar in read-only mode. A separate floating 3D orb visualizes the assistant's state.

Every action that could modify state, access sensitive information, or affect the system is classified by risk and gated accordingly — from no confirmation needed, up to spoken confirmation with voice verification and a passphrase for the most sensitive actions.

## Core capabilities

- Wake word detection ("FRIDAY"), continuous silence-based recording, and a short follow-up window so a conversation doesn't require repeating the wake word every turn
- Barge-in: interrupt FRIDAY mid-response by saying the wake word again (reliable on headphones; built-in speaker/mic setups are limited by acoustic feedback)
- Persistent conversation memory across sessions
- Local speech recognition (faster-whisper) and speech synthesis (Piper)
- Tool-calling via a local LLM (Qwen3, served through Ollama)
- File creation/deletion inside a sandboxed workspace folder
- Application launching from a fixed allowlist
- Screen vision (general scene description) and OCR (exact text extraction)
- System control: volume, active window management, screenshots, timers/reminders
- Web search and URL opening
- Gmail inbox and Google Calendar checking (read-only)
- A skills system: save a sequence of completed actions as a named, reusable skill and run it again later
- A floating 3D orb (separate process) that visually reflects FRIDAY's state — idle, listening, thinking, speaking — and can be shown, hidden, or repositioned by voice or drag

## Security architecture

FRIDAY's permission model is independent of the language model. The LLM can request a tool call, but a separate Python layer decides whether it is allowed to run:

- **Risk tiers**: every tool is classified GREEN (read-only), YELLOW (reversible local change), ORANGE (external effect), or RED (destructive or system-wide)
- **Confirmation gate**: ORANGE and RED actions require an explicit spoken "yes," matched against the user's transcribed words — not inferred by the model
- **Preview-then-confirm**: destructive tools resolve their target first (e.g., confirming a file exists) before asking for confirmation, so the user approves a specific, verified action
- **Voice authorization**: confirmations for ORANGE/RED actions are verified against an enrolled voiceprint (SpeechBrain speaker verification), so a recording or a different voice cannot approve an action
- **Passphrase second factor**: reserved for future "critical" (irreversible) actions, layered on top of voice verification, not replacing it
- **Fail-closed defaults**: unknown tools, unrecognized paths, and unset credentials are rejected rather than allowed by default
- **Sandboxing**: file operations are confined to a dedicated workspace folder regardless of what path is requested
- **Local audit log**: every tool call is recorded with its arguments, result, and whether it required confirmation
- **Untrusted content handling**: content read from the web or the screen is treated as data, never as instructions

## Architecture

FRIDAY runs as two independent local processes that communicate over a WebSocket on `127.0.0.1`:

- **The assistant process** — the voice loop, the LLM, tool execution, and all security logic
- **The orb process** — a PySide6 window hosting a Three.js scene, subscribing to state updates

The orb has no authority over the assistant; it only reflects state and forwards a small set of user-initiated commands (show, hide, shut down).

## Requirements

- Windows
- Python 3.11+
- [Ollama](https://ollama.com), with a local model pulled (e.g. `ollama pull qwen3:8b`)
- A Google Cloud project with the Gmail API and Calendar API enabled, and an OAuth client credentials file, if using Gmail/Calendar features
- Tesseract OCR, if using screen text reading

## Setup

1. Clone the repository and install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Place your Google OAuth credentials file in the project root as `credentials.json` (only required for Gmail/Calendar features).
3. Copy `.env.example` to `.env` and configure as needed.
4. Run the enrollment script once to register your voice for confirmation authorization:
   ```
   python voice_enroll.py
   ```
5. (Optional) Set a passphrase for future critical-action confirmation:
   ```
   python set_passphrase.py
   ```

## Running

Start both the assistant and the orb together:
```
python run_friday.py
```

Or run the assistant on its own:
```
python test_voice.py
```

Say "FRIDAY" to begin. The first Gmail or Calendar request will open a browser window for one-time Google account authorization.

## Project status

The core assistant, security architecture, local tool set, Gmail/Calendar integration, skills system, and orb are complete and functional. Open items include resolving barge-in reliability on built-in laptop hardware, finalizing the screen-vision model choice, packaging as a standalone application, and a planned Notion integration.

## Disclaimer

This is a personal project built for learning and personal use. It executes real actions on the host machine — review the tool definitions and risk classifications before granting it access to anything sensitive.
The credentials.json file is specific to your Google Cloud project and cannot be shared. Anyone setting up their own instance must create their own Google Cloud project at console.cloud.google.com, enable the Gmail API and Google Calendar API, create a Desktop OAuth client under APIs & Services, and download that client's credentials.json. Add your own Google account as a test user in Google Auth Platform before running for the first time.
