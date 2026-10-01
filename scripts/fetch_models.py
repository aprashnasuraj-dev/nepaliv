"""Download/verify model files from the user's shared Google Drive folder.

No model weights are committed to Git. On Windows the default destination is
%LOCALAPPDATA%\\NepaliSongGen\\models. Downloads support resume through HTTP Range.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime import default_models_dir

MANIFEST = ROOT / "models" / "manifest.json"
URL = "https://drive.usercontent.google.com/download?id={id}&export=download&confirm=t"


def sha256(path: Path, block: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def groups_for(profile: str) -> set[str]:
    if profile == "minimal": return {"piper"}
    if profile == "voices": return {"piper", "metadata"}
    if profile == "omnivoice": return {"omnivoice"}
    if profile == "all": return {"piper", "metadata", "omnivoice", "asr-metadata", "reference-audio"}
    raise ValueError(profile)


def _progress(name: str, done: int, total: int, started: float) -> None:
    pct = (done / total * 100) if total else 0
    rate = done / max(0.1, time.time() - started) / (1024 * 1024)
    print(f"\r{name}: {done/1048576:.1f}/{total/1048576:.1f} MiB {pct:5.1f}% {rate:.1f} MiB/s", end="", flush=True)


def download(file: dict, dest_root: Path, verify: bool = True) -> Path:
    dest = dest_root / file["name"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    expected_size = int(file.get("size") or 0)
    expected_hash = file.get("sha256")
    if dest.exists() and (not expected_size or dest.stat().st_size == expected_size):
        if not verify or not expected_hash or sha256(dest).lower() == expected_hash.lower():
            print(f"OK  {file['name']}")
            return dest
        dest.unlink()
    part = dest.with_suffix(dest.suffix + ".part")
    resume = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": "NepaliSongGen/0.6"}
    if resume: headers["Range"] = f"bytes={resume}-"
    req = urllib.request.Request(URL.format(id=file["id"]), headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416 and part.exists():
            part.replace(dest); return dest
        raise
    mode = "ab" if resume and getattr(resp, "status", 200) == 206 else "wb"
    if mode == "wb": resume = 0
    started = time.time(); done = resume
    with resp, part.open(mode) as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk: break
            out.write(chunk); done += len(chunk)
            if expected_size: _progress(file["name"], done, expected_size, started)
    print()
    if expected_size and part.stat().st_size != expected_size:
        raise RuntimeError(f"size mismatch for {file['name']}: {part.stat().st_size} != {expected_size}")
    part.replace(dest)
    digest = sha256(dest)
    if expected_hash and digest.lower() != expected_hash.lower():
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 mismatch for {file['name']}: {digest} != {expected_hash}")
    if not expected_hash:
        dest.with_suffix(dest.suffix + ".sha256").write_text(digest + "\n", encoding="ascii")
        print(f"SHA {file['name']}: {digest} (recorded locally; manifest had no upstream hash)")
    return dest


def selected_files(manifest: dict, profile: str) -> list[dict]:
    groups = groups_for(profile)
    files = [f for f in manifest["files"] if f.get("group") in groups]
    if profile == "all": files = [f for f in files if f.get("group") != "reference-audio"]
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", type=Path, default=default_models_dir())
    ap.add_argument("--profile", choices=["minimal", "voices", "omnivoice", "all"], default="voices")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args(); m = load_manifest(); args.dest.mkdir(parents=True, exist_ok=True)
    print(f"Models: {args.dest}")
    failures = []
    for f in selected_files(m, args.profile):
        try: download(f, args.dest, verify=not args.no_verify)
        except Exception as e:
            failures.append((f["name"], str(e))); print(f"FAILED {f['name']}: {e}", file=sys.stderr)
    if failures:
        for name, err in failures: print(f"- {name}: {err}")
        return 2
    return 0

if __name__ == "__main__": raise SystemExit(main())
