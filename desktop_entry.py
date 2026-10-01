"""PyInstaller-safe entry point for the Nepali Song Generator desktop app."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent; DESKTOP=ROOT/"desktop"
if str(DESKTOP) not in sys.path:sys.path.insert(0,str(DESKTOP))
from nsg_desktop.__main__ import main
if __name__=="__main__":raise SystemExit(main())
