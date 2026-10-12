# V1 Post-mortem and V2 Decision Gate

Date: 2026-10-12. Baseline: `main`, tree `a4bd275023026d5ceddf8a4fb2faa202d3af2494`. This is a source review, **not** a claim of executed Windows tests or native-speaker listening trials.

## 1. Inventory / current architecture

- **Windows client:** Python 3.11 / PySide6 in `desktop/nsg_desktop/app.py`, Qt Multimedia player and Matplotlib diagnostics. Main screen is a control grid (prompt, occasion, style, voice, length, seed, key, tempo), editable lyrics, syllable table, player, karaoke, and separate diagnostic/settings tabs.
- **HTTP/service:** FastAPI in `app/main.py`; optional Redis/RQ worker, local queue fallback, key/value job state, object/local storage, SSE event stream.
- **Music pipeline:** `app/pipeline/lyrics.py` (LLM and template fallback), `nepali_text.py` (phoneme/syllable heuristics), `composer.py` (seeded symbolic note composition), `tts.py` + `line_singer.py` + `singer.py` (Piper speech transformed toward singing), `backing.py`, `mixer.py`, `media.py` (audio/video packaging). Separate desktop `local_render.py` path creates drift risk.
- **Model assets:** downloadable Piper Nepali voices; OmniVoice labeled experimental and inoperable without missing decoder weights per `docs/MODEL_REPORT.md`. No weights shipped in Git.
- **Packaging:** PyInstaller onedir, Inno Setup; release workflow hardcodes v0.7.0 and runs tests, real-model smoke renders, measured metrics, packaged self-test before release.
- **Automated tests:** syllabification, composer determinism, timing/media/runtime checks. These establish deterministic code behavior, not audience-perceived song quality.

## 2. Working, incomplete, and unverified

| Area | Supported by code | Missing evidence / incomplete |
|---|---|---|
| Nepali lyrics | Template and optional cloud LLM paths; editable output | Native-speaker editorial evaluations and natural Hindi generation |
| Melody | Deterministic MIDI-note creation with range tests | Prosody-to-note alignment and memorable hook studies |
| Vocal audio | Piper/WORLD speech-to-pitch pipeline, stems | Expressive singing, breath, phrasing, pronunciation, human intelligibility at scale |
| Arrangement | Parameterized style accompaniment and mixing | Independent instrument articulation, musician-quality arrangements |
| Desktop | Windows Qt workflow, cancel/progress/player | Narrative-first creative flow, section-scoped non-destructive revisions |
| Export | MP3/WAV/MP4/lyrics/karaoke/stems in source | Fully verified reproducible cross-DAW MIDI + chord lead sheet workflow |
| CI/release | Configured Windows build and tests | Results of *current* CI run and fresh release availability are unverified here |

**Do not equate presence of a function or green unit tests with excellent songs.** In particular, the documentation itself states that Piper/WORLD output can sound synthetic; its ≥80% spoken and ≥60% sung native-listener accuracy levels are *targets*, not observed results.

## 3. Root causes

1. **Wrong creative abstraction:** A single pipeline turns a prompt into text, notes and artificially pitched TTS. It lacks an editable unified song model where every lyric syllable is linked to phrasing and note timing. Consequence: rewriting lyrics often means regenerating rather than composing.
2. **Wrong optimization target:** Technical audio metrics, deterministic note-range tests, and generic syllable logic cannot measure whether a Nepali chorus is moving, idiomatic, or singable. *Counterexample:* perfect pitch tracking with awkward words is still a bad song.
3. **Culture treated as a style dropdown:** Lok dohori, Teej, bhajan, Bollywood, ghazal, and Hindi indie require differing narrative conventions, call-and-response rules, accents, meter, melody and instruments—not only tempo presets.
4. **Voice capability overpromised by composition:** Text-to-speech is not expressive text-to-song; unsupported model dependencies and license restrictions make voice quality conditional.
5. **Deployment complexity without product leverage:** Desktop+FastAPI+optional Redis/S3/Docker duplicates orchestration for single-creator local usage; dependencies and artifacts substantially complicate reproducibility.
6. **UX mirrors implementation stages:** 'Write lyrics' then 'Sing' and diagnostics/voice controls expose the internal pipeline instead of creating a feeling-led studio session.
7. **Missing revision provenance:** No first-class immutable versions, diffable section edits, locked sections, quality annotations, or reproducible Song DNA. Existing remix endpoint only modifies coarse style settings.
8. **Hindi is not first class:** Nepali phonology and fixed style catalogs dominate domain assumptions.

## 4. Unexploited opportunities

A bilingual intent-to-song conversation; Devanagari and reversible/translucent transliteration; tradition-modernity DNA; culturally grounded imagery and seasonal/festival context; melody motifs as named reusable objects; lyric scansion preview; alternate emotional arcs and duet perspectives; section-level bounded revisions; musician-facing MIDI, MusicXML, lead sheets and stems; offline sketch mode with honest rendering status; transparent provenance and consent for all reference audio.

## 5. Keep / rewrite / discard

| Decision | Component | Reason |
|---|---|---|
| **Keep as reference only** | Existing culture/lexicon samples, QA scenarios, installation lessons | Data/behavioral constraints can inform fresh contracts; do not copy architecture |
| **Rewrite** | Song domain, generation orchestration, lyrics and melody, exports, UX, persistence | Need single typed score representation and non-destructive edits |
| **Discard from v2 critical path** | FastAPI/Redis/RQ/S3/Docker, PySide6 front-end, speech-to-pitch-as-quality-default | Excess local desktop complexity and expressive quality ceiling |
| **Optional future adapter** | Piper preview, cloud generation, DAW stems | Label previews accurately; verify licensing and listener scores before promotion |

## 6. Clean slate gate / acceptance criteria

- .NET 8 WPF for Windows 10/11 with MVVM, asynchronous cancellation, typed contracts; avoids embedding a Python server. Windows-only distribution is the primary goal. Avalonia adds portability but requires additional styling/Windows-media integration work. WinUI 3 has a larger packaging/runtime friction surface for the first shippable prototype.
- **Canonical SongDocument** describes concept, language, cultural DNA, sections, bars, notes, syllable spans, chords, arrangement, revisions and generator provenance. One schema must drive view, preview and exports.
- Provider contract separates **offline deterministic sketch** from **LLM text creativity** and **licensed, opt-in sung audio**. Never call speech conversion human-quality singing.
- Local JSON documents initially, atomic writes and immutable variant snapshots; switch to SQLite only when queries/projects demand it.
- Core creative loop: one story prompt → 3 distinct narrative takes → select and edit a section → lock/branch variants → MIDI and musician package export.
- Security: never place API tokens in projects/logs, respect consent for voice references, no unauthorized voice cloning, no copying reference melodies.
- Formal gate for a public v2 release: Windows build/test, installer smoke-test, 20 representative bilingual briefs, 2 native-language listeners per sample, pronunciation/prosody and originality review, and measured model/license/cost disclosures.

## 7. Architecture decision

This report precedes all v2 source additions. Build v2 in `v2/` without altering the v1 release workflow or its artifacts; change the default distribution only after v2 CI demonstrates the required quality. No claim of a production-ready sung vocal model is permitted at the initial foundation milestone.
