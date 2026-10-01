"""The band: procedural, CPU-cheap instrument synthesis in numpy/scipy.

Why procedural instead of an AI music model or a sample library?
  * zero licensing questions, zero downloads, deterministic
  * madal / harmonium / bansuri do not exist in General MIDI anyway
  * everything is rendered per *bar* and memoised by (style, chord, bpm, kind);
    a full song's band costs ~0.2-0.3 s of CPU.

Optional upgrade: set SOUNDFONT_PATH to a .sf2 and install `fluidsynth`;
harmony instruments are then rendered by FluidSynth (better realism),
while percussion stays procedural. Drop your own one-shot WAVs into
assets/samples/<hit>.wav (dha.wav, ta.wav, kick.wav ...) to override any drum.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import threading
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.signal import butter, lfilter, sawtooth, sosfilt

from ..config import get_settings
from .composer import Note, Score
from .styles import Style

SR = 44100


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def env_adsr(n: int, a=0.01, d=0.1, s=0.7, r=0.1, sr=SR) -> np.ndarray:
    a_n, d_n, r_n = int(a * sr), int(d * sr), int(r * sr)
    s_n = max(0, n - a_n - d_n - r_n)
    e = np.concatenate([np.linspace(0, 1, a_n, endpoint=False), np.linspace(1, s, d_n, endpoint=False),
                        np.full(s_n, s), np.linspace(s, 0, r_n)])
    return np.pad(e, (0, max(0, n - len(e))))[:n]


def lowpass(x: np.ndarray, fc: float, order=2) -> np.ndarray:
    return sosfilt(butter(order, fc, "low", fs=SR, output="sos"), x)


def bandpass(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return sosfilt(butter(2, [lo, hi], "band", fs=SR, output="sos"), x)


# ---- instruments -------------------------------------------------------------
def harmonium(midis: list[int], dur: float, vel=0.5) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for m in midis:
        f = hz(m)
        for det in (-0.12, 0.12):                       # two reeds, slightly detuned (beating)
            out += sawtooth(2 * np.pi * f * (1 + det / 100) * t) + 0.4 * sawtooth(2 * np.pi * 2 * f * t, 0.5)
    out = lowpass(out, 2200) * (1 + 0.06 * np.sin(2 * np.pi * 4.5 * t))   # bellows wobble
    return (out * env_adsr(n, 0.05, 0.1, 0.85, 0.12) * vel / (len(midis) * 3)).astype(np.float32)


def pad(midis: list[int], dur: float, vel=0.4) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = sum(np.sin(2 * np.pi * hz(m) * t) + 0.3 * np.sin(2 * np.pi * hz(m) * 2.003 * t) for m in midis)
    return (lowpass(out, 1800) * env_adsr(n, 0.25, 0.2, 0.8, 0.3) * vel / len(midis)).astype(np.float32)


def pluck(midi: float, dur: float, vel=0.5, bright=0.5) -> np.ndarray:
    """Karplus-Strong string via an IIR comb (lfilter keeps it in C, so it's fast)."""
    n = int(dur * SR)
    period = SR / hz(midi)
    N = int(period)
    burst = lowpass(np.random.default_rng(int(midi * 10)).uniform(-1, 1, N), 1500 + 5000 * bright)
    x = np.zeros(n)
    x[:N] = burst
    decay = 0.996
    a = np.zeros(N + 2)
    a[0], a[N], a[N + 1] = 1.0, -decay / 2, -decay / 2
    y = lfilter([1.0], a, x)
    return (y * vel * 0.6 * env_adsr(n, 0.001, 0.05, 1.0, 0.05)).astype(np.float32)


def bass(midi: float, dur: float, vel=0.6) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * hz(midi) * t) + 0.25 * np.sin(2 * np.pi * hz(midi) * 2 * t)
    return (y * env_adsr(n, 0.005, 0.15, 0.6, 0.08) * vel * 0.5).astype(np.float32)


