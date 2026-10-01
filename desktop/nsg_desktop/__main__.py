from __future__ import annotations
import os,sys

def _self_test()->int:
    from app.runtime import ffmpeg_exe,local_app_data
    from app.pipeline.nepali_text import romanize,syllabify_line
    from app.pipeline.media import render_cover_video, validate_cover
    sample="हिमालको हिउँजस्तै सेतो तिम्रो माया"; assert syllabify_line(sample); assert validate_cover(None) is None
    print("NepaliSongGen desktop self-test OK"); print("data:",local_app_data()); print("ffmpeg:",ffmpeg_exe()); print("roman:",romanize(sample)); print("media: cover + mp4 pipeline loaded"); return 0

def _apply_saved_settings():
    from PySide6.QtCore import QSettings
    q=QSettings("NepaliSongGen","NepaliSongGen"); mapping={"models_dir":"VOICES_DIR","data_dir":"DATA_DIR","threads":"TTS_THREADS","bitrate":"MP3_BITRATE","omnivoice_ref_audio":"OMNIVOICE_REF_AUDIO","omnivoice_ref_text":"OMNIVOICE_REF_TEXT"}
    for key,env in mapping.items():
        v=q.value(key)
        if v not in (None,""):os.environ[env]=str(v)
    try:
        import keyring
        for env in ("GEMINI_API_KEY","GROQ_API_KEY","OPENROUTER_API_KEY"):
            v=keyring.get_password("NepaliSongGen",env)
            if v:os.environ[env]=v
    except Exception:pass

def main()->int:
    if "--self-test" in sys.argv:return _self_test()
    os.environ.setdefault("PYTHONUTF8","1"); _apply_saved_settings()
    from PySide6.QtWidgets import QApplication
    from app.runtime import setup_logging
    setup_logging()
    from .media_ui import EnhancedMainWindow
    app=QApplication(sys.argv); app.setApplicationName("Nepali Song Generator"); app.setOrganizationName("NepaliSongGen"); w=EnhancedMainWindow(); w.show(); return app.exec()
if __name__=="__main__":raise SystemExit(main())
