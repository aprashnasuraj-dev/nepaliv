"""Rule-based melody composer.

Why not an AI music model? MusicGen-small on CPU needs ~minutes per 10 s of
audio and produces no lyric alignment. A rule-based composer is instant,
deterministic (cacheable via seed), and - crucially - knows exactly which
syllable sits on which note, which is what lets us *sing* the lyrics and
return karaoke timings for free.

Musical rules used (kept deliberately simple, tuned for Nepali songs):
  * one sung syllable per note, last syllable of a line is held
  * phrase form A B A' C (verse) and D E D F (chorus); repeated letters reuse
    the same melodic contour even if the syllable count differs
  * line endings follow a call/answer cadence: 5th, 2nd/3rd, 5th, tonic
  * strong beats snap to chord tones; leaps limited to a 4th-ish
  * chorus sits higher than the verse
"""
from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field

import numpy as np

from .nepali_text import Syllable, syllabify_line
from .styles import Style


@dataclass
class Note:
    midi: float
    start: float
    dur: float
    syl: Syllable | None = None
    line_id: int = -1
    section: str = ""


@dataclass
class Chord:
    start: float
    dur: float
    midis: list[int]
    degree: int
    section: str


@dataclass
class LineTiming:
    line_id: int
    section: str
    text: str
    start: float
    end: float
    syllables: list[dict]


@dataclass
class Score:
    style: Style
    bpm: int
    step_s: float
    tonic_midi: int
    total_dur: float
    vocal: list[Note] = field(default_factory=list)
    flute: list[Note] = field(default_factory=list)
    chords: list[Chord] = field(default_factory=list)
    lines: list[LineTiming] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)

    @property
    def bar_s(self) -> float:
        return self.step_s * self.style.steps_per_bar

    def karaoke(self) -> dict:
        return {
            "bpm": self.bpm, "duration": round(self.total_dur, 3),
            "sections": self.sections,
            "lines": [{"id": l.line_id, "section": l.section, "text": l.text,
                       "start": round(l.start, 3), "end": round(l.end, 3), "syllables": l.syllables}
                      for l in self.lines],
        }


