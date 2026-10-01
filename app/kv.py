"""Tiny KV layer: Redis when REDIS_URL is set, otherwise an in-process dict.
Used for job state, result cache, lyric-variant cache and rate limiting."""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from .config import get_settings


class MemoryKV:
    def __init__(self):
        self._d: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def _alive(self, k):
        v = self._d.get(k)
        if v and v[0] and v[0] < time.time():
            self._d.pop(k, None)
            return None
        return v

    def get(self, k: str):
        with self._lock:
            v = self._alive(k)
            return v[1] if v else None

    def set(self, k: str, val, ttl: int | None = None):
        with self._lock:
            self._d[k] = (time.time() + ttl if ttl else 0, val)

    def incr(self, k: str, ttl: int) -> int:
        with self._lock:
            v = self._alive(k)
            n = (v[1] if v else 0) + 1
            self._d[k] = (v[0] if v else time.time() + ttl, n)
            return n

    def lpush_trim(self, k: str, val, maxlen: int, ttl: int | None = None):
        with self._lock:
            v = self._alive(k)
            lst = ([val] + (v[1] if v else []))[:maxlen]
            self._d[k] = (time.time() + ttl if ttl else 0, lst)

    def lrange(self, k: str) -> list:
        with self._lock:
            v = self._alive(k)
            return list(v[1]) if v else []


class RedisKV:
    def __init__(self, url: str):
        import redis
        self.r = redis.Redis.from_url(url, decode_responses=True)

    def get(self, k):
        v = self.r.get(k)
        return json.loads(v) if v else None

    def set(self, k, val, ttl=None):
        self.r.set(k, json.dumps(val, ensure_ascii=False), ex=ttl)

    def incr(self, k, ttl):
        p = self.r.pipeline()
        p.incr(k)
        p.expire(k, ttl, nx=True)
        return int(p.execute()[0])

    def lpush_trim(self, k, val, maxlen, ttl=None):
        p = self.r.pipeline()
        p.lpush(k, json.dumps(val, ensure_ascii=False))
        p.ltrim(k, 0, maxlen - 1)
        if ttl:
            p.expire(k, ttl)
        p.execute()

    def lrange(self, k):
        return [json.loads(x) for x in self.r.lrange(k, 0, -1)]


_KV = None
_KV_LOCK = threading.Lock()


def kv():
    global _KV
    with _KV_LOCK:
        if _KV is None:
            url = get_settings().redis_url
            _KV = RedisKV(url) if url else MemoryKV()
        return _KV


# ---- job helpers ----
JOB_TTL = 7 * 24 * 3600


def job_get(job_id: str) -> dict | None:
    return kv().get(f"job:{job_id}")


def job_update(job_id: str, **fields) -> dict:
    cur = job_get(job_id) or {"id": job_id, "created_at": time.time()}
    cur.update(fields)
    cur["updated_at"] = time.time()
    kv().set(f"job:{job_id}", cur, JOB_TTL)
    return cur
