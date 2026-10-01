"""HTTP API.

Flow for the app:
  1. (optional) POST /v1/lyrics          -> instant lyrics preview the user can edit
  2. POST /v1/songs                        -> {id}, returns immediately
  3. GET  /v1/songs/{id}  (poll 1-2 s) or GET /v1/songs/{id}/events (SSE)
       lyrics + karaoke timings arrive within seconds, audio_url when done
  4. POST /v1/songs/{id}/remix {style}     -> same lyrics, new arrangement (fast: voicebank is warm)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .jobqueue import enqueue_song, queue_depth, queue_position
from .kv import job_get, job_update, kv
from .pipeline.lyrics import generate_lyrics
from .pipeline.styles import STYLES
from .pipeline.tts import VOICES
from .schemas import JobOut, LyricsRequest, RemixRequest, SongRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()
app = FastAPI(title="Nepali Song Generator", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])
if settings.storage_backend == "local":
    app.mount("/files", StaticFiles(directory=settings.data_dir / "songs"), name="files")


# ---- auth + rate limiting ---------------------------------------------------------
def client_id(request: Request, x_api_key: str | None = Header(None)) -> str:
    keys = settings.api_key_set
    if keys:
        if x_api_key not in keys:
            raise HTTPException(401, "invalid or missing X-API-Key")
        return f"key:{x_api_key}"
    fwd = request.headers.get("x-forwarded-for", "")
    return "ip:" + (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "anon"))


def rate_limit(cid: str, bucket: str, limit: int):
    n = kv().incr(f"rl:{bucket}:{cid}", 3600)
    if n > limit:
        raise HTTPException(429, f"rate limit: {limit} {bucket} per hour")


# ---- meta ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True, "queue_depth": queue_depth()}


@app.get("/v1/styles")
def styles():
    return [{"id": s.id, "label": s.label, "label_ne": s.label_ne, "bpm": s.bpm} for s in STYLES.values()]


@app.get("/v1/voices")
def voices():
    return [{"id": v.id, "label": v.label, "gender": v.gender, "engine": v.engine,
             "default": v.id == settings.default_voice} for v in VOICES.values()]


# ---- lyrics preview -------------------------------------------------------------------
@app.post("/v1/lyrics")
async def lyrics_preview(body: LyricsRequest, cid: str = Depends(client_id)):
    rate_limit(cid, "lyrics", settings.rate_limit_per_hour * 3)
    req = body.model_dump()
    seed = req.pop("seed") or random.randint(0, 2**31 - 1)
    lyrics = await asyncio.to_thread(generate_lyrics, req, seed)
    return {"seed": seed, "lyrics": lyrics}


# ---- songs ----------------------------------------------------------------------------
def _request_key(req: dict) -> str:
    sig = json.dumps(req, sort_keys=True, ensure_ascii=False)
    return "req:" + hashlib.sha1(sig.encode()).hexdigest()[:24]


def _public(job: dict) -> JobOut:
    out = JobOut(**{k: v for k, v in job.items() if k in JobOut.model_fields})
    if job.get("status") == "queued":
        out.queue_position = queue_position(job["id"])
    return out


def _submit(req: dict, cid: str) -> JobOut:
    explicit_seed = req.get("seed") is not None
    if not explicit_seed:
        req["seed"] = random.randint(0, 2**31 - 1)
    if req.get("style") not in STYLES:
        raise HTTPException(422, f"unknown style; choose one of {list(STYLES)}")
    if req.get("voice") and req["voice"] not in VOICES:
        raise HTTPException(422, f"unknown voice; choose one of {list(VOICES)}")
    # identical request with explicit seed -> identical song: serve from cache
    if explicit_seed:
        rk = _request_key(req)
        hit = kv().get(rk)
        if hit and (job := job_get(hit["job_id"])) and job.get("status") == "done":
            return _public(job)
        req["request_key"] = rk
    rate_limit(cid, "songs", settings.rate_limit_per_hour)
    depth = queue_depth()
    if depth > 50:
        raise HTTPException(503, "song studio is busy, please try again in a few minutes")
    job_id = uuid.uuid4().hex[:16]
    job = job_update(job_id, status="queued", stage="queued", progress=0,
                     request={k: v for k, v in req.items() if k != "request_key"})
    enqueue_song(job_id, req)
    return _public(job)


@app.post("/v1/songs", response_model=JobOut, status_code=202)
def create_song(body: SongRequest, cid: str = Depends(client_id)):
    req = body.model_dump()
    if req["lyrics"] is None:
        req.pop("lyrics")
    return _submit(req, cid)


@app.get("/v1/songs/{job_id}", response_model=JobOut)
def get_song(job_id: str):
    job = job_get(job_id)
    if not job:
        raise HTTPException(404, "song not found")
    return _public(job)


@app.post("/v1/songs/{job_id}/remix", response_model=JobOut, status_code=202)
def remix(job_id: str, body: RemixRequest, cid: str = Depends(client_id)):
    job = job_get(job_id)
    if not job or not job.get("lyrics"):
        raise HTTPException(404, "original song (with lyrics) not found")
    req = dict(job["request"])
    req["lyrics"] = {k: v for k, v in job["lyrics"].items() if k in ("title", "sections")}
    for k, v in body.model_dump().items():
        if v is not None:
            req[k] = v
    if body.seed is None:
        req["seed"] = None
    return _submit(req, cid)


@app.get("/v1/songs/{job_id}/events")
async def song_events(job_id: str):
    """Server-Sent Events stream of job updates (simpler for the app than polling)."""
    async def gen():
        last = None
        for _ in range(900):                        # max ~15 min
            job = job_get(job_id)
            if not job:
                yield "event: error\ndata: {\"error\": \"not found\"}\n\n"
                return
            payload = _public(job).model_dump_json()
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            if job.get("status") in ("done", "failed"):
                return
            await asyncio.sleep(1)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
