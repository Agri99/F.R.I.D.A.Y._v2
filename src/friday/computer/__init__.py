"""
src/friday/computer/__init__.py

Computer subsystem for F.R.I.D.A.Y. (UI Automation, Mouse, Keyboard, Target Resolution, Verification, Safety).
"""

from __future__ import annotations

from friday.computer.controller import (
    ComputerController,
    Observation,
    Target,
    ActionResult,
    WindowsComputerController,
)
from friday.computer.accessibility import AccessibilityProvider, UIElement
from friday.computer.windows import WindowInfo, WindowManager
from friday.computer.target_resolver import (
    ResolutionMethod,
    ResolvedTarget,
    TargetResolver,
)
from friday.computer.safety import SafetyCheck, SafetyResult
from friday.computer.verification import (
    VerificationResult,
    VerificationStrategy,
    ProcessVerifier,
    WindowVerifier,
    FileVerifier,
    FileContentVerifier,
    ControlVerifier,
    URLVerifier,
    ProcessExistsVerifier,
    WindowVisibleVerifier,
    FileExistsVerifier,
    URLLoadedVerifier,
)

__all__ = [
    "ComputerController",
    "Observation",
    "Target",
    "ActionResult",
    "WindowsComputerController",
    "AccessibilityProvider",
    "UIElement",
    "WindowManager",
    "ResolutionMethod",
    "ResolvedTarget",
    "TargetResolver",
    "SafetyCheck",
    "SafetyResult",
    "VerificationResult",
    "VerificationStrategy",
    "ProcessVerifier",
    "WindowVerifier",
    "FileVerifier",
    "FileContentVerifier",
    "ControlVerifier",
    "URLVerifier",
    "ProcessExistsVerifier",
    "WindowVisibleVerifier",
    "FileExistsVerifier",
    "URLLoadedVerifier",
]
