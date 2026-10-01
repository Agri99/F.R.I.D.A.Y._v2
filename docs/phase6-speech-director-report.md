# F.R.I.D.A.Y. v2 — Phase 6 Speech Director / Chatterbox Turbo Calibration Report

## 1. Environment

- **Repository**: `Agri99/F.R.I.D.A.Y._v2`
- **Git Commit Baseline**: `b6fc332a5a5c29c98823fdf24f87297313d307e5`
- **Date**: 2026-09-29
- **Python**: 3.14.0
- **PyTorch**: 2.14.0+cu126
- **CUDA**: 12.6
- **GPU**: NVIDIA GeForce RTX 4060 Laptop GPU
- **Chatterbox Model**: Chatterbox Turbo TTS (`models/chatterbox-turbo`, 24 kHz)
- **Active Profile**: `config/default.yaml`

---

## 2. Perceptual Calibration Table

Based on human listening evaluation across the 12-category fixed calibration corpus (`data/phase6_calibration/prompts.yaml`), each expression was scored across five dimensions (1 to 5 scale: 1=unacceptable, 2=poor, 3=usable but weak, 4=good, 5=production-quality):

| Expression | Status | Condition Profile | Blend Weight | Naturalness | Emotion Clarity | Voice Identity | Artifact Score | Context Fit | Qualitative Notes |
|---|---|---|---|---|---|---|---|---|---|
| `neutral` | **Production** | `master`/`neutral` | 1.00 (base) | 5 | 5 | 5 | 5 | 5 | Clean, natural Lune voice identity; perfect factual baseline. |
| `happy` | **Production** | `happy` | 0.65 | 5 | 4 | 5 | 5 | 5 | Sounds cheerful and upbeat; maintains consistent speaker identity without overacting. |
| `dramatic` | **Production** | `dramatic` | 0.60 | 4 | 4 | 4 | 4 | 4 | Measured pacing and gravity; natural transitions for solution and turning-point statements. |
| `whispering` | **Production** | `whispering` | 0.70 | 4 | 4 | 5 | 5 | 4 | Intimate, low-volume cadence; smooth consonant onset without hiss artifacts. |
| `laugh` | **Limited** | `chuckle` | 0.50 | 4 | 4 | 4 | 4 | 4 | Works well in explicitly humorous contexts; blocked in failure/error/blocked states to avoid mocking tone. |
| `chuckle` | **Disabled** | `neutral` | 0.65 (pending) | 3 | 2 | 4 | 4 | 3 | Sounds slightly weak and unconvincing; disabled until recalibration passes. |
| `sigh` | **Disabled** | `neutral` | 0.65 (pending) | 3 | 3 | 3 | 3 | 2 | Resembles a sigh mechanically, but produces awkward conversational phrasing. Empathy delivers soft neutral speech instead. |
| `gasp` | **Disabled** | `neutral` | 0.65 (pending) | 2 | 2 | 4 | 4 | 2 | Almost unnoticeable, very weak acoustic delta. Surprise delivers measured prosody instead. |
| `sarcastic` | **Disabled** | `neutral` | 0.65 (pending) | 2 | 2 | 4 | 4 | 2 | Almost imperceptible difference from neutral; doesn't sound sarcastic. |
| `angry` | **Disabled** | `neutral` | 0.65 (pending) | 3 | 2 | 3 | 3 | 2 | Modifies timbre but doesn't convey anger convincingly. Serious blocks use firm restrained neutral delivery. |
| `crying` | **Disabled** | `neutral` | 0.65 (pending) | 2 | 2 | 3 | 3 | 2 | Modifies voice but doesn't convey genuine crying. Strictly routes to neutral fallback; NEVER routes to sigh. |
| `fear` | **Disabled** | `neutral` | 0.65 (pending) | 2 | 2 | 3 | 3 | 2 | Altered timbre without convincing fear emotion. |
| `surprised` | **Disabled** | `neutral` | 0.65 (pending) | 3 | 3 | 4 | 4 | 3 | Noticeable pitch movement, but not convincingly surprised. |

---

## 3. Production Expression Policy

Configured canonically in `config/default.yaml` and enforced deterministically by `SpeechDirector`:

```yaml
voice:
  speech_director:
    enabled: true
    mode: "rules"
    max_tags_per_sentence: 1
    allow_vocal_effects: true
    allow_experimental_emotion_tags: true
    production_tags:
      - happy
      - dramatic
      - whispering
    limited_tags:
      - laugh
    disabled_tags:
      - chuckle
      - sigh
      - gasp
      - sarcastic
      - angry
      - crying
      - fear
      - surprised
    expression_blend_weights:
      happy: 0.65
      dramatic: 0.60
      whispering: 0.70
      laugh: 0.50
    log_decisions: true
```

