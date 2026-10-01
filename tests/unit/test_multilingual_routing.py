"""
tests/unit/test_multilingual_routing.py

Unit tests for the hybrid multi-engine SpeechSynthesizer routing.
Verifies language detection, dynamic routing of non-English turns to Gemini Voice,
preservation of Chatterbox Turbo for English turns, and fallback mechanisms.
"""

from unittest.mock import MagicMock, patch
import numpy as np

from friday.interaction.tts import (
    SpeechSynthesizer,
    GeminiTTSSynthesizer,
    detect_language,
)
from friday.interaction.stt import VoiceState


def test_language_detection():
    # English sentences
    assert detect_language("Good morning boss, how are you?") == "en"
    assert detect_language("All systems are operational and ready.") == "en"
    assert detect_language("[happy] I would be delighted to assist.") == "en"
    assert detect_language("Running system diagnostic tests now.") == "en"
    assert detect_language("") == "en"

    # Indonesian sentences
    assert detect_language("Selamat pagi boss, ada yang bisa saya bantu?") == "id"
    assert detect_language("Sistem sudah siap digunakan sekarang.") == "id"
    assert detect_language("Apa kabar hari ini?") == "id"
    assert detect_language("Terima kasih banyak atas bantuannya.") == "id"

    # Sundanese sentences
    assert detect_language("Wilujeng enjing, kumaha damang?") == "id"
    assert detect_language("Hatur nuhun pisan, mangga.") == "id"

    # Other non-English languages
    assert detect_language("こんにちは、元気ですか？") == "other"
    assert detect_language("你好，世界") == "other"


@patch("friday.interaction.tts.ChatterboxTurboSynthesizer._ensure_model")
def test_speech_synthesizer_routes_english_to_chatterbox(mock_ensure):
    synth = SpeechSynthesizer(multilingual_routing=True)
    synth._chatterbox_backend = MagicMock()
    synth._multilingual_backend = MagicMock()
    synth._active_backend = synth._chatterbox_backend

    synth._chatterbox_backend._build_audio.return_value = np.zeros(24000, dtype=np.float32)

    synth._build_audio("All systems are online, Boss.", emotion="happy", blend_weight=0.65)

    synth._chatterbox_backend._build_audio.assert_called_once_with(
        "All systems are online, Boss.", emotion="happy", blend_weight=0.65
    )
    synth._multilingual_backend._build_audio.assert_not_called()


@patch("friday.interaction.tts.ChatterboxTurboSynthesizer._ensure_model")
def test_speech_synthesizer_routes_indonesian_to_multilingual_backend(mock_ensure):
    synth = SpeechSynthesizer(multilingual_routing=True)
    synth._chatterbox_backend = MagicMock()
    synth._multilingual_backend = MagicMock()
    synth._active_backend = synth._chatterbox_backend

    synth._multilingual_backend._build_audio.return_value = np.zeros(24000, dtype=np.float32)

    synth._build_audio("Selamat pagi boss, ada yang bisa saya bantu?")

    synth._multilingual_backend._build_audio.assert_called_once_with(
        "Selamat pagi boss, ada yang bisa saya bantu?", emotion=None, blend_weight=None
    )
    synth._chatterbox_backend._build_audio.assert_not_called()


@patch("friday.interaction.tts.ChatterboxTurboSynthesizer._ensure_model")
def test_speech_synthesizer_routes_foreign_to_multilingual_backend(mock_ensure):
    synth = SpeechSynthesizer(multilingual_routing=True)
    synth._chatterbox_backend = MagicMock()
    synth._multilingual_backend = MagicMock()
    synth._active_backend = synth._chatterbox_backend

    synth._multilingual_backend._build_audio.return_value = np.zeros(24000, dtype=np.float32)

    synth._build_audio("こんにちは、世界")

    synth._multilingual_backend._build_audio.assert_called_once_with(
        "こんにちは、世界", emotion=None, blend_weight=None
    )
    synth._chatterbox_backend._build_audio.assert_not_called()


