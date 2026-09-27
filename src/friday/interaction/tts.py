"""Text-to-speech module using Resemble AI's Chatterbox Turbo for natural expressive neural TTS."""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import sounddevice as sd

from friday.interaction.stt import VoiceState

logger = logging.getLogger(__name__)

# Full list of emotion delivery & vocal sound effect tags supported natively by Chatterbox Turbo:
# Emotion delivery tags (changes tone, mood, prosody):
#   [happy], [sarcastic], [whispering], [whisper], [angry], [surprised],
#   [dramatic], [fear], [crying], [advertisement], [narration]
# Vocal sound effect tags (real human vocal expressions):
#   [laugh], [chuckle], [sigh], [gasp], [cough], [groan],
#   [sniff], [clear throat], [shush], [throat-clearing], [giggle], [pant], [grunt], [snicker]
CHATTERBOX_TAGS = {
    "happy", "sarcastic", "whispering", "whisper", "angry", "surprised",
    "dramatic", "fear", "crying", "advertisement", "narration",
    "laugh", "chuckle", "sigh", "gasp", "cough", "groan",
    "sniff", "clear throat", "shush", "throat-clearing", "giggle", "pant", "grunt", "snicker",
}
PARALINGUISTIC_TAGS = CHATTERBOX_TAGS

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_MODELS_DIR = _PROJECT_ROOT / "models"


def clean_tts_text(text: str, preserve_emotion_tags: bool = True) -> str:
    """Cleans text for TTS reading, preserving emotion and paralinguistic tags by default."""
    # Convert markdown links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Strip basic markdown formatting
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)

    if not preserve_emotion_tags:
        # Strip all bracketed emotion tags if explicitly requested
        pattern = r'\[(' + '|'.join(re.escape(tag) for tag in CHATTERBOX_TAGS) + r')\]'
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # Clean redundant whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _strip_markdown(text: str) -> str:
    """Cleans markdown formatting while preserving natural expression tags."""
    return clean_tts_text(text, preserve_emotion_tags=True)


@dataclass
class TTSResult:
    """Result of TTS synthesis and playback."""
    success: bool
    interrupted: bool = False
    duration_seconds: float = 0.0
    error: str | None = None


