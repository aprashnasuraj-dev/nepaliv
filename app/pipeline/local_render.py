"""In-process desktop renderer built from the same pipeline components as the API."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from ..config import get_settings
from .backing import render_backing
from .composer import MelodyComposer
from .lyrics import clean_user_lyrics, generate_lyrics
from .media import embed_cover_mp3, render_cover_video, validate_cover
from .mixer import export, mix
from .orchestrator import performance_order
from .singer import Singer, harmony_notes
from .styles import get_style
from .tts import get_engine, get_voice
from .user_lexicon import tts_text_for_line

Progress = Callable[[str, int, str], None]


class RenderCancelled(RuntimeError):
    pass


@dataclass
class RenderResult:
    title: str
    lyrics: dict
    karaoke: dict
    mp3: Path
    wav: Path
    vocal: Path
    harmony: Path | None
    band: Path
    karaoke_json: Path
    lrc: Path
    cover: Path | None
    video: Path | None
    seconds: float


def _notify(cb, stage, pct, message=""):
    if cb:
        cb(stage, pct, message)


def _check(cancelled):
    if cancelled and cancelled():
        raise RenderCancelled("Generation cancelled")


def lrc_from_karaoke(k):
    out = ["[ar:AI गायक]"]
    for line in k.get("lines", []):
        t = float(line.get("start", 0))
        mm = int(t // 60)
        ss = t - mm * 60
        out.append(f"[{mm:02d}:{ss:05.2f}]{line.get('text', '')}")
    return "\n".join(out) + "\n"


def render_song_local(req, out_dir, progress=None, cancelled=None, export_stems=True):
    s = get_settings()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    seed = int(req.get("seed") if req.get("seed") is not None else 83)
    req = {**req, "seed": seed}

    _check(cancelled)
    _notify(progress, "lyrics", 3, "लेख्दै")
    lyrics = clean_user_lyrics(req["lyrics"]) if req.get("lyrics") else generate_lyrics(req, seed)

    _check(cancelled)
    _notify(progress, "composing", 18, "धुन बनाउँदै")
    voice = get_voice(req.get("voice"))
    style = get_style(req.get("style", "adhunik"))
    bpm = int(round(style.bpm * float(req.get("tempo_scale", 1))))
    score = MelodyComposer(
        style,
        seed,
        center_midi=voice.center_midi + int(req.get("key_shift", 0)),
        bpm=bpm,
    ).compose(performance_order(lyrics, req.get("length", "short")))

    _check(cancelled)
    _notify(progress, "singing", 25, "गाउँदै")
    singer = Singer(voice, vibrato_cents=style.vibrato_cents, seed=seed)

    def vp(p):
        _check(cancelled)
        _notify(progress, "singing", 25 + int(38 * p), "गाउँदै")

    vocal = singer.sing(score.vocal, score.total_dur, s.sample_rate, progress=vp)
    harmony = None
    if req.get("harmony", True):
        _check(cancelled)
        _notify(progress, "harmony", 65, "हार्मोनी")
        harmony = singer.sing(
            harmony_notes(score),
            score.total_dur,
            s.sample_rate,
            progress=lambda p: _notify(progress, "harmony", 65 + int(8 * p), "हार्मोनी"),
        )

    _check(cancelled)
    _notify(progress, "band", 76, "बाजा बजाउँदै")
    band = render_backing(score)

    _check(cancelled)
    _notify(progress, "mixing", 86, "मिक्स गर्दै")
    mixed = mix(vocal, band, harmony, score.bpm, style.reverb_wet)

    stem = f"nepali-song-{time.strftime('%Y%m%d-%H%M%S')}-{seed}"
    files = export(mixed, out_dir, stem, lyrics.get("title", "गीत"), s.mp3_bitrate)
    vocal_path = out_dir / f"{stem}-vocal.wav"
    band_path = out_dir / f"{stem}-band.wav"
    harmony_path = out_dir / f"{stem}-harmony.wav" if harmony is not None else None

    if export_stems:
        sf.write(vocal_path, vocal, s.sample_rate, subtype="PCM_16")
        sf.write(band_path, band, s.sample_rate, subtype="PCM_16")
        if harmony_path is not None:
            sf.write(harmony_path, harmony, s.sample_rate, subtype="PCM_16")

    k = score.karaoke()
    notes_by_line = {}
    for note in score.vocal:
        notes_by_line.setdefault(note.line_id, []).append(note)
    for line in k.get("lines", []):
        for syl, note in zip(line.get("syllables", []), notes_by_line.get(line.get("id"), [])):
            syl["midi"] = round(float(note.midi), 3)

    kjson = out_dir / f"{stem}.karaoke.json"
    kjson.write_text(json.dumps(k, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lrc = out_dir / f"{stem}.lrc"
    lrc.write_text(lrc_from_karaoke(k), encoding="utf-8")

    cover = validate_cover(req.get("cover_path"))
    video_path = None
    if cover is not None or req.get("make_video", False):
        _check(cancelled)
        _notify(progress, "media", 94, "कभर / भिडियो बनाउँदै")
        if cover is not None:
            embed_cover_mp3(files["mp3"], cover, lyrics.get("title", "गीत"))
        if req.get("make_video", False):
            video_path = render_cover_video(files["mp3"], out_dir / f"{stem}.mp4", cover)

    _notify(progress, "done", 100, "तयार")
    return RenderResult(
        lyrics.get("title", "मेरो गीत"),
        lyrics,
        k,
        files["mp3"],
        files["wav"],
        vocal_path,
        harmony_path if export_stems else None,
        band_path,
        kjson,
        lrc,
        cover,
        video_path,
        time.perf_counter() - started,
    )


def speak_lyrics(lyrics, voice_id, out_path):
    spec = get_voice(voice_id)
    eng = get_engine(spec)
    chunks = []
    sr0 = None
    for sec in lyrics.get("sections", []):
        for line in sec.get("lines", []):
            y, sr = eng.synth(tts_text_for_line(line))
            sr0 = sr if sr0 is None else sr0
            if sr != sr0:
                from scipy.signal import resample_poly
                from math import gcd

                g = gcd(sr, sr0)
                y = resample_poly(y, sr0 // g, sr // g).astype(np.float32)
            chunks.extend([y.astype(np.float32), np.zeros(int(sr0 * .25), np.float32)])
    if not chunks:
        raise ValueError("No lyrics")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, np.concatenate(chunks), sr0, subtype="PCM_16")
    return out_path
