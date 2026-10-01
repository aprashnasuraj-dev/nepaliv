from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from mutagen.id3 import ID3

from app.pipeline.media import embed_cover_mp3, render_cover_video, validate_cover
from app.runtime import ffmpeg_exe


# Valid 1x1 RGBA PNG. Keep the fixture dependency-free so the runtime test does
# not rely on Pillow being installed by the application.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4kOL2HwAGfAKapVobZQAAAABJRU5ErkJggg=="
)


def _fixture_media(tmp_path: Path):
    cover = tmp_path / "cover.png"
    cover.write_bytes(PNG_1X1)
    wav = tmp_path / "tone.wav"
    sr = 22050
    t = np.arange(int(sr * .6), dtype=np.float32) / sr
    y = (.08 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(wav, y, sr, subtype="PCM_16")
    mp3 = tmp_path / "tone.mp3"
    subprocess.run(
        [ffmpeg_exe(), "-y", "-v", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "96k", str(mp3)],
        check=True,
    )
    return cover, mp3


def test_cover_validation_and_mp3_embedding(tmp_path):
    cover, mp3 = _fixture_media(tmp_path)
    assert validate_cover(cover) == cover.resolve()
    embed_cover_mp3(mp3, cover, "परीक्षण गीत")
    tags = ID3(mp3)
    assert tags.getall("APIC")
    assert str(tags.getall("TIT2")[0]) == "परीक्षण गीत"


def test_cover_video_export(tmp_path):
    cover, mp3 = _fixture_media(tmp_path)
    out = render_cover_video(mp3, tmp_path / "song.mp4", cover, size=(320, 180), audio_bitrate="96k")
    assert out.exists()
    assert out.stat().st_size > 2000
