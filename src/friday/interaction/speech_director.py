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
        format_prosody: bool = True,
        min_sentences_between_effects: int = 0,
    ):
        self.enabled = enabled
        self.mode = mode
        self.max_tags_per_sentence = max_tags_per_sentence
        self.allow_vocal_effects = allow_vocal_effects
        self.allow_experimental_emotion_tags = allow_experimental_emotion_tags
        self.log_decisions = log_decisions
        self.enable_prosody_formatting = format_prosody
        self.min_sentences_between_effects = min_sentences_between_effects
        self._sentences_since_last_effect = 999

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

        # 0. Upstream In-Band Tag Detection (Native LLM Expression from Gemini / Qwen)
        tag_match = re.search(r"\[([\w\s-]+)\]", text[:40])
        if tag_match:
            raw_tag = tag_match.group(1).lower().strip()
            # Safety gate: block cheerful/laugh tags in failure states
            if not (ctx.task_status in ("FAILED", "ERROR", "BLOCKED") and raw_tag in ("chuckle", "laugh", "happy")):
                tag_to_emotion = {
                    "chuckle": ("amused", 0.65, "playful"),
                    "laugh": ("amused", 0.7, "playful"),
                    "sigh": ("empathetic", 0.65, "soft"),
                    "whispering": ("thoughtful", 0.5, "intimate"),
                    "whisper": ("thoughtful", 0.5, "intimate"),
                    "sarcastic": ("sarcastic", 0.7, "witty"),
                    "happy": ("cheerful", 0.65, "upbeat"),
                    "surprised": ("surprised", 0.65, "inquisitive"),
                    "angry": ("serious", 0.7, "firm"),
                    "crying": ("empathetic", 0.8, "soft"),
                    "dramatic": ("dramatic", 0.7, "measured"),
                    "fear": ("tentative", 0.6, "cautious"),
                    "gasp": ("surprised", 0.7, "inquisitive"),
                }
                if raw_tag in tag_to_emotion:
                    emo, inten, deliv = tag_to_emotion[raw_tag]
                    return SpeechDecision(emotion=emo, intensity=inten, delivery=deliv, tags=(raw_tag,))

        # Rule order matters - more specific rules first
        tags: tuple[str, ...] = ()

        # 1. Empathy after frustration, failure, or apology
        if ctx.task_status == "FAILED" or any(kw in text_lower for kw in ["sorry", "apologize", "apologies", "unfortunately", "afraid not", "pardon"]):
            tags = ()
            if self.allow_vocal_effects and "sigh" in self._allowed_tags:
                tags = ("sigh",)
            return SpeechDecision(emotion="empathetic", intensity=0.4, delivery="soft", tags=tags)

        # 2. Critical/error/blocked action -> serious/restrained, no playful tags
        if ctx.task_status in ("ERROR", "BLOCKED") or any(kw in text_lower for kw in ["error", "failed", "cannot", "unable", "blocked", "critical", "denied"]):
            return SpeechDecision(emotion="serious", intensity=0.6, delivery="restrained", tags=())

        # 3. Confirmation prompt -> calm/clear, no effects
        if ctx.awaiting_confirmation or any(kw in text_lower for kw in ["confirm", "are you sure", "proceed?"]):
            return SpeechDecision(emotion="calm", intensity=0.5, delivery="clear", tags=())

        # 4. Goodbye/shutdown -> calm/warm
        if any(kw in text_lower for kw in ["goodbye", "shutting down", "bye", "farewell", "powering down"]):
            return SpeechDecision(emotion="calm", intensity=0.4, delivery="warm", tags=())

        # 5. Surprise/sudden discovery / interesting findings
        if any(kw in text_lower for kw in ["wow", "amazing", "incredible", "unexpected", "surprise", "look at that", "interestingly"]):
            tags = ()
            if self.allow_vocal_effects and "gasp" in self._allowed_tags:
                tags = ("gasp",)
            elif self.allow_experimental_emotion_tags and "surprised" in self._allowed_tags:
                tags = ("surprised",)
            return SpeechDecision(emotion="surprised", intensity=0.7, delivery="expressive", tags=tags)

        # 6. Friendly greetings & boot readiness
        if any(kw in text_lower for kw in ["good morning", "good afternoon", "good evening", "online and ready", "at your service", "systems online", "welcome back", "hello boss", "hi boss"]):
            tags = ()
            if self.allow_experimental_emotion_tags and "happy" in self._allowed_tags:
                tags = ("happy",)
            elif self.allow_vocal_effects and "chuckle" in self._allowed_tags:
                tags = ("chuckle",)
            return SpeechDecision(emotion="warm", intensity=0.6, delivery="cheerful", tags=tags)

        # 7. Willing / enthusiastic agreement & affirmation
        if any(kw in text_lower for kw in ["sure thing", "certainly", "absolutely", "happy to", "right away", "of course", "on it", "you got it", "no problem"]):
            tags = ()
            if self.allow_vocal_effects and "chuckle" in self._allowed_tags:
                tags = ("chuckle",)
            elif self.allow_experimental_emotion_tags and "happy" in self._allowed_tags:
                tags = ("happy",)
            return SpeechDecision(emotion="positive", intensity=0.6, delivery="upbeat", tags=tags)

        # 8. Operational success / good status / completion
        if ctx.task_status == "COMPLETED" or any(kw in text_lower for kw in ["completed", "finished", "all set", "done", "success", "running nicely", "up and running", "fully accessible", "fully operational"]):
            tags = ()
            if self.allow_experimental_emotion_tags and "happy" in self._allowed_tags:
                tags = ("happy",)
            elif self.allow_vocal_effects and "sigh" in self._allowed_tags:
                tags = ("sigh",)
            return SpeechDecision(emotion="satisfied", intensity=0.6, delivery="confident", tags=tags)

        # 9. Inquisitive / checking in
        if any(kw in text_lower for kw in ["what's on your mind", "what did you have in mind", "anything you need", "how can i help", "what are we working on"]):
            tags = ()
            if self.allow_vocal_effects and "chuckle" in self._allowed_tags:
                tags = ("chuckle",)
            return SpeechDecision(emotion="inquisitive", intensity=0.5, delivery="engaging", tags=tags)

        # 10. Thinking / pondering / checking
        if any(kw in text_lower for kw in ["let's see", "let me check", "looking into", "checking now", "hmm", "hmmm"]):
            tags = ()
            if self.allow_vocal_effects and "clear throat" in self._allowed_tags:
                tags = ("clear throat",)
            return SpeechDecision(emotion="thoughtful", intensity=0.4, delivery="measured", tags=tags)

        # 11. Lightly amusing / playful (never in failure or error states)
        if ctx.task_status not in ("FAILED", "ERROR", "BLOCKED") and any(kw in text_lower for kw in ["haha", "hehe", "lol", "funny", "amusing", "joke"]):
            tags = ()
            if self.allow_vocal_effects and "chuckle" in self._allowed_tags:
                tags = ("chuckle",)
            elif self.allow_vocal_effects and "laugh" in self._allowed_tags:
                tags = ("laugh",)
            return SpeechDecision(emotion="amused", intensity=0.5, delivery="playful", tags=tags)

        # Default: ordinary factual response
        return SpeechDecision(emotion="neutral", intensity=0.5, delivery="conversational", tags=())

    @staticmethod
    def format_prosody(text: str) -> str:
        """
        Enhance text with natural conversational prosody and breathing cadence.
        Inserts smooth pauses after discourse markers and softens transitions
        without altering the semantic meaning of the words.
        """
        if not text:
            return text

        # 1. Normalize excessive punctuation
        res = re.sub(r"!{2,}", "!", text)
        res = re.sub(r"\?{2,}", "?", res)

        # 2. Add natural breathing pauses after common conversational starters if punctuation is missing
        starters_comma = r"^(Right|Sure|Actually|Honestly|Naturally|Obviously|Indeed|Certainly|Alright)\s+([A-Za-z])"
        res = re.sub(starters_comma, r"\1, \2", res)

        starters_dash = r"^(Well|Now|So|Look)\s+([A-Za-z])"
        res = re.sub(starters_dash, r"\1— \2", res)

        starters_ellipsis = r"^(Let me check|Let's see|Looking into that)\s+([A-Za-z])"
        res = re.sub(starters_ellipsis, r"\1... \2", res)

        return res

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
        if self.enable_prosody_formatting:
            clean_text = self.format_prosody(clean_text)

        # Check if the original text already carried allowed tags (do not replace existing tags)
        existing_tags = tuple(
            t for t in re.findall(r"\[([\w\s-]+)\]", text[:40])
            if t in self._allowed_tags
        )

        decision = self.decide(clean_text, context)

        # Enforce safety: if failure or error state, never permit chuckle or laugh
        if context and context.task_status in ("FAILED", "ERROR", "BLOCKED"):
            existing_tags = tuple(t for t in existing_tags if t not in ("chuckle", "laugh"))

        if existing_tags:
            tags = existing_tags
        else:
            tags = decision.tags

        # Enforce cooldown if configured
        if tags and self.min_sentences_between_effects > 0:
            if self._sentences_since_last_effect < self.min_sentences_between_effects:
                tags = ()

        # No tags to inject
        if not tags:
            self._sentences_since_last_effect += 1
            return clean_text

        # Enforce max_tags_per_sentence
        tags_to_inject = tags[:self.max_tags_per_sentence]

        # Validate all tags are allowed
        allowed = self._get_allowed_tags()
        tags_to_inject = tuple(t for t in tags_to_inject if t in allowed)

        if not tags_to_inject:
            self._sentences_since_last_effect += 1
            return clean_text

        self._sentences_since_last_effect = 0

        # Inject tags at the beginning of the text (Chatterbox expects prefix tags)
        tag_prefix = " ".join(f"[{t}]" for t in tags_to_inject)
        rendered = f"{tag_prefix} {clean_text}"
        if self.log_decisions:
            print(f"FRIDAY [Speech Director]: {decision.emotion.upper()} {list(tags_to_inject)} -> \"{rendered[:50]}...\"")
        return rendered

    @staticmethod
    def get_condition_key(decision: SpeechDecision) -> str:
        """Map SpeechDecision (emotion, tags) to the precompiled condition profile key."""
        if decision.tags:
            tag = decision.tags[0].lower().strip()
            tag_map = {
                "laugh": "chuckle",
                "chuckles": "chuckle",
                "gasp": "surprised",
                "groan": "sigh",
                "crying": "sigh",
            }
            return tag_map.get(tag, tag)

        emo = decision.emotion.lower().strip()
        emotion_map = {
            "empathetic": "sigh",
            "warm": "happy",
            "cheerful": "happy",
            "upbeat": "happy",
            "positive": "happy",
            "playful": "chuckle",
            "amused": "chuckle",
            "surprised": "surprised",
            "thoughtful": "neutral",
            "serious": "angry",
            "restrained": "neutral",
            "calm": "neutral",
            "confident": "neutral",
            "inquisitive": "neutral",
        }
        return emotion_map.get(emo, "neutral")

    def __call__(self, text: str, context: SpeechContext | None = None) -> str:
        """Convenience: render text directly."""
        return self.render(text, context)