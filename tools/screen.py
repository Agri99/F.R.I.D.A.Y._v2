"""Local screen vision as a read-only tool.

FRIDAY's reasoning model (qwen3:8b) is NOT a vision model, and we deliberately
don't want to change it — the persona and the loop stay exactly as they are.
Instead this tool captures the screen and asks a SEPARATE local Ollama vision
model (default `llava`) to describe it, then returns that text description as
the tool result. qwen3:8b reasons over the description, the same way it reasons
over `get_system_info` output. Vision becomes a sense, not the brain.

Gated by the SCREEN_VISION_MODEL env var: unset (or empty) → the tool reports
that screen vision is disabled, never crashes the agent loop. Pull the model
with `ollama pull llava` (or set SCREEN_VISION_MODEL to another VL model).
"""
import os
import pytesseract

from tools.registry import register_tool
from security.policy import RiskClass


def _grab_screen() -> "bytes | None":
    """Capture the primary screen as PNG bytes, or None on failure."""
    try:
        from PIL import ImageGrab
    except Exception:                                   # noqa: BLE001
        return None
    try:
        img = ImageGrab.grab()
        # Downscale so the base64 payload stays small and the VL model is fast.
        # ~1280px on the long edge is enough to read a screen of text.
        max_edge = 1280
        if max(img.size) > max_edge:
            scale = max_edge / max(img.size)
            img = img.resize((int(img.size[0] * scale), int(img.size[1] * scale)))
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:                                   # noqa: BLE001
        return None


def _describe(png_bytes: bytes, question: str, model: str) -> str:
    """Ask a local Ollama vision model to describe the screenshot."""
    import base64
    from ollama import Client

    client = Client(host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    prompt = question or "Describe what is on the screen concisely and accurately."
    images = [base64.b64encode(png_bytes).decode("ascii")]
    response = client.generate(model=model, prompt=prompt, images=images)
    return (response.get("response") or "").strip()


@register_tool(risk=RiskClass.GREEN, pre_notice="Checking your screen now.")
def describe_screen(question: str = "") -> dict:
    """Look at the current screen and answer a question about it (local vision).

    Use this to see what is displayed on the monitor, read text in a window,
    check what an error dialog says, or understand the desktop state. It works
    entirely locally and does not send your screen anywhere external.

    Args:
        question: Optional question about the screen, e.g.
                  'What error is showing?' or 'What window is frontmost?'

    Returns:
        dict: description of the screen, or an error/honest-disabled status
    """
    model = os.environ.get("SCREEN_VISION_MODEL", "").strip()
    if not model:
        return {"status": "disabled",
                "message": "Screen vision is off. Pull a vision model and set "
                           "SCREEN_VISION_MODEL (e.g. `ollama pull llava`, then "
                           "SCREEN_VISION_MODEL=llava) to enable it."}

    png = _grab_screen()
    if png is None:
        return {"status": "error",
                "message": "Could not capture the screen (Pillow/PIL not available "
                           "or the display cannot be grabbed)."}

    try:
        description = _describe(png, question, model)
    except Exception as exc:                            # noqa: BLE001
        return {"status": "error",
                "message": f"Screen vision model '{model}' failed: {exc}. "
                           f"Is the model pulled (`ollama pull {model}`) and "
                           f"is Ollama running?"}

    if not description:
        return {"status": "error", "message": "The vision model returned no description."}
    return {"status": "ok", "model": model, "description": description}


pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


@register_tool(risk=RiskClass.GREEN, pre_notice="Reading your screen now.")
def read_screen_text() -> dict:
    """Read the actual visible text on screen verbatim, using OCR.

    Use this when the user wants exact text read back (a document, code,
    an error message) — not a general description of what's on screen.

    Returns:
        dict: the extracted text, or an error status
    """
    from PIL import ImageGrab

    try:
        img = ImageGrab.grab()
        text = pytesseract.image_to_string(img).strip()
    except Exception as exc:                            # noqa: BLE001
        return {"status": "error", "message": f"OCR failed: {exc}"}

    if not text:
        return {"status": "ok", "text": "", "message": "No readable text found on screen."}
    return {"status": "ok", "text": text}


@register_tool(risk=RiskClass.YELLOW)
def take_screenshot(filename: str = "screenshot.png") -> dict:
    """Capture the current screen and save it as an image in the workspace folder.

    Args:
        filename: Name for the screenshot file, e.g. 'screenshot.png'.

    Returns:
        dict: path of the saved screenshot
    """
    from pathlib import Path
    from PIL import ImageGrab

    workspace = Path("workspace")
    workspace.mkdir(exist_ok=True)
    safe_name = Path(filename).name
    if not safe_name.lower().endswith((".png", ".jpg", ".jpeg")):
        safe_name += ".png"

    path = workspace / safe_name
    ImageGrab.grab().save(path)
    return {"status": "ok", "path": str(path)}