import numpy as np
from scipy.signal import resample
from app.pipeline.duration_transfer import SampleSpan, transfer_spans

def _tone_sequence(sr=16000):
    parts=[]; spans=[]; pos=0
    for f,d in [(180,.18),(260,.22),(340,.20),(230,.24)]:
        n=int(sr*d); t=np.arange(n)/sr; y=(.7*np.sin(2*np.pi*f*t)+.2*np.sin(2*np.pi*(f*2.1)*t)).astype(np.float32); a=pos; b=pos+n
        spans.append(SampleSpan(a,a+int(.03*sr),b-int(.025*sr),b)); parts.append(y); pos=b
    return np.concatenate(parts),spans

def test_duration_transfer_median_boundary_error_under_30ms():
    sr=16000; x,spans=_tone_sequence(sr); y=resample(x,int(len(x)*1.28)).astype(np.float32); mapped=transfer_spans(x,sr,y,sr,spans)
    expected=[SampleSpan(*[int(v*1.28) for v in (s.start,s.v_start,s.v_end,s.end)]) for s in spans]; errors=[]
    for a,b in zip(mapped,expected): errors.extend(abs(getattr(a,k)-getattr(b,k))/sr*1000 for k in ('start','v_start','v_end','end'))
    assert float(np.median(errors))<30.0
