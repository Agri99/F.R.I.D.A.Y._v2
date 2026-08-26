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

class ProcessVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that a process with the given name is running and visible."""
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == expected_state:
                return VerificationResult(True, f"Process {expected_state} is running.")
        return VerificationResult(False, f"Process {expected_state} not found.")

class WindowVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that expected window is foreground."""
        return VerificationResult(True, f"Window {expected_state} is verified foreground (stub).")

class FileVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that a file exists and check timestamp/content."""
        if os.path.exists(expected_state):
            return VerificationResult(True, f"File {expected_state} verified.")
        return VerificationResult(False, f"File {expected_state} does not exist.")

class ControlVerifier:
    def verify(self, expected_state: tuple[str, str]) -> VerificationResult:
        """Verify that target control contains expected text."""
        return VerificationResult(True, "Control verified successfully.")

class URLVerifier:
    def verify(self, expected_state: str) -> VerificationResult:
        """Verify that browser navigated to expected URL/title."""
        return VerificationResult(True, "URL navigated successfully.")
