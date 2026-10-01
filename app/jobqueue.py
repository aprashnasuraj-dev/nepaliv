"""Job queue helpers shared by API and desktop.

Native Windows uses the in-process executor even when REDIS_URL is present,
because RQ worker signal/fork semantics are not supported reliably there.
"""
from __future__ import annotations

import sys
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor

from .config import get_settings

QUEUE_NAME = "songs"
_executor: ThreadPoolExecutor | None = None
_inline_pending = 0
_lock = threading.Lock()
_warned_windows_redis = False


def _use_redis_queue() -> bool:
    """Return whether this process should use Redis/RQ.

    Windows deliberately falls back to the in-process queue so the desktop app
    remains usable even if a stale REDIS_URL exists in the environment.
    """
    global _warned_windows_redis
    s = get_settings()
    if not getattr(s, "redis_url", ""):
        return False
    if sys.platform.startswith("win"):
        if not _warned_windows_redis:
            warnings.warn(
                "REDIS_URL is set on native Windows; using the in-process song queue instead of RQ",
                RuntimeWarning,
                stacklevel=2,
            )
            _warned_windows_redis = True
        return False
    return True


def _rq_queue():
    from redis import Redis
    from rq import Queue

    return Queue(QUEUE_NAME, connection=Redis.from_url(get_settings().redis_url))


def enqueue_song(job_id: str, req: dict) -> None:
    s = get_settings()
    if _use_redis_queue():
        _rq_queue().enqueue(
            "app.pipeline.orchestrator.run_song_job",
            job_id,
            req,
            job_id=job_id,
            job_timeout=s.job_timeout_s,
            result_ttl=3600,
            failure_ttl=24 * 3600,
        )
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
    if _use_redis_queue():
        try:
            return len(_rq_queue())
        except Exception:
            return -1
    return _inline_pending


def queue_position(job_id: str) -> int | None:
    if not _use_redis_queue():
        return None
    try:
        ids = _rq_queue().job_ids
        return ids.index(job_id) + 1 if job_id in ids else None
    except Exception:
        return None
