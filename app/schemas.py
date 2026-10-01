from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LyricsSection(BaseModel):
    type: Literal["verse", "chorus"]
    lines: list[str] = Field(min_length=1, max_length=8)


class Lyrics(BaseModel):
    title: str = "मेरो गीत"
    sections: list[LyricsSection] = Field(min_length=1, max_length=6)


class SongRequest(BaseModel):
    prompt: str = Field("", max_length=400, description="Song idea in Nepali or English")
    occasion: str | None = Field(None, max_length=60)
    mood: str | None = Field(None, max_length=60)
    dedicate_to: str | None = Field(None, max_length=40, description="Name to weave into the chorus (Devanagari best)")
    style: str = "adhunik"
    voice: str | None = None
    length: Literal["short", "full"] = "short"
    lyrics: Lyrics | None = Field(None, description="Skip the LLM and sing these lyrics (edited preview)")
    seed: int | None = Field(None, ge=0, le=2**31 - 1)
    harmony: bool = True
    key_shift: int = Field(0, ge=-6, le=6)
    tempo_scale: float = Field(1.0, ge=0.75, le=1.3)

    @field_validator("prompt", "occasion", "mood", "dedicate_to")
    @classmethod
    def strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class LyricsRequest(BaseModel):
    prompt: str = Field("", max_length=400)
    occasion: str | None = None
    mood: str | None = None
    dedicate_to: str | None = None
    style: str = "adhunik"
    length: Literal["short", "full"] = "short"
    seed: int | None = None


class RemixRequest(BaseModel):
    style: str | None = None
    voice: str | None = None
    seed: int | None = None
    harmony: bool | None = None
    key_shift: int | None = None


class JobOut(BaseModel):
    id: str
    status: Literal["queued", "running", "done", "failed"]
    stage: str | None = None
    progress: int = 0
    title: str | None = None
    lyrics: dict | None = None
    karaoke: dict | None = None
    audio_url: str | None = None
    wav_url: str | None = None
    duration: float | None = None
    error: str | None = None
    queue_position: int | None = None
    request: dict | None = None
