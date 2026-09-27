"""
tests/interaction/test_tts_tags.py

Unit tests for clean_tts_text tag preservation and Markdown stripping.
"""

from __future__ import annotations

from friday.interaction.tts import (
    CHATTERBOX_EVENT_TAGS,
    CHATTERBOX_EXPERIMENTAL_EMOTION_TAGS,
    clean_tts_text,
)


def test_markdown_stripped_while_tags_preserved():
    raw = "**Hello** Boss! [chuckle] Here is the `information`: *check it out*."
    cleaned = clean_tts_text(raw, preserve_emotion_tags=True)

    assert "[chuckle]" in cleaned
    assert "**" not in cleaned
    assert "`" not in cleaned
    assert "*" not in cleaned
    assert "Hello Boss! [chuckle] Here is the information: check it out." == cleaned


def test_tags_with_spaces_and_hyphens_survive():
    sample1 = "[clear throat] Excuse me, Boss."
    assert clean_tts_text(sample1, preserve_emotion_tags=True) == "[clear throat] Excuse me, Boss."

    sample2 = "[throat-clearing] Ahem, right here."
    assert clean_tts_text(sample2, preserve_emotion_tags=True) == "[throat-clearing] Ahem, right here."

    sample3 = "[throat clearing] Right away."
    assert clean_tts_text(sample3, preserve_emotion_tags=True) == "[throat clearing] Right away."


def test_event_and_experimental_tags_preserved_when_flag_true():
    for tag in ["sigh", "gasp", "chuckle", "laugh", "happy", "sarcastic", "whispering"]:
        text = f"[{tag}] This is test text."
        assert clean_tts_text(text, preserve_emotion_tags=True) == text


def test_tags_stripped_when_preserve_is_false():
    for tag in ["sigh", "gasp", "chuckle", "clear throat", "throat-clearing"]:
        text = f"[{tag}] This is test text."
        cleaned = clean_tts_text(text, preserve_emotion_tags=False)
        assert f"[{tag}]" not in cleaned
        assert cleaned == "This is test text."


def test_tag_sets_contain_expected_members():
    assert "sigh" in CHATTERBOX_EVENT_TAGS
    assert "gasp" in CHATTERBOX_EVENT_TAGS
    assert "chuckle" in CHATTERBOX_EVENT_TAGS
    assert "clear throat" in CHATTERBOX_EVENT_TAGS

    assert "happy" in CHATTERBOX_EXPERIMENTAL_EMOTION_TAGS
    assert "sarcastic" in CHATTERBOX_EXPERIMENTAL_EMOTION_TAGS
    assert "whispering" in CHATTERBOX_EXPERIMENTAL_EMOTION_TAGS
