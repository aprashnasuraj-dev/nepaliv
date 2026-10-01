"""Nepali (Devanagari) text utilities for *singing*.

Why this matters: a melody assigns one note per sung syllable. Devanagari
is an abugida, so a "letter" is not a syllable. We:
  1. normalise Unicode (NFC, strip ZWJ/ZWNJ, punctuation, Latin, digits),
  2. split words into aksharas (orthographic syllables),
  3. apply Nepali word-final schwa deletion so "घर" sings as one syllable
     "ghar", not two ("gha-ra"),
  4. expose a rough romanisation + vowel nucleus, used for rhyme checking,
     voicebank keys and debugging.

Pure Python, zero dependencies, microseconds per line.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ---- Unicode classes -------------------------------------------------------
VIRAMA = "\u094D"
NUKTA = "\u093C"
ZW = {"\u200C", "\u200D"}
MODIFIERS = {"\u0901", "\u0902", "\u0903"}           # chandrabindu, anusvara, visarga
MATRAS = {chr(c) for c in range(0x093E, 0x094D)} | {"\u0962", "\u0963", "\u093A", "\u093B", "\u094E", "\u094F"}
INDEP_VOWELS = {chr(c) for c in range(0x0904, 0x0915)} | {"\u0960", "\u0961"}
CONSONANTS = {chr(c) for c in range(0x0915, 0x093A)} | {chr(c) for c in range(0x0958, 0x0960)}

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_NON_DEV = re.compile(r"[^\u0900-\u097F\s]")

# ---- Romanisation tables (simple, singer-oriented, not ISO-15919) ----------
_C = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
    "ञ": "ny", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
    "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
    "ल": "l", "व": "w", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l", "ऱ": "r",
    "क़": "k", "ख़": "kh", "ग़": "g", "ज़": "j", "ड़": "d", "ढ़": "dh", "फ़": "f", "य़": "y",
}
_V = {"अ": "a", "आ": "aa", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri", "ए": "e", "ऐ": "ai",
      "ओ": "o", "औ": "au", "ऑ": "o", "ॠ": "ri", "ऌ": "li"}
_M = {"ा": "aa", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o",
      "ौ": "au", "ॉ": "o", "ॄ": "ri"}
_MOD = {"ं": "n", "ँ": "~", "ः": "h"}

# vowel nucleus -> sustainable vowel used when the singer holds a note
SUSTAIN_VOWEL = {"a": "a", "aa": "aa", "i": "i", "u": "u", "e": "e", "ai": "e", "o": "o", "au": "o", "ri": "i", "li": "i"}


@dataclass
class Syllable:
    text: str            # Devanagari, what we send to TTS
    roman: str           # rough romanisation
    vowel: str           # nucleus vowel ("a", "aa", "i" ...)
    coda: str = ""       # trailing consonant after schwa deletion
    word_index: int = 0
    word_final: bool = False

    @property
    def rhyme_key(self) -> str:
        return f"{SUSTAIN_VOWEL.get(self.vowel, self.vowel)}{self.coda}"


# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    """NFC, drop zero-width joiners, Latin, digits, punctuation (keeps danda as space)."""
    text = unicodedata.normalize("NFC", text)
    text = "".join(ch for ch in text if ch not in ZW)
    text = text.translate(_DEV_DIGITS)
    text = text.replace("।", " ").replace("॥", " ")
    text = _NON_DEV.sub(" ", text)
    text = re.sub(r"[\u0964\u0965\u0970]", " ", text)       # danda variants, abbreviation sign
    text = "".join(ch for ch in text if not ("\u0966" <= ch <= "\u096F"))   # stray digits
    return re.sub(r"\s+", " ", text).strip()


def devanagari_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha() or "\u0900" <= c <= "\u097F"]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "\u0900" <= c <= "\u097F") / len(letters)


def aksharas(word: str) -> list[str]:
    """Split one word into orthographic syllables (aksharas)."""
    out, i, n = [], 0, len(word)
    while i < n:
        ch = word[i]
        start = i
        if ch in CONSONANTS:
            i += 1
            if i < n and word[i] == NUKTA:
                i += 1
            # conjuncts: C (nukta) virama C ...
            while i + 1 < n and word[i] == VIRAMA and word[i + 1] in CONSONANTS:
                i += 2
                if i < n and word[i] == NUKTA:
                    i += 1
            if i < n and word[i] == VIRAMA:          # explicit halanta (e.g. word-final ्)
                i += 1
            elif i < n and word[i] in MATRAS:
                i += 1
            while i < n and word[i] in MODIFIERS:
                i += 1
        elif ch in INDEP_VOWELS:
            i += 1
            while i < n and word[i] in MODIFIERS:
                i += 1
        else:                                        # stray matra/modifier: attach to previous
            i += 1
            if out:
                out[-1] += word[start:i]
                continue
        out.append(word[start:i])
    return out


def _roman_akshara(ak: str) -> tuple[str, str, str]:
    """Return (onset, vowel, modifiers) romanised for one akshara."""
    onset, vowel, mods = "", "", ""
    consonant_count = 0
    halanta = False
    for idx, ch in enumerate(ak):
        if ch in CONSONANTS:
            nxt = ak[idx + 1] if idx + 1 < len(ak) else ""
            key = ch + NUKTA if nxt == NUKTA else ch
            onset += _C.get(key, _C.get(ch, ""))
            consonant_count += 1
        elif ch in INDEP_VOWELS:
            vowel = _V.get(ch, "a")
        elif ch in MATRAS:
            vowel = _M.get(ch, "a")
        elif ch in MODIFIERS:
            mods += _MOD.get(ch, "")
        elif ch == VIRAMA:
            halanta = ak.endswith(VIRAMA)
    if not vowel and not halanta and consonant_count:
        vowel = "a"                                  # inherent schwa
    return onset, vowel, mods


def is_bare_consonant(ak: str) -> bool:
    """Single consonant (optionally with nukta), no matra, no conjunct, no modifier."""
    core = ak.replace(NUKTA, "")
    return len(core) == 1 and core in CONSONANTS


# Verb endings where the final schwa IS pronounced: आउँछ (aaũ-chha), गएन (ga-e-na), होइन.
_KEEP_SCHWA_FINAL = {"छ"}
# Per-word overrides for anything the heuristic gets wrong: word -> list of sung syllables.
LEXICON: dict[str, list[str]] = {
    "हुन": ["हु", "न"],
    "भन": ["भ", "न"],
}


def _keeps_final_schwa(aks: list[str]) -> bool:
    last = aks[-1]
    if last in _KEEP_SCHWA_FINAL:
        return True
    if last == "न" and len(aks) >= 2 and aks[-2][0] in INDEP_VOWELS:   # गएन, होइन
        return True
    return False


def syllabify_word(word: str, word_index: int = 0) -> list[Syllable]:
    """Akshara split + Nepali schwa deletion + conjunct re-split, i.e. *sung* syllables.

    हिमालको -> हि|मा|ल|को -> हि|माल|को       (medial schwa deletion: hi-maal-ko)
    जन्मदिन -> ज|न्म|दि|न  -> जन्|म|दिन      (jan-ma-din)
    घर      -> घ|र         -> घर              (word-final deletion: ghar)
    आउँछ    -> आ|उँ|छ                        (verb ending keeps schwa: aa-ũ-chha)
    """
    if word in LEXICON:
        return _from_parts(LEXICON[word], word_index)
    aks = aksharas(word)
    if not aks:
        return []
    n = len(aks)
    deleted = [False] * n
    if n > 1 and is_bare_consonant(aks[-1]) and not _keeps_final_schwa(aks):
        deleted[-1] = True
    # medial deletion (right to left): V C(a) CV  ->  VC.CV
    for k in range(n - 2, 0, -1):
        if (is_bare_consonant(aks[k]) and not deleted[k + 1] and not deleted[k - 1]
                and not aks[k - 1].endswith(VIRAMA) and _has_vowel(aks[k + 1])
                and not _is_conjunct(aks[k + 1])):                 # avoid 3-consonant clusters
            deleted[k] = True
    merged: list[str] = []
    for k, ak in enumerate(aks):
        if merged and (deleted[k] or ak.endswith(VIRAMA)):
            merged[-1] += ak + ("" if ak.endswith(VIRAMA) else VIRAMA)
        else:
            merged.append(ak)
    # medial conjunct split: तिम्रो -> तिम्|रो, जस्तै -> जस्|तै (singers close the previous syllable)
    for j in range(1, len(merged)):
        m = merged[j]
        if len(m) > 2 and m[0] in CONSONANTS and m[1] == VIRAMA and m[2] in CONSONANTS:
            merged[j - 1] += m[:2]
            merged[j] = m[2:]
    return _from_parts(merged, word_index)


def _is_conjunct(ak: str) -> bool:
    return len(ak) > 2 and ak[0] in CONSONANTS and ak[1] == VIRAMA


def _has_vowel(ak: str) -> bool:
    return not ak.endswith(VIRAMA)


def _from_parts(merged: list[str], word_index: int) -> list[Syllable]:
    syls: list[Syllable] = []
    for j, ak in enumerate(merged):
        parts = aksharas(ak)
        onset, vowel, mods = _roman_akshara(parts[0])
        coda = ""
        for extra in parts[1:]:                       # schwa-deleted trailing consonant(s)
            o, _, m = _roman_akshara(extra if extra.endswith(VIRAMA) else extra + VIRAMA)
            coda += o + m
        roman = onset + vowel + mods + coda
        syls.append(Syllable(text=ak, roman=roman, vowel=vowel or "a", coda=mods.replace("~", "") + coda,
                             word_index=word_index, word_final=(j == len(merged) - 1)))
    return syls


def syllabify_line(line: str) -> list[Syllable]:
    words = normalize(line).split()
    out: list[Syllable] = []
    for wi, w in enumerate(words):
        out.extend(syllabify_word(w, wi))
    return out


def count_syllables(line: str) -> int:
    return len(syllabify_line(line))


def romanize(line: str) -> str:
    words = normalize(line).split()
    return " ".join("".join(s.roman for s in syllabify_word(w)) for w in words)


def rhymes(line_a: str, line_b: str) -> bool:
    a, b = syllabify_line(line_a), syllabify_line(line_b)
    if not a or not b:
        return False
    return a[-1].rhyme_key == b[-1].rhyme_key
