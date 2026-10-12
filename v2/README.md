# NepaliV Song Atelier — v2 foundation

An **honest early-stage Windows creative application**, separate from the Python v1 release line.

## Current capabilities (source milestone 0.1)

- .NET 8 WPF / Windows 10 and 11; designed with Devanagari-capable Nirmala UI.
- Feeling-first creative brief, Nepali/Hindi selection, tradition/modernity axis.
- Three deterministic **symbolic** song takes with intro, verses, pre-chorus, chorus, bridge, outro, chord progressions and pitch/time events.
- SongDocument JSON project export and Standard MIDI format 1 export.
- Asynchronous generation so the window is responsive.

**Not yet included:** original model-generated poetry, phoneme-aware Hindi/Nepali scansion, lyrical revision UI, an actual singing voice, audio rendering, playable arrangements, model connectors, installer, provenance database. The current lyric lines are clearly marked editorial placeholders. Do **not** promote this build as a complete AI song generator.

## Build

On Windows with .NET 8 SDK and Desktop Runtime:

```powershell
dotnet build v2/src/NepaliV.Studio/NepaliV.Studio.csproj -c Release
dotnet run --project v2/src/NepaliV.Studio/NepaliV.Studio.csproj
dotnet publish v2/src/NepaliV.Studio/NepaliV.Studio.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true
```

The app has not yet been compiled in an available Windows/.NET runner during this architecture pass. Windows CI and smoke testing are release blockers.

## Product direction

**Song DNA** is a typed, versioned score, not a prompt string. Every generation provider returns this schema; section revisions operate against immutable baselines and can lock untouched content. Offline = symbolic sketch; remote = high-quality narrative candidate; singer = separately licensed/rendered performance.

The first acceptance demonstration for genuine v2 generation will require native Nepali/Hindi listeners assessing prosody, poetry, and cultural fit; a human singing or appropriately licensed singing synthesis backend is a separate quality gate.

See `docs/V1_POSTMORTEM_V2_GATE.md` and `v2/docs/ADR-0001.md`.
