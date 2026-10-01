"""Duration transfer between two renditions of the same Nepali line.

Piper exposes phoneme durations. Heavy TTS engines usually do not. We align
short-time spectral features with monotonic DTW and map Piper's syllable spans
onto the target waveform. No ASR/aligner model is required.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.fft import dct

@dataclass(frozen=True)
class SampleSpan:
    start:int; v_start:int; v_end:int; end:int

def _frames(x:np.ndarray,sr:int,hop_ms:float=5.0,win_ms:float=25.0)->tuple[np.ndarray,int]:
    x=np.asarray(x,dtype=np.float32).reshape(-1); hop=max(1,int(round(sr*hop_ms/1000))); win=max(hop+1,int(round(sr*win_ms/1000)))
    if len(x)<win: x=np.pad(x,(0,win-len(x)))
    n=1+max(0,(len(x)-win)//hop); idx=np.arange(win)[None,:]+hop*np.arange(n)[:,None]
    fr=x[idx]*np.hanning(win)[None,:]; spec=np.abs(np.fft.rfft(fr,n=1<<int(np.ceil(np.log2(win))),axis=1))+1e-6
    feat=dct(np.log(spec),type=2,norm="ortho",axis=1)[:,:24]; feat-=feat.mean(axis=0,keepdims=True); feat/=feat.std(axis=0,keepdims=True)+1e-5
    return feat.astype(np.float32),hop

def dtw_path(a:np.ndarray,b:np.ndarray,band_ratio:float=0.35)->list[tuple[int,int]]:
    n,m=len(a),len(b)
    if not n or not m:return []
    inf=np.float32(1e30); cost=np.full((n+1,m+1),inf,dtype=np.float32); prev=np.zeros((n+1,m+1),dtype=np.uint8); cost[0,0]=0.0
    band=max(abs(n-m)+2,int(max(n,m)*band_ratio))
    for i in range(1,n+1):
        center=int(round(i*m/n)); j0,j1=max(1,center-band),min(m,center+band)
        for j in range(j0,j1+1):
            d=float(np.mean((a[i-1]-b[j-1])**2)); vals=(cost[i-1,j-1],cost[i-1,j],cost[i,j-1]); k=int(np.argmin(vals)); cost[i,j]=d+vals[k]; prev[i,j]=k
    i,j=n,m
    if not np.isfinite(cost[i,j]):return []
    path=[]
    while i>0 and j>0:
        path.append((i-1,j-1)); k=prev[i,j]
        if k==0:i-=1;j-=1
        elif k==1:i-=1
        else:j-=1
    path.reverse(); return path

def _map_frame(path,src_frame,target_len):
    if not path:return 0
    ys=[j for i,j in path if i==src_frame]
    if ys:return int(round(float(np.median(ys))))
    k=min(range(len(path)),key=lambda z:abs(path[z][0]-src_frame)); return int(np.clip(path[k][1],0,max(0,target_len-1)))

def transfer_spans(source_audio,source_sr,target_audio,target_sr,source_spans,hop_ms:float=5.0):
    af,ah=_frames(source_audio,source_sr,hop_ms); bf,bh=_frames(target_audio,target_sr,hop_ms); path=dtw_path(af,bf)
    if not path:raise ValueError("DTW alignment failed")
    def map_sample(s):
        sf=int(round(s/ah)); tf=_map_frame(path,int(np.clip(sf,0,len(af)-1)),len(bf)); return int(np.clip(tf*bh,0,len(target_audio)))
    out=[]; last=0
    for sp in source_spans:
        vals=[map_sample(sp.start),map_sample(sp.v_start),map_sample(sp.v_end),map_sample(sp.end)]; vals[0]=max(last,vals[0]); vals[1]=max(vals[0],vals[1]); vals[2]=max(vals[1]+1,vals[2]); vals[3]=max(vals[2],vals[3]); vals[3]=min(vals[3],len(target_audio)); vals[2]=min(vals[2],vals[3]); out.append(SampleSpan(*vals)); last=vals[3]
    return out
