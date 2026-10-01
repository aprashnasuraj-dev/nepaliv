"""Nepali speech engines. Any engine implements synth(text) -> (audio, sr)."""
from __future__ import annotations
import asyncio, io, subprocess, threading, wave
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from ..config import get_settings
from ..runtime import ffmpeg_exe, temp_path

@dataclass(frozen=True)
class VoiceSpec:
    id: str; engine: str; model: str; label: str; gender: str; center_midi: int
    length_scale: float = 1.35
    speaker_id: int | None = None
    license: str = ""
    experimental: bool = False

VOICES: dict[str, VoiceSpec] = {v.id:v for v in [
    VoiceSpec("ne_NP-chitwan-medium","piper","ne_NP-chitwan-medium","Chitwan (male)","male",53,license="CC0"),
    VoiceSpec("ne_NP-google-medium","piper","ne_NP-google-medium","Google Nepali (female)","female",63,speaker_id=0,license="CC-BY-SA-4.0"),
    VoiceSpec("ne_NP-google-medium-s8","piper","ne_NP-google-medium","Google Nepali, speaker 8","female",61,speaker_id=8,license="CC-BY-SA-4.0"),
    VoiceSpec("ne_NP-google-medium-s11","piper","ne_NP-google-medium","Google Nepali, speaker 11","female",64,speaker_id=11,license="CC-BY-SA-4.0"),
    VoiceSpec("edge-hemkala","edge","ne-NP-HemkalaNeural","Hemkala (Edge, online)","female",62,license="service terms"),
    VoiceSpec("edge-sagar","edge","ne-NP-SagarNeural","Sagar (Edge, online)","male",52,license="service terms"),
    VoiceSpec("mms-npi","mms","facebook/mms-tts-npi","Meta MMS Nepali (testing only)","male",52,license="CC-BY-NC-4.0",experimental=True),
    VoiceSpec("omnivoice-nepali-v2","omnivoice","omnivoice","OmniVoice Nepali HD (experimental)","clone",57,license="Apache-2.0 claim + decoder dependency review required",experimental=True),
]}

def decode_audio_file(path: str|Path)->tuple[np.ndarray,int]:
    sr=22050
    raw=subprocess.run([ffmpeg_exe(),"-v","error","-i",str(path),"-ac","1","-ar",str(sr),"-f","f32le","-"],check=True,capture_output=True).stdout
    return np.frombuffer(raw,dtype=np.float32).copy(),sr

class TTSEngine:
    def synth(self,text:str)->tuple[np.ndarray,int]: raise NotImplementedError

class PiperEngine(TTSEngine):
    def __init__(self,spec:VoiceSpec):
        from piper import PiperVoice
        model=get_settings().voices_dir/f"{spec.model}.onnx"
        if not model.exists(): raise FileNotFoundError(f"{model} missing - run `python scripts/fetch_models.py --profile voices`")
        self.voice=PiperVoice.load(str(model)); self.spec=spec; self._lock=threading.Lock()
        id_map=getattr(getattr(self.voice,"config",None),"phoneme_id_map",{}) or {}
        self.strip_chandrabindu="\u0303" not in id_map
    def synth(self,text:str)->tuple[np.ndarray,int]:
        if self.strip_chandrabindu: text=text.replace("\u0901","")
        buf=io.BytesIO()
        with self._lock,wave.open(buf,"wb") as wf:
            if hasattr(self.voice,"synthesize_wav"):
                from piper import SynthesisConfig
                self.voice.synthesize_wav(text,wf,syn_config=SynthesisConfig(length_scale=self.spec.length_scale,speaker_id=self.spec.speaker_id))
            else:
                self.voice.synthesize(text,wf,length_scale=self.spec.length_scale,speaker_id=self.spec.speaker_id)
        buf.seek(0)
        with wave.open(buf,"rb") as rf:
            sr=rf.getframerate(); pcm=np.frombuffer(rf.readframes(rf.getnframes()),dtype=np.int16)
        return pcm.astype(np.float32)/32768.0,sr

