"""Post-action verification logic."""
from __future__ import annotations
from typing import Protocol, Any
from dataclasses import dataclass
import psutil
import os

@dataclass
class VerificationResult:
    """Result of a verification attempt."""
    success: bool
    message: str

class VerificationStrategy(Protocol):
    """Protocol for post-action verification."""
    def verify(self, expected_state: Any) -> VerificationResult: ...

class ProcessExistsVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that a process with the given name is running."""
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == expected_state:
                return VerificationResult(True, f"Process {expected_state} is running.")
        return VerificationResult(False, f"Process {expected_state} not found.")

class WindowVisibleVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that a window with the given title is visible."""
        from friday.computer.windows import WindowManager
        windows = WindowManager().list_windows()
        for win in windows:
            if expected_state.lower() in win.title.lower():
                return VerificationResult(True, f"Window {expected_state} is visible.")
        return VerificationResult(False, f"Window {expected_state} not found.")

class FileExistsVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that a file exists at the given path."""
        if os.path.exists(expected_state):
            return VerificationResult(True, f"File {expected_state} exists.")
        return VerificationResult(False, f"File {expected_state} does not exist.")

class FileContentVerifier:
    def verify(self, expected_state: tuple[str, str]) -> VerificationResult:
        """Verify that a file contains the expected text."""
        path, text = expected_state
        if not os.path.exists(path):
            return VerificationResult(False, f"File {path} does not exist.")
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                if text in content:
                    return VerificationResult(True, f"File {path} contains expected text.")
                return VerificationResult(False, f"File {path} does not contain expected text.")
        except Exception as e:
            return VerificationResult(False, f"Error reading {path}: {e}")

class URLLoadedVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that a URL was loaded (placeholder implementation)."""
        return VerificationResult(False, "URL verification not fully implemented.")
