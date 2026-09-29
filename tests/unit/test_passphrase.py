from __future__ import annotations

import os
from unittest.mock import patch

from friday.security.passphrase import set_passphrase, verify_passphrase


def test_passphrase_hashing_and_verification():
    secret = "jarvis protocol"
    h = set_passphrase(secret)
    assert len(h) == 64

    with patch.dict(os.environ, {"PASSPHRASE_HASH": h}):
        assert verify_passphrase("jarvis protocol")
        # Case insensitive and stripped
        assert verify_passphrase("  JARVIS PROTOCOL  ")
        # Incorrect phrase fails
        assert not verify_passphrase("wrong phrase")


def test_passphrase_fails_closed_when_unset():
    with patch.dict(os.environ, {}, clear=True):
        assert not verify_passphrase("anything")


def test_keyboard_unicode_type_text():
    from friday.computer.keyboard import type_text

    # Verify type_text handles string execution cleanly without error
    type_text("Hello, FRIDAY benchmark!", interval=0.0)
