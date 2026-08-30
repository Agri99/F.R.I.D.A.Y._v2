"""
src/friday/computer/screen.py

WHAT THIS IS FOR:
Handles screen capture, OCR text extraction, and local vision model perception
using Ollama (defaulting to llava / gemma3 / qwen3-vl) per blueprint §10, §46.

Adds progressive observation and screen change detection for observe-act-verify loop.
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any

import pytesseract
from PIL import Image, ImageGrab

# Standard default path for Tesseract on Windows
if Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe").exists():
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def capture_screen(region: tuple[int, int, int, int] | None = None) -> Image.Image | None:
    """Capture the primary screen or a specific region."""
    try:
        if region:
            return ImageGrab.grab(bbox=region)
        return ImageGrab.grab()
    except Exception:
        return None


def grab_screen_bytes(max_edge: int = 1280) -> bytes | None:
    """Capture screen and downscale for low-latency vision inference."""
    try:
        img = ImageGrab.grab()
        if max(img.size) > max_edge:
            scale = max_edge / max(img.size)
            img = img.resize((int(img.size[0] * scale), int(img.size[1] * scale)))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def ocr(image: Image.Image | None = None) -> str:
    """Perform OCR on screen or given image."""
    try:
        img = image or ImageGrab.grab()
        return pytesseract.image_to_string(img).strip()
    except Exception as exc:
        return f"OCR error: {exc}"


def describe_screen(
    question: str = "Describe what is on the screen concisely and accurately.",
    model: str | None = None,
    host: str | None = None,
) -> dict[str, Any]:
    """Ask a local Ollama vision model (llava/gemma3/qwen3-vl) to describe the screen."""
    vision_model = (
        model
        or os.environ.get("SCREEN_VISION_MODEL")
        or "llava"
    ).strip()

    png_bytes = grab_screen_bytes()
    if png_bytes is None:
        return {"status": "error", "message": "Could not capture display screen."}

    ollama_host = (host or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")

    try:
        import requests
        b64_img = base64.b64encode(png_bytes).decode("ascii")
        resp = requests.post(
            f"{ollama_host}/api/generate",
            json={
                "model": vision_model,
                "prompt": question or "Describe what is on the screen concisely and accurately.",
                "images": [b64_img],
                "stream": False,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return {"status": "error", "message": f"Ollama vision request failed (HTTP {resp.status_code}): {resp.text}"}

        data = resp.json()
        description = data.get("response", "").strip()
        if not description:
            return {"status": "error", "message": "Vision model returned empty description."}

        return {"status": "ok", "model": vision_model, "description": description}
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Vision inference failed for '{vision_model}': {exc}. Ensure Ollama is running.",
        }


def save_screenshot(filename: str = "screenshot.png", workspace_dir: str | Path = "workspace") -> str:
    """Capture screen and save to workspace directory."""
    dest_dir = Path(workspace_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    if not safe_name.lower().endswith((".png", ".jpg", ".jpeg")):
        safe_name += ".png"
    output_path = dest_dir / safe_name
    img = ImageGrab.grab()
    img.save(output_path)
    return str(output_path)


def compute_screen_hash(image: Image.Image | None = None) -> str:
    """Compute perceptual hash of screen for quick change detection."""
    try:
        img = image or ImageGrab.grab()
        # Resize to small size and convert to grayscale for perceptual hash
        small = img.resize((16, 16), Image.Resampling.LANCZOS).convert('L')
        try:
            pixels = list(small.get_flattened_data())
        except AttributeError:
            pixels = list(small.getdata())
        avg = sum(pixels) / len(pixels)
        bits = ''.join('1' if p > avg else '0' for p in pixels)
        return hex(int(bits, 2))[2:].zfill(16)
    except Exception:
        return ""


def compare_screens(before_hash: str, after_hash: str, threshold: float = 0.05) -> dict[str, Any]:
    """Compare two screen hashes and detect significant changes."""
    if not before_hash or not after_hash:
        return {"changed": False, "confidence": 0.0, "reason": "missing hash"}

    # Hamming distance
    try:
        h1 = int(before_hash, 16)
        h2 = int(after_hash, 16)
        diff = bin(h1 ^ h2).count('1')
        max_diff = 64  # 16 hex chars * 4 bits
        change_ratio = diff / max_diff
        return {
            "changed": change_ratio > threshold,
            "confidence": 1.0 - change_ratio,
            "change_ratio": change_ratio,
            "reason": f"Pixel change ratio: {change_ratio:.2%}"
        }
    except Exception:
        return {"changed": False, "confidence": 0.0, "reason": "hash compare error"}


from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Observation:
    """Complete screen observation state."""
    active_window: str
    visible_windows: list[str]
    accessibility_tree: dict | None
    screenshot_path: str | None
    focused_control: str | None
    browser_url: str | None
    timestamp: datetime
    screen_hash: str = ""
    ocr_text: str = ""
    vlm_description: str = ""
    dialog_detected: bool = False
    popup_detected: bool = False
    error_state_detected: bool = False


class ScreenObserver:
    """Progressive screen observation with change detection."""

    def __init__(self):
        self._last_observation: Observation | None = None
        self._last_hash: str = ""

    def observe_cheap(self) -> Observation:
        """Fast state check without screenshot or VLM - uses active window + OCR."""
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd) if hwnd else "Unknown"
            img = ImageGrab.grab()
            screen_hash = compute_screen_hash(img)
            ocr_text = ocr(img)
        except Exception:
            title = "Unknown"
            screen_hash = ""
            ocr_text = ""

        obs = Observation(
            active_window=title,
            visible_windows=[],
            accessibility_tree=None,
            screenshot_path=None,
            focused_control=None,
            browser_url=None,
            timestamp=datetime.now(),
            screen_hash=screen_hash,
            ocr_text=ocr_text[:500],  # Limit for context
        )
        return obs

    def observe_targeted(self, region: tuple | None = None) -> Observation:
        """Targeted screenshot of specific region with OCR."""
        try:
            img = ImageGrab.grab(bbox=region) if region else ImageGrab.grab()
            screen_hash = compute_screen_hash(img)
            ocr_text = ocr(img)
        except Exception:
            img = None
            screen_hash = ""
            ocr_text = ""

        obs = Observation(
            active_window="",
            visible_windows=[],
            accessibility_tree=None,
            screenshot_path=save_screenshot("targeted") if img else None,
            focused_control=None,
            browser_url=None,
            timestamp=datetime.now(),
            screen_hash=screen_hash,
            ocr_text=ocr_text[:1000],
        )
        return obs

    def observe_full(self) -> Observation:
        """Full screenshot + VLM analysis. Only when ambiguity remains."""
        try:
            img = ImageGrab.grab()
            screen_hash = compute_screen_hash(img)
            ocr_text = ocr(img)
            vlm_result = describe_screen()
            vlm_desc = vlm_result.get("description", "") if vlm_result.get("status") == "ok" else ""
            screenshot_path = save_screenshot("full")
        except Exception:
            img = None
            screen_hash = ""
            ocr_text = ""
            vlm_desc = ""
            screenshot_path = None

        obs = Observation(
            active_window="",
            visible_windows=[],
            accessibility_tree=None,
            screenshot_path=screenshot_path,
            focused_control=None,
            browser_url=None,
            timestamp=datetime.now(),
            screen_hash=screen_hash,
            ocr_text=ocr_text[:2000],
            vlm_description=vlm_desc,
        )
        return obs

    def detect_changes(self, before: Observation, after: Observation) -> dict[str, Any]:
        """Detect significant changes between two observations."""
        changes = {
            "screen_changed": False,
            "window_changed": False,
            "dialog_appeared": False,
            "popup_appeared": False,
            "error_appeared": False,
            "text_changes": [],
            "confidence": 0.0,
        }

        # Screen hash comparison
        if before.screen_hash and after.screen_hash:
            cmp = compare_screens(before.screen_hash, after.screen_hash)
            changes["screen_changed"] = cmp["changed"]
            changes["confidence"] = cmp["confidence"]

        # Window title change
        if before.active_window != after.active_window and after.active_window:
            changes["window_changed"] = True

        # Dialog/popup detection via OCR text
        dialog_keywords = ["dialog", "confirm", "alert", "warning", "error", "save as", "open file"]
        popup_keywords = ["popup", "tooltip", "menu", "dropdown", "context menu"]

        after_text = after.ocr_text.lower()
        before_text = before.ocr_text.lower()

        for kw in dialog_keywords:
            if kw in after_text and kw not in before_text:
                changes["dialog_appeared"] = True
                changes["text_changes"].append(f"dialog: {kw}")
                break

        for kw in popup_keywords:
            if kw in after_text and kw not in before_text:
                changes["popup_appeared"] = True
                changes["text_changes"].append(f"popup: {kw}")
                break

        # Error state detection
        error_keywords = ["error", "exception", "failed", "crash", "not responding"]
        for kw in error_keywords:
            if kw in after_text and kw not in before_text:
                changes["error_appeared"] = True
                changes["text_changes"].append(f"error: {kw}")
                break

        return changes


# Convenience function for quick change detection
def quick_change_check() -> dict[str, Any]:
    """Quick check if screen has changed since last call."""
    observer = ScreenObserver()
    current = observer.observe_cheap()
    changes = {"changed": False, "reason": "first check"}

    if current.screen_hash and hasattr(quick_change_check, "_last_hash"):
        cmp = compare_screens(quick_change_check._last_hash, current.screen_hash)
        changes = {"changed": cmp["changed"], "confidence": cmp["confidence"], "reason": cmp["reason"]}

    quick_change_check._last_hash = current.screen_hash
    return changes

