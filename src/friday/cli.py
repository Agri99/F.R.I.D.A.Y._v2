"""
cli.py — Master CLI Router for F.R.I.D.A.Y. v2

Routes commands like:
  friday doctor
  friday test-fault
  friday --brain gemini
  friday --gemini
  friday --brain qwen
  friday --text
  friday (interactive brain selection)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure src/ and root are in sys.path when invoked directly
_SRC_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _SRC_DIR.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

try:
    import dotenv
    dotenv.load_dotenv()
except Exception:
    pass


def _ensure_gemini_key() -> bool:
    """Check if GEMINI_API_KEY is configured; if interactive, prompt to save it."""
    if os.environ.get("GEMINI_API_KEY"):
        return True

    from friday.security.secrets import SecretsManager
    secrets = SecretsManager()
    key = secrets.get("gemini_api_key") or secrets.get("google/gemini_api_key")
    if key:
        os.environ["GEMINI_API_KEY"] = key
        return True

    if sys.stdin.isatty():
        print("\n" + "─" * 54)
        print("  [!] Google Gemini API Key Required")
        print("  Get a free API key at: https://aistudio.google.com/app/apikey")
        print("─" * 54)
        entered = input("Enter GEMINI_API_KEY (or Enter to cancel): ").strip()
        if entered:
            secrets_dir = Path("secrets")
            secrets_dir.mkdir(parents=True, exist_ok=True)
            key_path = secrets_dir / "gemini_api_key"
            key_path.write_text(entered, encoding="utf-8")
            os.environ["GEMINI_API_KEY"] = entered
            print("[+] API key securely saved to secrets/gemini_api_key.\n")
            return True

    return False


def _resolve_brain_choice() -> str:
    """Determine whether to use Qwen or Gemini from CLI flags or interactive prompt."""
    args = sys.argv[1:]

    # Check CLI flags
    for i, arg in enumerate(args):
        if arg == "--gemini":
            return "gemini"
        if arg == "--qwen":
            return "qwen"
        if arg == "--brain" and i + 1 < len(args):
            return args[i + 1].lower()
        if arg.startswith("--brain="):
            return arg.split("=", 1)[1].lower()

    # If running interactively, prompt the user
    if sys.stdin.isatty():
        print("\n" + "═" * 54)
        print("       F.R.I.D.A.Y. — Brain Engine Selection")
        print("═" * 54)
        print("  [1] Qwen (Local / Ollama - Offline & Private)")
        print("  [2] Google Gemini (Cloud API - Fast & Smart)")
        print("═" * 54)
        try:
            choice = input("Select brain [1/2] (Default: 1): ").strip()
            if choice in ("2", "gemini", "g"):
                return "gemini"
        except (KeyboardInterrupt, EOFError):
            print()
            return "qwen"

    # Default fallback
    return "qwen"


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "doctor":
            from scripts.doctor import run_diagnostics
            sys.argv.pop(1)
            run_diagnostics()
            sys.exit(0)
            
        elif cmd == "test-fault":
            from scripts.test_fault import parser, run_fault_injection
            sys.argv.pop(1)
            args = parser.parse_args()
            sys.exit(run_fault_injection(args))

        elif cmd in ("--help", "-h"):
            print("F.R.I.D.A.Y. v2 — Local-First Personal Computer AI\n")
            print("Usage:")
            print("  friday [options]")
            print("  python -m friday [options]\n")
            print("Options:")
            print("  --brain [qwen|gemini]  Select AI brain engine")
            print("  --gemini               Use Google Gemini API brain")
            print("  --qwen                 Use local Qwen/Ollama brain (default)")
            print("  --text                 Launch in interactive text-only mode")
            print("  doctor                 Run hardware and dependency diagnostics")
            print("  test-fault             Run fault injection tests")
            sys.exit(0)

    brain = _resolve_brain_choice()
    if brain == "gemini":
        if not _ensure_gemini_key():
            print("[!] GEMINI_API_KEY is not configured. Falling back to local Qwen brain.\n")
            brain = "qwen"

    # Start the main app
    from friday.app import main as app_main
    app_main(brain=brain)


if __name__ == "__main__":
    main()
