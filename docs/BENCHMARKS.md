# Benchmarks

## Previously supplied baseline evidence

The project brief reports the following earlier measurements from a 2-vCPU Linux sandbox for the v2 line singer: ~0.5 s TTS+WORLD analysis per line, 9–13 s end-to-end for a ~1-minute song, 99–100% of measured notes within 50 cents (median ~3 cents), and ~0.4% silence inside sung lines. These are **historical supplied measurements**, not fresh Windows measurements.

## Windows release evidence

The release workflow runs on `windows-latest`, Python 3.11 x64 and records:

1. `scripts/smoke_test.py` — a short offline song with Chitwan and Google Piper voices.
2. `scripts/quality_report.py` — segmentation success, pitch accuracy, silence ratio, TTS RTF, vocal render RTF and note-energy spread.
3. Packaged `NepaliSongGen.exe --self-test`.

The workflow uploads `WINDOWS_SMOKE.log`, `QUALITY.md`, `quality.json` and `MODEL_REPORT.md` next to the installer artifact. This repository file intentionally does not fabricate numbers before that Windows run completes.
