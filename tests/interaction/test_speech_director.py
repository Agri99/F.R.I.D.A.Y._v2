"""
tests/interaction/test_speech_director.py

Unit tests for SpeechDirector policy engine, tag injection, and idempotence.
"""

from __future__ import annotations

from friday.interaction.speech_director import SpeechContext, SpeechDecision, SpeechDirector


def test_default_text_gets_neutral_decision_and_no_tags():
    director = SpeechDirector()
    decision = director.decide("The local temperature is 22 degrees Celsius.")

    assert decision.emotion == "neutral"
    assert decision.tags == ()
    assert decision.delivery == "conversational"

    rendered = director.render("The local temperature is 22 degrees Celsius.")
    assert rendered == "The local temperature is 22 degrees Celsius."


def test_failure_error_context_never_receives_laugh_or_chuckle():
    director = SpeechDirector(allow_vocal_effects=True)

    # 1. Error keyword in text
    dec1 = director.decide("The operation failed due to a critical network timeout.")
    assert dec1.emotion == "serious"
    assert "chuckle" not in dec1.tags
    assert "laugh" not in dec1.tags
    assert dec1.tags == ()

    # 2. FAILED context with ambiguous or laughing text
    ctx_failed = SpeechContext(task_status="FAILED")
    dec2 = director.decide("Haha that was an error", context=ctx_failed)
    assert dec2.emotion in ("serious", "empathetic")
    assert "chuckle" not in dec2.tags
    assert "laugh" not in dec2.tags

    # 3. Rendered text must not contain [chuckle] or [laugh]
    rendered = director.render("Error occurred. That was unfortunate haha.", context=ctx_failed)
    assert "[chuckle]" not in rendered
    assert "[laugh]" not in rendered


def test_empathy_rule_emits_soft_delivery_and_no_disabled_sigh():
    # Phase 6 default: sigh is disabled; empathy uses soft delivery and neutral condition
    director_default = SpeechDirector(allow_vocal_effects=True)
    ctx_failed = SpeechContext(task_status="FAILED")

    dec = director_default.decide("I'm sorry, I couldn't find any results for that.", context=ctx_failed)
    assert dec.emotion == "empathetic"
    assert dec.delivery == "soft"
    assert dec.tags == ()
    assert SpeechDirector.get_condition_key(dec) == "neutral"

    rendered = director_default.render("I'm sorry, I couldn't find any results for that.", context=ctx_failed)
    assert not rendered.startswith("[sigh]")
    assert "I'm sorry, I couldn't find any results for that." in rendered

    # When sigh is explicitly allowed in production_tags and removed from disabled_tags
    director_custom = SpeechDirector(
        allow_vocal_effects=True,
        production_tags=["sigh"],
        disabled_tags=[],
    )
    dec_custom = director_custom.decide("I'm sorry, I couldn't find any results for that.", context=ctx_failed)
    assert "sigh" in dec_custom.tags
    assert director_custom.render("I'm sorry, I couldn't find any results for that.", context=ctx_failed).startswith("[sigh] ")


def test_playful_rule_emits_laugh_when_appropriate():
    director = SpeechDirector(allow_vocal_effects=True)
    dec = director.decide("Haha, that is definitely funny.")

    assert dec.emotion == "amused"
    # Phase 6: chuckle is disabled, laugh is in limited_tags
    assert "laugh" in dec.tags
    assert "chuckle" not in dec.tags

    rendered = director.render("Haha, that is definitely funny.")
    assert rendered.startswith("[laugh] ")


def test_experimental_emotion_tags_blocked_by_default():
    director_default = SpeechDirector(allow_experimental_emotion_tags=False)
    ctx_done = SpeechContext(task_status="COMPLETED")

    dec_default = director_default.decide("Task completed successfully.", context=ctx_done)
    assert "happy" not in dec_default.tags

    rendered = director_default.render("Task completed successfully.", context=ctx_done)
    assert "[happy]" not in rendered

    # Allowed when explicitly enabled and in production_tags
    director_experimental = SpeechDirector(
        allow_experimental_emotion_tags=True,
        production_tags=["happy"],
    )
    dec_exp = director_experimental.decide("Task completed successfully.", context=ctx_done)
    assert "happy" in dec_exp.tags

    rendered_exp = director_experimental.render("Task completed successfully.", context=ctx_done)
    assert "[happy]" in rendered_exp


