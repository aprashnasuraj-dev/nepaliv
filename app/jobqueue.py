"""Job queue.

* REDIS_URL set  -> RQ (Redis Queue). API enqueues, `python -m app.worker`
  processes. Scale by running more worker processes / boxes.
* REDIS_URL empty -> in-process ThreadPoolExecutor. Zero extra services:
  perfect for a single free VM or a Hugging Face Space. Jobs are lost on
  restart, which is acceptable for an MVP.

CPU rule of thumb: one worker per 2 vCPUs. WORLD + numpy release the GIL
for most of the heavy lifting, but don't oversubscribe a free-tier box.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from .config import get_settings

QUEUE_NAME = "songs"
_executor: ThreadPoolExecutor | None = None
_inline_pending = 0
_lock = threading.Lock()


def _rq_queue():
    from redis import Redis
    from rq import Queue
    return Queue(QUEUE_NAME, connection=Redis.from_url(get_settings().redis_url))


def enqueue_song(job_id: str, req: dict) -> None:
    s = get_settings()
    if s.redis_url:
        _rq_queue().enqueue("app.pipeline.orchestrator.run_song_job", job_id, req,
                            job_id=job_id, job_timeout=s.job_timeout_s, result_ttl=3600, failure_ttl=24 * 3600)
        return
    global _executor, _inline_pending
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=s.inline_workers, thread_name_prefix="song")
        _inline_pending += 1

    def _run():
        global _inline_pending
        from .pipeline.orchestrator import run_song_job
        try:
            run_song_job(job_id, req)
        finally:
            with _lock:
                _inline_pending -= 1

    _executor.submit(_run)


def queue_depth() -> int:
    if get_settings().redis_url:
        try:
            return len(_rq_queue())
        except Exception:
            return -1
    return _inline_pending


def queue_position(job_id: str) -> int | None:
    if not get_settings().redis_url:
        return None
    try:
        ids = _rq_queue().job_ids
        return ids.index(job_id) + 1 if job_id in ids else None
    except Exception:
        return None
