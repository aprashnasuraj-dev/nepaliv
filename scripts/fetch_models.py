#!/usr/bin/env python3
"""Download model assets from the shared Google Drive manifest.

Supports resume, progress, size validation and SHA-256 verification. Re-running
is idempotent: verified files are skipped and partial downloads continue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime import default_models_dir  # noqa: E402

MANIFEST = ROOT / "models" / "manifest.json"
URL = "https://drive.usercontent.google.com/download?id={id}&export=download&confirm=t"
CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def verify(path: Path, item: dict) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    expected_size = int(item["size"])
    if path.stat().st_size != expected_size:
        return False, f"size {path.stat().st_size:,} != {expected_size:,}"
    digest = sha256_file(path)
    if digest.lower() != item["sha256"].lower():
        return False, f"sha256 {digest} != {item['sha256']}"
    return True, digest


def download(client: httpx.Client, item: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    existing = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={existing}-"} if existing else {}
    mode = "ab" if existing else "wb"
    started = time.perf_counter()

    with client.stream("GET", URL.format(id=item["drive_id"]), headers=headers) as r:
        r.raise_for_status()
        # Some hosts ignore Range; restarting prevents duplicated bytes.
        if existing and r.status_code != 206:
            existing = 0
            mode = "wb"
        total = int(item["size"])
        done = existing
        with part.open(mode) as f:
            for chunk in r.iter_bytes(CHUNK):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                elapsed = max(0.001, time.perf_counter() - started)
                speed = max(0.0, (done - existing) / elapsed / (1024 * 1024))
                pct = min(100.0, 100.0 * done / total)
                print(f"\r  {pct:6.2f}%  {done/1048576:8.1f}/{total/1048576:8.1f} MiB  {speed:5.1f} MiB/s", end="", flush=True)
    print()
    os.replace(part, dest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-dir", type=Path, default=default_models_dir())
    ap.add_argument("--group", default="piper", help="manifest group to download, or 'all'")
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items = [x for x in manifest["files"] if args.group == "all" or x.get("group") == args.group]
    if not items:
        raise SystemExit(f"No manifest files found for group {args.group!r}")

    failures = 0
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60.0, read=300.0)) as client:
        for item in items:
            dest = args.models_dir / item.get("download_name", item["name"])
            ok, detail = verify(dest, item)
            if ok:
                print(f"OK   {item['name']}  {detail[:12]}…")
                continue
            if args.verify_only:
                print(f"FAIL {item['name']}: {detail}")
                failures += 1
                continue
            print(f"GET  {item['name']} ({int(item['size'])/1048576:.1f} MiB) [{detail}]")
            download(client, item, dest)
            ok, detail = verify(dest, item)
            if not ok:
                print(f"FAIL {item['name']}: {detail}")
                failures += 1
            else:
                print(f"OK   {item['name']}  {detail[:12]}…")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
