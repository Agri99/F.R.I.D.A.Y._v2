"""Computer subsystem for F.R.I.D.A.Y. v2."""
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

from friday.computer.verification import (
    VerificationStrategy,
    ProcessExistsVerifier,
    WindowVisibleVerifier,
    FileExistsVerifier,
    FileContentVerifier,
    URLLoadedVerifier,
)

__all__ = [
    "ComputerController",
    "Observation",
    "Target",
    "ActionResult",
    "WindowInfo",
    "WindowsComputerController",
    "AccessibilityProvider",
    "UIElement",
    "WindowManager",
    "VerificationStrategy",
    "ProcessExistsVerifier",
    "WindowVisibleVerifier",
    "FileExistsVerifier",
    "FileContentVerifier",
    "URLLoadedVerifier",
]
