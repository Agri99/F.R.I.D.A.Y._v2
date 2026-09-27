"""
src/friday/interaction/speech_director.py

WHAT THIS IS FOR:
Deterministic Speech Director that decides how LLM-generated text should be spoken.
Injects Chatterbox Turbo paralinguistic tags at the TTS boundary.
User-visible text remains clean; tags are private to the TTS layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from friday.interaction.tts import CHATTERBOX_EVENT_TAGS, CHATTERBOX_EXPERIMENTAL_EMOTION_TAGS


@dataclass(frozen=True)
class SpeechContext:
    """Context available when deciding speech policy."""
    user_text: str = ""
    task_status: str = ""
    awaiting_confirmation: bool = False
    tool_name: str = ""


@dataclass(frozen=True)
class SpeechDecision:
    """Decision rendered by the Speech Director."""
    emotion: str
    intensity: float
    delivery: str
    tags: tuple[str, ...] = ()


class SpeechDirector:
    """
    Rule-based speech policy engine. No network calls, no LLM calls.
    Cheap enough to run for every sentence.
    """

    def __init__(
        self,
        enabled: bool = True,
        mode: str = "rules",
        max_tags_per_sentence: int = 1,
        allow_vocal_effects: bool = True,
        allow_experimental_emotion_tags: bool = False,
        log_decisions: bool = False,
    ):
        self.enabled = enabled
        self.mode = mode
        self.max_tags_per_sentence = max_tags_per_sentence
        self.allow_vocal_effects = allow_vocal_effects
        self.allow_experimental_emotion_tags = allow_experimental_emotion_tags
        self.log_decisions = log_decisions

        # Build allowed tag set based on config
        self._allowed_tags = set()
        if self.allow_vocal_effects:
            self._allowed_tags.update(CHATTERBOX_EVENT_TAGS)
        if self.allow_experimental_emotion_tags:
            self._allowed_tags.update(CHATTERBOX_EXPERIMENTAL_EMOTION_TAGS)

    def _get_allowed_tags(self) -> set[str]:
        """Get the current allowed tag set."""
        return self._allowed_tags.copy()

    def decide(self, text: str, context: SpeechContext | None = None) -> SpeechDecision:
        """
        Decide emotion, intensity, delivery, and tags for the given text.
        Returns a SpeechDecision with the policy decision.
        """
        if not self.enabled or self.mode != "rules":
            return SpeechDecision(emotion="neutral", intensity=0.5, delivery="conversational", tags=())

        ctx = context or SpeechContext()
        text_lower = text.lower().strip()

        # Rule order matters - more specific rules first

        # Empathy after frustration/failure
        if ctx.task_status == "FAILED" or any(kw in text_lower for kw in ["sorry", "apologize", "unfortunately"]):
            tags = ()
            if self.allow_vocal_effects and "sigh" in self._allowed_tags:
                tags = ("sigh",)
            return SpeechDecision(emotion="empathetic", intensity=0.4, delivery="soft", tags=tags)

        # Critical/error/blocked action -> serious/restrained, no playful tags
        if ctx.task_status in ("ERROR", "BLOCKED") or any(kw in text_lower for kw in ["error", "failed", "cannot", "unable", "blocked", "critical", "denied"]):
            return SpeechDecision(emotion="serious", intensity=0.6, delivery="restrained", tags=())

        # Confirmation prompt -> calm/clear, no effects
        if ctx.awaiting_confirmation or any(kw in text_lower for kw in ["confirm", "are you sure", "proceed?"]):
            return SpeechDecision(emotion="calm", intensity=0.5, delivery="clear", tags=())

        # Goodbye/shutdown -> calm/warm
        if any(kw in text_lower for kw in ["goodbye", "shutting down", "bye", "farewell"]):
            return SpeechDecision(emotion="calm", intensity=0.4, delivery="warm", tags=())

        # Surprise/sudden discovery
        if any(kw in text_lower for kw in ["wow", "amazing", "incredible", "unexpected", "surprise"]):
            tags = ()
            if self.allow_vocal_effects and "gasp" in self._allowed_tags:
                tags = ("gasp",)
            elif self.allow_experimental_emotion_tags and "surprised" in self._allowed_tags:
                tags = ("surprised",)
            return SpeechDecision(emotion="surprised", intensity=0.7, delivery="expressive", tags=tags)

        # User reports success / FRIDAY confirms success
        if ctx.task_status == "COMPLETED" or any(kw in text_lower for kw in ["completed", "finished", "done", "success", "works"]):
            tags = ()
            if self.allow_experimental_emotion_tags and "happy" in self._allowed_tags:
                tags = ("happy",)
            return SpeechDecision(emotion="positive", intensity=0.6, delivery="confident", tags=tags)

        # Lightly amusing / playful (never in failure or error states)
        if ctx.task_status not in ("FAILED", "ERROR", "BLOCKED") and any(kw in text_lower for kw in ["haha", "hehe", "lol", "funny", "amusing"]):
            tags = ()
            if self.allow_vocal_effects and "chuckle" in self._allowed_tags:
                tags = ("chuckle",)
            return SpeechDecision(emotion="amused", intensity=0.5, delivery="playful", tags=tags)

        # Default: ordinary factual response
        return SpeechDecision(emotion="neutral", intensity=0.5, delivery="conversational", tags=())

    def render(self, text: str, context: SpeechContext | None = None) -> str:
        """
        Render the final TTS text by injecting allowed tags.
        Returns the private TTS text with tags; original text is unchanged.
        Idempotent: render(render(text)) == render(text).
        """
        if not self.enabled:
            return text

        # Strip existing leading bracket tags to guarantee idempotence
        clean_text = re.sub(r"^(?:\[[\w\s-]+\]\s*)+", "", text).strip()
        decision = self.decide(clean_text, context)

        # No tags to inject
        if not decision.tags:
            return clean_text if clean_text != text and not any(t in self._allowed_tags for t in re.findall(r"\[([\w\s-]+)\]", text[:30])) else text

        # Enforce max_tags_per_sentence
        tags_to_inject = decision.tags[:self.max_tags_per_sentence]

        # Validate all tags are allowed
        allowed = self._get_allowed_tags()
        tags_to_inject = tuple(t for t in tags_to_inject if t in allowed)

        if not tags_to_inject:
            return text

        # Inject tags at the beginning of the text (Chatterbox expects prefix tags)
        tag_prefix = " ".join(f"[{t}]" for t in tags_to_inject)
        return f"{tag_prefix} {clean_text}"

    def __call__(self, text: str, context: SpeechContext | None = None) -> str:
        """Convenience: render text directly."""
        return self.render(text, context)