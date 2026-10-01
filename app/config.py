"""Central configuration. Every knob is an env var so the same image runs
locally, on a free VM, or on a Hugging Face Space without code changes."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from .runtime import default_models_dir


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- general ----
    app_env: str = "dev"
    data_dir: Path = Path("./data")            # caches, voicebank, local songs
    voices_dir: Path = default_models_dir()    # Piper/voice models; LocalAppData on Windows
    assets_dir: Path = Path("./assets")        # optional samples / soundfont
    public_base_url: str = "http://localhost:8000"
    api_keys: str = ""                         # comma separated; empty = open API (dev only)
    cors_origins: str = "*"

    # ---- queue ----
    redis_url: str = ""                        # empty => in-process thread queue (single box)
    inline_workers: int = 1                    # threads when redis_url is empty
    job_timeout_s: int = 600
    rate_limit_per_hour: int = 10              # songs per api key / IP

    # ---- storage ----
    storage_backend: str = "local"             # local | s3  (s3 also covers Cloudflare R2)
    s3_bucket: str = ""
    s3_endpoint_url: str = ""                  # R2: https://<account>.r2.cloudflarestorage.com
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "auto"
    s3_public_base_url: str = ""               # e.g. https://songs.yourdomain.com (R2 custom domain)
    signed_url_ttl_s: int = 7 * 24 * 3600

    # ---- lyrics LLM chain (OpenAI-compatible endpoints, tried in order) ----
    llm_providers: str = "gemini,groq,openrouter,local"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    local_llm_base_url: str = ""               # llama.cpp server, e.g. http://llm:8080/v1
    local_llm_model: str = "qwen2.5-7b-instruct"
    llm_timeout_s: int = 60

    # ---- voice ----
    tts_engine: str = "piper"                  # piper | edge | mms
    default_voice: str = "ne_NP-chitwan-medium"
    tts_threads: int = 2

    # ---- audio ----
    sample_rate: int = 44100
    mp3_bitrate: str = "160k"
    soundfont_path: str = ""                   # optional .sf2 -> FluidSynth backing (better instruments)

    @property
    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.data_dir, s.data_dir / "songs", s.data_dir / "voicebank",
              s.data_dir / "backing", s.voices_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s
