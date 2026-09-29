"""
scripts/set_passphrase.py

Security Passphrase Configuration Tool for F.R.I.D.A.Y.
Hashes your secret spoken passphrase using SHA-256 and securely stores
PASSPHRASE_HASH in your .env file for RED-tier critical action authorization.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from friday.security.passphrase import set_passphrase, verify_passphrase


def update_env_file(key: str, value: str) -> None:
    env_path = _ROOT / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    print("=======================================================")
    print("       F.R.I.D.A.Y. Security Passphrase Setup          ")
    print("=======================================================")
    print("For critical operations (such as code self-upgrades, file")
    print("deletions, or system shutdown), F.R.I.D.A.Y. requires a")
    print("spoken passphrase verified against a SHA-256 hash.\n")

    current_hash = os.environ.get("PASSPHRASE_HASH")
    if current_hash:
        print(f"[*] Current status: Configured (Hash: {current_hash[:8]}...)")
    else:
        print("[*] Current status: NOT CONFIGURED (Critical actions currently fail-closed)")

    print("\nEnter your new security passphrase (e.g., 'jarvis protocol' or 'omega override'):")
    phrase = input("Passphrase: ").strip()

    if not phrase:
        print("[-] Passphrase cannot be empty. Aborted.")
        return

    phrase_confirm = input("Confirm passphrase: ").strip()
    if phrase.lower() != phrase_confirm.lower():
        print("[-] Passphrases do not match. Aborted.")
        return

    pass_hash = set_passphrase(phrase)
    update_env_file("PASSPHRASE_HASH", pass_hash)
    os.environ["PASSPHRASE_HASH"] = pass_hash

    # Verification test
    if verify_passphrase(phrase):
        print("\n[+] Passphrase successfully configured and verified!")
        print(f"    SHA-256 Hash: {pass_hash}")
        print("    Saved to: .env (PASSPHRASE_HASH)")
        print("\nWhen prompted by Friday for critical actions, speak this phrase clearly.")
    else:
        print("[-] Verification failed. Please check permissions on .env file.")


if __name__ == "__main__":
    main()
