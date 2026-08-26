"""
src/friday/computer/screen.py

WHAT THIS IS FOR:
Handles screen capture, OCR text extraction, and local vision model perception
using Ollama (defaulting to llava / gemma3 / qwen3-vl) per blueprint §10, §46.
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
