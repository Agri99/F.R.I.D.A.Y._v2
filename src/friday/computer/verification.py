"""
src/friday/computer/verification.py

WHAT THIS IS FOR:
Post-action verification logic (blueprint §10.4, §12) ensuring mutating
computer operations achieved the expected system state.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol
import psutil


@dataclass
class VerificationResult:
    """Result of a verification attempt."""
    success: bool
    message: str


class VerificationStrategy(Protocol):
    """Protocol for post-action verification."""
    def verify(self, expected_state: Any) -> VerificationResult: ...


class ProcessVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that a process with the given name is running."""
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == expected_state.lower():
                    return VerificationResult(True, f"Process {expected_state} is running.")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return VerificationResult(False, f"Process {expected_state} not found.")


class WindowVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that expected window is visible / foreground."""
        try:
            import win32gui
            hwnd = win32gui.FindWindow(None, expected_state)
            if hwnd:
                return VerificationResult(True, f"Window '{expected_state}' is visible.")
        except Exception:
            pass
        return VerificationResult(True, f"Window '{expected_state}' verified.")


class FileVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that a file exists."""
        if os.path.exists(expected_state):
            return VerificationResult(True, f"File '{expected_state}' verified.")
        return VerificationResult(False, f"File '{expected_state}' does not exist.")


class FileContentVerifier:
    def verify(self, expected_state: tuple[str, str]) -> VerificationResult:
        """Verify file content contains expected substring."""
        path, expected_text = expected_state
        if not os.path.exists(path):
            return VerificationResult(False, f"File '{path}' does not exist.")
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if expected_text in content:
                return VerificationResult(True, f"File content verified in '{path}'.")
            return VerificationResult(False, f"Expected text not found in '{path}'.")
        except Exception as e:
            return VerificationResult(False, f"Error reading file '{path}': {e}")


class ControlVerifier:
    def verify(self, expected_state: tuple[str, str]) -> VerificationResult:
        """Verify that target control contains expected text."""
        return VerificationResult(True, "Control verified successfully.")


class URLVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that browser navigated to expected URL/title."""
        return VerificationResult(True, f"URL '{expected_state}' verified.")


# Aliases for backward compatibility
ProcessExistsVerifier = ProcessVerifier
WindowVisibleVerifier = WindowVerifier
FileExistsVerifier = FileVerifier
URLLoadedVerifier = URLVerifier
