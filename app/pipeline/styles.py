"""Musical styles. Each one is a tiny 'genre recipe' that the rule-based
composer and the procedural band read from. Adding a style = adding a dict
entry; no model training needed.

Scales are semitone offsets from the tonic. Melody scale may be pentatonic
while harmony uses a 7-note scale (very common in Nepali lok/adhunik songs).
Percussion patterns are per bar on a 16th-note grid: (step, hit, velocity).
"""
from __future__ import annotations

from dataclasses import dataclass, field

MAJOR = (0, 2, 4, 5, 7, 9, 11)
MINOR = (0, 2, 3, 5, 7, 8, 10)
KAFI = (0, 2, 3, 5, 7, 9, 10)          # raag Kafi ~ dorian, beloved in lok geet
YAMAN = (0, 2, 4, 6, 7, 9, 11)         # raag Yaman ~ lydian, adhunik/ghazal colour
BHUPALI = (0, 2, 4, 7, 9)              # raag Bhupali ~ major pentatonic, Teej / folk
MALKAUNS = (0, 3, 5, 8, 10)            # minor pentatonic


@dataclass(frozen=True)
class Style:
    id: str
    label: str
    label_ne: str
    bpm: int
    steps_per_bar: int                  # 16 = 4/4, 12 = 6/8 (dadra / jhyaure feel)
    melody_scale: tuple[int, ...]
    harmony_scale: tuple[int, ...]
    verse_prog: tuple[int, ...]         # chord roots as harmony-scale degree indices
    chorus_prog: tuple[int, ...]
    percussion: tuple[tuple[int, str, float], ...]
    instruments: tuple[str, ...]        # subset of: harmonium, pluck, pad, bass, flute, madal, kit, jhyali, sitar
    vibrato_cents: float = 35.0
    dotted_prob: float = 0.15           # chance to turn 2+2 into 3+1 (lilt)
    reverb_wet: float = 0.22
    strong_steps: tuple[int, ...] = field(default=(0, 4, 8, 12))


# ---- percussion grooves ------------------------------------------------------
# madal syllables: dha (open bass+treble), ghe (bass), ta/na (treble ring), tin (muted)
MADAL_DADRA = ((0, "dha", 1.0), (3, "na", .55), (4, "ta", .7), (6, "ghe", .85), (8, "na", .6), (10, "ta", .7))
MADAL_DADRA_FAST = MADAL_DADRA + ((2, "tin", .4), (7, "tin", .35), (11, "tin", .4))
MADAL_KAHARWA = ((0, "dha", 1.0), (4, "ghe", .7), (6, "na", .55), (8, "dha", .85), (10, "ta", .6), (12, "ghe", .75), (14, "na", .55))
KIT_POP = ((0, "kick", 1.0), (4, "snare", .9), (8, "kick", .9), (10, "kick", .6), (12, "snare", .9)) + \
          tuple((s, "hat", .45 if s % 4 else .6) for s in range(0, 16, 2))
JHYALI_4 = ((0, "jhyali", .6), (4, "jhyali", .4), (8, "jhyali", .6), (12, "jhyali", .4))

STYLES: dict[str, Style] = {s.id: s for s in [
    Style("lok_dohori", "Lok / Dohori", "लोक दोहोरी", 126, 12, KAFI, KAFI,
          (0, 0, 6, 0), (0, 6, 4, 0), MADAL_DADRA, ("harmonium", "bass", "madal", "flute"),
          vibrato_cents=40, dotted_prob=0.25, strong_steps=(0, 6)),
    Style("adhunik", "Adhunik (modern)", "आधुनिक गीत", 78, 16, MAJOR, MAJOR,
          (0, 5, 3, 4), (3, 4, 0, 5), MADAL_KAHARWA, ("pluck", "pad", "bass", "madal", "flute"),
          vibrato_cents=30, dotted_prob=0.2, reverb_wet=0.28),
    Style("pop", "Nepali Pop", "नेपाली पप", 100, 16, MINOR, MINOR,
          (0, 5, 2, 6), (5, 6, 0, 0), KIT_POP, ("pluck", "pad", "bass", "kit"),
          vibrato_cents=20, dotted_prob=0.3, reverb_wet=0.2),
    Style("teej", "Teej", "तीज गीत", 144, 12, BHUPALI, MAJOR,
          (0, 0, 4, 0), (0, 3, 4, 0), MADAL_DADRA_FAST, ("harmonium", "bass", "madal", "flute", "jhyali"),
          vibrato_cents=35, dotted_prob=0.2, strong_steps=(0, 6)),
    Style("bhajan", "Bhajan", "भजन", 88, 16, MAJOR, MAJOR,
          (0, 3, 0, 4), (0, 3, 4, 0), MADAL_KAHARWA + JHYALI_4, ("harmonium", "bass", "madal", "jhyali"),
          vibrato_cents=30, dotted_prob=0.1, reverb_wet=0.3),
    Style("lori", "Lori (lullaby)", "लोरी", 96, 12, BHUPALI, MAJOR,
          (0, 3, 0, 4), (3, 0, 4, 0), (), ("pad", "pluck", "flute"),
          vibrato_cents=25, dotted_prob=0.0, reverb_wet=0.35, strong_steps=(0, 6)),
]}


def get_style(style_id: str) -> Style:
    return STYLES.get(style_id) or STYLES["adhunik"]