### Policy Rules:
1. **Disabled expressions are never emitted**: Tags in `disabled_tags` are strictly filtered out from `_allowed_tags`.
2. **Upstream bypass blocked**: If an upstream model (Gemini / Qwen) generates `[crying]`, `[sigh]`, or `[angry]` in-band, the Speech Director strips the tag so disabled expressions cannot bypass production policy.
3. **Limited tags constrained**: `[laugh]` is allowed exclusively in humorous contexts and strictly blocked during `FAILED`, `ERROR`, or `BLOCKED` states.
4. **Canonical neutral fallback**: Any disabled or unmapped tag falls back to `neutral`/`master` acoustics. No silent cross-emotion substitutions (`crying -> sigh`, `serious -> angry`, or `empathy -> sigh` are completely eliminated).
5. **Calibrated continuous blend weights**: Blending uses per-expression weights rather than a single hardcoded default.

---

## 4. Speech Director Rule Mapping

| Scenario | Rule Context / Keywords | Decision Emotion | Delivery | Injected Tag | Resolved Condition | Calibrated Weight |
|---|---|---|---|---|---|---|
| **Ordinary factual** | Default / general queries | `neutral` | `conversational` | `()` | `neutral` | 0.65 |
| **Greeting** | "good morning", "online and ready", etc. | `warm` | `cheerful` | `[happy]` | `happy` | 0.65 |
| **Agreement** | "sure thing", "certainly", "right away" | `positive` | `upbeat` | `[happy]` | `happy` | 0.65 |
| **Success** | `COMPLETED` / "done", "finished", "all set" | `satisfied` | `confident` | `[happy]` | `happy` | 0.65 |
| **Dramatic** | "And now, we have a solution." | `dramatic` | `measured` | `[dramatic]` | `dramatic` | 0.60 |
| **Whispering** | "Keep this between us, Boss." | `thoughtful` | `intimate` | `[whispering]` | `whispering` | 0.70 |
| **Humorous / Playful** | "haha", "funny", "amusing", "joke" | `amused` | `playful` | `[laugh]` | `chuckle` | 0.50 |
| **Empathy / Apology** | `FAILED` / "sorry", "unfortunately", "pardon" | `empathetic` | `soft` | `()` | `neutral` | 0.65 |
| **Serious / Blocked** | `ERROR`, `BLOCKED` / "critical", "denied", "error" | `serious` | `restrained` | `()` | `neutral` | 0.65 |
| **Confirmation** | `awaiting_confirmation` / "are you sure", "confirm" | `calm` | `clear` | `()` | `neutral` | 0.65 |
| **Surprise** | "wow", "amazing", "unexpected", "surprise" | `surprised` | `measured` | `()` | `neutral` | 0.65 |
| **Thinking** | "let's see", "let me check", "hmm" | `thoughtful` | `measured` | `()` | `neutral` | 0.65 |
| **Farewell** | "goodbye", "shutting down", "bye" | `calm` | `warm` | `()` | `neutral` | 0.65 |

---

## 5. Regression Status & Verification

All automated test suites and regression scripts pass:

1. **Speech Director Regression Suite (`scripts/phase6_speech_regression.py`)**:
   - 12 conversational scenarios verified
   - 3 safety & invariance checks verified (laugh blocked in error, idempotence, semantic preservation)
   - **Result**: 15 passed, 0 failed.

2. **Speech Director Unit Tests (`tests/interaction/test_speech_director.py`)**:
   - 14 tests covering policy enforcement, disabled tag blocking, upstream tag stripping, per-expression blend weights, idempotence, and prosody formatting.
   - **Result**: 14 passed in 1.79s.

3. **Chatterbox Turbo TTS Tests (`tests/unit/test_chatterbox_tts.py`)**:
   - 12 tests covering weight clamping (0.0 to 1.0), condition restoration on success and failure, crying-never-resolves-to-sigh, float32 audio, cancel/interrupt, and sounddevice integration.
   - **Result**: 12 passed in 29.04s.

4. **Streaming TTS Tests (`tests/interaction/test_streaming_tts.py`)**:
   - 8 tests covering sentence streaming, cancellation, generation ID invalidation, and playback queue drain.
   - **Result**: 8 passed in 1.72s.

5. **Full Interaction Test Suite (`tests/interaction/`)**:
   - 154 tests across audio input, condition bank, conversation, echo suppression, event-driven voice pipeline, barge-in, turn detector, and voice E2E matrix.
   - **Result**: 154 passed in 42.49s.

6. **Linter Integrity (`ruff check src/ tests/ scripts/`)**:
   - **Result**: All checks passed with 0 errors.

---

## 6. Known Limitations

1. **Experimental Emotion Expressiveness**:
   The current Chatterbox Turbo voice model relies on latent flow matching for non-event emotion profiles (`angry`, `crying`, `fear`). Without separate phoneme acoustic models, these expressions alter vocal timbre without conveying legible emotional intent. They appropriately remain in `disabled_tags` until future voice training runs produce higher-clarity latent clusters.
2. **Event Tags Discretion**:
   Vocal sound effects (`[laugh]`) are effective but can sound repetitive if triggered on consecutive turns. The Speech Director's `min_sentences_between_effects` cooldown protects against overuse in continuous conversation.
