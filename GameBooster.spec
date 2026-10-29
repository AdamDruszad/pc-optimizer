# -*- mode: python ; coding: utf-8 -*-
#
# GameBooster v3 — PyInstaller .spec fájl
#
# Használat:
#   pyinstaller GameBooster.spec
#
# Vagy a build.bat szkripttel (ajánlott):
#   build.bat
#
# Kimenet: dist\GameBooster\GameBooster.exe
#
# ─────────────────────────────────────────────────────────────
# MEGJEGYZÉSEK:
#   - onedir mód (nem onefile): gyorsabb indítás, nincs temp kicsomagolás
#   - uac_admin=True: Windows automatikusan kér admin jogot indításkor
#   - console=False: nincs fekete CMD ablak
#   - A customtkinter assets (témák, fontok) manuálisan be kell másolni
# ─────────────────────────────────────────────────────────────

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

block_cipher = None

# ── Verzióinformáció (Fájl tulajdonságai → Részletek) ─────────
# Egy forrásból, a gamebooster.__version__-ből: a kiadás és az exe verziója mindig egyezik
sys.path.insert(0, SPECPATH)
from gamebooster import __version__ as APP_VERSION  # noqa: E402

_numeric = tuple(int(p) for p in APP_VERSION.split(".")) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_numeric, prodvers=_numeric),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "AdamDruszad"),
            StringStruct("FileDescription", "GameBooster"),
            StringStruct("FileVersion", APP_VERSION),
            StringStruct("InternalName", "GameBooster"),
            StringStruct("LegalCopyright", "MIT License"),
            StringStruct("OriginalFilename", "GameBooster.exe"),
            StringStruct("ProductName", "GameBooster"),
            StringStruct("ProductVersion", APP_VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

# ── Adatfájlok összegyűjtése ──────────────────────────────────

# customtkinter: témák (JSON) és fontok (OTF) szükségesek
# collect_data_files automatikusan megtalálja a package assets-eit
try:
    ctk_datas = collect_data_files("customtkinter")
except Exception:
    ctk_datas = []

# Az összes adat amit be kell csomagolni
datas = ctk_datas + [
    ("assets/icon.ico", "assets"),  # az ablak címsor-ikonjához
]

# ── Hidden imports ────────────────────────────────────────────
# Ezek a modulok futásidőben töltődnek be, PyInstaller nem találja meg
# statikus elemzéssel

hidden_imports = [
    # customtkinter belső moduljai
    "customtkinter",
    "customtkinter.windows",
    "customtkinter.windows.widgets",
    "customtkinter.windows.widgets.theme",
    "customtkinter.windows.ctk_tk",

    # psutil Windows-specifikus moduljai
    "psutil",
    "psutil._pswindows",
    "psutil._common",
    "psutil._psutil_windows",

    # Windows API
    "winreg",
    "ctypes",
    "ctypes.wintypes",

    # tkinter teljes csomag
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "tkinter.filedialog",
    "tkinter.simpledialog",

    # Egyéb stdlib
    "json",
    "subprocess",
    "threading",
    "collections",
    "dataclasses",
    "enum",
    "re",
    "platform",
    "logging",
    "logging.handlers",
] + collect_submodules("gamebooster")  # saját csomag: az oldalak lusta betöltése miatt is

# ── Analysis ──────────────────────────────────────────────────

a = Analysis(
    ["main.py"],                    # Belépési pont
    pathex=["."],                   # Keresési útvonal (projekt gyökér)
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=["."],                # Saját hook fájlok helye (ha van)
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Nem kell becsomgolni — csökkenti a méretet
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "PIL",
        "cv2",
        "PyQt5",
        "PyQt6",
        "wx",
        "gtk",
        "IPython",
        "notebook",
        "sphinx",
        "pytest",
        "setuptools",
        "pkg_resources",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── PYZ (Python zip archívum) ─────────────────────────────────

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# ── EXE ──────────────────────────────────────────────────────

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # onedir mód
    name="GameBooster",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX-tömörített exe-t a vírusirtók gyakrabban gyanúsítanak
    console=False,                  # Nincs fekete CMD ablak
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,                 # ← FONTOS: automatikus admin UAC prompt
    uac_uiaccess=False,
    icon="assets/icon.ico",
    version=version_info,
)

# ── COLLECT (onedir csomag) ───────────────────────────────────

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GameBooster",             # dist\GameBooster\ mappa neve
)
