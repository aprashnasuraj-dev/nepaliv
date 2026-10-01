# 🎵 Nepali Song Generator (CPU-only, no paid APIs)

Prompt → Nepali lyrics (Devanagari) → melody → sung vocals → band → MP3, plus
syllable-level karaoke timings. Runs on a normal CPU box. Read
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the design, decisions,
CPU budget, roadmap and deployment options.

## Project layout

```
app/
  main.py              FastAPI endpoints (songs, lyrics preview, remix, SSE)
  config.py            all settings from env
  schemas.py           request/response models
  kv.py                Redis or in-memory KV (jobs, caches, rate limits)
  jobqueue.py          RQ queue or in-process thread pool
  worker.py            RQ SimpleWorker entrypoint (keeps models warm)
  storage.py           local disk or S3 / Cloudflare R2
  pipeline/
    orchestrator.py    the song job: lyrics → compose → sing → band → mix → upload
    lyrics.py          free LLM chain, validation, variant cache, offline templates
    nepali_text.py     Devanagari normalisation, syllabification, schwa deletion, rhyme
    styles.py          lok_dohori, adhunik, pop, teej, bhajan, lori
    composer.py        rule-based melody + chords + karaoke timings
    tts.py             Piper (default) / Edge / MMS Nepali TTS engines
    singer.py          WORLD speech-to-singing + syllable voicebank + harmony
    backing.py         procedural madal/harmonium/flute/bass (+ optional FluidSynth)
    mixer.py           pedalboard mix/master, ffmpeg MP3
scripts/
  download_voices.py   fetch Piper ne_NP voice
  prewarm.py           pre-build the syllable voicebank
tests/test_core.py     syllabifier, validator, composer tests (no model needed)
```

## Quick start (local, no Docker, no Redis)

Needs Python 3.11+ and `ffmpeg` on PATH.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # for local dev: set REDIS_URL= , STORAGE_BACKEND=local,
                                # DATA_DIR=./data, VOICES_DIR=./voices, PUBLIC_BASE_URL=http://localhost:8000
python scripts/download_voices.py
python scripts/prewarm.py       # optional but makes songs fast
uvicorn app.main:app --reload
pytest -q
```

With `REDIS_URL` empty, jobs run inside the API process (keep `--workers 1`).

## Docker (production-ish, one VM)

```bash
cp .env.example .env    # fill in keys
docker compose up -d --build
docker compose exec worker python scripts/prewarm.py
```

## API

```bash
# 1. optional: instant lyrics preview the user can edit
curl -s localhost:8000/v1/lyrics -H 'content-type: application/json' \
  -d '{"prompt":"बहिनीको जन्मदिन","dedicate_to":"सीता"}'

# 2. create a song (returns immediately with an id)
curl -s localhost:8000/v1/songs -H 'content-type: application/json' -d '{
  "prompt": "दसैँमा घर फर्किँदाको खुसी",
  "style": "lok_dohori",
  "length": "short",
  "dedicate_to": "आमा",
  "harmony": true
}'
# style: lok_dohori | adhunik | pop | teej | bhajan | lori ; length: short (~1 min) | full (~2 min)
# -> {"id":"9f2c...","status":"queued",...}

# 3. poll (or stream: GET /v1/songs/{id}/events as Server-Sent Events)
curl -s localhost:8000/v1/songs/9f2c...
# -> status, stage, progress, lyrics (early), karaoke (early), audio_url (when done)

# 4. same lyrics, new arrangement
curl -s localhost:8000/v1/songs/9f2c.../remix -H 'content-type: application/json' -d '{"style":"pop"}'

# sing user-edited lyrics directly
curl -s localhost:8000/v1/songs -H 'content-type: application/json' -d '{
  "style":"adhunik",
  "lyrics":{"title":"माया","sections":[
    {"type":"verse","lines":["हिमालको हिउँजस्तै सेतो तिम्रो माया","खोलाको पानीझैँ बगिरहन्छ यो मन"]},
    {"type":"chorus","lines":["माया लाग्छ तिमीलाई, साँचो माया लाग्छ"]}]}}'
```

Set `API_KEYS` in production and send `X-API-Key`. Other endpoints:
`GET /v1/styles`, `GET /v1/voices`, `GET /health`.

### Karaoke JSON (for the player)

```json
{"bpm": 126, "duration": 55.8,
 "sections": [{"name": "verse", "start": 5.71, "end": 28.57}],
 "lines": [{"id": 0, "section": "verse", "text": "दसैँ आयो घरघरमा खुसी छायो",
            "start": 5.71, "end": 9.9,
            "syllables": [{"t": "द", "r": "da", "w": 0, "start": 5.714, "end": 6.19}]}]}
```
`w` is the word index inside the line, so the app can highlight per word or per syllable.

## Voices

`python scripts/download_voices.py` fetches both from Hugging Face
(`rhasspy/piper-voices`, folder `ne/ne_NP`):

| Voice id | Who | Licence |
|---|---|---|
| `ne_NP-chitwan-medium` (default) | male, 1 speaker, 22 kHz | CC0 |
| `ne_NP-google-medium`, `-s8`, `-s11` | female, 18 speakers, 22 kHz | CC-BY-SA-4.0 |

Add more google speakers with `VoiceSpec(..., speaker_id=N)` in `app/pipeline/tts.py`.

## Tuning checklist (do this with a Nepali speaker)
- Wrong syllable splits → add the word to `LEXICON` in `nepali_text.py`.
- Voice too high/low → `center_midi` in `tts.py` `VOICES`; user-level `key_shift`.
- Mumbled syllables → raise `length_scale` (slower TTS = longer vowels).
- Too robotic → lower `vibrato_cents`, raise `reverb_wet` per style.
