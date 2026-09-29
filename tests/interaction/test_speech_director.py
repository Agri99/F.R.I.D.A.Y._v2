"""
tests/interaction/test_speech_director.py

Unit tests for SpeechDirector policy engine, tag injection, and idempotence.
"""

from __future__ import annotations

from friday.interaction.speech_director import SpeechContext, SpeechDirector


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


def test_empathy_rule_emits_sigh_when_allowed():
    director_enabled = SpeechDirector(allow_vocal_effects=True)
    ctx_failed = SpeechContext(task_status="FAILED")

    dec = director_enabled.decide("I'm sorry, I couldn't find any results for that.", context=ctx_failed)
    assert dec.emotion == "empathetic"
    assert "sigh" in dec.tags

    rendered = director_enabled.render("I'm sorry, I couldn't find any results for that.", context=ctx_failed)
    assert rendered.startswith("[sigh] ")
    assert "I'm sorry, I couldn't find any results for that." in rendered

    # When vocal effects disabled:
    director_disabled = SpeechDirector(allow_vocal_effects=False)
    dec_disabled = director_disabled.decide("I'm sorry, I couldn't find any results for that.", context=ctx_failed)
    assert dec_disabled.tags == ()
    assert not director_disabled.render("I'm sorry, I couldn't find any results for that.", context=ctx_failed).startswith("[sigh]")


def test_playful_rule_emits_chuckle_when_appropriate():
    director = SpeechDirector(allow_vocal_effects=True)
    dec = director.decide("Haha, that is definitely funny.")

    assert dec.emotion == "amused"
    assert "chuckle" in dec.tags

    rendered = director.render("Haha, that is definitely funny.")
    assert rendered.startswith("[chuckle] ")


def test_experimental_emotion_tags_blocked_by_default():
    director_default = SpeechDirector(allow_experimental_emotion_tags=False)
    ctx_done = SpeechContext(task_status="COMPLETED")

    dec_default = director_default.decide("Task completed successfully.", context=ctx_done)
    assert "happy" not in dec_default.tags

    rendered = director_default.render("Task completed successfully.", context=ctx_done)
    assert "[happy]" not in rendered

    # Allowed when explicitly enabled
    director_experimental = SpeechDirector(allow_experimental_emotion_tags=True)
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
    director = SpeechDirector(allow_vocal_effects=True)
    original = "I apologize, but that operation failed."
    ctx = SpeechContext(task_status="FAILED")

    once = director.render(original, context=ctx)
    twice = director.render(once, context=ctx)
    thrice = director.render(twice, context=ctx)

    assert once == twice == thrice
    assert once.count("[sigh]") == 1


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
    director = SpeechDirector(allow_vocal_effects=True)
    rendered = director.render("[chuckle] Well that was unexpected.")
    assert rendered == "[chuckle] Well— that was unexpected."


def test_get_condition_key_mapping():
    from friday.interaction.speech_director import SpeechDecision, SpeechDirector

    # 1. Tags take precedence
    dec_laugh = SpeechDecision(emotion="neutral", intensity=0.5, delivery="conversational", tags=("laugh",))
    assert SpeechDirector.get_condition_key(dec_laugh) == "chuckle"

    dec_gasp = SpeechDecision(emotion="neutral", intensity=0.5, delivery="conversational", tags=("gasp",))
    assert SpeechDirector.get_condition_key(dec_gasp) == "surprised"

    dec_sigh = SpeechDecision(emotion="neutral", intensity=0.5, delivery="conversational", tags=("sigh",))
    assert SpeechDirector.get_condition_key(dec_sigh) == "sigh"

    # 2. Emotion mappings when no tags
    dec_empath = SpeechDecision(emotion="empathetic", intensity=0.5, delivery="conversational", tags=())
    assert SpeechDirector.get_condition_key(dec_empath) == "sigh"

    dec_warm = SpeechDecision(emotion="warm", intensity=0.5, delivery="conversational", tags=())
    assert SpeechDirector.get_condition_key(dec_warm) == "happy"

    dec_playful = SpeechDecision(emotion="playful", intensity=0.5, delivery="conversational", tags=())
    assert SpeechDirector.get_condition_key(dec_playful) == "chuckle"

    dec_serious = SpeechDecision(emotion="serious", intensity=0.5, delivery="conversational", tags=())
    assert SpeechDirector.get_condition_key(dec_serious) == "angry"

    dec_unknown = SpeechDecision(emotion="unknown_emotion", intensity=0.5, delivery="conversational", tags=())
    assert SpeechDirector.get_condition_key(dec_unknown) == "neutral"

