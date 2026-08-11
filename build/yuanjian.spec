# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path(SPEC).parent.parent
source_root = project_root / "src"
static_root = source_root / "yuanjian_app" / "static"

a = Analysis(
    [str(project_root / "build" / "windows_entry.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=[(str(static_root), "yuanjian_app/static")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YuanJian",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="YuanJian",
)