def flute(midi: float, dur: float, vel=0.45) -> np.ndarray:
    """Bansuri-ish: sine + soft 2nd/3rd harmonic + breath noise + delayed vibrato."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    vib = 1 + 0.006 * np.clip((t - 0.2) / 0.3, 0, 1) * np.sin(2 * np.pi * 5.2 * t)
    ph = 2 * np.pi * np.cumsum(hz(midi) * vib) / SR
    tone = np.sin(ph) + 0.18 * np.sin(2 * ph) + 0.06 * np.sin(3 * ph)
    breath = bandpass(np.random.default_rng(int(midi)).normal(0, 1, n), 1500, 6000) * 0.08
    return ((tone + breath) * env_adsr(n, 0.06, 0.1, 0.85, 0.1) * vel * 0.5).astype(np.float32)


# ---- percussion one-shots (procedural; overridable with assets/samples/*.wav) --------
def _drum(pitch_hi, pitch_lo, decay, tone_mix, noise_mix, ring=None, length=0.45) -> np.ndarray:
    n = int(length * SR)
    t = np.arange(n) / SR
    f = pitch_lo + (pitch_hi - pitch_lo) * np.exp(-t * 30)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / decay)
    noise = np.random.default_rng(int(pitch_hi)).normal(0, 1, n) * np.exp(-t / 0.015)
    y = tone_mix * body + noise_mix * noise
    if ring:  # treble head ring (madal right side)
        y += 0.5 * np.sin(2 * np.pi * ring * t) * np.exp(-t / 0.12)
    return (y / (np.abs(y).max() + 1e-9)).astype(np.float32)


@lru_cache(maxsize=None)
def one_shot(hit: str) -> np.ndarray:
    custom = get_settings().assets_dir / "samples" / f"{hit}.wav"
    if custom.exists():
        import soundfile as sf
        x, sr = sf.read(custom, dtype="float32", always_2d=True)
        x = x.mean(axis=1)
        if sr != SR:
            from scipy.signal import resample_poly
            x = resample_poly(x, SR, sr).astype(np.float32)
        return x
    if hit == "dha":
        return _drum(140, 70, 0.22, 1.0, 0.15, ring=330)
    if hit == "ghe":
        return _drum(120, 60, 0.25, 1.0, 0.1)
    if hit in ("ta", "na"):
        return _drum(420 if hit == "ta" else 520, 380, 0.05, 0.3, 0.2, ring=400 if hit == "ta" else 500, length=0.3)
    if hit == "tin":
        return _drum(700, 600, 0.02, 0.2, 0.4, length=0.12)
    if hit == "kick":
        return _drum(150, 45, 0.18, 1.0, 0.1)
    if hit == "snare":
        n = int(0.25 * SR)
        t = np.arange(n) / SR
        y = 0.5 * np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05) + \
            bandpass(np.random.default_rng(2).normal(0, 1, n), 1500, 8000) * np.exp(-t / 0.07)
        return (y / np.abs(y).max()).astype(np.float32)
    if hit == "hat":
        n = int(0.08 * SR)
        y = bandpass(np.random.default_rng(3).normal(0, 1, n), 6000, 15000) * np.exp(-np.arange(n) / SR / 0.02)
        return (y / np.abs(y).max()).astype(np.float32)
    if hit == "jhyali":
        n = int(0.5 * SR)
        t = np.arange(n) / SR
        metal = sum(np.sin(2 * np.pi * f * t) for f in (3150, 4270, 5340, 6890))
        y = (bandpass(np.random.default_rng(4).normal(0, 1, n), 4000, 12000) + 0.3 * metal) * np.exp(-t / 0.18)
        return (y / np.abs(y).max()).astype(np.float32)
    return np.zeros(10, dtype=np.float32)


def _add(buf: np.ndarray, x: np.ndarray, start: int, pan: float = 0.0, gain: float = 1.0):
    """Mix mono x into stereo buf at sample `start` with constant-power pan (-1..1)."""
    if start >= buf.shape[0] or len(x) == 0:
        return
    e = min(buf.shape[0], start + len(x))
    seg = x[: e - start] * gain
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[start:e, 0] += seg * l
    buf[start:e, 1] += seg * r


# ---- bar renderer with cache ---------------------------------------------------
class BarCache:
    """In-memory LRU of rendered bars. (Measured: a whole song's band renders
    in ~0.2-0.3 s cold on one core, so a disk cache isn't worth the GBs.)"""

    def __init__(self, max_items: int = 600):
        self._mem: OrderedDict[str, np.ndarray] = OrderedDict()
        self._max = max_items
        self._lock = threading.Lock()

    def get_or_render(self, key: str, fn) -> np.ndarray:
        with self._lock:
            if key in self._mem:
                self._mem.move_to_end(key)
                return self._mem[key]
        arr = fn()
        with self._lock:
            self._mem[key] = arr
            if len(self._mem) > self._max:
                self._mem.popitem(last=False)
        return arr


_BAR_CACHE = BarCache()


def bar_cache() -> BarCache:
    return _BAR_CACHE


def render_bar(style: Style, chord: list[int], bpm: int, kind: str) -> np.ndarray:
    """One bar (+1 bar of release tail) of harmony + bass + percussion. Stereo float32."""
    step_s = 60.0 / bpm / 4
    spb = style.steps_per_bar
    bar_n = int(spb * step_s * SR)
    buf = np.zeros((bar_n * 2, 2), dtype=np.float32)
    bar_s = spb * step_s
    soft = kind in ("intro", "outro")
    root = chord[0]
    use_fs = bool(get_settings().soundfont_path) and shutil.which("fluidsynth")
    if not use_fs:
        if "harmonium" in style.instruments:
            _add(buf, harmonium(chord, bar_s * 0.98, 0.45 if soft else 0.55), 0, -0.25)
        if "pad" in style.instruments:
            _add(buf, pad([m + 12 for m in chord], bar_s * 1.05, 0.35), 0, 0.2)
        if "pluck" in style.instruments:
            pattern = [0, 4, 6, 8, 12, 14] if spb == 16 else [0, 3, 6, 9]
            arp = [chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[1] + 12, chord[0] + 24, chord[2] + 12]
            for i, st in enumerate(pattern):
                _add(buf, pluck(arp[i % len(arp)], step_s * 6, 0.45), int(st * step_s * SR), 0.35)
        if "bass" in style.instruments:
            bass_steps = (0, 8) if spb == 16 else (0, 6)
            for j, st in enumerate(bass_steps):
                note = root - 12 if j == 0 else root - 12 + (7 if spb == 12 else 0)
                _add(buf, bass(note, step_s * (spb // len(bass_steps)) * 0.95, 0.7), int(st * step_s * SR), 0.0)
    if not (kind == "intro" and style.id in ("lori",)):
        for st, hit, vel in style.percussion:
            if soft and hit not in ("dha", "ghe", "kick"):
                continue
            pan = {"ta": 0.3, "na": 0.3, "tin": 0.35, "jhyali": -0.4, "hat": 0.25}.get(hit, 0.0)
            _add(buf, one_shot(hit), int(st * step_s * SR), pan, vel * (0.5 if soft else 0.75))
    return buf


def render_backing(score: Score, progress=None) -> np.ndarray:
    st = score.style
    total_n = int(score.total_dur * SR) + SR
    out = np.zeros((total_n, 2), dtype=np.float32)
    cache = bar_cache()
    for i, ch in enumerate(score.chords):
        kind = ch.section if ch.section in ("intro", "outro") else "main"
        key = hashlib.sha1(f"{st.id}|{tuple(ch.midis)}|{score.bpm}|{kind}|v1".encode()).hexdigest()[:20]
        bar = cache.get_or_render(key, lambda: render_bar(st, ch.midis, score.bpm, kind))
        s = int(ch.start * SR)
        e = min(total_n, s + len(bar))
        out[s:e] += bar[: e - s]
        if progress and i % 4 == 0:
            progress(i / len(score.chords) * 0.7)
    for n in score.flute:                                   # melodic lines are unique per song
        _add(out, flute(n.midi, n.dur), int(n.start * SR), -0.15, 0.9)
    if get_settings().soundfont_path and shutil.which("fluidsynth"):
        fs = render_fluidsynth(score)
        if fs is not None:
            m = min(len(fs), len(out))
            out[:m] += fs[:m]
    return out[: int(score.total_dur * SR)]


# ---- optional FluidSynth path ----------------------------------------------------
GM = {"harmonium": 20, "pad": 89, "pluck": 25, "bass": 33, "sitar": 104}


def render_fluidsynth(score: Score) -> np.ndarray | None:
    import mido
    import soundfile as sf
    sf2 = get_settings().soundfont_path
    if not Path(sf2).exists():
        return None
    mid = mido.MidiFile(ticks_per_beat=480)
    tempo = mido.bpm2tempo(score.bpm)
    sec2tick = lambda s: int(round(s / (60 / score.bpm) * 480))
    for ch_i, inst in enumerate(i for i in score.style.instruments if i in GM):
        tr = mido.MidiTrack()
        mid.tracks.append(tr)
        tr.append(mido.MetaMessage("set_tempo", tempo=tempo))
        tr.append(mido.Message("program_change", channel=ch_i, program=GM[inst]))
        events = []
        for c in score.chords:
            notes = [c.midis[0] - 12] if inst == "bass" else c.midis
            for m in notes:
                events.append((sec2tick(c.start), "on", m))
                events.append((sec2tick(c.start + c.dur * 0.97), "off", m))
        events.sort(key=lambda e: (e[0], e[1] == "on"))
        last = 0
        for tick, kind, m in events:
            tr.append(mido.Message("note_on" if kind == "on" else "note_off", channel=ch_i, note=int(m),
                                   velocity=70 if kind == "on" else 0, time=tick - last))
            last = tick
    with tempfile.TemporaryDirectory() as d:
        mp, wp = Path(d) / "b.mid", Path(d) / "b.wav"
        mid.save(mp)
        subprocess.run(["fluidsynth", "-ni", "-g", "0.6", "-r", str(SR), "-F", str(wp), sf2, str(mp)],
                       check=True, capture_output=True)
        x, _ = sf.read(wp, dtype="float32", always_2d=True)
    return x if x.shape[1] == 2 else np.repeat(x, 2, axis=1)
