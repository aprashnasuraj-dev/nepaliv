#!/usr/bin/env python3
"""Offline end-to-end smoke test for the two Piper Nepali voices."""
from __future__ import annotations

import argparse
import os
import platform
import sys
import time
import uuid
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Set safe local defaults before importing settings-backed pipeline modules.
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("DATA_DIR", str(ROOT / "data" / "smoke"))

from app.config import get_settings  # noqa: E402
from app.kv import job_get  # noqa: E402
from app.pipeline import orchestrator  # noqa: E402
from app.runtime import default_models_dir  # noqa: E402

VOICES = ("ne_NP-chitwan-medium", "ne_NP-google-medium")


def render_one(voice: str, length: str, seed: int) -> tuple[dict, OrderedDict[str, float]]:
    events: list[tuple[str, float]] = []
    original_update = orchestrator.job_update

    def timed_update(job_id: str, **fields):
        stage = fields.get("stage")
        if stage and (not events or events[-1][0] != stage):
            events.append((stage, time.perf_counter()))
        return original_update(job_id, **fields)

    orchestrator.job_update = timed_update
    job_id = f"smoke-{voice}-{uuid.uuid4().hex[:8]}"
    req = {
        "prompt": "दसैँमा घर फर्किँदाको खुसी",
        "style": "lok_dohori",
        "length": length,
        "dedicate_to": "आमा",
        "harmony": True,
        "voice": voice,
        "seed": seed,
        "tempo_scale": 1.0,
        "key_shift": 0,
        "keep_wav": True,
    }
    start = time.perf_counter()
    try:
        result = orchestrator.run_song_job(job_id, req)
    finally:
        orchestrator.job_update = original_update
    end = time.perf_counter()
    if result.get("status") != "done":
        raise RuntimeError(f"Smoke render failed for {voice}: {result.get('error') or result}")

    timings: OrderedDict[str, float] = OrderedDict()
    timeline = [("start", start)] + events + [("finished", end)]
    for (name, t0), (_, t1) in zip(timeline, timeline[1:]):
        timings[name] = timings.get(name, 0.0) + (t1 - t0)
    timings["total"] = end - start
    return result, timings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-dir", type=Path, default=default_models_dir())
    ap.add_argument("--length", choices=("short", "full"), default="short")
    ap.add_argument("--seed", type=int, default=20261001)
    args = ap.parse_args()
    os.environ["VOICES_DIR"] = str(args.models_dir)
    get_settings.cache_clear()

    print(f"Python: {sys.version.split()[0]} | OS: {platform.platform()} | CPU: {platform.processor() or 'unknown'}")
    print(f"Models: {args.models_dir}")
    for voice in VOICES:
        result, timings = render_one(voice, args.length, args.seed)
        print(f"\n[{voice}]")
        for stage, seconds in timings.items():
            print(f"  {stage:12s} {seconds:8.3f}s")
        data_root = get_settings().data_dir / "songs" / "songs"
        mp3 = data_root / f"{result['render_id']}.mp3"
        wav = data_root / f"{result['render_id']}.wav"
        print(f"  MP3: {mp3}")
        print(f"  WAV: {wav}")
        if not mp3.exists() or mp3.stat().st_size == 0:
            raise RuntimeError(f"Missing/empty MP3: {mp3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
