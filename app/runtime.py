"""Small cross-platform runtime helpers used by both server and desktop modes."""
from __future__ import annotations

import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path


def is_windows() -> bool:
    return sys.platform == "win32"


def default_models_dir() -> Path:
    """Return the default external model directory without creating it.

    Model weights intentionally live outside the Git checkout on Windows.
    Other platforms keep the historical ./voices default for server/dev use.
    """
    if is_windows():
        root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return root / "NepaliSongGen" / "models"
    return Path("./voices")


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    """Resolve ffmpeg from imageio-ffmpeg, with PATH as a defensive fallback."""
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return str(Path(exe))
    except Exception:
        pass

    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    raise RuntimeError(
        "ffmpeg is unavailable. Install imageio-ffmpeg (included in requirements.txt) "
        "or put ffmpeg on PATH."
    )