class ChatterboxTurboSynthesizer:
    """Synthesizes expressive, human-like speech using Resemble AI's Chatterbox Turbo."""

    def __init__(
        self,
        device: str = "cuda",
        audio_prompt_path: str | None = None,
        model_path: str | None = None,
        exaggeration: float = 0.5,
        **kwargs: Any,
    ):
        self.device = device
        self.model_path = model_path
        self.audio_prompt_path = audio_prompt_path

        # 1. Resolve custom model directory
        if not self.model_path:
            model_cands = [
                _MODELS_DIR / "chatterbox-turbo",
                _MODELS_DIR / "chatterbox_turbo",
                _MODELS_DIR / "chatterbox",
                Path("models/chatterbox-turbo"),
                Path("models/chatterbox_turbo"),
                Path("models/chatterbox"),
            ]
            for cand in model_cands:
                if cand.exists():
                    self.model_path = str(cand.resolve())
                    break
        elif self.model_path:
            p = Path(self.model_path)
            if not p.is_absolute():
                if (_MODELS_DIR / p.name).exists():
                    self.model_path = str((_MODELS_DIR / p.name).resolve())
                elif (_PROJECT_ROOT / p).exists():
                    self.model_path = str((_PROJECT_ROOT / p).resolve())

        # 2. Auto-detect reference audio sample for speaker timbre
        if not self.audio_prompt_path:
            voice_cands = [
                _MODELS_DIR / "voice_reference.wav",
                _MODELS_DIR / "speaker_reference.wav",
                _MODELS_DIR / "voice_prompt.wav",
                _MODELS_DIR / "speaker.wav",
                _MODELS_DIR / "reference.wav",
                Path("models/voice_reference.wav"),
                Path("models/speaker_reference.wav"),
                Path("models/voice_prompt.wav"),
                Path("models/speaker.wav"),
                Path("models/reference.wav"),
            ]
            for cand in voice_cands:
                if cand.exists():
                    self.audio_prompt_path = str(cand.resolve())
                    break
        elif self.audio_prompt_path:
            p = Path(self.audio_prompt_path)
            if not p.is_absolute():
                if (_MODELS_DIR / p.name).exists():
                    self.audio_prompt_path = str((_MODELS_DIR / p.name).resolve())
                elif (_PROJECT_ROOT / p).exists():
                    self.audio_prompt_path = str((_PROJECT_ROOT / p).resolve())

        self.exaggeration = float(exaggeration)
        self.model: Any = None
        self.sample_rate = 24000
        self._state_callback: Callable[[VoiceState], None] | None = None
        self._interrupt_event = threading.Event()
        self._current_audio: np.ndarray | None = None
        self._lock = threading.Lock()

    def set_state_callback(self, callback: Callable[[VoiceState], None]):
        self._state_callback = callback

    def _set_state(self, state: VoiceState):
        if self._state_callback:
            self._state_callback(state)

    def _ensure_model(self):
        if self.model is None:
            with self._lock:
                    import torch
                    from chatterbox.tts_turbo import ChatterboxTurboTTS
                    # Silence benign warning about CFG/exaggeration being ignored in Turbo mode
                    logging.getLogger("chatterbox.tts_turbo").setLevel(logging.ERROR)
                    dev = self.device
                    if dev == "cuda" and not torch.cuda.is_available():
                        logger.warning("CUDA requested for Chatterbox Turbo but not available. Falling back to CPU.")
                        dev = "cpu"
                    logger.info("Loading Chatterbox Turbo on %s...", dev)

                    # Patch Chatterbox norm_loudness to guarantee float32 array output
                    # Preventing numpy float promotion to float64 which triggers "expected scalar type Double but found Float"
                    orig_norm = getattr(ChatterboxTurboTTS, "_friday_orig_norm_loudness", None)
                    if orig_norm is None:
                        ChatterboxTurboTTS._friday_orig_norm_loudness = ChatterboxTurboTTS.norm_loudness

                        def safe_norm_loudness(model_self, wav, sr, target_lufs=-27):
                            out = ChatterboxTurboTTS._friday_orig_norm_loudness(model_self, wav, sr, target_lufs=target_lufs)
                            if isinstance(out, np.ndarray):
                                return out.astype(np.float32)
                            return out

                        ChatterboxTurboTTS.norm_loudness = safe_norm_loudness

                    # Patch Chatterbox prepare_conditionals to auto-tile audio prompts <= 5s
                    # Resolves "AssertionError: Audio prompt must be longer than 5 seconds!" for clips like Lune 106
                    orig_prepare = getattr(ChatterboxTurboTTS, "_friday_orig_prepare_conditionals", None)
                    if orig_prepare is None:
                        ChatterboxTurboTTS._friday_orig_prepare_conditionals = ChatterboxTurboTTS.prepare_conditionals

                        def safe_prepare_conditionals(model_self, wav_fpath, exaggeration=0.5, norm_loudness=True):
                            import librosa
                            import math
                            from chatterbox.tts_turbo import S3GEN_SR, S3_SR, T3Cond, Conditionals
                            s3gen_ref_wav, _sr = librosa.load(wav_fpath, sr=S3GEN_SR)
                            s3gen_ref_wav = s3gen_ref_wav.astype(np.float32)
                            duration = len(s3gen_ref_wav) / _sr
                            if duration <= 5.0 and duration > 0:
                                repeats = int(math.ceil(5.5 / duration))
                                s3gen_ref_wav = np.tile(s3gen_ref_wav, repeats)
                            if norm_loudness:
                                s3gen_ref_wav = model_self.norm_loudness(s3gen_ref_wav, _sr)
                            ref_16k_wav = librosa.resample(s3gen_ref_wav, orig_sr=S3GEN_SR, target_sr=S3_SR)
                            s3gen_ref_wav = s3gen_ref_wav[:model_self.DEC_COND_LEN]
                            s3gen_ref_dict = model_self.s3gen.embed_ref(s3gen_ref_wav, S3GEN_SR, device=model_self.device)
                            if plen := model_self.t3.hp.speech_cond_prompt_len:
                                s3_tokzr = model_self.s3gen.tokenizer
                                t3_cond_prompt_tokens, _ = s3_tokzr.forward([ref_16k_wav[:model_self.ENC_COND_LEN]], max_len=plen)
                                t3_cond_prompt_tokens = torch.atleast_2d(t3_cond_prompt_tokens).to(model_self.device)
                            ve_embed = torch.from_numpy(model_self.ve.embeds_from_wavs([ref_16k_wav], sample_rate=S3_SR))
                            ve_embed = ve_embed.mean(axis=0, keepdim=True).to(model_self.device)
                            t3_cond = T3Cond(
                                speaker_emb=ve_embed,
                                cond_prompt_speech_tokens=t3_cond_prompt_tokens,
                                emotion_adv=exaggeration * torch.ones(1, 1, 1),
                            ).to(device=model_self.device)
                            model_self.conds = Conditionals(t3_cond, s3gen_ref_dict)

                        ChatterboxTurboTTS.prepare_conditionals = safe_prepare_conditionals


                    # 1. Custom model path if specified or detected
                    chosen_local = None
                    if self.model_path and Path(self.model_path).exists():
                        chosen_local = Path(self.model_path)

                    if chosen_local and hasattr(ChatterboxTurboTTS, "from_local"):
                        print(f"FRIDAY [Voice]: Loading custom trained Chatterbox model from {chosen_local}...")
                        self.model = ChatterboxTurboTTS.from_local(chosen_local, device=dev)
                    else:
                        print("FRIDAY [Voice]: Loading pretrained Chatterbox model from Hugging Face...")
                        self.model = ChatterboxTurboTTS.from_pretrained(device=dev)

                    self.device = dev
                    if hasattr(self.model, "sr"):
                        self.sample_rate = int(self.model.sr)
                    if self.audio_prompt_path and Path(self.audio_prompt_path).exists():
                        logger.info("Preparing reference conditionals from %s...", self.audio_prompt_path)
                        print(f"FRIDAY [Voice]: Applied custom voice timbre reference from {self.audio_prompt_path}")
                        self.model.prepare_conditionals(str(self.audio_prompt_path), exaggeration=self.exaggeration)

    def _build_audio(self, text: str) -> np.ndarray:
        self._ensure_model()
        cleaned = clean_tts_text(text, preserve_emotion_tags=True)
        if not cleaned:
            return np.zeros(0, dtype=np.float32)

        prompt_path = str(self.audio_prompt_path) if (self.audio_prompt_path and Path(self.audio_prompt_path).exists()) else None
        # If conditionals have already been prepared/cached in the model, pass None to avoid recomputing every turn
        prompt_to_pass = None if getattr(self.model, "conds", None) is not None else prompt_path
        wav_tensor = self.model.generate(
            cleaned,
            audio_prompt_path=prompt_to_pass,
            exaggeration=self.exaggeration,
        )
        wav = wav_tensor.squeeze().detach().cpu().numpy().astype(np.float32)
        # Gentle padding for natural cadence
        padding_start = np.zeros(int(0.06 * self.sample_rate), dtype=np.float32)
        padding_end = np.zeros(int(0.12 * self.sample_rate), dtype=np.float32)
        return np.concatenate([padding_start, wav, padding_end])

    def speak(self, text: str) -> TTSResult:
        if self._interrupt_event.is_set():
            return TTSResult(success=True, interrupted=True, duration_seconds=0.0)
        try:
            audio = self._build_audio(text)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as synth_err:
            logger.exception("Chatterbox Turbo synthesis failed: %s", synth_err)
            return TTSResult(success=False, error=str(synth_err))

        if len(audio) == 0:
            return TTSResult(success=True, duration_seconds=0.0)

        if self._interrupt_event.is_set():
            return TTSResult(success=True, interrupted=True, duration_seconds=0.0)

        self._set_state(VoiceState.SPEAKING)
        self._current_audio = audio

        try:
            sd.play(audio, samplerate=self.sample_rate)
            start_time = time.time()
            sd.wait()
            interrupted = self._interrupt_event.is_set()
            duration = time.time() - start_time
            return TTSResult(success=True, interrupted=interrupted, duration_seconds=duration)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
            logger.exception("Chatterbox Turbo playback failed: %s", exc)
            return TTSResult(success=False, error=str(exc))
        finally:
            self._current_audio = None
            if self._interrupt_event.is_set():
                self._set_state(VoiceState.INTERRUPTED)
            else:
                self._set_state(VoiceState.IDLE)

    def speak_interruptible(self, text: str, wakeword_listener: Any = None,
                            playback_gain: float = 0.8, on_interrupt: Callable[[], None] | None = None) -> TTSResult:
        self._interrupt_event.clear()
        try:
            audio = self._build_audio(text)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as synth_err:
            logger.exception("Chatterbox Turbo synthesis failed: %s", synth_err)
            return TTSResult(success=False, error=str(synth_err))

        if len(audio) == 0:
            return TTSResult(success=True, duration_seconds=0.0)

        self._set_state(VoiceState.SPEAKING)
        self._current_audio = audio

        audio = (audio * playback_gain).astype(np.float32)
        duration = len(audio) / self.sample_rate

        if wakeword_listener and hasattr(wakeword_listener, 'model') and hasattr(wakeword_listener.model, 'reset'):
            wakeword_listener.model.reset()

        sd.play(audio, samplerate=self.sample_rate)
        start_time = time.time()
        interrupted = False

        try:
            with sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=1280) as stream:
                warmup_frames = 5
                frame_count = 0

                while time.time() - start_time < duration:
                    if self._interrupt_event.is_set():
                        interrupted = True
                        break

                    frame_count += 1
                    if frame_count <= warmup_frames:
                        stream.read(1280)
                        continue

                    if wakeword_listener and hasattr(wakeword_listener, 'check_frame'):
                        try:
                            if wakeword_listener.check_frame(stream, debug=False):
                                interrupted = True
                                break
                        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                            pass

                    if not interrupted:
                        time.sleep(0.01)

                if not interrupted:
                    remaining = duration - (time.time() - start_time)
                    if remaining > 0:
                        time.sleep(remaining)

        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            logger.warning("Barge-in monitoring failed, falling back to simple playback: %s", e)
            remaining = duration - (time.time() - start_time)
            if remaining > 0:
                time.sleep(remaining)

        finally:
            if interrupted:
                try:
                    sd.stop()
                except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
                    pass
            self._current_audio = None
            if interrupted:
                self._set_state(VoiceState.INTERRUPTED)
                if on_interrupt:
                    on_interrupt()
            else:
                self._set_state(VoiceState.IDLE)

        return TTSResult(success=True, interrupted=interrupted, duration_seconds=time.time() - start_time)

    def reset_interrupt(self):
        """Reset the cancellation event so subsequent speech can proceed."""
        self._interrupt_event.clear()

    def cancel(self):
        self._interrupt_event.set()
        try:
            sd.stop()
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError):
            pass
        self._current_audio = None
        self._set_state(VoiceState.INTERRUPTED)

    def get_state(self) -> VoiceState:
        if self._current_audio is not None:
            return VoiceState.SPEAKING
        return VoiceState.IDLE