@patch("friday.interaction.tts.ChatterboxTurboSynthesizer._ensure_model")
def test_speech_synthesizer_routing_disabled_routes_all_to_chatterbox(mock_ensure):
    synth = SpeechSynthesizer(multilingual_routing=False)
    synth._chatterbox_backend = MagicMock()
    synth._multilingual_backend = None
    synth._active_backend = synth._chatterbox_backend

    synth._chatterbox_backend._build_audio.return_value = np.zeros(24000, dtype=np.float32)

    synth._build_audio("Selamat pagi boss, ada yang bisa saya bantu?")

    synth._chatterbox_backend._build_audio.assert_called_once_with(
        "Selamat pagi boss, ada yang bisa saya bantu?", emotion=None, blend_weight=None
    )


@patch("friday.interaction.tts.ChatterboxTurboSynthesizer._ensure_model")
def test_speech_synthesizer_multilingual_fallback_on_failure(mock_ensure):
    synth = SpeechSynthesizer(multilingual_routing=True)
    synth._chatterbox_backend = MagicMock()
    synth._multilingual_backend = MagicMock()
    synth._active_backend = synth._chatterbox_backend

    # Simulate network failure on multilingual engine
    synth._multilingual_backend._build_audio.side_effect = RuntimeError("Network down")
    synth._chatterbox_backend._build_audio.return_value = np.zeros(24000, dtype=np.float32)

    audio = synth._build_audio("Selamat pagi boss")

    # Should fall back cleanly to Chatterbox
    synth._chatterbox_backend._build_audio.assert_called_once()
    assert len(audio) == 24000


@patch("friday.interaction.tts.ChatterboxTurboSynthesizer._ensure_model")
def test_speech_synthesizer_interrupt_propagation(mock_ensure):
    synth = SpeechSynthesizer(multilingual_routing=True)
    synth._chatterbox_backend = MagicMock()
    synth._multilingual_backend = MagicMock()

    synth.cancel()
    synth._chatterbox_backend.cancel.assert_called_once()
    synth._multilingual_backend.cancel.assert_called_once()

    synth.reset_interrupt()
    synth._chatterbox_backend.reset_interrupt.assert_called_once()
    synth._multilingual_backend.reset_interrupt.assert_called_once()


@patch("friday.interaction.tts.ChatterboxTurboSynthesizer._ensure_model")
def test_speech_synthesizer_speaking_state_aggregation(mock_ensure):
    synth = SpeechSynthesizer(multilingual_routing=True)
    synth._chatterbox_backend = MagicMock()
    synth._multilingual_backend = MagicMock()

    # Case 1: Both idle
    synth._chatterbox_backend.get_state.return_value = VoiceState.IDLE
    synth._multilingual_backend.get_state.return_value = VoiceState.IDLE
    assert synth.get_state() == VoiceState.IDLE

    # Case 2: Multilingual backend speaking
    synth._multilingual_backend.get_state.return_value = VoiceState.SPEAKING
    assert synth.get_state() == VoiceState.SPEAKING

    # Case 3: Chatterbox backend speaking
    synth._chatterbox_backend.get_state.return_value = VoiceState.SPEAKING
    synth._multilingual_backend.get_state.return_value = VoiceState.IDLE
    assert synth.get_state() == VoiceState.SPEAKING


