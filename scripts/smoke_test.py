"""Offline end-to-end smoke test for both Piper voice families."""
from __future__ import annotations
import argparse, json, sys, time, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.config import get_settings
from app.kv import job_update
from app.pipeline.orchestrator import run_song_job

def run(voice: str, out: Path):
    req={"prompt":"आमाको माया","style":"adhunik","voice":voice,"length":"short","seed":83,"harmony":False,"key_shift":0,"tempo_scale":1.0,"keep_wav":True}
    jid=str(uuid.uuid4()); job_update(jid, status="queued", request=req, progress=0)
    t=time.perf_counter(); result=run_song_job(jid,req); dt=time.perf_counter()-t
    print(json.dumps({"voice":voice,"seconds":round(dt,3),"status":result.get("status"),"audio":result.get("audio_url"),"error":result.get("error")},ensure_ascii=False))
    if result.get("status") != "done": raise SystemExit(2)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--models',type=Path); args=ap.parse_args()
    if args.models:
        import os; os.environ['VOICES_DIR']=str(args.models); get_settings.cache_clear()
    s=get_settings(); print('models',s.voices_dir,'data',s.data_dir)
    for v in ('ne_NP-chitwan-medium','ne_NP-google-medium'): run(v,s.data_dir/'songs')
if __name__=='__main__': main()