def test_maximum_tags_per_sentence_enforced():
    director = SpeechDirector(max_tags_per_sentence=1, allow_vocal_effects=True)
    rendered = director.render("Haha, that was hilarious and funny.")
    # Check that at most 1 bracket tag is present at the start
    bracket_count = rendered.count("[")
    assert bracket_count <= 1


def test_repeated_rendering_does_not_duplicate_tags():
    director = SpeechDirector(allow_experimental_emotion_tags=True, production_tags=["happy"])
    original = "Good morning, Boss. Everything is ready."

    once = director.render(original)
    twice = director.render(once)
    thrice = director.render(twice)

    assert once == twice == thrice
    assert once.count("[happy]") == 1


def test_director_never_changes_semantic_words():
    director = SpeechDirector(allow_vocal_effects=True)
    original = "I am sorry that happened, Boss. Let's try another approach."
    ctx = SpeechContext(task_status="FAILED")

    rendered = director.render(original, context=ctx)
    # Removing any leading bracket tags must leave the exact original text
    import re
    cleaned = re.sub(r"^(?:\[[\w\s-]+\]\s*)+", "", rendered).strip()
    assert cleaned == original


def test_prosody_formatting_rules():
    assert SpeechDirector.format_prosody("Sure I will check that now.") == "Sure, I will check that now."
    assert SpeechDirector.format_prosody("Well that sounds good.") == "Well— that sounds good."
    assert SpeechDirector.format_prosody("Let's see what happens next.") == "Let's see... what happens next."
    assert SpeechDirector.format_prosody("Really??? That is awesome!!!!") == "Really? That is awesome!"


def test_prosody_preserves_existing_tags():
    director = SpeechDirector(allow_experimental_emotion_tags=True, production_tags=["happy"])
    rendered = director.render("[happy] Well that was unexpected.")
    assert rendered == "[happy] Well— that was unexpected."


def test_get_condition_key_mapping():
    from friday.interaction.speech_director import SpeechDecision, SpeechDirector

    # 1. Tags take precedence for approved production / limited expressions
    dec_laugh = SpeechDecision(emotion="neutral", intensity=0.5, delivery="conversational", tags=("laugh",))
    assert SpeechDirector.get_condition_key(dec_laugh) == "chuckle"

    dec_happy = SpeechDecision(emotion="warm", intensity=0.6, delivery="cheerful", tags=("happy",))
    assert SpeechDirector.get_condition_key(dec_happy) == "happy"

    dec_dramatic = SpeechDecision(emotion="dramatic", intensity=0.7, delivery="measured", tags=("dramatic",))
    assert SpeechDirector.get_condition_key(dec_dramatic) == "dramatic"

    dec_whisper = SpeechDecision(emotion="thoughtful", intensity=0.5, delivery="intimate", tags=("whispering",))
    assert SpeechDirector.get_condition_key(dec_whisper) == "whispering"

    # 2. Disabled tags must resolve to neutral, NEVER to an unrelated profile
    dec_crying_tag = SpeechDecision(emotion="empathetic", intensity=0.8, delivery="soft", tags=("crying",))
    assert SpeechDirector.get_condition_key(dec_crying_tag) == "neutral"  # NEVER sigh

    dec_gasp = SpeechDecision(emotion="surprised", intensity=0.5, delivery="conversational", tags=("gasp",))
    assert SpeechDirector.get_condition_key(dec_gasp) == "neutral"  # Disabled gasp resolves to neutral

    dec_sigh = SpeechDecision(emotion="empathetic", intensity=0.5, delivery="conversational", tags=("sigh",))
    assert SpeechDirector.get_condition_key(dec_sigh) == "neutral"  # Disabled sigh resolves to neutral

    dec_angry = SpeechDecision(emotion="serious", intensity=0.7, delivery="firm", tags=("angry",))
    assert SpeechDirector.get_condition_key(dec_angry) == "neutral"  # Disabled angry resolves to neutral

    # 3. Emotion mappings when no tags
    dec_empath = SpeechDecision(emotion="empathetic", intensity=0.5, delivery="conversational", tags=())
    assert SpeechDirector.get_condition_key(dec_empath) == "neutral"  # Corrected: no longer sigh

    dec_serious = SpeechDecision(emotion="serious", intensity=0.5, delivery="conversational", tags=())
    assert SpeechDirector.get_condition_key(dec_serious) == "neutral"  # Corrected: no longer angry

    dec_surprised = SpeechDecision(emotion="surprised", intensity=0.5, delivery="conversational", tags=())
    assert SpeechDirector.get_condition_key(dec_surprised) == "neutral"  # Corrected: no longer surprised profile

    dec_warm = SpeechDecision(emotion="warm", intensity=0.5, delivery="conversational", tags=())
    assert SpeechDirector.get_condition_key(dec_warm) == "happy"

    dec_playful = SpeechDecision(emotion="playful", intensity=0.5, delivery="conversational", tags=())
    assert SpeechDirector.get_condition_key(dec_playful) == "neutral"

    dec_unknown = SpeechDecision(emotion="unknown_emotion", intensity=0.5, delivery="conversational", tags=())
    assert SpeechDirector.get_condition_key(dec_unknown) == "neutral"