class SpeechSynthesizer:
    """Master SpeechSynthesizer powered exclusively by Chatterbox Turbo."""

    def __init__(
        self,
        engine: str = "chatterbox_turbo",
        device: str = "cuda",
        audio_prompt_path: str | None = None,
        model_path: str | None = None,
        exaggeration: float = 0.5,
        **kwargs: Any,
    ):
        self.engine_name = "chatterbox_turbo"
        self.device = device
        self.audio_prompt_path = audio_prompt_path
        self.model_path = model_path
        self.exaggeration = exaggeration
        self._state_callback: Callable[[VoiceState], None] | None = None

        self._active_backend = ChatterboxTurboSynthesizer(
            device=self.device,
            audio_prompt_path=self.audio_prompt_path,
            model_path=self.model_path,
            exaggeration=self.exaggeration,
            **kwargs,
        )
        try:
            self._active_backend._ensure_model()
            timbre_info = f" (timbre: {Path(self._active_backend.audio_prompt_path).name})" if self._active_backend.audio_prompt_path else ""
            print(f"FRIDAY [Voice]: Initialized Chatterbox Turbo TTS engine on {self._active_backend.device.upper()}{timbre_info}.")
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as e:
            logger.warning("Chatterbox Turbo lazy-load deferred or warning: %s", e)

    @property
    def engine(self) -> str:
        return self.engine_name

    @property
    def sample_rate(self) -> int:
        return getattr(self._active_backend, "sample_rate", 24000)

    def _build_audio(self, text: str) -> np.ndarray:
        return self._active_backend._build_audio(text)

    def set_state_callback(self, callback: Callable[[VoiceState], None]):
        self._state_callback = callback
        if hasattr(self._active_backend, "set_state_callback"):
            self._active_backend.set_state_callback(callback)

    def speak(self, text: str) -> TTSResult:
        try:
            return self._active_backend.speak(text)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
            logger.exception("Chatterbox Turbo speak failed: %s", exc)
            return TTSResult(success=False, error=str(exc))

    def speak_interruptible(self, text: str, wakeword_listener: Any = None,
                            playback_gain: float = 0.8, on_interrupt: Callable[[], None] | None = None) -> TTSResult:
        try:
            return self._active_backend.speak_interruptible(
                text, wakeword_listener=wakeword_listener,
                playback_gain=playback_gain, on_interrupt=on_interrupt
            )
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, IndexError, ImportError) as exc:
            logger.exception("Chatterbox Turbo speak_interruptible failed: %s", exc)
            return TTSResult(success=False, error=str(exc))

    def reset_interrupt(self):
        if hasattr(self._active_backend, "reset_interrupt"):
            self._active_backend.reset_interrupt()

    def cancel(self):
        if hasattr(self._active_backend, "cancel"):
            self._active_backend.cancel()

    def get_state(self) -> VoiceState:
        return self._active_backend.get_state()


__all__ = [
    "SpeechSynthesizer",
    "ChatterboxTurboSynthesizer",
    "TTSResult",
    "clean_tts_text",
    "CHATTERBOX_TAGS",
    "PARALINGUISTIC_TAGS",
]
