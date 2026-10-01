# Changelog

## Unreleased

### Phase 1 — Windows baseline
- Added external model manifest/downloader with resume and SHA-256 verification.
- Added bundled ffmpeg discovery via `imageio-ffmpeg`.
- Fixed temporary-file handling for Windows Edge-TTS decoding.
- Added Windows-safe in-process job execution when RQ/Redis is configured.
- Added offline two-voice smoke-test and benchmark scaffold.
- Added Windows + Ubuntu unit-test CI.
