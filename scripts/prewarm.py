"""Pre-build the syllable voicebank so the first real users get fast songs.

Speaks + analyses every common Nepali syllable: the CV grid, independent
vowels, every syllable in the template bank and in an optional corpus file
of lyrics (one line per row - feed it popular song lyrics you are allowed to
use for this, or your own LLM outputs). The band needs no pre-rendering.

    python scripts/prewarm.py [--voice ne_NP-google-medium] [--corpus lyrics.txt]

Takes a few minutes on 2 vCPUs, once (~400-1000 syllables, ~15-30 MB on disk). Caches live in DATA_DIR - mount it as a
volume (or bake it into the image) so they survive restarts.
"""
import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline.lyrics import BANK  # noqa: E402
from app.pipeline.nepali_text import syllabify_line  # noqa: E402
from app.pipeline.singer import VoiceBank  # noqa: E402
from app.pipeline.tts import get_voice  # noqa: E402

CONS = "कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह"
MATRAS = ["", "ा", "ि", "ी", "ु", "ू", "े", "ै", "ो", "ौ", "ं"]
VOWELS = "अआइईउऊएऐओऔ"


def syllable_set(corpus: str | None) -> list[str]:
    syl = {c + m for c in CONS for m in MATRAS} | set(VOWELS)
    lines = [l for b in BANK.values() for part in b.values() for l in part]
    if corpus:
        lines += Path(corpus).read_text(encoding="utf-8").splitlines()
    for ln in lines:
        syl |= {s.text for s in syllabify_line(ln.replace("{name}", ""))}
    return sorted(syl)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default=None)
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--threads", type=int, default=2)
    a = ap.parse_args()

    bank = VoiceBank(get_voice(a.voice))
    syls = syllable_set(a.corpus)
    t = time.time()
    with ThreadPoolExecutor(a.threads) as ex:
        for i, _ in enumerate(ex.map(bank.get, syls)):
            if i % 50 == 0:
                print(f"voicebank {i}/{len(syls)}  {time.time() - t:.0f}s", flush=True)
    print(f"voicebank ready: {len(syls)} syllables in {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
