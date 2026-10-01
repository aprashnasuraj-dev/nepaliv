"""Download Piper Nepali voice models into VOICES_DIR.

    python scripts/download_voices.py                 # chitwan (male, CC0) + google (female)
    python scripts/download_voices.py ne_NP-chitwan-medium

Read the MODEL_CARD next to each voice on Hugging Face for the dataset
licence before shipping commercially.
"""
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings  # noqa: E402

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
# Fallback for google only: the original Piper GitHub release (older 2023 export: 16 kHz, no nasal
# vowels). Prefer the Hugging Face files. chitwan exists only on Hugging Face.
GH = "https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-{short}.tar.gz"


def url_for(name: str) -> str:
    lang, dataset, quality = name.split("-", 2)          # ne_NP-google-medium
    family = lang.split("_")[0]
    return f"{BASE}/{family}/{lang}/{dataset}/{quality}/{name}"


def from_github(name: str, out: Path) -> None:
    # ne_NP-google-medium -> ne-google-medium ; ne_NP-google-x_low -> ne-google-x-low
    lang, dataset, quality = name.split("-", 2)
    short = f"{lang.split('_')[0]}-{dataset}-{quality.replace('_', '-')}"
    u = GH.format(short=short)
    print("falling back to", u)
    with tempfile.TemporaryDirectory() as d:
        tgz = Path(d) / "v.tar.gz"
        urllib.request.urlretrieve(u, tgz)
        with tarfile.open(tgz) as tf:
            tf.extractall(d)
        for ext in (".onnx", ".onnx.json"):
            src = next(Path(d).glob(f"*{ext}"))
            (out / f"{name}{ext}").write_bytes(src.read_bytes())


def main(names):
    out = get_settings().voices_dir
    out.mkdir(parents=True, exist_ok=True)
    for name in names:
        if all((out / f"{name}{e}").exists() for e in (".onnx", ".onnx.json")):
            print("exists", name)
            continue
        try:
            for ext in (".onnx", ".onnx.json"):
                u = url_for(name) + ext
                print("downloading", u)
                urllib.request.urlretrieve(u, out / f"{name}{ext}")
        except Exception as e:
            print("Hugging Face download failed:", e)
            from_github(name, out)
    print("done ->", out)


if __name__ == "__main__":
    main(sys.argv[1:] or ["ne_NP-chitwan-medium", "ne_NP-google-medium"])
