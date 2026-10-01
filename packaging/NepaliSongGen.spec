# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules
from pathlib import Path

# SPECPATH is the directory containing this .spec file (repo/packaging).
# Its parent is the repository root.
root = Path(SPECPATH).parent

datas = [(str(root / 'models' / 'manifest.json'), 'models')]
binaries = []
hiddenimports = ['scripts.fetch_models']
for pkg in ('piper', 'espeakng_loader', 'onnxruntime', 'imageio_ffmpeg', 'pedalboard', 'soundfile', 'mutagen'):
    try:
        d,b,h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass
hiddenimports += collect_submodules('PySide6')

a = Analysis(
    [str(root / 'desktop_entry.py')],
    pathex=[str(root), str(root / 'desktop')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'transformers', 'edge_tts'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NepaliSongGen',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='NepaliSongGen',
)
