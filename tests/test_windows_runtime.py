from pathlib import Path

import app.jobqueue as jobqueue
import app.runtime as runtime


def test_windows_default_models_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert runtime.default_models_dir() == tmp_path / "NepaliSongGen" / "models"


def test_windows_rq_falls_back_to_inline(monkeypatch):
    class Settings:
        redis_url = "redis://localhost:6379/0"

    monkeypatch.setattr(jobqueue.sys, "platform", "win32")
    monkeypatch.setattr(jobqueue, "get_settings", lambda: Settings())
    monkeypatch.setattr(jobqueue, "_warned_windows_redis", False)
    assert jobqueue._use_redis_queue() is False
    assert jobqueue.queue_position("anything") is None
