import re

_NON_ALNUM = re.compile(r"[^a-z0-9\s]+")
_SPACES = re.compile(r"\s+")

HIDE_PHRASES = (
    "hide yourself",
    "hide your self",
    "hide the orb",
    "hide your orb",
    "hide orb",
    "disappear",
    "go away",
    "minimize yourself",
    "minimise yourself",
    "make yourself invisible",
)

SHOW_PHRASES = (
    "come back",
    "show yourself",
    "show your self",
    "show the orb",
    "show your orb",
    "appear",
    "unhide",
)

SHUTDOWN_EXACT = {
    "goodbye",
    "good bye",
    "bye",
    "good night",
    "shut down",
    "shutdown",
    "exit",
    "quit",
}

HIDE_OFFER_MARKERS = (
    "cannot hide",
    "can't hide",
    "can not hide",
    "minimize my interface",
    "minimise my interface",
    "close any open windows if that's what you mean",
)


def normalize(text: str) -> str:
    return _SPACES.sub(" ", _NON_ALNUM.sub(" ", (text or "").lower())).strip()


def _negated(text: str) -> bool:
    return text.startswith("do not ") or text.startswith("dont ") or " never " in f" {text} "


def match_direct_intent(user_text: str, last_assistant: str | None = None) -> dict | None:
    """Map a spoken phrase to toggle_orb / shutdown_friday without asking the LLM."""
    text = normalize(user_text)
    if not text or _negated(text):
        return None

    if _is_shutdown(text):
        return {
            "tool": "shutdown_friday",
            "arguments": {},
            "success_reply": "Have a good day!",
        }

    if any(phrase in text for phrase in SHOW_PHRASES):
        return {
            "tool": "toggle_orb",
            "arguments": {"visible": True},
            "success_reply": "I'm back.",
        }

    if any(phrase in text for phrase in HIDE_PHRASES):
        return {
            "tool": "toggle_orb",
            "arguments": {"visible": False},
            "success_reply": "Okay, I'll stay out of sight.",
        }

    last = normalize(last_assistant or "")
    if last and any(marker in last for marker in HIDE_OFFER_MARKERS) and _is_affirmative(text):
        return {
            "tool": "toggle_orb",
            "arguments": {"visible": False},
            "success_reply": "Okay, I'll stay out of sight.",
        }

    return None


def _is_shutdown(text: str) -> bool:
    if any(phrase in text for phrase in HIDE_PHRASES):
        return False
    if text in SHUTDOWN_EXACT:
        return True
    if "goodbye" in text or "good bye" in text:
        return True
    if "friday" in text and any(word in text for word in ("bye", "goodbye", "good night")):
        return True
    if "shut down" in text or text.startswith("shutdown"):
        return True
    if "shut yourself down" in text or "close yourself" in text:
        return True
    if "stop running" in text or "exit program" in text or "quit program" in text:
        return True
    if "turn yourself off" in text:
        return True
    return False


def _is_affirmative(text: str) -> bool:
    tokens = set(text.split())
    if tokens & {"yes", "yeah", "yep", "please", "confirm"}:
        return True
    return text in {
        "ok",
        "okay",
        "do it",
        "go ahead",
        "thats what i mean",
        "that is what i mean",
        "yes please",
        "yes thats what i mean",
        "yes that is what i mean",
    }
