"""Create a local, measured model inventory."""
from __future__ import annotations
import argparse, json, os, platform, sys, time
from pathlib import Path
try:
    import resource
except ImportError:
    resource = None
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime import default_models_dir

def peak_mb() -> float:
    try:
        if resource is None: return 0.0
        v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return v / (1024 if sys.platform != "darwin" else 1024 * 1024)
    except Exception: return 0.0

def inspect_json(path: Path) -> dict:
    try: d=json.loads(path.read_text(encoding="utf-8"))
    except Exception as e: return {"error":str(e)}
    out={"model_type":d.get("model_type"),"architectures":d.get("architectures")}
    if "audio" in d:
        out["sample_rate"]=d["audio"].get("sample_rate"); out["num_speakers"]=d.get("num_speakers")
    if d.get("sample_rate"): out["sample_rate"]=d.get("sample_rate")
    if d.get("llm_config"):
        llm=d["llm_config"]; out["llm"]={k:llm.get(k) for k in ("model_type","hidden_size","num_hidden_layers","num_attention_heads")}
    return out

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--models",type=Path,default=default_models_dir()); ap.add_argument("--out",type=Path,default=ROOT/"docs"/"MODEL_REPORT.md"); args=ap.parse_args()
    manifest=json.loads((ROOT/"models"/"manifest.json").read_text(encoding="utf-8"))
    lines=["# Model report","",f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",f"Host: {platform.platform()} | Python {platform.python_version()} | CPU cores {os.cpu_count()}","","| Model/file | Present | Size MiB | Type / notes |","|---|---:|---:|---|"]
    for f in manifest["files"]:
        p=args.models/f["name"]; present=p.exists(); notes=f.get("license","")
        if present and p.suffix==".json" and p.stat().st_size<2_000_000: notes += "; "+json.dumps(inspect_json(p),ensure_ascii=False)
        lines.append(f"| `{f['name']}` | {'yes' if present else 'no'} | {int(f.get('size') or 0)/1048576:.1f} | {notes} |")
    lines += ["","## OmniVoice gate","","The shared folder describes OmniVoice Nepali v2 as a Qwen-conditioned flow-matching TTS checkpoint, but the folder inventory contains only the main ~2.03 GB checkpoint plus audio-tokenizer *configuration* files. The model card itself says an additional ~805 MB audio-tokenizer is required. Until the full decoder/tokenizer weights are available and CPU RTF is measured <= 3.0, the desktop app keeps OmniVoice behind an Experimental label and does not use it as the default voice.","",f"Peak process RAM during this metadata inventory: {peak_mb():.1f} MiB."]
    args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text("\n".join(lines)+"\n",encoding="utf-8"); print(args.out); return 0
if __name__=="__main__": raise SystemExit(main())
