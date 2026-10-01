"""Mixing & mastering with Spotify's `pedalboard` (C++ DSP, CPU-cheap) and
ffmpeg for MP3. A good mix hides a lot of synthesis artefacts: reverb and a
slap delay glue the WORLD voice into the band, ducking keeps words clear."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from pedalboard import Compressor, Delay, Gain, HighpassFilter, HighShelfFilter, Limiter, Pedalboard, PeakFilter, Reverb

from ..runtime import ffmpeg_exe

SR = 44100


def _stereo(mono: np.ndarray, width: float = 0.0, delay_ms: float = 0.0) -> np.ndarray:
    if delay_ms <= 0:
        return np.stack([mono, mono], axis=1)
    d = int(SR * delay_ms / 1000)
    shifted = np.concatenate([np.zeros(d, dtype=mono.dtype), mono[:-d]]) if d else mono
    return np.stack([mono * (1 - width) + shifted * width, shifted * (1 - width) + mono * width], axis=1)


def _fit(x: np.ndarray, n: int) -> np.ndarray:
    if len(x) >= n:
        return x[:n]
    pad = ((0, n - len(x)),) + ((0, 0),) * (x.ndim - 1)
    return np.pad(x, pad)


def mix(vocal: np.ndarray, backing: np.ndarray, harmony: np.ndarray | None,
        bpm: int, reverb_wet: float = 0.22) -> np.ndarray:
    n = max(len(vocal), len(backing))
    vocal, backing = _fit(vocal, n), _fit(backing, n)
    eighth_s = 60.0 / bpm / 2

    vocal_chain = Pedalboard([
        HighpassFilter(110),
        PeakFilter(3000, 2.5, 1.0),             # presence: Devanagari consonants intelligible
        HighShelfFilter(9000, -3.0),            # tame WORLD's buzzy top end
        Compressor(threshold_db=-20, ratio=3.5, attack_ms=5, release_ms=120),
        Delay(delay_seconds=eighth_s, feedback=0.18, mix=0.10),
        Reverb(room_size=0.55, damping=0.5, wet_level=reverb_wet, dry_level=0.85, width=0.9),
        Gain(2.0),
    ])
    v = vocal_chain(_stereo(vocal).T.astype(np.float32), SR).T          # lead stays centred: phone speakers are mono

    if harmony is not None and np.any(harmony):
        harmony = _fit(harmony, n)
        h_chain = Pedalboard([HighpassFilter(180), Compressor(threshold_db=-22, ratio=4),
                              Reverb(room_size=0.7, wet_level=reverb_wet + 0.1, dry_level=0.6), Gain(-8.0)])
        v = v + h_chain(_stereo(harmony, 0.6, 22).T.astype(np.float32), SR).T

    # duck the band ~3 dB under the voice (smoothed envelope "sidechain")
    env = np.abs(vocal)
    k = int(SR * 0.08)
    env = np.convolve(env, np.ones(k) / k, mode="same")
    duck = 1.0 - 0.3 * np.clip(env / (env.max() + 1e-9) * 3, 0, 1)
    band_chain = Pedalboard([HighpassFilter(35), Compressor(threshold_db=-18, ratio=2.0), Gain(-2.0)])
    b = band_chain(backing.T.astype(np.float32), SR).T * duck[:, None]

    master = Pedalboard([Compressor(threshold_db=-14, ratio=2.0, attack_ms=10, release_ms=200),
                         Gain(3.0), Limiter(threshold_db=-1.0, release_ms=150)])
    out = master((v + b).T.astype(np.float32), SR).T
    peak = float(np.abs(out).max())
    if peak > 0.95:                                   # limiter has no look-ahead; final safety
        out *= 0.95 / peak
    # fade out last 1.5 s
    f = min(len(out), int(1.5 * SR))
    out[-f:] *= np.linspace(1, 0, f)[:, None]
    return out.astype(np.float32)


def export(audio: np.ndarray, out_dir: Path, name: str, title: str, bitrate: str = "160k") -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / f"{name}.wav"
    mp3 = out_dir / f"{name}.mp3"
    sf.write(wav, audio, SR, subtype="PCM_16")
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", bitrate,
                    "-metadata", f"title={title}", "-metadata", "artist=AI गायक", str(mp3)],
                   check=True)
    return {"wav": wav, "mp3": mp3}
