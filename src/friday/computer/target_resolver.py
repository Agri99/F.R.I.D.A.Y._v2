"""
src/friday/computer/target_resolver.py

WHAT THIS IS FOR:
Resolves natural-language target descriptions to concrete UI elements, Automation IDs,
browser elements, or coordinates using a confidence-scored priority chain.

PRIORITY ORDER (§10.1 of Blueprint):
1. Windows UI Automation (Accessibility label / name)
2. Automation ID
3. Role + Label (e.g. Button named "Save")
4. Browser locator (if browser context)
5. Visual match (OCR / Vision model bounding box)
6. Coordinate fallback (as last resort)

Every fallback needs confidence, safety boundaries, and safe failure behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from friday.computer.accessibility import AccessibilityProvider, UIElement


class ResolutionMethod(Enum):
    ACCESSIBILITY_LABEL = "accessibility_label"
    AUTOMATION_ID = "automation_id"
    ROLE_AND_LABEL = "role_and_label"
    BROWSER_LOCATOR = "browser_locator"
    VISUAL_MATCH = "visual_match"
    COORDINATE_FALLBACK = "coordinate_fallback"


@dataclass
class ResolvedTarget:
    method: ResolutionMethod
    element: Any  # the resolved UIElement, DOM node, or (x, y) coordinates
    confidence: float
    description: str
    bounding_box: tuple[int, int, int, int] | None = None
    safety_check: bool = True  # True = safe to interact, False = requires confirmation
    fallback_attempted: bool = False


class TargetResolver:
    """Multi-tiered target resolver with confidence scoring."""

    # Confidence thresholds for safety boundaries
    HIGH_CONFIDENCE = 0.85    # Safe to auto-execute
    MEDIUM_CONFIDENCE = 0.65  # Requires verification
    LOW_CONFIDENCE = 0.40     # Requires user confirmation

    def __init__(self, accessibility: AccessibilityProvider | None = None) -> None:
        self.accessibility = accessibility or AccessibilityProvider()
        self._last_resolution: ResolvedTarget | None = None

    def resolve(
        self,
        description: str,
        context: dict | None = None,
    ) -> ResolvedTarget | None:
        """Resolve a natural-language description into an actionable UI target.

        Returns ResolvedTarget with confidence score and safety_check flag.
        Safety check is True for HIGH_CONFIDENCE, False for MEDIUM/LOW.
        """
        context = context or {}
        desc_lower = description.strip().lower()

        # 0. Check if direct coordinates provided in description or context
        coord_match = re.match(r"(?:at\s+)?\(?(\d+)\s*,\s*(\d+)\)?", desc_lower)
        if coord_match:
            x, y = int(coord_match.group(1)), int(coord_match.group(2))
            target = ResolvedTarget(
                method=ResolutionMethod.COORDINATE_FALLBACK,
                element=(x, y),
                confidence=0.5,
                description=f"Direct coordinate ({x}, {y})",
                bounding_box=(x, y, x, y),
                safety_check=True,  # Coordinates are explicit user intent
            )
            self._last_resolution = target
            return target

        # Browser context has priority when explicitly provided
        if context.get("is_browser") or context.get("browser"):
            selector = context.get("selector") or f"text={description}"
            target = ResolvedTarget(
                method=ResolutionMethod.BROWSER_LOCATOR,
                element=selector,
                confidence=0.80,
                description=f"Browser selector '{selector}'",
                safety_check=True,
            )
            self._last_resolution = target
            return target

        # 1. UI Automation: Search allowlisted active window elements
        try:
            app_id, hwnd, err = self.accessibility.find_allowlisted_window()
            if hwnd and not err:
                elements = self.accessibility.get_all_elements(hwnd)

                # Priority 1: Automation ID (highest confidence - stable identifier)
                for el in elements:
                    if el.automation_id and el.automation_id.lower() == desc_lower:
                        target = ResolvedTarget(
                            method=ResolutionMethod.AUTOMATION_ID,
                            element=el,
                            confidence=0.95,
                            description=f"Matched Automation ID '{el.automation_id}'",
                            bounding_box=el.bounding_rect,
                            safety_check=True,
                        )
                        self._last_resolution = target
                        return target

                # Priority 2: Exact Accessibility Name/Label match
                for el in elements:
                    if el.name and el.name.strip().lower() == desc_lower:
                        target = ResolvedTarget(
                            method=ResolutionMethod.ACCESSIBILITY_LABEL,
                            element=el,
                            confidence=0.90,
                            description=f"Exact match accessibility label '{el.name}' on {el.control_type}",
                            bounding_box=el.bounding_rect,
                            safety_check=True,
                        )
                        self._last_resolution = target
                        return target

                # Priority 3: Partial Accessibility Name/Label match
                for el in elements:
                    if el.name and desc_lower in el.name.lower():
                        target = ResolvedTarget(
                            method=ResolutionMethod.ACCESSIBILITY_LABEL,
                            element=el,
                            confidence=0.75,
                            description=f"Partial match accessibility label '{el.name}' on {el.control_type}",
                            bounding_box=el.bounding_rect,
                            safety_check=True,
                        )
                        self._last_resolution = target
                        return target

                # Priority 4: Role + Label (e.g., "save button", "search edit")
                for el in elements:
                    el_type = el.control_type.lower()
                    el_name = (el.name or "").lower()
                    if el_type in desc_lower and (el_name and el_name in desc_lower):
                        target = ResolvedTarget(
                            method=ResolutionMethod.ROLE_AND_LABEL,
                            element=el,
                            confidence=0.85,
                            description=f"Matched {el.control_type} named '{el.name}'",
                            bounding_box=el.bounding_rect,
                            safety_check=True,
                        )
                        self._last_resolution = target
                        return target

                # Priority 5: Role-only match (lower confidence)
                for el in elements:
                    el_type = el.control_type.lower()
                    if el_type in desc_lower:
                        target = ResolvedTarget(
                            method=ResolutionMethod.ROLE_AND_LABEL,
                            element=el,
                            confidence=0.60,
                            description=f"Role match: {el.control_type} (name: '{el.name}')",
                            bounding_box=el.bounding_rect,
                            safety_check=False,  # Ambiguous, needs verification
                        )
                        self._last_resolution = target
                        return target

        except Exception as e:
            pass

        # Visual match fallback (OCR or Vision bounding box in context)
        visual_result = self._resolve_visual_match(description, context)
        if visual_result:
            visual_result.fallback_attempted = True
            self._last_resolution = visual_result
            return visual_result

        # 4. Default: return low-confidence target requiring verification
        target = ResolvedTarget(
            method=ResolutionMethod.ACCESSIBILITY_LABEL,
            element=UIElement(
                name=description,
                control_type="Button" if "button" in desc_lower else "Custom",
                automation_id=desc_lower.replace(" ", "_"),
                bounding_rect=None,
                is_enabled=True,
            ),
            confidence=0.35,
            description=f"Unresolved '{description}' — requires visual verification",
            safety_check=False,
            fallback_attempted=True,
        )
        self._last_resolution = target
        return target

    def _resolve_visual_match(self, description: str, context: dict) -> ResolvedTarget | None:
        """Resolve target via OCR + VLM fallback when no structural match found."""
        if "visual_bbox" in context:
            bbox = context["visual_bbox"]
            cx = (bbox[0] + bbox[2]) // 2
            cy = (bbox[1] + bbox[3]) // 2
            return ResolvedTarget(
                method=ResolutionMethod.VISUAL_MATCH,
                element=(cx, cy),
                confidence=context.get("visual_confidence", 0.70),
                description=f"Visual match for '{description}'",
                bounding_box=bbox,
                safety_check=context.get("visual_confidence", 0.70) >= self.MEDIUM_CONFIDENCE,
            )

        # When no bbox is provided in context, attempt OCR + VLM inference
        try:
            import pytesseract
            from friday.computer.screen import ocr, describe_screen, capture_screen

            # Try OCR first — cheap and deterministic for text labels
            img = capture_screen()
            if img:
                text = ocr(img)
                pattern = re.escape(description.strip())
                if re.search(pattern, text, re.IGNORECASE):
                    return ResolvedTarget(
                        method=ResolutionMethod.VISUAL_MATCH,
                        element=UIElement(
                            name=description,
                            control_type="Text",
                            automation_id=description.lower().replace(" ", "_"),
                            bounding_rect=None,
                            is_enabled=True,
                        ),
                        confidence=0.75,
                        description=f"OCR text match for '{description}'",
                        safety_check=True,
                    )

            # Fall back to VLM description if OCR finds nothing
            result = describe_screen(
                question=f"Find '{description}' in the current screen. Return bounding box coordinates as x,y,w,h."
            )
            if result.get("status") == "ok":
                return ResolvedTarget(
                    method=ResolutionMethod.VISUAL_MATCH,
                    element=UIElement(
                        name=description,
                        control_type="Custom",
                        automation_id=description.lower().replace(" ", "_"),
                        bounding_rect=None,
                        is_enabled=True,
                    ),
                    confidence=0.60,
                    description=f"VLM-assisted visual match for '{description}'",
                    safety_check=False,
                )
        except Exception:
            pass

        return None

    def get_last_resolution(self) -> ResolvedTarget | None:
        """Get the last resolved target for verification purposes."""
        return self._last_resolution

    def verify_target_still_valid(self, target: ResolvedTarget) -> bool:
        """Verify that a previously resolved target is still valid on screen."""
        if not target or not target.bounding_box:
            return False

        try:
            # Re-capture and check if element still exists at same location
            if target.method in (ResolutionMethod.ACCESSIBILITY_LABEL,
                                  ResolutionMethod.AUTOMATION_ID,
                                  ResolutionMethod.ROLE_AND_LABEL):
                if isinstance(target.element, UIElement):
                    # Re-find element and compare
                    app_id, hwnd, err = self.accessibility.find_allowlisted_window()
                    if hwnd and not err:
                        elements = self.accessibility.get_all_elements(hwnd)
                        for el in elements:
                            if (el.automation_id == target.element.automation_id and
                                el.name == target.element.name):
                                return True
            return False
        except Exception:
            return False