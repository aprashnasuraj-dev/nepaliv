"""Nepali speech engines. The singer only needs `synth(text) -> (audio, sr)`;
everything musical happens later in WORLD, so any TTS can be plugged in.

Engines (pick with TTS_ENGINE):
  piper  - DEFAULT. Piper ne_NP voice, ~15M-param VITS in ONNX, faster than
           real time on one CPU core, fully offline. Check the voice's
           MODEL_CARD for the training-data licence before commercial use.
  edge   - Microsoft Edge neural voices (ne-NP-HemkalaNeural / SagarNeural)
           via the unofficial `edge-tts` package. Best quality, but needs
           internet and is NOT an officially licensed API - treat as a
           prototype/fallback, not something to build a business on.
  mms    - Meta MMS-TTS `facebook/mms-tts-npi` via transformers + torch CPU.
           Good Nepali, ~1 GB of deps, licence CC-BY-NC 4.0 (non-commercial!).
"""
from __future__ import annotations

import asyncio
import io
import subprocess
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import get_settings
from ..runtime import ffmpeg_exe


@dataclass(frozen=True)
class VoiceSpec:
    id: str
    engine: str
    model: str
    label: str
    gender: str
    center_midi: int          # comfortable singing centre; melody is transposed around it
    length_scale: float = 1.35  # slower speech -> longer vowels -> cleaner stretching
    speaker_id: int | None = None   # multi-speaker models (ne_NP-google has 18 speakers)


VOICES: dict[str, VoiceSpec] = {v.id: v for v in [
    # chitwan: 1 MALE speaker, 22 kHz, dataset CC0 -> the safest production voice. Speech F0 ~140 Hz.
    VoiceSpec("ne_NP-chitwan-medium", "piper", "ne_NP-chitwan-medium", "Chitwan (male)", "male", 53),
    # google: 18 FEMALE speakers (OpenSLR 43, CC-BY-SA-4.0), 22 kHz HF export. Speech F0 ~225-235 Hz.
    VoiceSpec("ne_NP-google-medium", "piper", "ne_NP-google-medium", "Google Nepali (female)", "female", 63, speaker_id=0),
    VoiceSpec("ne_NP-google-medium-s8", "piper", "ne_NP-google-medium", "Google Nepali, speaker 8", "female", 61, speaker_id=8),
    VoiceSpec("ne_NP-google-medium-s11", "piper", "ne_NP-google-medium", "Google Nepali, speaker 11", "female", 64, speaker_id=11),
    VoiceSpec("edge-hemkala", "edge", "ne-NP-HemkalaNeural", "Hemkala (Edge, online)", "female", 62),
    VoiceSpec("edge-sagar", "edge", "ne-NP-SagarNeural", "Sagar (Edge, online)", "male", 52),
    VoiceSpec("mms-npi", "mms", "facebook/mms-tts-npi", "Meta MMS Nepali (non-commercial)", "male", 52),
]}


