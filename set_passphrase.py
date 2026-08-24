import hashlib
from getpass import getpass

phrase = getpass("Set your critical-action passphrase (input hidden): ").strip().lower()
confirm = getpass("Confirm passphrase: ").strip().lower()

if phrase != confirm:
    print("Passphrases didn't match. Nothing saved.")
else:
    hashed = hashlib.sha256(phrase.encode()).hexdigest()
    print("\nAdd this line to your .env file:")
    print(f"PASSPHRASE_HASH={hashed}")