class EdgeEngine(TTSEngine):
    def __init__(self,spec): import edge_tts; self.spec=spec
    def synth(self,text):
        import edge_tts
        async def _run(path): await edge_tts.Communicate(text,self.spec.model,rate="-25%").save(path)
        tmp=temp_path(".mp3")
        try: asyncio.run(_run(str(tmp))); return decode_audio_file(tmp)
        finally: tmp.unlink(missing_ok=True)

class MMSEngine(TTSEngine):
    def __init__(self,spec):
        import torch
        from transformers import AutoTokenizer,VitsModel
        torch.set_num_threads(get_settings().tts_threads); self.tok=AutoTokenizer.from_pretrained(spec.model); self.model=VitsModel.from_pretrained(spec.model).eval(); self.model.speaking_rate=1.0/spec.length_scale; self.spec=spec; self._lock=threading.Lock()
    def synth(self,text):
        import torch
        with self._lock,torch.no_grad(): wav=self.model(**self.tok(text,return_tensors="pt")).waveform[0].numpy().astype(np.float32)
        return wav,self.model.config.sampling_rate

class OmniVoiceEngine(TTSEngine):
    def __init__(self,spec):
        import torch
        try: from omnivoice import OmniVoice
        except Exception as e: raise RuntimeError("OmniVoice runtime is not installed; install the optional HD voice pack") from e
        s=get_settings(); root=s.voices_dir/"omnivoice"; model=root/"model.safetensors"; config=root/"config.json"; tok=root/"audio_tokenizer"/"model.safetensors"
        if not model.exists() or not config.exists(): raise FileNotFoundError(f"incomplete OmniVoice pack under {root}")
        if not tok.exists(): raise RuntimeError("OmniVoice experimental pack is missing audio_tokenizer/model.safetensors; HD voice stays disabled")
        ref=Path(s.omnivoice_ref_audio) if s.omnivoice_ref_audio else None
        if not ref or not ref.exists() or not s.omnivoice_ref_text.strip(): raise RuntimeError("OmniVoice requires a consented 3-10 s reference recording and matching reference text")
        torch.set_num_threads(max(1,s.tts_threads)); self.torch=torch; self.model=OmniVoice.from_pretrained(str(root),dtype=torch.float32,device_map="cpu").eval(); self.ref_audio=str(ref); self.ref_text=s.omnivoice_ref_text.strip(); self.steps=max(8,min(32,s.omnivoice_steps)); self.spec=spec; self._lock=threading.Lock()
    def synth(self,text):
        with self._lock,self.torch.inference_mode(): audio=self.model.generate(text=text,language="npi",ref_audio=self.ref_audio,ref_text=self.ref_text,num_step=self.steps,speed=1.0)
        if hasattr(audio,"__len__") and not isinstance(audio,np.ndarray): audio=audio[0]
        if hasattr(audio,"detach"): audio=audio.detach().float().cpu().numpy()
        return np.asarray(audio,dtype=np.float32).squeeze(),24000

_ENGINES={}; _ENGINES_LOCK=threading.Lock()
def get_voice(voice_id): return VOICES.get(voice_id or "") or VOICES[get_settings().default_voice]
def get_engine(spec):
    with _ENGINES_LOCK:
        if spec.id not in _ENGINES:
            cls={"piper":PiperEngine,"edge":EdgeEngine,"mms":MMSEngine,"omnivoice":OmniVoiceEngine}[spec.engine]
            if spec.engine=="piper":
                shared=next((e for e in _ENGINES.values() if isinstance(e,PiperEngine) and e.spec.model==spec.model),None)
                if shared:
                    eng=PiperEngine.__new__(PiperEngine); eng.voice,eng._lock,eng.spec=shared.voice,shared._lock,spec; eng.strip_chandrabindu=shared.strip_chandrabindu; _ENGINES[spec.id]=eng; return eng
            _ENGINES[spec.id]=cls(spec)
        return _ENGINES[spec.id]
