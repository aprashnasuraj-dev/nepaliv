"""End-to-end song job: lyrics -> melody -> singing -> band -> mix -> upload.
Runs inside the RQ worker (or the in-process thread pool). Every stage
writes progress to the job record so the app can show a live progress bar
and reveal the lyrics/karaoke *before* the audio is ready."""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import time
import traceback
from pathlib import Path

from ..config import get_settings
from ..kv import job_update, kv
from ..storage import storage
from .backing import render_backing
from .composer import MelodyComposer
from .lyrics import clean_user_lyrics, generate_lyrics
from .mixer import export, mix
from .singer import Singer, harmony_notes
from .styles import get_style
from .tts import get_voice

log = logging.getLogger(__name__)
RESULT_TTL = 30 * 24 * 3600


def render_fingerprint(lyrics: dict, req: dict, voice_id: str) -> str:
    sig = json.dumps({"l": [s["lines"] for s in lyrics["sections"]], "t": [s["type"] for s in lyrics["sections"]],
                      "style": req.get("style"), "voice": voice_id, "seed": req.get("seed"),
                      "h": req.get("harmony", True), "k": req.get("key_shift", 0),
                      "tempo": req.get("tempo_scale", 1.0), "v": 4}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(sig.encode()).hexdigest()[:24]


def performance_order(lyrics: dict, length: str) -> list[dict]:
    """Turn written sections into the sung order.

    Short = first verse + chorus. Full = every verse + chorus, followed by a
    final chorus repeat. The extra refrain makes the desktop full-song mode
    behave like an actual finished song rather than a one-pass demo.
    """
    verses = [s for s in lyrics["sections"] if s["type"] == "verse"]
    chorus = next((s for s in lyrics["sections"] if s["type"] == "chorus"), None)
    order: list[dict] = []
    for v in verses or [lyrics["sections"][0]]:
        order.append(v)
        if chorus:
            order.append(chorus)
        if length != "full":
            break
    if length == "full" and chorus and order:
        order.append(chorus)
    return order


def run_song_job(job_id: str, req: dict) -> dict:
    s = get_settings()
    t0 = time.time()
    try:
        def stage(name: str, pct: float, **extra):
            job_update(job_id, status="running", stage=name, progress=int(pct), **extra)

        stage("lyrics", 3)
        lyrics = clean_user_lyrics(req["lyrics"]) if req.get("lyrics") else generate_lyrics(req, req["seed"])
        stage("composing", 20, lyrics=lyrics, title=lyrics.get("title"))

        voice = get_voice(req.get("voice"))
        fp = render_fingerprint(lyrics, req, voice.id)
        cached = kv().get(f"render:{fp}")
        if cached:
            return job_update(job_id, status="done", stage="cached", progress=100, lyrics=lyrics, **cached)

        style = get_style(req.get("style", "adhunik"))
        bpm = int(round(style.bpm * float(req.get("tempo_scale", 1.0))))
        composer = MelodyComposer(style, req["seed"], center_midi=voice.center_midi + int(req.get("key_shift", 0)), bpm=bpm)
        score = composer.compose(performance_order(lyrics, req.get("length", "short")))
        stage("singing", 25, karaoke=score.karaoke())

        singer = Singer(voice, vibrato_cents=style.vibrato_cents, seed=req["seed"])
        vocal = singer.sing(score.vocal, score.total_dur, s.sample_rate,
                            progress=lambda p: stage("singing", 25 + 40 * p))
        harmony = None
        if req.get("harmony", True):
            harmony = singer.sing(harmony_notes(score), score.total_dur, s.sample_rate,
                                  progress=lambda p: stage("harmony", 65 + 10 * p))

        stage("band", 76)
        backing = render_backing(score)

        stage("mixing", 85)
        audio = mix(vocal, backing, harmony, score.bpm, style.reverb_wet)
        tmp = Path(tempfile.mkdtemp(prefix="song_"))
        try:
            files = export(audio, tmp, fp, lyrics.get("title", "गीत"), s.mp3_bitrate)
            stage("uploading", 95)
            st = storage()
            mp3_url = st.put(files["mp3"], f"songs/{fp}.mp3", "audio/mpeg")
            wav_url = st.put(files["wav"], f"songs/{fp}.wav", "audio/wav") if req.get("keep_wav") else None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        result = {"audio_url": mp3_url, "wav_url": wav_url, "duration": round(score.total_dur, 2),
                  "karaoke": score.karaoke(), "title": lyrics.get("title"), "render_id": fp}
        kv().set(f"render:{fp}", result, RESULT_TTL)
        if req.get("request_key"):
            kv().set(req["request_key"], {"job_id": job_id}, RESULT_TTL)
        log.info("song %s done in %.1fs (%s, %s)", job_id, time.time() - t0, style.id, voice.id)
        return job_update(job_id, status="done", stage="done", progress=100,
                          render_seconds=round(time.time() - t0, 1), **result)
    except Exception as e:
        log.error("job %s failed: %s\n%s", job_id, e, traceback.format_exc())
        return job_update(job_id, status="failed", stage="failed", error=str(e)[:500])
