# Engineering Decisions

## 2026-10-01 — External model storage on Windows
**Context:** model weights must never be committed and a packaged desktop install should not depend on the source checkout.  
**Options:** keep historical `./voices`; bundle weights; use a per-user application-data directory.  
**Choice:** Windows defaults to `%LOCALAPPDATA%\NepaliSongGen\models`; non-Windows server/dev keeps `./voices` for compatibility. `VOICES_DIR` overrides both.  
**Evidence:** this preserves the existing server path on Linux while satisfying the Windows packaging constraint.

## 2026-10-01 — Bundled ffmpeg resolver
**Context:** a fresh Windows PC cannot be assumed to have `ffmpeg.exe` on PATH.  
**Options:** require a manual ffmpeg install; ship a custom binary; use `imageio-ffmpeg`.  
**Choice:** resolve the binary with `imageio_ffmpeg.get_ffmpeg_exe()` and retain PATH only as a fallback.  
**Evidence:** both MP3 export and compressed TTS decoding now call one `ffmpeg_exe()` helper.

## 2026-10-01 — RQ on Windows
**Context:** RQ process-worker semantics are not a supported desktop execution path on Windows.  
**Options:** attempt RQ anyway; reject startup; fall back to the already-existing in-process executor.  
**Choice:** when `REDIS_URL` is set on Windows, emit one explicit runtime warning and execute songs in-process. Redis may still serve the KV layer.  
**Evidence:** avoids a desktop crash without forking the song pipeline.

## 2026-10-01 — OmniVoice licensing gate remains closed
**Context:** the fine-tuned README declares Apache-2.0, while the supplied `LICENSE` is the Boson Higgs Audio 2 Community License and imposes additional attribution/commercial terms.  
**Options:** trust README metadata; trust the included LICENSE; treat licensing as unresolved pending Phase 2 provenance review.  
**Choice:** do not expose OmniVoice as a production/HD option yet.  
**Evidence:** supplied files conflict; Phase 2 must resolve the applicable upstream and derivative-model licences before the quality gate can pass.

## 2026-10-01 — Pin Windows-critical audio packages
**Context:** Phase 1 targets CPython 3.11 x64 and must avoid accidental source builds on a clean Windows machine.  
**Options:** leave broad lower bounds; track newest releases; pin versions with known Windows wheels.  
**Choice:** pin `piper-tts==1.8.0` and `pyworld==0.3.5`; keep `pedalboard` and `onnxruntime` on wheel-backed ranges.  
**Evidence:** PyPI publishes a Windows x86-64 abi3 wheel for Piper 1.8.0 and a CPython 3.11 Windows x86-64 wheel for PyWorld 0.3.5; PyWorld 0.3.6 does not publish a CPython 3.11 Windows wheel.
