# Windows clean-machine test guide

Target: Windows 10/11 x64, 4–8 CPU cores, 8–16 GB RAM. No GPU and no paid API are required.

## Install

1. Download `NepaliSongGen-Setup-x64.exe` and the `.sha256` file from the GitHub release.
2. Verify the SHA-256 if desired, then run the installer. The app installs per-user and does not require Administrator rights.
3. Launch **Nepali AI Song Generator** from Start or the optional desktop shortcut.

## First-run model setup

Open **Settings** → **Download / verify Piper models**. The app downloads the default Chitwan model plus the Google comparison model to `%LOCALAPPDATA%\NepaliSongGen\models`. Model files are not embedded in the installer.

If the model download is interrupted, press the same button again; `.part` downloads resume. Completed files are checked against size and SHA-256 when an expected digest is available.

## Make the first song

1. On **Create**, enter a prompt or keep the sample prompt.
2. Press **1 · Write lyrics**. Edit any line you dislike. The table shows sung-syllable count, romanisation and the exact halanta-marked text sent to TTS.
3. Press **2 · Sing**. Progress advances through writing → composing → singing → band → mixing.

The player starts automatically. Karaoke highlights the current sung syllable. The output folder contains MP3, WAV, vocal stem, band stem, optional harmony stem, `.lrc` and karaoke JSON.

## Intelligibility test

Open **Diagnostics**:

- **Speak lyrics** isolates the TTS from speech-to-singing conversion.
- **Play a cappella** removes the band/mix as a masking variable.
- **Prepare A/B** randomizes Chitwan vs Google labels. Listen before voting; the mapping is revealed only after the vote is saved.
- Select a diagnostic row after rendering to display the a-cappella spectrogram, note onsets and median note-pitch error for that line.
- **Mark word as wrong** writes the issue to `%LOCALAPPDATA%\NepaliSongGen\feedback.jsonl`.
- **Lexicon correction** stores word → sung-syllable overrides in `%LOCALAPPDATA%\NepaliSongGen\lexicon.json` and applies them on the next render.

## OmniVoice HD

The current Windows installer intentionally does **not** install torch or OmniVoice. The shared OmniVoice snapshot lacks the audio-tokenizer weight file claimed by its own model card, so HD voice remains Experimental. Do not use downloaded commercial recordings as cloning references; use only a short recording for which you have permission plus its exact transcript.

## Troubleshooting

Logs are written to `%LOCALAPPDATA%\NepaliSongGen\logs\nepali-song-gen.log`. If the app cannot produce a song, first test **Speak lyrics**. If speech is clear but singing is unclear, use the per-line diagnostics and pronunciation lexicon rather than changing the lyrics blindly.