# ---------------------------------------------------------------------------
class MelodyComposer:
    def __init__(self, style: Style, seed: int, center_midi: int = 60, bpm: int | None = None):
        self.style = style
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.center_midi = center_midi
        self.bpm = bpm or style.bpm
        self.step_s = 60.0 / self.bpm / 4.0
        self.ms = style.melody_scale
        self.L = len(self.ms)
        self.fifth = self._idx_of(7)
        self.third = self._idx_of(4) if 4 in self.ms else self._idx_of(3)
        self._contours: dict[str, dict] = {}

    # ---- scale helpers ----
    def _idx_of(self, semi: int) -> int:
        return min(range(self.L), key=lambda i: abs(self.ms[i] - semi))

    def idx_to_semi(self, idx: int) -> int:
        return self.ms[idx % self.L] + 12 * (idx // self.L)

    def chord_pcs(self, degree: int) -> set[int]:
        hs = self.style.harmony_scale
        return {hs[(degree + k) % len(hs)] % 12 for k in (0, 2, 4)}

    def chord_midis(self, degree: int, tonic: int) -> list[int]:
        hs = self.style.harmony_scale
        out = []
        for k in (0, 2, 4):
            d = degree + k
            out.append(tonic + hs[d % len(hs)] + 12 * (d // len(hs)))
        return out

    # ---- rhythm ----
    def bars_needed(self, n: int) -> int:
        spb = self.style.steps_per_bar
        for bars in (2, 4):
            usable = bars * spb - 2 - 3          # rest tail + minimum hold
            if (n - 1) * 2 <= usable or bars == 4:
                if (n - 1) * 1.5 <= usable or bars == 4:
                    return bars
        return 4

    def rhythm(self, syls: list[Syllable], span: int, rng: np.random.Generator) -> tuple[int, list[int]]:
        n = len(syls)
        spb = self.style.steps_per_bar
        rest = 2 if span <= 2 * spb else 4
        start = int(rng.choice([0, 0, 0, 2])) if n * 2 + rest + 6 < span else 0
        usable = span - rest - start
        if n == 1:
            return start, [usable]
        hold = max(3, min(int(usable * 0.22), spb // 2 + 2))
        remaining = usable - hold
        base = max(1, min(4, remaining // (n - 1)))
        durs = [base] * (n - 1)
        slack = remaining - base * (n - 1)
        if slack < 0:                        # too dense: squeeze the hold
            hold = max(1, hold + slack)
            slack = 0
        # spend slack on word-final syllables first (natural Nepali phrasing), then spread
        finals = [i for i in range(n - 1) if syls[i].word_final]
        rng.shuffle(finals)
        order = finals + [i for i in range(n - 1) if not syls[i].word_final]
        k = 0
        while slack > 0 and order:
            i = order[k % len(order)]
            if durs[i] < 6:
                durs[i] += 1
                slack -= 1
            k += 1
            if k > 400:
                break
        hold += slack
        # lilt: 2+2 -> 3+1 occasionally
        for i in range(len(durs) - 1):
            if durs[i] == 2 and durs[i + 1] == 2 and rng.random() < self.style.dotted_prob:
                durs[i], durs[i + 1] = 3, 1
        return start, durs + [hold]

    # ---- pitch ----
    def _contour(self, label: str, section: str) -> dict:
        if label not in self._contours:
            r = np.random.default_rng(zlib.crc32(f"{self.seed}:{label}".encode()))
            shape = r.choice(["arch", "rise", "fall", "valley", "arch"])
            self._contours[label] = {
                "shape": shape,
                "amp": float(r.uniform(2.0, 3.5)),
                "offset": float(r.uniform(-1.0, 1.0)),
                "noise": r.normal(0, 0.7, 9),
            }
        return self._contours[label]

    @staticmethod
    def _shape(name: str, t: float) -> float:
        return {"arch": math.sin(math.pi * t), "rise": t, "fall": 1 - t,
                "valley": 1 - math.sin(math.pi * t)}[name]

    def line_pitches(self, n: int, label: str, section: str, target: int,
                     onsets: list[int], degrees_at: list[int], rng: np.random.Generator) -> list[int]:
        c = self._contour(label, section)
        center = self.third if section == "verse" else self.fifth + 1
        lo, hi = -2, self.L + 3
        idxs: list[int] = []
        for i in range(n):
            t = i / max(1, n - 1)
            noise = float(np.interp(t, np.linspace(0, 1, len(c["noise"])), c["noise"]))
            v = center + c["offset"] + (self._shape(c["shape"], t) - 0.5) * c["amp"] + noise
            idxs.append(int(round(min(hi, max(lo, v)))))
        # strong-beat chord tones
        for i, (st, deg) in enumerate(zip(onsets, degrees_at)):
            if st % self.style.steps_per_bar in self.style.strong_steps and rng.random() < 0.6:
                pcs = self.chord_pcs(deg)
                for d in (0, 1, -1, 2, -2):
                    if self.idx_to_semi(idxs[i] + d) % 12 in pcs:
                        idxs[i] = max(lo, min(hi, idxs[i] + d))
                        break
        # cadence
        idxs[-1] = target
        if n >= 2 and abs(idxs[-2] - target) > 2:
            idxs[-2] = target + (1 if idxs[-2] > target else -1)
        # limit leaps, avoid >3 repeated notes
        for i in range(1, n):
            if idxs[i] - idxs[i - 1] > 3:
                idxs[i] = idxs[i - 1] + 3
            elif idxs[i - 1] - idxs[i] > 3:
                idxs[i] = idxs[i - 1] - 3
            if i >= 3 and idxs[i] == idxs[i - 1] == idxs[i - 2] == idxs[i - 3] and i != n - 1:
                idxs[i] += 1 if rng.random() < 0.5 else -1
        idxs[-1] = target
        return idxs

    # ---- full song ----
    def compose(self, sections: list[dict], intro_flute: bool = True) -> Score:
        """sections: [{"type": "verse"|"chorus", "lines": [str, ...]}, ...] in performance order."""
        st = self.style
        spb = st.steps_per_bar
        verse_labels, chorus_labels = ["A", "B", "A", "C"], ["D", "E", "D", "F"]
        verse_targets = [self.fifth, self.third, self.fifth, 0]
        chorus_targets = [self.L, self.fifth, self.L, 0]

        # pass 1: syllabify + bars per line per section
        prepared = []
        for sec in sections:
            lines = [(ln, syllabify_line(ln)) for ln in sec["lines"]]
            lines = [(t, s) for t, s in lines if s]
            bars = max([self.bars_needed(len(s)) for _, s in lines] or [2])
            prepared.append({**sec, "lines": lines, "bars": bars})

        score = Score(style=st, bpm=self.bpm, step_s=self.step_s, tonic_midi=0, total_dur=0)
        semis: list[tuple[Note, int]] = []        # (note, scale idx) -> resolved to midi later
        step = 0
        line_id = 0
        chorus_hook: list[tuple[int, int, int]] = []   # (rel_step, dur, idx) of chorus line 1

        def add_chords(sec_type: str, start_step: int, nbars: int):
            prog = st.chorus_prog if sec_type == "chorus" else st.verse_prog
            for b in range(nbars):
                deg = prog[b % len(prog)]
                if b == nbars - 1:
                    deg = 0
                elif b == nbars - 2 and nbars >= 4 and len(st.harmony_scale) == 7 and sec_type != "intro":
                    deg = 4
                score.chords.append(Chord(start=(start_step + b * spb) * self.step_s, dur=spb * self.step_s,
                                          midis=[deg], degree=deg, section=sec_type))

        # reserve intro (filled with the chorus hook on flute after we know it)
        chorus_sec = next((p for p in prepared if p["type"] == "chorus"), prepared[0])
        intro_bars = chorus_sec["bars"] if intro_flute else 2
        intro_bars = max(2, intro_bars)
        score.sections.append({"name": "intro", "start": 0.0, "end": intro_bars * spb * self.step_s})
        add_chords("intro", 0, intro_bars)
        step = intro_bars * spb

        chorus_count = 0
        for p_i, sec in enumerate(prepared):
            sec_type = sec["type"]
            is_chorus = sec_type == "chorus"
            labels = chorus_labels if is_chorus else verse_labels
            targets = chorus_targets if is_chorus else verse_targets
            sec_start = step
            nbars = sec["bars"] * len(sec["lines"])
            add_chords(sec_type, sec_start, nbars)
            rng = np.random.default_rng((self.seed * 31 + p_i * 7 + (0 if is_chorus else 1000)) % (2**32))
            if is_chorus:
                rng = np.random.default_rng((self.seed * 31 + 999) % (2**32))   # identical chorus each time
                chorus_count += 1
            for li, (text, syls) in enumerate(sec["lines"]):
                span = sec["bars"] * spb
                line_start = step
                off, durs = self.rhythm(syls, span, rng)
                onsets, s = [], line_start + off
                for d in durs:
                    onsets.append(s)
                    s += d
                degrees = [self._degree_at(score, o * self.step_s) for o in onsets]
                idxs = self.line_pitches(len(syls), labels[li % 4], "chorus" if is_chorus else "verse",
                                         targets[li % 4] if li < 4 else 0, onsets, degrees, rng)
                syl_info = []
                for syl, o, d, ix in zip(syls, onsets, durs, idxs):
                    note = Note(midi=0, start=o * self.step_s, dur=d * self.step_s, syl=syl,
                                line_id=line_id, section=sec_type)
                    semis.append((note, ix))
                    score.vocal.append(note)
                    syl_info.append({"t": syl.text, "r": syl.roman, "w": syl.word_index,
                                     "start": round(note.start, 3), "end": round(note.start + note.dur, 3)})
                    if is_chorus and li == 0 and chorus_count == 1:
                        chorus_hook.append((o - line_start, d, ix))
                score.lines.append(LineTiming(line_id, sec_type, text, onsets[0] * self.step_s,
                                              (onsets[-1] + durs[-1]) * self.step_s, syl_info))
                line_id += 1
                step += span
            score.sections.append({"name": sec_type, "start": sec_start * self.step_s, "end": step * self.step_s})

        # outro: 2 bars, flute plays the hook tail, ends on tonic chord
        outro_start = step
        add_chords("outro", outro_start, 2)
        score.sections.append({"name": "outro", "start": step * self.step_s, "end": (step + 2 * spb) * self.step_s})
        step += 2 * spb

        # flute: hook in intro (+1 octave), long tonic in outro
        flute_idx: list[tuple[Note, int]] = []
        if "flute" in st.instruments and chorus_hook:
            for rel, d, ix in chorus_hook:
                if rel < intro_bars * spb:
                    flute_idx.append((Note(0, rel * self.step_s, d * self.step_s, section="intro"), ix + self.L))
        if "flute" in st.instruments:
            flute_idx.append((Note(0, outro_start * self.step_s, 2 * spb * self.step_s * 0.9, section="outro"), self.L))

        # resolve key: centre the vocal line on the singer's comfortable pitch
        vocal_semis = [self.idx_to_semi(ix) for _, ix in semis]
        median = float(np.median(vocal_semis)) if vocal_semis else 7.0
        tonic = int(round(self.center_midi - median))
        score.tonic_midi = tonic
        for note, ix in semis:
            note.midi = tonic + self.idx_to_semi(ix)
        for note, ix in flute_idx:
            note.midi = tonic + self.idx_to_semi(ix)
            while note.midi > 86:
                note.midi -= 12
            while note.midi < 67:
                note.midi += 12
            score.flute.append(note)
        for ch in score.chords:
            ch.midis = self.chord_midis(ch.degree, tonic - 12 if tonic >= 60 else tonic)
        score.total_dur = step * self.step_s + 1.5         # reverb tail
        return score

    def _degree_at(self, score: Score, t: float) -> int:
        for ch in reversed(score.chords):
            if ch.start <= t + 1e-6:
                return ch.degree
        return 0
