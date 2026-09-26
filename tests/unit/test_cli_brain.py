"""Unit tests for CLI brain selection and flag parsing."""
import sys
from unittest.mock import patch
from friday.cli import _resolve_brain_choice


def test_cli_flag_gemini():
    with patch.object(sys, "argv", ["friday", "--gemini"]):
        assert _resolve_brain_choice() == "gemini"


def test_cli_flag_qwen():
    with patch.object(sys, "argv", ["friday", "--qwen"]):
        assert _resolve_brain_choice() == "qwen"


def test_cli_flag_brain_param():
    with patch.object(sys, "argv", ["friday", "--brain", "gemini"]):
        assert _resolve_brain_choice() == "gemini"

    with patch.object(sys, "argv", ["friday", "--brain", "qwen"]):
        assert _resolve_brain_choice() == "qwen"


def test_cli_flag_brain_equals():
    with patch.object(sys, "argv", ["friday", "--brain=gemini"]):
        assert _resolve_brain_choice() == "gemini"


def test_cli_non_interactive_defaults_qwen():
    with patch.object(sys, "argv", ["friday"]), patch("sys.stdin.isatty", return_value=False):
        assert _resolve_brain_choice() == "qwen"