def test_disabled_upstream_tags_cannot_bypass_policy():
    director = SpeechDirector(allow_vocal_effects=True, allow_experimental_emotion_tags=True)

    # An upstream prompt with [crying] or [sigh] or [angry] should have tag stripped from decision
    dec_crying = director.decide("[crying] Please listen to me.")
    assert "crying" not in dec_crying.tags
    assert dec_crying.tags == ()
    rendered_crying = director.render("[crying] Please listen to me.")
    assert not rendered_crying.startswith("[crying]")

    dec_sigh = director.decide("[sigh] That is frustrating.")
    assert "sigh" not in dec_sigh.tags
    assert dec_sigh.tags == ()
    rendered_sigh = director.render("[sigh] That is frustrating.")
    assert not rendered_sigh.startswith("[sigh]")

    dec_angry = director.decide("[angry] Stop right now.")
    assert "angry" not in dec_angry.tags
    assert dec_angry.tags == ()
    rendered_angry = director.render("[angry] Stop right now.")
    assert not rendered_angry.startswith("[angry]")


def test_per_expression_blend_weights():
    director = SpeechDirector(
        expression_blend_weights={
            "happy": 0.65,
            "dramatic": 0.60,
            "whispering": 0.70,
            "laugh": 0.50,
        }
    )

    dec_happy = SpeechDecision(emotion="warm", intensity=0.6, delivery="cheerful", tags=("happy",))
    assert director.get_blend_weight(dec_happy) == 0.65

    dec_dramatic = SpeechDecision(emotion="dramatic", intensity=0.7, delivery="measured", tags=("dramatic",))
    assert director.get_blend_weight(dec_dramatic) == 0.60

    dec_whisper = SpeechDecision(emotion="thoughtful", intensity=0.5, delivery="intimate", tags=("whispering",))
    assert director.get_blend_weight(dec_whisper) == 0.70

    dec_laugh = SpeechDecision(emotion="amused", intensity=0.5, delivery="playful", tags=("laugh",))
    assert director.get_blend_weight(dec_laugh) == 0.50

    dec_neutral = SpeechDecision(emotion="neutral", intensity=0.5, delivery="conversational", tags=())
    assert director.get_blend_weight(dec_neutral) == 0.65  # Default fallback


def test_from_config_factory():
    from friday.config import SpeechDirectorConfig

    cfg = SpeechDirectorConfig(
        production_tags=["happy", "dramatic"],
        limited_tags=["laugh"],
        disabled_tags=["sigh", "chuckle", "crying"],
        expression_blend_weights={"happy": 0.62, "laugh": 0.48},
    )
    director = SpeechDirector.from_config(cfg)
    assert director.production_tags == {"happy", "dramatic"}
    assert director.limited_tags == {"laugh"}
    assert "sigh" in director.disabled_tags
    assert director.expression_blend_weights["happy"] == 0.62
    assert director.expression_blend_weights["laugh"] == 0.48

