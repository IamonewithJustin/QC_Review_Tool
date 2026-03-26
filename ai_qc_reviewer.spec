# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir bundle: run `pyinstaller ai_qc_reviewer.spec` from project root."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas, binaries, hiddenimports = collect_all("customtkinter")
# Double-click launcher next to the exe for users who prefer .bat over .exe
try:
    _spec_root = Path(SPECPATH).parent
except NameError:
    try:
        _spec_root = Path(__file__).resolve().parent
    except NameError:
        _spec_root = Path(".").resolve()
_launcher = _spec_root / "Start AI QC Reviewer.bat"
if _launcher.is_file():
    datas = datas + [(str(_launcher), ".")]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports
    + [
        "pdfplumber",
        "pdfminer",
        "pdfminer.six",
        "pdfminer.high_level",
        "docx",
        "docx.opc",
        "docx.oxml",
        "lxml",
        "lxml.etree",
        "PIL",
        "certifi",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AI_QC_Document_Reviewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AI_QC_Document_Reviewer",
)
