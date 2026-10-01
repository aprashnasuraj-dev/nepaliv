"""Background worker:  python -m app.worker

Uses RQ's SimpleWorker (no fork per job) so the TTS model, the syllable
voicebank LRU and the bar cache stay warm in memory between songs - on a
CPU box that's the difference between ~40 s and ~10 s per song."""
from __future__ import annotations

import logging
import os

from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("worker")


def preload():
    s = get_settings()
    os.environ.setdefault("OMP_NUM_THREADS", str(s.tts_threads))
    from .pipeline.tts import get_engine, get_voice
    try:
        get_engine(get_voice(None))
        log.info("TTS voice %s loaded", s.default_voice)
    except Exception as e:                       # worker can still serve cached voicebank syllables
        log.warning("could not preload TTS: %s", e)


def main():
    s = get_settings()
    if not s.redis_url:
        raise SystemExit("REDIS_URL is empty: the API runs jobs in-process; no separate worker needed.")
    from redis import Redis
    from rq import Queue, SimpleWorker
    preload()
    conn = Redis.from_url(s.redis_url)
    worker = SimpleWorker([Queue("songs", connection=conn)], connection=conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
