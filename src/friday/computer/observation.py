"""
src/friday/computer/observation.py

WHAT THIS IS FOR:
Progressive perception pipeline (blueprint §36).

The observation pipeline is the single entry point for all screen perception.
It implements progressive perception:

    capture active screen/window
        -> identify relevant application
        -> crop relevant region
        -> OCR if needed
        -> vision model if needed
        -> rank semantic targets

Crucially, it NEVER sends a full screen to the vision model for every click.
The vision model is only invoked when cheaper strategies have failed and the
caller explicitly opts in.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from friday.computer.screen import (
    ScreenObserver,
    capture_screen,
    grab_screen_bytes,
    ocr,
    save_screenshot,
    compute_screen_hash,
    compare_screens,
    Observation,
)


class ObservationLevel(str, Enum):
    """Progressive perception levels, cheapest first."""
    CHEAP = "cheap"            # active window + OCR only
    TARGETED = "targeted"      # crop region + OCR
    FULL = "full"              # screenshot + VLM (expensive)


@dataclass
class ObservationRequest:
    """A request for screen perception."""
    region: tuple[int, int, int, int] | None = None  # crop region, if known
    app_hint: str | None = None                      # application context
    target_hint: str | None = None                   # what we're looking for
    allow_vision: bool = False                       # opt-in for expensive VLM
    max_vision_calls: int = 1                        # budget for VLM calls


@dataclass
class PerceptionResult:
    """Result of a perception request."""
    observation: Observation
    level_used: ObservationLevel
    targets: list[dict[str, Any]] = field(default_factory=list)
    vision_calls_used: int = 0
    timestamp: float = 0.0


class ObservationCollector:
    """Single entry point for all screen perception.

    Implements progressive perception so the vision model is only invoked
    when cheaper strategies have failed and the caller explicitly opts in.
    """

    def __init__(self) -> None:
        self.observer = ScreenObserver()
        self._last_observation: Observation | None = None
        self._vision_calls_this_turn: int = 0
        self._turn_started_at: float = 0.0

    def begin_turn(self) -> None:
        """Reset per-turn budgets."""
        self._vision_calls_this_turn = 0
        self._turn_started_at = time.time()

    def perceive(self, request: ObservationRequest) -> PerceptionResult:
        """Run the progressive perception pipeline.

        Strategy:
          1. CHEAP — active window title + full-screen OCR. Always runs.
          2. TARGETED — if a region is given, crop + OCR the region only.
          3. FULL — only if the caller opted in (allow_vision=True) and the
             budget hasn't been exhausted. Never sends a full screen to the
             vision model per click.
        """
        # Step 1: cheap observation (active window + OCR).
        cheap = self.observer.observe_cheap()
        self._last_observation = cheap

        # Step 2: targeted observation if a region is given.
        if request.region is not None:
            targeted = self.observer.observe_targeted(request.region)
            # Merge targeted OCR into the cheap observation.
            if targeted.ocr_text:
                cheap.ocr_text = targeted.ocr_text
            cheap.screenshot_path = targeted.screenshot_path
            level_used = ObservationLevel.TARGETED
        else:
            level_used = ObservationLevel.CHEAP

        # Step 3: full observation with VLM — opt-in only.
        vision_calls_used = 0
        if request.allow_vision and self._vision_calls_this_turn < request.max_vision_calls:
            full = self.observer.observe_full()
            cheap.vlm_description = full.vlm_description
            cheap.screenshot_path = full.screenshot_path
            level_used = ObservationLevel.FULL
            vision_calls_used = 1
            self._vision_calls_this_turn += 1

        # Rank targets from OCR text.
        targets = self._rank_targets(cheap, request.target_hint)

        return PerceptionResult(
            observation=cheap,
            level_used=level_used,
            targets=targets,
            vision_calls_used=vision_calls_used,
            timestamp=time.time(),
        )

    def perceive_cheap(self) -> PerceptionResult:
        """Fastest path: active window + OCR only."""
        return self.perceive(ObservationRequest(allow_vision=False))

    def perceive_targeted(
        self,
        region: tuple[int, int, int, int],
        target_hint: str | None = None,
        allow_vision: bool = False,
    ) -> PerceptionResult:
        """Perception scoped to a region."""
        return self.perceive(ObservationRequest(
            region=region,
            target_hint=target_hint,
            allow_vision=allow_vision,
        ))

    def perceive_full(
        self,
        target_hint: str | None = None,
    ) -> PerceptionResult:
        """Full perception with VLM — expensive, opt-in only."""
        return self.perceive(ObservationRequest(
            target_hint=target_hint,
            allow_vision=True,
        ))

    def detect_change(self, before: Observation, after: Observation) -> dict[str, Any]:
        """Detect significant changes between two observations."""
        return self.observer.detect_changes(before, after)

    def get_last_observation(self) -> Observation | None:
        return self._last_observation

    @staticmethod
    def _rank_targets(observation: Observation, target_hint: str | None) -> list[dict[str, Any]]:
        """Rank semantic targets from OCR text.

        Returns a list of {text, confidence, source} dicts. Cheap — no VLM.
        """
        if not observation.ocr_text:
            return []
        text = observation.ocr_text
        targets: list[dict[str, Any]] = []
        if target_hint:
            hint_lower = target_hint.lower()
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if hint_lower in line.lower():
                    targets.append({
                        "text": line,
                        "confidence": 0.9,
                        "source": "ocr_exact",
                    })
                else:
                    # Partial match: lower confidence.
                    targets.append({
                        "text": line,
                        "confidence": 0.5,
                        "source": "ocr_partial",
                    })
        else:
            for line in text.splitlines():
                line = line.strip()
                if line:
                    targets.append({
                        "text": line,
                        "confidence": 0.7,
                        "source": "ocr",
                    })
        # Rank by confidence, then by text length (longer = more likely a label).
        targets.sort(key=lambda t: (-t["confidence"], -len(t["text"])))
        return targets[:10]


__all__ = [
    "ObservationCollector",
    "ObservationLevel",
    "ObservationRequest",
    "PerceptionResult",
]