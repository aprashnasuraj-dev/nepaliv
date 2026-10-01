# Model inventory report

Inventory date: 2026-10-01. Source: the user-provided shared Google Drive folder. `models/manifest.json` is the machine-readable inventory.

| Asset | Size | What is verified from the supplied files | Release status |
|---|---:|---|---|
| `ne_NP-chitwan-medium.onnx` | 62,950,044 B | Piper Nepali, 22,050 Hz, one speaker; matching config present | **Default** |
| `ne_NP-google-medium.onnx` | 76,766,385 B | Piper Nepali, 22,050 Hz, 18 speakers; matching config present | Optional comparison voice |
| OmniVoice `model.safetensors` | 2,030,864,036 B | Top-level config identifies `OmniVoice` with Qwen3 causal-LM conditioning and 8 audio codebooks | Experimental |
| OmniVoice tokenizer | 11,423,986 B | Qwen2 tokenizer config + tokenizer JSON present | Experimental dependency |
| OmniVoice audio-tokenizer configs | ~2.7 KB configs | Config identifies `HiggsAudioV2TokenizerModel`, 24 kHz output, DAC acoustic model and HuBERT semantic model | **Weights missing from shared folder** |
| ASR metadata files | small | Metadata references an ASR dataset; no ASR model/weights are present | Not used |
| Two reference MP3s | ~13 MB total | Audio files are present, but consent/licensing for voice cloning is not established | Inventory only; never auto-used |

## OmniVoice findings

The supplied OmniVoice model card says the checkpoint was trained for 18,000 steps on 54 shards (~45 hours) of native Nepali speech. It accepts Devanagari text, uses language code `npi`, outputs 24 kHz audio, and conditions voice cloning on a 3–10 s reference clip plus matching reference text. It recommends 16 inference steps for speed and 32 for quality.

The same model card states that the standalone checkpoint requires an `audio_tokenizer` of roughly 805 MB. The shared Drive inventory contains only that tokenizer's configuration/preprocessor/license files, not its weight file. Therefore a fully offline OmniVoice inference run cannot be honestly claimed from the shared assets as they stand.

The audio-tokenizer license file is the **Boson Higgs Audio 2 Community License**, not Apache-2.0. It contains attribution obligations and additional commercial terms, including a 100,000 annual-active-user threshold for expanded licensing. For that reason the desktop app does not infer the entire OmniVoice dependency chain is Apache-2.0 merely because the top-level fine-tune model card says so.

## Runtime gate

`OmniVoice HD` is enabled only after all of these are true:

- complete local decoder/tokenizer weights are available;
- a consented user reference recording + transcript are supplied;
- measured CPU RTF is ≤3.0 on the target 4–8 core Windows machine;
- a native-speaker listening test shows intelligibility is at least as good as Piper line mode;
- the intended deployment complies with the full dependency license chain.

Until then, Piper remains the production/test path.
