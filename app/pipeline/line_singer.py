"""Line-level singing (v2) - the fix for the "sounds like Chinese" problem.

v1 spoke every syllable in isolation, so each one got its own little
sentence intonation and no coarticulation: that monosyllabic, tonal sound.

v2 speaks the WHOLE LINE naturally with Piper, then:
  1. reads exact per-phoneme durations out of the VITS model itself
     (we expose the hidden `Ceil` duration tensor of the ONNX graph as an
     extra output - no aligner model, no extra download),
  2. groups phonemes into the same sung syllables the composer used
     (one vowel nucleus per syllable; consonant clusters split like Nepali),
  3. analyses the line once with WORLD and rebuilds it on the melody's
     timeline: consonants keep their natural length and land just before
     the beat, vowels stretch to the note, pitch follows the melody with
     portamento + vibrato, all in one continuous resynthesis (true legato).
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyworld as pw

from ..config import get_settings
from .composer import Note
from .nepali_text import syllabify_word
from .tts import VoiceSpec

FRAME_MS = 5.0
# Appended to every line before TTS and cut off afterwards, so the real last syllable is not
# utterance-final (speech devoices / whispers final vowels and lets pitch fall away).
SENTINEL = "हो"
VOWELS = set("aɪiuʊeɛoɔʌəæɐɨ")
ATTACH = {"ː", "̃", "ʰ", "ʲ", "ʱ", "ʷ"}       # modifiers glued to the previous phoneme
STRESS = {"ˈ", "ˌ"}


# ---------------------------------------------------------------------------
class DurationTTS:
    """Piper voice + a patched ONNX session that also returns phoneme durations."""

    _cache: dict[str, "DurationTTS"] = {}
    _lock = threading.Lock()

    def __init__(self, model_path: Path):
        import onnx
        import onnxruntime as ort
        from onnx import TensorProto, helper
        from piper import PiperVoice

        self.voice = PiperVoice.load(str(model_path))
        cfg = self.voice.config
        self.sr = cfg.sample_rate
        self.multi = (cfg.num_speakers or 1) > 1
        m = onnx.load(str(model_path))
        ceil = [n.output[0] for n in m.graph.node if n.op_type == "Ceil"]
        if len(ceil) != 1:
            raise RuntimeError("could not find the VITS duration node")
        m.graph.output.append(helper.make_tensor_value_info(ceil[0], TensorProto.FLOAT, None))
        so = ort.SessionOptions()
        so.intra_op_num_threads = get_settings().tts_threads
        self.sess = ort.InferenceSession(m.SerializeToString(), so, providers=["CPUExecutionProvider"])
        self.noise = float(getattr(cfg, "noise_scale", 0.667))
        self.noise_w = float(getattr(cfg, "noise_w_scale", getattr(cfg, "noise_w", 0.8)))
        inv: dict[int, str] = {}
        for ph, ids in cfg.phoneme_id_map.items():
            for i in ids:
                inv.setdefault(i, ph)
        self.inv = inv
        self.run_lock = threading.Lock()

    @classmethod
    def get(cls, model: str) -> "DurationTTS":
        with cls._lock:
            if model not in cls._cache:
                cls._cache[model] = DurationTTS(get_settings().voices_dir / f"{model}.onnx")
            return cls._cache[model]

    def speak(self, text: str, speaker_id: int | None, length_scale: float):
        """-> audio float32, list of (phoneme, start_sample, end_sample)."""
        phon = [p for sent in self.voice.phonemize(text) for p in sent]
        known = set(self.voice.config.phoneme_id_map)
        phon = [p for p in phon if p in known]
        ids = self.voice.phonemes_to_ids(phon)
        feeds = {"input": np.array([ids], np.int64), "input_lengths": np.array([len(ids)], np.int64),
                 "scales": np.array([self.noise, length_scale, self.noise_w], np.float32)}
        if self.multi:
            feeds["sid"] = np.array([speaker_id or 0], np.int64)
        with self.run_lock:
            audio, dur = self.sess.run(None, feeds)
        audio = audio.squeeze().astype(np.float32)
        dur = dur.squeeze().astype(np.int64)
        hop = len(audio) / max(1, dur.sum())
        bounds = np.concatenate([[0], np.cumsum(dur)]) * hop
        spans = []
        for k, i in enumerate(ids):
            ph = self.inv.get(int(i), "")
            s, e = int(bounds[k]), int(bounds[k + 1])
            if ph in ("^", "$", "_", "") or ph in STRESS:
                if spans:                             # pads/stress marks extend the previous phoneme
                    p, s0, _ = spans[-1]
                    spans[-1] = (p, s0, e)
                continue
            spans.append((ph, s, e))
        peak = float(np.abs(audio).max()) or 1.0
        return audio / peak * 0.8, spans


# ---------------------------------------------------------------------------
@dataclass
class SylSpan:
    start: int
    v_start: int
    v_end: int
    end: int


def _units(spans):
    units = []                     # [kind, start, end]
    for ph, s, e in spans:
        if ph in ATTACH and units and units[-1][0] != "SP":
            units[-1][2] = e
            continue
        kind = "SP" if ph == " " else ("V" if ph in VOWELS else "C")
        units.append([kind, s, e])
    return units


def segment(spans, syl_counts: list[int]) -> list[SylSpan] | None:
    """Split a line's phoneme spans into sung syllables. None if it can't be matched."""
    words, cur = [], []
    for u in _units(spans):
        if u[0] == "SP":
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append(u)
    if cur:
        words.append(cur)
    if len(words) != len(syl_counts):
        return None
    out: list[SylSpan] = []
    for units, n in zip(words, syl_counts):
        nuclei = [i for i, u in enumerate(units) if u[0] == "V"]
        # diphthongs / espeak glides (e.g. "-नु" -> n u ʲ u): merge adjacent vowels until counts match
        while len(nuclei) > n:
            adj = [j for j in range(len(nuclei) - 1) if nuclei[j + 1] == nuclei[j] + 1]
            if not adj:
                return None
            j = adj[-1]
            a, b = nuclei[j], nuclei[j + 1]
            units[a] = ["V", units[a][1], units[b][2]]
            units.pop(b)
            nuclei = [i for i, u in enumerate(units) if u[0] == "V"]
        if len(nuclei) != n:
            return None
        starts = [units[0][1]]
        for j in range(n - 1):
            a, b = nuclei[j], nuclei[j + 1]
            cons = b - a - 1
            cut = b if cons == 0 else (b - 1 if cons == 1 else a + 2)   # VC.CV, V.CV
            starts.append(units[cut][1])
        ends = starts[1:] + [units[-1][2]]
        for j in range(n):
            nu = units[nuclei[j]]
            out.append(SylSpan(starts[j], nu[1], nu[2], ends[j]))
    return out


# ---------------------------------------------------------------------------
@dataclass
class LineAnalysis:
    sr: int
    f0: np.ndarray
    log_sp: np.ndarray
    ap: np.ndarray
    syl: list[SylSpan]             # in WORLD frame units


class LineSinger:
    def __init__(self, spec: VoiceSpec, vibrato_cents: float, seed: int):
        self.spec = spec
        self.tts = DurationTTS.get(spec.model)
        self.vibrato_cents = vibrato_cents
        self.rng = np.random.default_rng(seed)
        self._cache: OrderedDict[str, LineAnalysis | None] = OrderedDict()

    @staticmethod
    def line_text(notes: list[Note]) -> tuple[str, list[int]]:
        words: OrderedDict[int, list[str]] = OrderedDict()
        for n in notes:
            words.setdefault(n.syl.word_index, []).append(n.syl.text)
        return " ".join("".join(w) for w in words.values()), [len(w) for w in words.values()]

    def analyse(self, notes: list[Note]) -> LineAnalysis | None:
        text, counts = self.line_text(notes)
        if text in self._cache:
            return self._cache[text]
        audio, spans = self.tts.speak(f"{text} {SENTINEL}", self.spec.speaker_id, 1.05)
        segs = segment(spans, counts + [len(syllabify_word(SENTINEL))])
        if segs is not None:
            segs = segs[: sum(counts)]                 # drop the sentinel word
        res = None
        if segs is not None:
            sr = self.tts.sr
            x = audio.astype(np.float64)
            f0, t = pw.dio(x, sr, frame_period=FRAME_MS, f0_floor=60, f0_ceil=600)
            f0 = pw.stonemask(x, f0, t, sr)
            sp = pw.cheaptrick(x, f0, t, sr)
            ap = pw.d4c(x, f0, t, sr)
            fr = lambda smp: min(len(f0) - 1, int(round(smp / sr * 1000 / FRAME_MS)))
            syl = []
            for s in segs:
                a, b = fr(s.v_start), max(fr(s.v_start) + 1, fr(s.v_end))
                v = np.where(f0[a:b] > 0)[0]
                if len(v) >= 3:                         # nucleus = voiced part of the vowel span
                    a, b = a + int(v[0]), a + int(v[-1]) + 1
                syl.append(SylSpan(fr(s.start), a, b, max(b, fr(s.end))))
            log_sp = np.log(sp + 1e-12)
            # level every vowel to the line's typical vowel loudness (weak unstressed vowels
            # would otherwise turn into near-silent sung notes); gain limited to +-9 dB
            energy = np.log(np.sum(sp, axis=1) + 1e-12)          # log power per frame
            nuc_e = [float(np.median(energy[x.v_start:x.v_end])) for x in syl]
            target = float(np.median(nuc_e))
            for x, e in zip(syl, nuc_e):
                g = np.clip(target - e, -2.07, 2.07)              # ln(power): +-9 dB
                log_sp[x.start:x.end] += g
            res = LineAnalysis(sr, f0, log_sp, ap, syl)
        self._cache[text] = res
        if len(self._cache) > 64:
            self._cache.popitem(last=False)
        return res

    def render(self, notes: list[Note], an: LineAnalysis, pitch_offset: float = 0.0) -> tuple[np.ndarray, float]:
        """Return (audio @ an.sr, start_time_s) for one sung line."""
        fp = FRAME_MS / 1000.0
        n = len(notes)
        onset = [max(0, s.v_start - s.start) for s in an.syl]
        onset = [min(o, int(0.12 / fp)) for o in onset]
        coda = [min(max(0, s.end - s.v_end), int(0.10 / fp)) for s in an.syl]
        # output timeline (frames, relative to line start)
        t0 = notes[0].start - onset[0] * fp
        starts = [max(0, int(round((nt.start - t0) / fp)) - onset[i]) for i, nt in enumerate(notes)]
        for i in range(1, n):
            starts[i] = max(starts[i], starts[i - 1] + 2)
        last_end = int(round((notes[-1].start + notes[-1].dur - t0) / fp))
        ends = starts[1:] + [max(last_end, starts[-1] + 4)]

        src_idx, midi, rel_t, note_dur, force_v, note_id = [], [], [], [], [], []
        for i, (nt, s) in enumerate(zip(notes, an.syl)):
            L = ends[i] - starts[i]
            on_src = np.arange(s.v_start - onset[i], s.v_start)
            co_src = np.arange(s.v_end, s.v_end + coda[i])
            on_len, co_len = len(on_src), len(co_src)
            if on_len + co_len > 0.7 * L:                       # fast note: squeeze consonants
                k = 0.7 * L / max(1, on_len + co_len)
                on_len, co_len = int(on_len * k), int(co_len * k)
            nuc_len = max(1, L - on_len - co_len)
            vlen = s.v_end - s.v_start
            a, b = s.v_start + int(vlen * 0.2), s.v_end - int(vlen * 0.15)   # stable middle of the vowel
            if b <= a:
                a, b = s.v_start, s.v_end
            head = np.linspace(s.v_start, a, max(1, min(int(vlen * 0.2), nuc_len // 3)), endpoint=False)
            tail_n = max(1, min(int(vlen * 0.15), nuc_len // 4))
            mid_n = max(1, nuc_len - len(head) - tail_n)
            nuc_src = np.concatenate([head, np.linspace(a, b, mid_n), np.linspace(b, s.v_end - 1, tail_n)])
            seg = np.concatenate([
                np.linspace(on_src[0], on_src[-1], on_len) if on_len and len(on_src) else np.zeros(0),
                nuc_src,
                np.linspace(co_src[0], co_src[-1], co_len) if co_len and len(co_src) else np.zeros(0)])
            src_idx.append(seg)
            m = nt.midi + pitch_offset
            midi.append(np.full(len(seg), m))
            beat = on_len
            rel_t.append((np.arange(len(seg)) - beat) * fp)
            note_dur.append(np.full(len(seg), nt.dur))
            fv = np.zeros(len(seg), bool)
            fv[on_len:on_len + len(nuc_src)] = True
            force_v.append(fv)
            note_id.append(np.full(len(seg), i))
        src = np.clip(np.concatenate(src_idx), 0, len(an.f0) - 1)
        midi_a, rel_a = np.concatenate(midi), np.concatenate(rel_t)
        dur_a, fv_a, nid = np.concatenate(note_dur), np.concatenate(force_v), np.concatenate(note_id)

        i0 = np.floor(src).astype(int)
        i1 = np.minimum(i0 + 1, len(an.f0) - 1)
        w = (src - i0)[:, None]
        sp = np.exp((1 - w) * an.log_sp[i0] + w * an.log_sp[i1])
        ap = (1 - w) * an.ap[i0] + w * an.ap[i1]
        voiced = (an.f0[i0] > 0) | fv_a
        ap = np.where(fv_a[:, None], ap * 0.55, ap)        # sung vowels: less breath noise, more tone

        # pitch: note pitch + portamento into each note + delayed vibrato + slow drift
        cents = np.zeros(len(src))
        for i in range(1, len(notes)):
            idx = np.where(nid == i)[0]
            if len(idx) == 0:
                continue
            prev = notes[i - 1].midi - notes[i].midi
            g = np.clip((rel_a[idx] + 0.03) / 0.09, 0, 1)
            cents[idx] += prev * 100 * (1 - g) ** 2
        ramp = np.clip((rel_a - 0.25) / 0.3, 0, 1) * (dur_a > 0.4)
        cents += self.vibrato_cents * ramp * np.sin(2 * np.pi * 5.5 * np.clip(rel_a, 0, None))
        cents += np.interp(np.arange(len(src)), np.linspace(0, len(src), 8), self.rng.normal(0, 5, 8))
        f0 = 440.0 * 2 ** ((midi_a - 69 + cents / 100) / 12)
        f0 = np.where(voiced, f0, 0.0)

        y = pw.synthesize(np.ascontiguousarray(f0), np.ascontiguousarray(sp), np.ascontiguousarray(ap),
                          an.sr, FRAME_MS)
        rms = np.sqrt(np.mean(y[np.abs(y) > 1e-4] ** 2) + 1e-12) if np.any(np.abs(y) > 1e-4) else 1.0
        y = y * (0.12 / rms)
        f = min(len(y) // 4, int(0.012 * an.sr))
        if f:
            y[:f] *= np.linspace(0, 1, f)
            y[-f:] *= np.linspace(1, 0, f)
        return y.astype(np.float32), t0
