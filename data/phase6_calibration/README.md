# Phase 6 Speech Director / Chatterbox Turbo Calibration Corpus

This directory contains the fixed calibration corpus, evaluation records, and manifest metadata for F.R.I.D.A.Y. v2 Phase 6 perceptual voice calibration.

## Directory Structure

```text
data/phase6_calibration/
├── README.md               # Calibration guide and directory documentation
├── prompts.yaml            # Fixed 12-category calibration sentence corpus
├── raw/                    # Generated WAV output during screening and sweeps (gitignored)
│   ├── screening/
│   ├── sweeps/
│   └── stability/
├── selected/               # Final representative audio samples
├── rejected/               # Rejected samples with acoustic artifacts
├── ratings/                # Human evaluation scoring sheets
└── manifests/              # Machine-readable JSONL generation manifests
```

## Running Voice Calibration

To generate reproducible calibration audio:

```bash
# Screening pass across all categories
python scripts/phase6_voice_calibration.py --screening

# Specific expression weight sweep
python scripts/phase6_voice_calibration.py --expression happy --sweep

# Single test generation
python scripts/phase6_voice_calibration.py --expression dramatic --text-id D01 --blend-weight 0.60
```

## Running Speech Regression

To run automated policy regression testing across all interaction scenarios:

```bash
python scripts/phase6_speech_regression.py
```
