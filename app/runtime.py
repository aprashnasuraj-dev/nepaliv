"""Runtime helpers shared by the API, desktop app and packaging.

Keep OS-specific behavior here so the audio pipeline remains portable.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import tempfile
from pathlib import Path

APP_NAME = "NepaliSongGen"


def is_windows() -> bool:
    return sys.platform.startswith("win")


def local_app_data() -> Path:
    if is_windows():
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_NAME


def default_data_dir() -> Path:
    return local_app_data() / "data" if is_windows() else Path("./data")


def default_models_dir() -> Path:
    return local_app_data() / "models" if is_windows() else Path("./voices")


def default_logs_dir() -> Path:
    return local_app_data() / "logs"


def ffmpeg_exe() -> str:
    """Return a bundled ffmpeg executable when available, otherwise PATH ffmpeg."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg.exe" if is_windows() else "ffmpeg"


def temp_path(suffix: str = "") -> Path:
    """Create a closed temp file so Windows processes may reopen it."""
    fd, name = tempfile.mkstemp(suffix=suffix, prefix="nsg_")
    os.close(fd)
    return Path(name)


def setup_logging(level: int = logging.INFO) -> Path:
    d = default_logs_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / "nepali-song-gen.log"
    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        fh = logging.handlers.RotatingFileHandler(path, maxBytes=3_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(fh)
    return path
