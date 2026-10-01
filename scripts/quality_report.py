"""Measured quality report for installed Piper voices.

Run locally or in the Windows release workflow after downloading models. Unit CI
does not need weights. Exit status is non-zero when objective gates regress.
Human listening word accuracy is intentionally separate because a native speaker
must type what they heard in the Diagnostics tab.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.config import get_settings
from app.pipeline.composer import MelodyComposer
from app.pipeline.line_singer import DurationTTS, SENTINEL, segment
from app.pipeline.lyrics import BANK
from app.pipeline.nepali_text import normalize, syllabify_word
from app.pipeline.user_lexicon import tts_text_for_line
from app.pipeline.orchestrator import performance_order
from app.pipeline.singer import Singer
from app.pipeline.styles import get_style
from app.pipeline.tts import get_voice


def template_lines() -> list[str]:
    out=[]
    for bank in BANK.values():
        for lines in bank.values():
            for x in lines:
                x=x.replace('{name}','माया').strip()
                if x and x not in out: out.append(x)
    return out


def word_counts(line: str) -> list[int]:
    return [len(syllabify_word(w)) for w in normalize(line).split()]


def frame_silence_ratio(y: np.ndarray, sr: int) -> float:
    hop=max(1,int(.01*sr)); n=len(y)//hop
    if not n: return 1.0
    rms=np.sqrt(np.mean(y[:n*hop].reshape(n,hop)**2,axis=1)+1e-12)
    mx=float(rms.max())+1e-12
    return float(np.mean(20*np.log10(rms/mx)<-45))


def cents_error_for_notes(vocal, sr, notes):
    import pyworld as pw
    errors=[]; within=[]
    for n in notes:
        if n.dur < .08: continue
        a=max(0,int((n.start+min(.04,n.dur*.15))*sr)); b=min(len(vocal),int((n.start+n.dur-min(.03,n.dur*.1))*sr))
        if b-a<int(.04*sr): continue
        x=np.asarray(vocal[a:b],np.float64)
        f0,t=pw.dio(x,sr,frame_period=5.0,f0_floor=60,f0_ceil=600); f0=pw.stonemask(x,f0,t,sr); v=f0[f0>0]
        if len(v)<2: continue
        target=440*2**((float(n.midi)-69)/12)
        err=float(abs(1200*math.log2(float(np.median(v))/target)))
        errors.append(err); within.append(err<=50)
    return errors,within


def note_energy_sd(vocal,sr,notes):
    vals=[]
    for n in notes:
        a=max(0,int((n.start+.05)*sr)); b=min(len(vocal),int((n.start+n.dur-.03)*sr))
        if b>a:
            rms=float(np.sqrt(np.mean(vocal[a:b]**2)+1e-12)); vals.append(20*np.log10(rms+1e-12))
    return float(np.std(vals)) if vals else float('nan')


def evaluate_voice(voice_id: str) -> dict:
    s=get_settings(); spec=get_voice(voice_id); dtts=DurationTTS.get(spec.model)
    lines=template_lines(); ok=0; tts_seconds=0.0; audio_seconds=0.0
    for line in lines:
        text=tts_text_for_line(line); counts=word_counts(line)
        t0=time.perf_counter(); audio,spans=dtts.speak(f"{text} {SENTINEL}",spec.speaker_id,1.05); tts_seconds+=time.perf_counter()-t0; audio_seconds+=len(audio)/dtts.sr
        segs=segment(spans,counts+[len(syllabify_word(SENTINEL))]); ok += int(segs is not None)

    lyrics={"title":"गुणस्तर परीक्षण","sections":[
        {"type":"verse","lines":[lines[0],lines[1],lines[2],lines[3]]},
        {"type":"chorus","lines":[lines[8],lines[9],lines[10],lines[11]]},
    ]}
    style=get_style('adhunik'); comp=MelodyComposer(style,83,center_midi=spec.center_midi,bpm=style.bpm); score=comp.compose(performance_order(lyrics,'short'))
    singer=Singer(spec,vibrato_cents=style.vibrato_cents,seed=83)
    t0=time.perf_counter(); vocal=singer.sing(score.vocal,score.total_dur,s.sample_rate); render=time.perf_counter()-t0
    errors,within=cents_error_for_notes(vocal,s.sample_rate,score.vocal)
    sil=[]
    for ln in score.lines:
        a=int(ln.start*s.sample_rate); b=min(len(vocal),int(ln.end*s.sample_rate)); sil.append(frame_silence_ratio(vocal[a:b],s.sample_rate))
    return {
        "voice":voice_id,"template_lines":len(lines),"segmentation_success_pct":100*ok/max(1,len(lines)),
        "plain_tts_rtf":tts_seconds/max(.001,audio_seconds),"song_duration_s":score.total_dur,"vocal_render_s":render,
        "vocal_rtf":render/max(.001,score.total_dur),"pitch_within_50c_pct":100*sum(within)/max(1,len(within)),
        "pitch_median_cents":float(np.median(errors)) if errors else None,"silence_inside_lines_pct":100*float(np.mean(sil)) if sil else None,
        "note_rms_sd_db":note_energy_sd(vocal,s.sample_rate,score.vocal),"notes_measured":len(errors),
    }


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--models',type=Path); ap.add_argument('--out',type=Path,default=ROOT/'docs'/'QUALITY.md'); ap.add_argument('--json',type=Path,default=ROOT/'docs'/'quality.json'); args=ap.parse_args()
    if args.models:
        os.environ['VOICES_DIR']=str(args.models); get_settings.cache_clear()
    results=[]
    for v in ('ne_NP-chitwan-medium','ne_NP-google-medium'): results.append(evaluate_voice(v))
    args.json.parent.mkdir(parents=True,exist_ok=True); args.json.write_text(json.dumps({"host":platform.platform(),"python":platform.python_version(),"results":results},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Quality report','',f'Host: `{platform.platform()}` · Python `{platform.python_version()}`','',
           '| Voice | Segmentation | Pitch ≤50c | Silence in lines | TTS RTF | Vocal RTF | Median pitch error | Note RMS SD |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in results:
        lines.append(f"| {r['voice']} | {r['segmentation_success_pct']:.1f}% | {r['pitch_within_50c_pct']:.1f}% | {r['silence_inside_lines_pct']:.2f}% | {r['plain_tts_rtf']:.3f} | {r['vocal_rtf']:.3f} | {r['pitch_median_cents']:.1f}c | {r['note_rms_sd_db']:.2f} dB |")
    lines += ['', '## Human intelligibility gate', '', 'Objective metrics cannot establish whether a Nepali listener understands the words. The Diagnostics tab runs blinded A/B tests and logs typed/listener feedback. Release target: spoken word accuracy ≥80%; sung word accuracy ≥60%. These numbers must be entered from native-speaker listening tests and are not fabricated by this script.', '']
    args.out.write_text('\n'.join(lines),encoding='utf-8'); print('\n'.join(lines))
    failed=[]
    for r in results:
        if r['segmentation_success_pct']<95: failed.append(f"{r['voice']} segmentation")
        if r['pitch_within_50c_pct']<95: failed.append(f"{r['voice']} pitch")
        if r['silence_inside_lines_pct']>2: failed.append(f"{r['voice']} silence")
    if failed:
        print('QUALITY GATE FAILED:',', '.join(failed),file=sys.stderr); return 2
    return 0
if __name__=='__main__': raise SystemExit(main())
