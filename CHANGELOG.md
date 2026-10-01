# Changelog

## 0.7.0 - Cover/video + full-song Windows release

- Added cover-photo selection in the Windows studio with preview and persistent settings.
- Embedded selected artwork and title into generated MP3 ID3 metadata.
- Added H.264/AAC MP4 export using the selected cover, with a safe default canvas when no cover is supplied.
- Added media-export unit tests and packaged media self-test coverage.
- Fixed native-Windows Redis/RQ behavior so stale `REDIS_URL` values fall back to the in-process queue instead of crashing.
- Extended full-song structure with a final repeated chorus.
- Retuned the default Adhunik tempo to 94 BPM using the supplied reference recordings only as non-cloning musical references.
- Added PyInstaller collection for Mutagen and kept bundled ffmpeg support for video creation.

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
