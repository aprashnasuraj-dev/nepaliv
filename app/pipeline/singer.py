"""The singing voice: speech-to-singing conversion with the WORLD vocoder.

Idea (the core trick of this project):
  1. Each sung syllable ("मा", "माल्", "तिम्") is spoken ONCE by the Nepali TTS.
  2. WORLD decomposes it into F0 (pitch), spectral envelope (the "who/what"
     timbre + vowel) and aperiodicity (breath/noise). We store a compact,
     coded version on disk -> an automatically built UTAU-style *voicebank*.
  3. To sing a note we keep the consonant attack, time-stretch the vowel
     nucleus to the note length, replace the pitch curve with the melody
     (+ portamento + delayed vibrato + tiny drift), and resynthesise.

Cost: TTS + WORLD analysis happen only on a cache miss (~30-80 ms per
syllable on one core). Nepali songs reuse a few hundred syllables, so after
warm-up a 60 s song needs only WORLD synthesis: typically 3-10 s of CPU.

Honest quality note: this sounds like a clean, slightly "vocaloid" singer,
not a human recording. Phase 2/3 upgrades (RVC timbre conversion, DiffSinger)
are described in docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from math import gcd
from pathlib import Path

import numpy as np
import pyworld as pw
from scipy.signal import resample_poly

from ..config import get_settings
from .composer import Note, Score
from .tts import VoiceSpec, get_engine

log = logging.getLogger(__name__)
FRAME_MS = 5.0
SP_DIM = 80          # coded spectral envelope dims (WORLD mel-cepstrum-like coding)


@dataclass
class SylFeat:
    f0: np.ndarray        # (T,)
    sp_c: np.ndarray      # (T, SP_DIM) coded
    ap_c: np.ndarray      # (T, bands) coded
    fs: int
    vs: int               # first voiced frame
    ve: int               # last voiced frame + 1


class VoiceBank:
    """Disk + memory cache of WORLD features for every syllable a voice has sung."""

    def __init__(self, spec: VoiceSpec, mem_items: int = 3000):
        self.spec = spec
        self.dir = get_settings().data_dir / "voicebank" / spec.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self._mem: OrderedDict[str, SylFeat] = OrderedDict()
        self._mem_items = mem_items
        self._lock = threading.Lock()

    def _path(self, text: str) -> Path:
        return self.dir / (hashlib.sha1(text.encode()).hexdigest()[:16] + ".npz")

    def get(self, text: str) -> SylFeat | None:
        with self._lock:
            if text in self._mem:
                self._mem.move_to_end(text)
                return self._mem[text]
        p = self._path(text)
        feat = None
        if p.exists():
            d = np.load(p)
            feat = SylFeat(d["f0"], d["sp_c"], d["ap_c"], int(d["fs"]), int(d["vs"]), int(d["ve"]))
        else:
            feat = self._analyse(text)
            if feat is not None:
                np.savez_compressed(p, f0=feat.f0, sp_c=feat.sp_c, ap_c=feat.ap_c, fs=feat.fs, vs=feat.vs, ve=feat.ve)
        if feat is not None:
            with self._lock:
                self._mem[text] = feat
                if len(self._mem) > self._mem_items:
                    self._mem.popitem(last=False)
        return feat

    def _analyse(self, text: str) -> SylFeat | None:
        audio, sr = get_engine(self.spec).synth(text)
        return analyse_audio(audio, sr)


def analyse_audio(audio: np.ndarray, sr: int) -> SylFeat | None:
    x = trim_silence(audio.astype(np.float64), sr)
    if len(x) < sr * 0.05:
        return None
    f0, t = pw.dio(x, sr, frame_period=FRAME_MS, f0_floor=60, f0_ceil=600)
    f0 = pw.stonemask(x, f0, t, sr)
    sp = pw.cheaptrick(x, f0, t, sr)
    ap = pw.d4c(x, f0, t, sr)
    voiced = np.where(f0 > 0)[0]
    if len(voiced) < 3:                      # unvoiced syllable: fake a short nucleus
        vs, ve = len(f0) // 3, max(len(f0) // 3 + 2, len(f0) - 2)
        f0 = f0.copy()
        f0[vs:ve] = 150.0
    else:
        vs, ve = int(voiced[0]), int(voiced[-1]) + 1
    return SylFeat(
        f0=f0.astype(np.float32),
        sp_c=pw.code_spectral_envelope(sp, sr, SP_DIM).astype(np.float32),
        ap_c=pw.code_aperiodicity(ap, sr).astype(np.float32),
        fs=sr, vs=vs, ve=ve)


def trim_silence(x: np.ndarray, sr: int, thresh_db: float = -40.0) -> np.ndarray:
    hop = int(sr * 0.01)
    if len(x) < hop * 3:
        return x
    frames = len(x) // hop
    rms = np.sqrt(np.mean(x[: frames * hop].reshape(frames, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms / (rms.max() + 1e-12))
    idx = np.where(db > thresh_db)[0]
    if len(idx) == 0:
        return x
    a, b = max(0, idx[0] - 1) * hop, min(len(x), (idx[-1] + 2) * hop)
    return x[a:b]


def midi_to_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


# ---------------------------------------------------------------------------
class Singer:
    def __init__(self, spec: VoiceSpec, vibrato_cents: float = 35.0, seed: int = 0, mode: str = "line"):
        self.spec = spec
        self.bank = VoiceBank(spec)
        self.vibrato_cents = vibrato_cents
        self.rng = np.random.default_rng(seed)
        self.line = None
        if mode == "line" and spec.engine == "piper":
            try:
                from .line_singer import LineSinger
                self.line = LineSinger(spec, vibrato_cents, seed)
            except Exception as e:                    # model without a duration node etc.
                log.warning("line singer unavailable (%s); using syllable mode", e)

    def render_note(self, feat: SylFeat, note: Note, prev_hz: float | None,
                    pitch_offset: float = 0.0, overlap_s: float = 0.04) -> tuple[np.ndarray, float]:
        """Return (audio, lead_s): audio starts lead_s before the note onset
        (consonant lands before the beat, vowel on the beat) and runs overlap_s
        past the note end so neighbouring syllables crossfade (legato)."""
        fp = FRAME_MS / 1000.0
        has_coda = bool(note.syl and note.syl.coda)
        # drop the spoken "trailing off": keep only a short release (longer if a final consonant follows)
        T_src = min(len(feat.f0), feat.ve + (16 if has_coda else 3))
        head = feat.vs                               # consonant / attack frames
        coda_frames = max(0, T_src - feat.ve)
        vlen = feat.ve - feat.vs
        # stretch the stable middle of the vowel, keep the onset & release transitions
        a = feat.vs + int(vlen * 0.25)
        b = feat.ve - int(vlen * (0.25 if has_coda else 0.1))
        if b <= a:
            a, b = feat.vs, max(feat.vs + 1, feat.ve)
        lead_frames = min(head, int(0.12 / fp))      # at most 120 ms of consonant before the beat
        target = max(4, int(round((note.dur + overlap_s) / fp)) + lead_frames)
        keep = a + (T_src - b)
        if keep >= target:                           # very short note: keep the consonant, squeeze the rest
            rest = np.linspace(head, T_src - 1, max(2, target - head)) if target > head + 2 else \
                np.linspace(0, T_src - 1, target)
            src_idx = np.concatenate([np.arange(0, head), rest]) if target > head + 2 else rest
        else:
            mid = np.linspace(a, b - 1, target - keep)
            src_idx = np.concatenate([np.arange(0, a), mid, np.arange(b, T_src)]).astype(np.float64)
        i0 = np.floor(src_idx).astype(int)
        i1 = np.minimum(i0 + 1, T_src - 1)
        w = (src_idx - i0)[:, None]
        sp_c = (1 - w) * feat.sp_c[i0] + w * feat.sp_c[i1]
        ap_c = (1 - w) * feat.ap_c[i0] + w * feat.ap_c[i1]
        voiced = feat.f0[i0] > 0

        # melody pitch curve
        n = len(src_idx)
        t = np.arange(n) * fp - lead_frames * fp     # seconds relative to note onset
        hz = midi_to_hz(note.midi + pitch_offset)
        cents = np.zeros(n)
        if prev_hz:                                  # portamento from previous note (~70 ms)
            start_c = 1200 * np.log2(prev_hz / hz)
            glide = np.clip(t / 0.07, 0, 1)
            cents += np.where(t < 0.07, start_c * (1 - glide) ** 2, 0.0)
        if note.dur > 0.35:                          # delayed vibrato on held notes
            ramp = np.clip((t - 0.22) / 0.3, 0, 1)
            cents += self.vibrato_cents * ramp * np.sin(2 * np.pi * 5.6 * np.clip(t, 0, None))
        drift = np.interp(np.arange(n), np.linspace(0, n, 6), self.rng.normal(0, 6, 6))
        f0 = hz * 2 ** ((cents + drift) / 1200)
        f0 = np.where(voiced, f0, 0.0)
        # voice the whole stretched nucleus even if the analysis had gaps
        f0[max(0, head):max(0, n - coda_frames)] = np.where(
            f0[max(0, head):max(0, n - coda_frames)] > 0, f0[max(0, head):max(0, n - coda_frames)],
            hz)

        fs = feat.fs
        fft = pw.get_cheaptrick_fft_size(fs)
        sp = pw.decode_spectral_envelope(np.ascontiguousarray(sp_c, dtype=np.float64), fs, fft)
        ap = pw.decode_aperiodicity(np.ascontiguousarray(ap_c, dtype=np.float64), fs, fft)
        y = pw.synthesize(np.ascontiguousarray(f0, dtype=np.float64), sp, ap, fs, FRAME_MS)
        # loudness normalisation + fades
        voiced_part = y[int(head * fp * fs):] if head * fp * fs < len(y) else y
        rms = np.sqrt(np.mean(voiced_part ** 2) + 1e-12)
        y = y * (0.12 / rms)
        fin, fout = min(len(y) // 4, int(0.006 * fs)), min(len(y) // 3, int(overlap_s * fs))
        if fin > 0:
            y[:fin] *= np.linspace(0, 1, fin)
        if fout > 0:                                   # equal-power-ish crossfade tail into the next syllable
            y[-fout:] *= np.cos(np.linspace(0, np.pi / 2, fout))
        return y.astype(np.float32), lead_frames * fp

    def sing(self, notes: list[Note], total_dur: float, out_sr: int,
             pitch_offset: float = 0.0, progress=None) -> np.ndarray:
        """Render all vocal notes into one mono track at out_sr.
        Line mode (whole line spoken naturally, then sung) with per-line fallback
        to syllable mode."""
        notes = [n for n in notes if n.syl]
        if not notes:
            return np.zeros(int(total_dur * out_sr), dtype=np.float32)
        lines: dict[int, list[Note]] = {}
        for n in notes:
            lines.setdefault(n.line_id, []).append(n)
        rendered: list[tuple[np.ndarray, float, int]] = []
        leftovers: list[Note] = []
        for k, (lid, ln) in enumerate(lines.items()):
            done = False
            if self.line is not None:
                try:
                    an = self.line.analyse(ln)
                    if an is not None:
                        y, t0 = self.line.render(ln, an, pitch_offset)
                        rendered.append((y, t0, an.sr))
                        done = True
                except Exception as e:
                    log.warning("line %s fell back to syllable mode: %s", lid, e)
            if not done:
                leftovers.extend(ln)
            if progress:
                progress(0.8 * (k + 1) / len(lines))
        sr = rendered[0][2] if rendered else None
        if leftovers:
            y, fs = self._sing_syllables(leftovers, total_dur, pitch_offset)
            sr = sr or fs
            rendered.append((y, 0.0, fs))
        buf = np.zeros(int((total_dur + 1) * sr), dtype=np.float32)
        for y, t0, fs in rendered:
            if fs != sr:
                g = gcd(fs, sr)
                y = resample_poly(y, sr // g, fs // g).astype(np.float32)
            s0 = int(max(0.0, t0) * sr)
            e = min(len(buf), s0 + len(y))
            buf[s0:e] += y[: e - s0]
        if sr != out_sr:
            g = gcd(sr, out_sr)
            buf = resample_poly(buf, out_sr // g, sr // g).astype(np.float32)
        return buf[: int(total_dur * out_sr)]

    def _sing_syllables(self, notes: list[Note], total_dur: float, pitch_offset: float):
        """v1 fallback: isolated-syllable voicebank (fast after warm-up, less natural)."""
        uniq = list(dict.fromkeys(n.syl.text for n in notes))
        feats = {t: self.bank.get(t) for t in uniq}
        fs = next(f.fs for f in feats.values() if f is not None)
        buf = np.zeros(int((total_dur + 1) * fs), dtype=np.float32)
        prev_hz, prev_end = None, -1.0
        for note in notes:
            feat = feats.get(note.syl.text)
            if feat is None:
                continue
            legato = prev_hz if (note.start - prev_end) < 0.08 else None
            y, lead = self.render_note(feat, note, legato, pitch_offset)
            s = int(max(0.0, note.start - lead) * fs)
            e = min(len(buf), s + len(y))
            buf[s:e] += y[: e - s]
            prev_hz, prev_end = midi_to_hz(note.midi + pitch_offset), note.start + note.dur
        return buf, fs


def harmony_notes(score: Score) -> list[Note]:
    """Diatonic third above the melody, chorus only - the 'duet chorus' effect."""
    hs = score.style.harmony_scale
    out = []
    for n in score.vocal:
        if n.section != "chorus":
            continue
        rel = (int(round(n.midi)) - score.tonic_midi) % 12
        octv = (int(round(n.midi)) - score.tonic_midi) // 12
        k = min(range(len(hs)), key=lambda i: abs(hs[i] - rel))
        k2 = k + 2
        midi = score.tonic_midi + hs[k2 % len(hs)] + 12 * (octv + k2 // len(hs))
        out.append(Note(midi=midi, start=n.start, dur=n.dur, syl=n.syl, line_id=n.line_id, section=n.section))
    return out
