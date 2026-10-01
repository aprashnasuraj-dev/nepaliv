# 🎵 Nepali Song Generator (CPU-only, no paid APIs)

Prompt → Nepali lyrics (Devanagari) → melody → sung vocals → Nepali-style band → MP3/WAV/MP4, with syllable-level karaoke timings. The same core pipeline serves FastAPI and the Windows PySide6 studio.

## Windows desktop release

**Current desktop release line: v0.7.0.** The Windows x64 installer is built with PyInstaller + Inno Setup only after unit tests, two real Piper song renders, objective quality gates and a packaged self-test pass on `windows-latest` / Python 3.11.

The desktop studio provides:

- editable Nepali lyrics with sung-syllable count, romanisation and exact halanta-marked TTS text;
- Lok Dohori, Adhunik, Pop, Teej, Bhajan and Lori styles;
- Chitwan/Google Piper voices, key shift, tempo, seed and harmony controls;
- line-level speech-to-singing with melody pitch, portamento, delayed vibrato and natural line timing;
- short and full-song arrangements, with the full mode ending on a repeated final chorus;
- cancellable in-process rendering with real stage progress;
- MP3/WAV player with syllable karaoke;
- **cover photo upload/selection**, cover art embedded into MP3 metadata, and **MP4 video export** using the selected artwork;
- vocal/band/harmony stems, `.lrc`, and karaoke JSON export;
- plain-speech versus sung diagnostics, blinded A/B voice tests, feedback logging and pronunciation lexicon overrides;
- per-line spectrogram and pitch diagnostics;
- model download/verification into `%LOCALAPPDATA%\NepaliSongGen\models`;
- optional free LLM keys stored via Windows Credential Manager/keyring.

The two project reference songs in Google Drive are treated only as musical references. They are **not** used for voice cloning or redistributed. Their tempo analysis was used to move the default Adhunik recipe into the low/mid-90 BPM range, while the generated melody, vocals and arrangement remain original.

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

With `REDIS_URL` empty, jobs run in-process. On native Windows, a configured `REDIS_URL` safely falls back to the in-process queue; Linux deployment may continue to use Redis/RQ.

## Project layout

```text
app/                         FastAPI + shared song pipeline
app/pipeline/                Nepali NLP, composer, TTS, singer, band and mix
app/pipeline/media.py        MP3 cover embedding + H.264/AAC MP4 generation
app/pipeline/duration_transfer.py  DTW seam for TTS without native timings
desktop/nsg_desktop/         PySide6 Windows studio
desktop/nsg_desktop/media_ui.py   cover/video UI extension
models/manifest.json         Drive model inventory (weights excluded from Git)
scripts/fetch_models.py      resumable model downloader + verification
scripts/smoke_test.py        two-voice real render test
scripts/quality_report.py    measurable objective quality gates
packaging/NepaliSongGen.spec PyInstaller onedir build
installer/nsg.iss            Inno Setup installer
```

## Quality policy

The system produces an actual pitched song, not spoken text laid over music. The present CPU path is still a WORLD/Piper speech-to-singing system, so it can sound more synthetic than a studio-recorded human singer. Intelligibility is the primary product gate. Objective metrics prevent technical regressions, but they do **not** prove that Nepali words are understandable. The app therefore includes native-listener feedback tooling. Current targets are ≥80% word accuracy for plain speech and ≥60% for sung output. Those human scores are never filled with synthetic/ASR guesses.

See `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/MODEL_REPORT.md`, `docs/QUALITY.md` and `docs/WINDOWS_TEST_GUIDE.md`.