def decode_audio_file(path: str | Path) -> tuple[np.ndarray, int]:
    """Decode anything ffmpeg understands to mono float32 @ 22050 Hz."""
    sr = 22050
    raw = subprocess.run(
        [ffmpeg_exe(), "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy(), sr


class TTSEngine:
    def synth(self, text: str) -> tuple[np.ndarray, int]:
        raise NotImplementedError


class PiperEngine(TTSEngine):
    def __init__(self, spec: VoiceSpec):
        from piper import PiperVoice  # lazy import: API process never needs it
        s = get_settings()
        model = s.voices_dir / f"{spec.model}.onnx"
        if not model.exists():
            raise FileNotFoundError(f"{model} missing - run `python scripts/download_voices.py`")
        self.voice = PiperVoice.load(str(model))
        self.spec = spec
        self._lock = threading.Lock()      # onnxruntime session is not re-entrant-safe for our use
        # The 2023 ne_NP-google export has no nasal-vowel phoneme (U+0303), so espeak's ũ/ɛ̃ from
        # chandrabindu would be dropped with a warning per call. We drop it up front (oral vowel).
        id_map = getattr(getattr(self.voice, "config", None), "phoneme_id_map", {}) or {}
        self.strip_chandrabindu = "\u0303" not in id_map

    def synth(self, text: str) -> tuple[np.ndarray, int]:
        if getattr(self, "strip_chandrabindu", False):
            text = text.replace("\u0901", "")
        buf = io.BytesIO()
        with self._lock, wave.open(buf, "wb") as wf:
            if hasattr(self.voice, "synthesize_wav"):          # piper-tts >= 1.3
                try:
                    from piper import SynthesisConfig
                    cfg = SynthesisConfig(length_scale=self.spec.length_scale, speaker_id=self.spec.speaker_id)
                    self.voice.synthesize_wav(text, wf, syn_config=cfg)
                except ImportError:
                    self.voice.synthesize_wav(text, wf)
            else:                                               # piper-tts 1.2.x
                self.voice.synthesize(text, wf, length_scale=self.spec.length_scale, speaker_id=self.spec.speaker_id)
        buf.seek(0)
        with wave.open(buf, "rb") as rf:
            sr = rf.getframerate()
            pcm = np.frombuffer(rf.readframes(rf.getnframes()), dtype=np.int16)
        return pcm.astype(np.float32) / 32768.0, sr


class EdgeEngine(TTSEngine):
    def __init__(self, spec: VoiceSpec):
        import edge_tts  # noqa: F401
        self.spec = spec

    def synth(self, text: str) -> tuple[np.ndarray, int]:
        import edge_tts

        async def _run(path: str):
            await edge_tts.Communicate(text, self.spec.model, rate="-25%").save(path)

        # Windows locks NamedTemporaryFile while it is open. Close the file
        # descriptor before edge-tts/ffmpeg reopen it, then clean up explicitly.
        fd, tmp_name = tempfile.mkstemp(suffix=".mp3")
        import os
        os.close(fd)
        try:
            asyncio.run(_run(tmp_name))
            return decode_audio_file(tmp_name)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass


class MMSEngine(TTSEngine):
    def __init__(self, spec: VoiceSpec):
        import torch
        from transformers import AutoTokenizer, VitsModel
        torch.set_num_threads(get_settings().tts_threads)
        self.tok = AutoTokenizer.from_pretrained(spec.model)
        self.model = VitsModel.from_pretrained(spec.model).eval()
        self.model.speaking_rate = 1.0 / spec.length_scale
        self.spec = spec
        self._lock = threading.Lock()

    def synth(self, text: str) -> tuple[np.ndarray, int]:
        import torch
        with self._lock, torch.no_grad():
            inputs = self.tok(text, return_tensors="pt")
            wav = self.model(**inputs).waveform[0].numpy().astype(np.float32)
        return wav, self.model.config.sampling_rate


_ENGINES: dict[str, TTSEngine] = {}
_ENGINES_LOCK = threading.Lock()


def get_voice(voice_id: str | None) -> VoiceSpec:
    return VOICES.get(voice_id or "") or VOICES[get_settings().default_voice]


def get_engine(spec: VoiceSpec) -> TTSEngine:
    with _ENGINES_LOCK:
        if spec.id not in _ENGINES:
            cls = {"piper": PiperEngine, "edge": EdgeEngine, "mms": MMSEngine}[spec.engine]
            if spec.engine == "piper":            # share one ONNX session across speakers of a model
                shared = next((e for e in _ENGINES.values()
                               if isinstance(e, PiperEngine) and e.spec.model == spec.model), None)
                if shared:
                    eng = PiperEngine.__new__(PiperEngine)
                    eng.voice, eng._lock, eng.spec = shared.voice, shared._lock, spec
                    eng.strip_chandrabindu = shared.strip_chandrabindu
                    _ENGINES[spec.id] = eng
                    return eng
            _ENGINES[spec.id] = cls(spec)
        return _ENGINES[spec.id]
