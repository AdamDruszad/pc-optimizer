# -*- mode: python ; coding: utf-8 -*-
#
# GameBooster v2.1 — PyInstaller .spec fájl
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

block_cipher = None

# ── Adatfájlok összegyűjtése ──────────────────────────────────

# customtkinter: témák (JSON) és fontok (OTF) szükségesek
# collect_data_files automatikusan megtalálja a package assets-eit
try:
    ctk_datas = collect_data_files("customtkinter")
except Exception:
    ctk_datas = []

# Az összes adat amit be kell csomagolni
datas = ctk_datas + [
    # (forrás, cél a bundle-ben)
    # Ha lenne ikon fájl:
    # ("assets/icon.ico", "assets"),
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
    "psutil._compat",

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

    # Saját modulok (biztosítjuk hogy bekerülnek)
    "gui.app",
    "gui.sparkline",
    "gui.app_paths",
    "modules.hardware_detector",
    "modules.hw_optimizer",
    "modules.profile_manager",
    "modules.registry_tweaks",
    "modules.registry_optimizer",
    "modules.windows_optimizer",
    "modules.ram_cleaner",
    "modules.monitor",
    "modules.igpu_monitor",
    "utils.state_manager",

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
]

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
    upx=True,                       # UPX tömörítés (ha telepítve van)
    console=False,                  # Nincs fekete CMD ablak
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,                 # ← FONTOS: automatikus admin UAC prompt
    uac_uiaccess=False,
    # icon="assets\\icon.ico",      # Ikon (ha van)
    version_info=None,
)

# ── COLLECT (onedir csomag) ───────────────────────────────────

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="GameBooster",             # dist\GameBooster\ mappa neve
)
