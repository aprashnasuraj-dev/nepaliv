# 🎵 Nepali Song Generator (CPU-only, no paid APIs)

Prompt → Nepali lyrics (Devanagari) → melody → sung vocals → band → MP3, plus syllable-level karaoke timings. The same core pipeline serves FastAPI and the Windows PySide6 test studio.

## Windows desktop release

**Current desktop test line: v0.6.0.** The Windows x64 release is built from this repository with PyInstaller + Inno Setup **only after** unit tests, two real Piper song renders, objective quality gates and a packaged self-test pass on `windows-latest` / Python 3.11.

The desktop studio provides:

- editable Nepali lyrics with sung-syllable count, romanisation and exact halanta-marked TTS text;
- Lok Dohori, Adhunik, Pop, Teej, Bhajan and Lori styles;
- Chitwan/Google Piper voices, key shift, tempo, seed and harmony controls;
- cancellable in-process rendering with real stage progress;
- MP3/WAV player with syllable karaoke;
- vocal/band/harmony stems, `.lrc`, and karaoke JSON export;
- plain-speech versus sung diagnostics, blinded A/B voice tests, feedback logging and pronunciation lexicon overrides;
- per-line spectrogram and pitch diagnostics;
- model download/verification into `%LOCALAPPDATA%\NepaliSongGen\models`;
- optional free LLM keys stored via Windows Credential Manager/keyring.

Model weights are deliberately not committed or bundled. Chitwan (CC0) is the default. Google Nepali is an optional CC-BY-SA comparison voice. OmniVoice remains an **Experimental adapter** until its complete decoder/tokenizer dependency is available and it passes the CPU RTF, license and native-speaker intelligibility gates.

### Run from source on Windows

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --prefer-binary -r requirements-desktop.txt
python scripts\fetch_models.py --profile voices
$env:PYTHONPATH = "$PWD;$PWD\desktop"
python -m nsg_desktop
```

### Build installer

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

## Backend/API quick start

```bash
python -m venv .venv
# activate the environment for your OS
pip install -r requirements.txt
python scripts/fetch_models.py --profile voices
uvicorn app.main:app --reload
pytest -q
```

With `REDIS_URL` empty, jobs run in-process. Native Windows intentionally rejects RQ/Redis worker mode; use the in-process queue for the desktop. Linux deployment may continue to use Redis/RQ.

## Project layout

```text
app/                         FastAPI + shared song pipeline
app/pipeline/                Nepali NLP, composer, TTS, singer, band and mix
app/pipeline/duration_transfer.py  DTW seam for TTS without native timings
desktop/nsg_desktop/         PySide6 Windows studio
models/manifest.json         Drive model inventory (weights excluded from Git)
scripts/fetch_models.py      resumable model downloader + verification
scripts/smoke_test.py        two-voice real render test
scripts/quality_report.py    measurable objective quality gates
packaging/NepaliSongGen.spec PyInstaller onedir build
installer/nsg.iss            Inno Setup installer
```

## Quality policy

Intelligibility is the primary product gate. Objective metrics prevent technical regressions, but they do **not** prove that Nepali words are understandable. The app therefore includes native-listener feedback tooling. Current targets are ≥80% word accuracy for plain speech and ≥60% for sung output. Those human scores are never filled with synthetic/ASR guesses.

See `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/MODEL_REPORT.md`, `docs/QUALITY.md` and `docs/WINDOWS_TEST_GUIDE.md`.
