"""Album-art embedding and robust MP4 cover-video export.

This module is intentionally independent of the Qt UI so the same media
finalisation can be reused by desktop, CLI and future API upload flows.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..runtime import ffmpeg_exe

_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_MAX_COVER_BYTES = 25 * 1024 * 1024


def validate_cover(path: str | Path | None) -> Path | None:
    if path in (None, ""):
        return None
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Cover image not found: {p}")
    if p.suffix.lower() not in _IMAGE_MIME:
        raise ValueError("Cover image must be JPG, JPEG, PNG or WEBP")
    if p.stat().st_size > _MAX_COVER_BYTES:
        raise ValueError("Cover image is larger than 25 MB")
    return p


def embed_cover_mp3(mp3_path: str | Path, cover_path: str | Path, title: str = "") -> Path:
    """Embed cover art and title in an existing MP3 using ID3/APIC."""
    from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TIT2

    mp3 = Path(mp3_path)
    cover = validate_cover(cover_path)
    if cover is None:
        return mp3
    try:
        tags = ID3(mp3)
    except ID3NoHeaderError:
        tags = ID3()
    tags.delall("APIC")
    tags.add(APIC(encoding=3, mime=_IMAGE_MIME[cover.suffix.lower()], type=3, desc="Cover", data=cover.read_bytes()))
    if title:
        tags.delall("TIT2")
        tags.add(TIT2(encoding=3, text=title))
    tags.save(mp3, v2_version=3)
    return mp3


def render_cover_video(
    audio_path: str | Path,
    out_path: str | Path,
    cover_path: str | Path | None = None,
    size: tuple[int, int] = (1280, 720),
    audio_bitrate: str = "192k",
) -> Path:
    """Create an H.264/AAC MP4 from a song and optional still cover.

    If no cover is supplied, a dark neutral canvas is used. The filter keeps
    the complete cover visible, letterboxing as necessary, so portrait artwork
    is never cropped unexpectedly.
    """
    audio = Path(audio_path).resolve()
    if not audio.is_file():
        raise FileNotFoundError(f"Audio not found: {audio}")
    out = Path(out_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    cover = validate_cover(cover_path)
    w, h = size
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p"
    )
    cmd = [ffmpeg_exe(), "-y", "-v", "error"]
    if cover is not None:
        cmd += ["-loop", "1", "-framerate", "30", "-i", str(cover)]
    else:
        cmd += ["-f", "lavfi", "-i", f"color=c=0x101820:s={w}x{h}:r=30"]
    cmd += [
        "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", audio_bitrate,
        "-pix_fmt", "yuv420p", "-shortest", "-movflags", "+faststart",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode:
        detail = (proc.stderr or proc.stdout or "ffmpeg failed")[-2500:]
        raise RuntimeError(f"Video export failed: {detail.strip()}")
    if not out.is_file() or out.stat().st_size < 1024:
        raise RuntimeError("Video export produced no usable MP4")
    return out