def test_gemini_tts_synthesizer_build_audio():
    synth = GeminiTTSSynthesizer(api_key="test-key", voice="Aoede")
    synth._client = MagicMock()

    mock_interaction = MagicMock()
    mock_audio = MagicMock()
    # 1 second of 24kHz int16 zero audio in bytes
    raw_pcm = np.zeros(24000, dtype=np.int16).tobytes()
    mock_audio.data = raw_pcm
    mock_audio.sample_rate = 24000
    mock_interaction.output_audio = mock_audio
    synth._client.interactions.create.return_value = mock_interaction

    audio = synth._build_audio("Halo, selamat pagi")
    assert isinstance(audio, np.ndarray)
    # Includes 0.06s start and 0.12s end padding (4320 samples)
    assert len(audio) == 24000 + int(0.18 * 24000)
    synth._client.interactions.create.assert_called_once()
    call_kwargs = synth._client.interactions.create.call_args.kwargs
    assert call_kwargs["input"] == "Halo, selamat pagi"


def test_gemini_tts_synthesizer_emotion_directive_mapping():
    synth = GeminiTTSSynthesizer(api_key="test-key", voice="Aoede")
    synth._client = MagicMock()
    mock_interaction = MagicMock()
    mock_audio = MagicMock()
    mock_audio.data = np.zeros(24000, dtype=np.int16).tobytes()
    mock_audio.sample_rate = 24000
    mock_interaction.output_audio = mock_audio
    synth._client.interactions.create.return_value = mock_interaction

    # Case 1: Emotion tag prefix in text [happy]
    synth._build_audio("[happy] Halo, selamat pagi Boss!")
    call_kwargs = synth._client.interactions.create.call_args.kwargs
    assert call_kwargs["input"] == "Say cheerfully: Halo, selamat pagi Boss!"

    # Case 2: Explicit emotion argument
    synth._build_audio("Peringatan kritis terjadi.", emotion="dramatic")
    call_kwargs = synth._client.interactions.create.call_args.kwargs
    assert call_kwargs["input"] == "Say dramatically: Peringatan kritis terjadi."

    # Case 3: Whispering tag
    synth._build_audio("[whispering] Rahasia ini sangat penting.")
    call_kwargs = synth._client.interactions.create.call_args.kwargs
    assert call_kwargs["input"] == "Say in a whisper: Rahasia ini sangat penting."


@patch("friday.interaction.tts.ChatterboxTurboSynthesizer._ensure_model")
def test_speech_synthesizer_turn_language_locking(mock_ensure):
    synth = SpeechSynthesizer(multilingual_routing=True)
    synth._chatterbox_backend = MagicMock()
    synth._multilingual_backend = MagicMock()
    synth._active_backend = synth._chatterbox_backend

    synth._chatterbox_backend._build_audio.return_value = np.zeros(24000, dtype=np.float32)
    synth._multilingual_backend._build_audio.return_value = np.zeros(24000, dtype=np.float32)

    # 1. Turn locked to English (User spoke English)
    synth.set_turn_language("en")
    assert synth.get_turn_language() == "en"

    # Even if Friday outputs an Indonesian greeting, she stays on Chatterbox Turbo (Lune's voice)
    synth._build_audio("Selamat pagi Boss, let me check that.")
    synth._chatterbox_backend._build_audio.assert_called_once()
    synth._multilingual_backend._build_audio.assert_not_called()

    # 2. Turn locked to Indonesian (User spoke Indonesian)
    synth._chatterbox_backend._build_audio.reset_mock()
    synth._multilingual_backend._build_audio.reset_mock()
    synth.set_turn_language("id")
    assert synth.get_turn_language() == "id"

    # Even if Friday opens with an English acknowledgement, she stays on Gemini Voice
    synth._build_audio("Alright Boss, saya siap membantu.")
    synth._multilingual_backend._build_audio.assert_called_once()
    synth._chatterbox_backend._build_audio.assert_not_called()

    # 3. Turn unlocked (None) -> falls back to sentence detection
    synth._chatterbox_backend._build_audio.reset_mock()
    synth._multilingual_backend._build_audio.reset_mock()
    synth.set_turn_language(None)
    assert synth.get_turn_language() is None

    synth._build_audio("Good morning Boss.")
    synth._chatterbox_backend._build_audio.assert_called_once()
    synth._multilingual_backend._build_audio.assert_not_called()


