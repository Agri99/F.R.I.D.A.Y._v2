from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import torch

from friday.interaction.tts import (
    SpeechSynthesizer,
    ChatterboxTurboSynthesizer,
    TTSResult,
    clean_tts_text,
    CHATTERBOX_TAGS,
    PARALINGUISTIC_TAGS,
)
from friday.interaction.stt import VoiceState


class TestChatterboxTTS(unittest.TestCase):
    def test_clean_tts_text_preserves_emotion_tags_for_chatterbox(self):
        text = "Hello Boss! [happy] [chuckle] I am **ready** for your command. [sigh]"
        cleaned = clean_tts_text(text, preserve_emotion_tags=True)
        self.assertIn("[happy]", cleaned)
        self.assertIn("[chuckle]", cleaned)
        self.assertIn("[sigh]", cleaned)
        self.assertNotIn("**", cleaned)
        self.assertIn("ready", cleaned)

    def test_clean_tts_text_can_strip_emotion_tags(self):
        text = "Hello Boss! [happy] [chuckle] I am **ready** for your command. [sigh]"
        cleaned = clean_tts_text(text, preserve_emotion_tags=False)
        self.assertNotIn("[happy]", cleaned)
        self.assertNotIn("[chuckle]", cleaned)
        self.assertNotIn("[sigh]", cleaned)
        self.assertNotIn("**", cleaned)
        self.assertEqual(cleaned, "Hello Boss! I am ready for your command.")

    def test_clean_tts_text_strips_markdown_links(self):
        text = "Open [Google Search](https://google.com) right now [whisper]."
        cleaned = clean_tts_text(text, preserve_emotion_tags=True)
        self.assertEqual(cleaned, "Open Google Search right now [whisper].")

    @patch("chatterbox.tts_turbo.ChatterboxTurboTTS.from_pretrained")
    def test_chatterbox_synthesizer_build_audio_and_speak(self, mock_from_pretrained):
        mock_model = MagicMock()
        mock_model.sr = 24000
        # Return fake 1-second sine wave
        mock_model.generate.return_value = torch.zeros((1, 24000), dtype=torch.float32)
        mock_from_pretrained.return_value = mock_model

        synth = ChatterboxTurboSynthesizer(device="cuda")
        with patch("sounddevice.play") as mock_play, patch("sounddevice.wait"):
            res = synth.speak("Testing [laugh] Chatterbox Turbo.")
            self.assertTrue(res.success)
            self.assertGreater(res.duration_seconds, 0.0)
            mock_play.assert_called_once()
            args, kwargs = mock_play.call_args
            self.assertEqual(kwargs["samplerate"], 24000)

    @patch("chatterbox.tts_turbo.ChatterboxTurboTTS.from_pretrained")
    def test_speech_synthesizer_initializes_chatterbox(self, mock_from_pretrained):
        mock_model = MagicMock()
        mock_model.sr = 24000
        mock_from_pretrained.return_value = mock_model

        synth = SpeechSynthesizer(engine="chatterbox_turbo", device="cuda")
        self.assertEqual(synth.engine, "chatterbox_turbo")
        self.assertEqual(synth.sample_rate, 24000)

    @patch("friday.interaction.tts.ChatterboxTurboSynthesizer._ensure_model")
    def test_speech_synthesizer_handles_speak_failure_gracefully(self, mock_ensure):
        synth = SpeechSynthesizer(engine="chatterbox_turbo")
        with patch.object(synth._active_backend, "speak", return_value=TTSResult(success=False, error="Device busy")):
            res = synth.speak("Testing failure")
            self.assertFalse(res.success)
            self.assertEqual(res.error, "Device busy")

    @patch("chatterbox.tts_turbo.ChatterboxTurboTTS.from_pretrained")
    def test_cancel_stops_playback(self, mock_from_pretrained):
        mock_model = MagicMock()
        mock_model.sr = 24000
        mock_from_pretrained.return_value = mock_model

        synth = ChatterboxTurboSynthesizer(device="cuda")
        synth._current_audio = np.zeros(1000, dtype=np.float32)
        with patch("sounddevice.stop") as mock_stop:
            synth.cancel()
            mock_stop.assert_called_once()
            self.assertEqual(synth.get_state(), VoiceState.IDLE)
            self.assertTrue(synth._interrupt_event.is_set())

    @patch("chatterbox.tts_turbo.ChatterboxTurboTTS.from_pretrained")
    def test_reset_interrupt_allows_subsequent_playback(self, mock_from_pretrained):
        mock_model = MagicMock()
        mock_model.sr = 24000
        mock_model.generate.return_value = torch.zeros((1, 24000), dtype=torch.float32)
        mock_from_pretrained.return_value = mock_model

        synth = ChatterboxTurboSynthesizer(device="cuda")
        synth.cancel()
        # Immediately speaking while cancelled returns interrupted without building audio
        res_cancelled = synth.speak("Interrupted sentence")
        self.assertTrue(res_cancelled.interrupted)

        # Resetting the interrupt event allows subsequent speech
        synth.reset_interrupt()
        with patch("sounddevice.play"), patch("sounddevice.wait"):
            res_resumed = synth.speak("Subsequent sentence")
            self.assertTrue(res_resumed.success)
            self.assertFalse(res_resumed.interrupted)

    @patch("friday.interaction.tts.ChatterboxTurboSynthesizer._ensure_model")
    def test_speech_synthesizer_delegates_reset_interrupt(self, mock_ensure):
        synth = SpeechSynthesizer(engine="chatterbox_turbo")
        synth._active_backend._interrupt_event.set()
        self.assertTrue(synth._active_backend._interrupt_event.is_set())

        synth.reset_interrupt()
        self.assertFalse(synth._active_backend._interrupt_event.is_set())


if __name__ == "__main__":
    unittest.main()

