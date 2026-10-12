# Local Singing Synthesis — Decision and Acceptance Plan (2026-10-12)

Status: **Research-backed proposal, not a deployed trained singer.** The present WAV synthesis is instrumental only. No publicly verified turnkey commercially licensed Nepali/Hindi singing voicebank was established in this review.

## Decision

Implement a modular native **Song Score → Phonemes → Expression Curves → Offline Singing Renderer → Stems/Mix** architecture. Default functioning offline guide mode remains, and the singing control is capability-gated until a compatible and legally usable model passes tests.

**Primary renderer:** OpenVPI DiffSinger acoustic and variance models, exported to ONNX with matching vocoder; run locally with ONNX Runtime using CPU or DirectML GPU where supported. The upstream OpenVPI code is Apache-2.0, but separately obtained weights, phonemizers, datasets, vocoders, and voice samples require their own license audits. A model stack is not portable merely because its code is open.

**Validation tool (not shipping dependency):** OpenUtau to render identical lyric+note sequences and compare pitch/timing/phoneme behavior. OpenUtau already supports DiffSinger and Windows DirectML; it does **not** guarantee Nepali/Hindi phonemization or the availability of suitable trained voicebanks.

**Secondary R&D:** NVIDIA Magpie multilingual local TTS supports Hindi, but is a **speech** model, not a melody-controlled singing synthesizer. Evaluate only as a phonetic guide and consented speech baseline; never pass speech-to-pitch output as a professional neural singing model. Nepali is not among the languages declared by the referenced local Magpie version.

## Concrete integration layers

1. `IPronunciationService`: Unicode NFC, language detection explicitly per word (NE/HI), numbers, abbreviations, sandhi, schwa deletion, conjuncts, vowel duration, nasalization, aspirated/retroflex contrasts; culturally relevant grapheme-to-phoneme dictionary. Preserve user-editable phoneme overrides.
2. `IAlignmentService`: map every syllable and phoneme to score notes in frames, distinguish melisma/legato and word-final consonants, enforce note / phoneme duration sum and explicit pauses.
3. `IExpressionPlanner`: derive pitch-bend, vibrato onset/rate/depth, breath markers, portamento, energy and tension contours; expose section and line-level overrides. Distinguish rule heuristics from learned behavior.
4. `ISingingVoiceProvider`: `Capabilities`, `ValidateModel`, `RenderAsync(SingingPhrase, CancellationToken)`; model provenance, phoneme inventory, allowed languages, sample rate, memory/VRAM estimates, declared commercial rights. Reject missing assets and unsupported phonemes instead of silently substituting.
5. `IMixPipeline`: deterministic arrangement timeline, input sample-rate normalization, delay compensation, peak guarding, export voice/stems/wet/dry mix. No waveforms that silently exceed song duration.

## Two-stage product workaround

**Stage A — immediately shippable without training:** export clearly labeled instrumental melody guides (existing WAV/MIDI), editable Devanagari and phoneme-score JSON, and optionally OpenUtau-compatible song parts for an independently licensed and language-compatible singer. Do not claim singing audio when no supported bank is installed.

**Stage B — genuinely autonomous singing:** procure/record consented original Nepali and Hindi singing datasets covering the full target phoneme inventory, expressive registers, sustained vowels, ornaments and meaningful lyric genres. Human transcribe and align; train or fine-tune independent language-capable DiffSinger voicebanks. Package ONNX inference, not a training runtime. Offer machine-specific CPU/GPU quality presets after benchmark.

## Evaluation protocol and numeric *proposed acceptance thresholds*, not measured performance

| Gate | Proposed threshold | Method |
|---|---|---|
| Phoneme coverage | 100% of supported inventory mapped, 0 silent substitutions | Trie/dictionary contract tests |
| Word intelligibility | >=85% native-listener transcription on held-out phrases (each language separately) | 30+ blind samples per language, >=3 native raters |
| Pitch accuracy | median absolute error <=35 cents on sustained vowels | reference aligned note score |
| Rhythmic accuracy | median onset error <=60 ms | forced alignment + manual spot checks |
| Expressive preference | >=60% blind preference over the previous TTS/pitch-shift baseline | >=30 paired items per language |
| Inference speed | render 60 s vocals in <=180 s on published minimum hardware | 3 runs/device, cold and warm |
| Safety/license | documented provenance and commercial distribution permission for every weight and training recording | release checklist |
| App reliability | crash-free 100 representative renders and 100% cancellation cleanup | Windows integration tests |

These targets must be revised based on measured samples; they are not evidence that the goal has been met.

## Important technical risks

- **Hindi ≠ Nepali phonology** even when both are Devanagari. Shared scripts do not ensure aligned pronunciation.
- Speech vocoders with heavy time/pitch modification distort consonants and formants, particularly over melismatic phrases.
- A model trained on one phoneme set will not generalize to arbitrary new Hindi/Nepali phonemes, regardless of the frontend being translated.
- Open source framework license does not grant rights to a singer's identity, recordings, or third-party datasets.
- Voicebanks for English/Japanese/Chinese cannot safely be labeled as native Nepali/Hindi singers.
- Full offline packaging may require several hundred MB to multiple GB of model data; exact totals depend on chosen verified checkpoints.

## Evidence checked

- OpenVPI DiffSinger: https://github.com/openvpi/DiffSinger
- DiffSinger ONNX export documentation: https://github.com/SleePerwtm/DiffSinger-openvpi/blob/main/docs/GettingStarted.md
- OpenUtau DiffSinger support: https://www.openutau.com/DiffSinger-support/
- OpenUtau voicebank development: https://www.openutau.com/Voicebank-development/
- NVIDIA NeMo Speech.cpp Hindi-support documentation: https://github.com/NVIDIA/NeMo-Speech.cpp/blob/main/docs/tts/configuration.md

## Release rule

No production-level Hindi or Nepali *singing* claim until trained checkpoints, their licenses, pronunciation tests, perceptual listening tests and hardware benchmarks exist. The honest alternative is a successful offline **composing** release with a clearly disabled singing feature and documentation of missing model assets.
