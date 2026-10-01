# Changelog

## 0.6.0 - Windows desktop test release

- Added PySide6 Windows desktop studio with Create, Player/Karaoke, Diagnostics and Settings tabs.
- Added Windows-safe ffmpeg discovery, temp-file handling and RQ guard.
- Added resumable Google Drive model downloader with size/SHA-256 verification.
- Added model inventory, smoke-test and objective quality-report scripts.
- Added generic DTW duration transfer seam for non-Piper TTS engines.
- Added optional OmniVoice adapter, intentionally gated as Experimental until its complete decoder pack and CPU/native-listener gates pass.
- Added persistent user pronunciation lexicon and word-level feedback logging.
- Added stem export, LRC/JSON karaoke export, blind A/B voice tests and per-line spectrogram/pitch diagnostics.
- Added PyInstaller + Inno Setup packaging and a GitHub Actions workflow that builds and publishes `NepaliSongGen-Setup-x64.exe` only after Windows tests, two-voice smoke rendering and objective quality gates pass.

## 0.1.0 - Baseline backend

- CPU-only FastAPI pipeline for Nepali lyrics → melody → line-level sung vocals → procedural band → MP3.
