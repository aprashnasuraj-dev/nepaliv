# Engineering decisions

This file records non-trivial choices as **context → options → choice → evidence**.

## D001 — Default production/test voice

**Context.** Native-speaker intelligibility is the gating problem. The shared assets contain two Piper Nepali voices and a much larger OmniVoice checkpoint.

**Choice.** `ne_NP-chitwan-medium` remains the default. Google Piper is an optional comparison voice. OmniVoice is Experimental. MMS is labelled testing-only/non-commercial. Edge voices remain online prototypes.

**Evidence.** Chitwan is a 22.05 kHz, single-speaker Piper voice and the supplied model card identifies the dataset as CC0. The Google voice is 22.05 kHz, 18-speaker and requires CC-BY-SA attribution. The existing line singer can obtain exact Piper duration predictions.

## D002 — Windows queue mode

Desktop mode uses the in-process thread executor. If `REDIS_URL` is set on native Windows the app fails clearly. FastAPI/RQ remains for Linux deployment.

## D003 — ffmpeg distribution

Resolve ffmpeg through `imageio_ffmpeg.get_ffmpeg_exe()` with PATH fallback. PyInstaller collects the package binary.

## D004 — OmniVoice gate

The shared Drive includes a ~2.03 GB checkpoint and configs, but the model card says the merged checkpoint depends on an ~805 MB audio tokenizer and the Drive folder contains only that tokenizer's config/license files, not its weights.

**Choice.** Ship an engine adapter but keep it **Experimental and disabled by default**. It becomes an HD voice only when complete local dependencies exist, measured CPU RTF ≤3.0, and native-speaker intelligibility improves. Reference audio must be user-supplied and consented.

**Evidence.** The incomplete Drive snapshot cannot satisfy a fully offline clean-machine test. Its audio tokenizer carries the Boson Higgs Audio 2 Community License, so the full dependency/license chain must be reviewed rather than assuming the top-level Apache-2.0 front matter covers everything.

## D005 — Duration transfer for engines without timings

Use 5 ms short-time cepstral features + monotonic DTW to transfer Piper syllable spans to a target rendition, instead of reverting to isolated-syllable TTS. `tests/test_duration_transfer.py` requires median transferred-boundary error <30 ms.

## D006 — Installer does not contain model weights

The Windows installer contains application code and runtimes only. First use downloads model files into `%LOCALAPPDATA%\NepaliSongGen\models` using the checked manifest.

## D007 — Quality hierarchy

Objective metrics are regression guards, not the success definition. Primary quality remains native-speaker word accuracy: target ≥80% for plain speech and ≥60% for singing. The desktop Diagnostics tab collects blinded A/B votes and wrong-word feedback.
