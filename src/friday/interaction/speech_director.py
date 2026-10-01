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
from typing import Any

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
        production_tags: list[str] | tuple[str, ...] | set[str] | None = None,
        limited_tags: list[str] | tuple[str, ...] | set[str] | None = None,
        disabled_tags: list[str] | tuple[str, ...] | set[str] | None = None,
        expression_blend_weights: dict[str, float] | None = None,
        log_decisions: bool = False,
        format_prosody: bool = True,
        min_sentences_between_effects: int = 0,
    ):
        self.enabled = enabled
        self.mode = mode
        self.max_tags_per_sentence = max_tags_per_sentence
        self.allow_vocal_effects = allow_vocal_effects
        self.allow_experimental_emotion_tags = allow_experimental_emotion_tags
        self.production_tags = set(
            production_tags if production_tags is not None else ["happy", "dramatic", "whispering"]
        )
        self.limited_tags = set(
            limited_tags if limited_tags is not None else ["laugh"]
        )
        self.disabled_tags = set(
            disabled_tags if disabled_tags is not None else [
                "chuckle", "sigh", "gasp", "sarcastic", "angry", "crying", "fear", "surprised"
            ]
        )
        self.expression_blend_weights = dict(
            expression_blend_weights if expression_blend_weights is not None else {
                "happy": 0.65,
                "dramatic": 0.60,
                "whispering": 0.70,
                "laugh": 0.50,
            }
        )
        self.log_decisions = log_decisions
        self.enable_prosody_formatting = format_prosody
        self.min_sentences_between_effects = min_sentences_between_effects
        self._sentences_since_last_effect = 999

        # Build allowed tag set based on config and production/limited policy
        base_allowed: set[str] = set()
        if self.allow_vocal_effects:
            base_allowed.update(CHATTERBOX_EVENT_TAGS)
        if self.allow_experimental_emotion_tags:
            base_allowed.update(CHATTERBOX_EXPERIMENTAL_EMOTION_TAGS)

        # Policy: allowed tags must be in production or limited tags, and NEVER in disabled_tags
        self._allowed_tags = (base_allowed & (self.production_tags | self.limited_tags)) - self.disabled_tags

    def _get_allowed_tags(self) -> set[str]:
        """Get the current allowed tag set."""
        return self._allowed_tags.copy()

    @classmethod
    def from_config(cls, cfg: Any) -> SpeechDirector:
        """Instantiate SpeechDirector from a SpeechDirectorConfig or settings object."""
        if cfg is None:
            return cls()
        return cls(
            enabled=getattr(cfg, "enabled", True),
            mode=getattr(cfg, "mode", "rules"),
            max_tags_per_sentence=getattr(cfg, "max_tags_per_sentence", 1),
            allow_vocal_effects=getattr(cfg, "allow_vocal_effects", True),
            allow_experimental_emotion_tags=getattr(cfg, "allow_experimental_emotion_tags", False),
            production_tags=getattr(cfg, "production_tags", None),
            limited_tags=getattr(cfg, "limited_tags", None),
            disabled_tags=getattr(cfg, "disabled_tags", None),
            expression_blend_weights=getattr(cfg, "expression_blend_weights", None),
            log_decisions=getattr(cfg, "log_decisions", False),
        )

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
                    # Upstream tags cannot bypass production policy
                    if raw_tag in self.disabled_tags or raw_tag not in self._allowed_tags:
                        allowed_tags: tuple[str, ...] = ()
                    elif raw_tag in self.limited_tags and ctx.task_status in ("FAILED", "ERROR", "BLOCKED"):
                        allowed_tags = ()
                    else:
                        allowed_tags = (raw_tag,)
                    return SpeechDecision(emotion=emo, intensity=inten, delivery=deliv, tags=allowed_tags)

        # Rule order matters - more specific rules first
        tags: tuple[str, ...] = ()

        # 1. Empathy after frustration, failure, or apology -> soft delivery, neutral condition, no automatic sigh tag
        if ctx.task_status == "FAILED" or any(kw in text_lower for kw in ["sorry", "apologize", "apologies", "unfortunately", "afraid not", "pardon"]):
            tags = ()
            if "sigh" in self.production_tags and "sigh" in self._allowed_tags:
                tags = ("sigh",)
            return SpeechDecision(emotion="empathetic", intensity=0.4, delivery="soft", tags=tags)

        # 2. Critical/error/blocked action -> serious/restrained, no playful or angry tags
        if ctx.task_status in ("ERROR", "BLOCKED") or any(kw in text_lower for kw in ["error", "failed", "cannot", "unable", "blocked", "critical", "denied"]):
            return SpeechDecision(emotion="serious", intensity=0.6, delivery="restrained", tags=())

        # 3. Confirmation prompt -> calm/clear, no effects
        if ctx.awaiting_confirmation or any(kw in text_lower for kw in ["confirm", "are you sure", "proceed?"]):
            return SpeechDecision(emotion="calm", intensity=0.5, delivery="clear", tags=())

        # 4. Goodbye/shutdown -> calm/warm
        if any(kw in text_lower for kw in ["goodbye", "shutting down", "bye", "farewell", "powering down"]):
            return SpeechDecision(emotion="calm", intensity=0.4, delivery="warm", tags=())

        # 5. Surprise/sudden discovery / interesting findings -> measured delivery, no weak gasp/surprised tag unless approved
        if any(kw in text_lower for kw in ["wow", "amazing", "incredible", "unexpected", "surprise", "look at that", "interestingly"]):
            tags = ()
            if "gasp" in self.production_tags and "gasp" in self._allowed_tags:
                tags = ("gasp",)
            elif "surprised" in self.production_tags and "surprised" in self._allowed_tags:
                tags = ("surprised",)
            return SpeechDecision(emotion="surprised", intensity=0.6, delivery="measured", tags=tags)

        # 6. Friendly greetings & boot readiness
        if any(kw in text_lower for kw in ["good morning", "good afternoon", "good evening", "online and ready", "at your service", "systems online", "welcome back", "hello boss", "hi boss"]):
            tags = ()
            if "happy" in self.production_tags and "happy" in self._allowed_tags:
                tags = ("happy",)
            return SpeechDecision(emotion="warm", intensity=0.6, delivery="cheerful", tags=tags)

        # 7. Willing / enthusiastic agreement & affirmation
        if any(kw in text_lower for kw in ["sure thing", "certainly", "absolutely", "happy to", "right away", "of course", "on it", "you got it", "no problem"]):
            tags = ()
            if "happy" in self.production_tags and "happy" in self._allowed_tags:
                tags = ("happy",)
            return SpeechDecision(emotion="positive", intensity=0.6, delivery="upbeat", tags=tags)

        # 8. Operational success / good status / completion
        if ctx.task_status == "COMPLETED" or any(kw in text_lower for kw in ["completed", "finished", "all set", "done", "success", "running nicely", "up and running", "fully accessible", "fully operational"]):
            tags = ()
            if "happy" in self.production_tags and "happy" in self._allowed_tags:
                tags = ("happy",)
            return SpeechDecision(emotion="satisfied", intensity=0.6, delivery="confident", tags=tags)

        # 9. Inquisitive / checking in
        if any(kw in text_lower for kw in ["what's on your mind", "what did you have in mind", "anything you need", "how can i help", "what are we working on"]):
            return SpeechDecision(emotion="inquisitive", intensity=0.5, delivery="engaging", tags=())

        # 10. Thinking / pondering / checking
        if any(kw in text_lower for kw in ["let's see", "let me check", "looking into", "checking now", "hmm", "hmmm"]):
            tags = ()
            if "clear throat" in self.production_tags and "clear throat" in self._allowed_tags:
                tags = ("clear throat",)
            return SpeechDecision(emotion="thoughtful", intensity=0.4, delivery="measured", tags=tags)

        # 11. Lightly amusing / playful (never in failure or error states)
        if ctx.task_status not in ("FAILED", "ERROR", "BLOCKED") and any(kw in text_lower for kw in ["haha", "hehe", "lol", "funny", "amusing", "joke"]):
            tags = ()
            if "laugh" in self.limited_tags and "laugh" in self._allowed_tags:
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
            if t in self._allowed_tags and t not in self.disabled_tags
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
        tags_to_inject = tuple(t for t in tags_to_inject if t in allowed and t not in self.disabled_tags)

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
            # Phase 6 canonical condition routing:
            # - Disabled expressions must resolve to neutral, never an unrelated profile
            # - Crying must never map to sigh
            # - Serious must never map to angry
            # - Surprise must never map to gasp
            # - Laugh routes to chuckle profile in condition bank (if approved)
            tag_map = {
                "laugh": "chuckle",
                "chuckles": "chuckle",
                "happy": "happy",
                "dramatic": "dramatic",
                "whispering": "whispering",
                "whisper": "whispering",
                # Explicit neutral fallback for disabled/pending expressions
                "crying": "neutral",
                "empathetic": "neutral",
                "sigh": "neutral",
                "gasp": "neutral",
                "surprised": "neutral",
                "angry": "neutral",
                "sarcastic": "neutral",
                "fear": "neutral",
                "chuckle": "neutral",
                "groan": "neutral",
            }
            return tag_map.get(tag, "neutral")

        emo = decision.emotion.lower().strip()
        emotion_map = {
            "warm": "happy",
            "cheerful": "happy",
            "upbeat": "happy",
            "positive": "happy",
            "dramatic": "dramatic",
            "empathetic": "neutral",  # Corrected: no longer routes to sigh
            "serious": "neutral",     # Corrected: no longer routes to angry
            "surprised": "neutral",   # Corrected: no longer routes to surprised
            "playful": "neutral",     # Playful without tag is neutral
            "amused": "neutral",
            "thoughtful": "neutral",
            "restrained": "neutral",
            "calm": "neutral",
            "confident": "neutral",
            "inquisitive": "neutral",
        }
        return emotion_map.get(emo, "neutral")

    def get_blend_weight(self, decision: SpeechDecision) -> float:
        """Get calibrated condition blend weight for the given SpeechDecision."""
        if decision.tags:
            tag = decision.tags[0].lower().strip()
            if tag in self.expression_blend_weights:
                return float(self.expression_blend_weights[tag])
        cond_key = self.get_condition_key(decision)
        if cond_key in self.expression_blend_weights:
            return float(self.expression_blend_weights[cond_key])
        return 0.65

    def __call__(self, text: str, context: SpeechContext | None = None) -> str:
        """Convenience: render text directly."""
        return self.render(text, context)