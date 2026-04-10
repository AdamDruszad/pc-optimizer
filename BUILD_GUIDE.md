# GameBooster v2.1 — Build Útmutató / Build Guide

> **Magyar / English**

---

## 🇭🇺 Magyar

### Előfeltételek

| Szoftver | Verzió | Letöltés |
|---|---|---|
| Python | 3.11 vagy újabb | [python.org/downloads](https://python.org/downloads) |
| Windows | 10 (2004+) vagy 11 | — |

> ⚠ **Fontos Python telepítésnél:** pipáld be az **"Add Python to PATH"** opciót!

---

### Gyors build — egy kattintás

```
Dupla klikk: build.bat
```

A szkript elvégzi:
1. Python verzió ellenőrzés
2. Virtuális környezet (`.venv`) létrehozása
3. `customtkinter`, `psutil`, `pyinstaller` telepítése
4. Régi build törlése
5. PyInstaller fordítás
6. Eredmény ellenőrzése

**Kimenet:** `dist\GameBooster\GameBooster.exe`

---

### Kézi build (ha a .bat nem megy)

```cmd
:: Adminként futtatott PowerShell vagy CMD-ben:

cd C:\GameBooster

:: 1. Virtuális környezet
python -m venv .venv
.venv\Scripts\activate

:: 2. Telepítés
pip install customtkinter psutil pyinstaller

:: 3. Build
pyinstaller GameBooster.spec --noconfirm --clean
```

---

### A kimenet struktúrája

```
dist\
└── GameBooster\
    ├── GameBooster.exe        ← Ez az indítható fájl
    ├── _internal\             ← Python runtime + modulok
    │   ├── customtkinter\     ← GUI könyvtár + témák
    │   ├── psutil\            ← Rendszer monitoring
    │   ├── python3xx.dll      ← Python DLL
    │   └── ...egyéb DLL-ek
    └── (első indítás után):
        ├── gamebooster.log    ← Log fájl
        ├── profiles\          ← Mentett profilok
        └── registry_snapshot.json  ← Ha volt registry boost
```

> ⚠ **Terjesztéshez az egész `dist\GameBooster\` mappát** kell átadni, nem csak az `.exe`-t! A DLL-ek nélkül nem indul el.

---

### Admin jogok

A `GameBooster.spec`-ben az `uac_admin=True` beállítás miatt Windows **automatikusan kér admin jogot** indításkor (UAC prompt). Nem kell jobb klikk → "Futtatás rendszergazdaként".

---

### Build opciók

```cmd
build.bat              :: Teljes build (clean + install + compile)
build.bat --fast       :: Csak újrafordít (nem törli a régit, nem telepít)
build.bat --clean      :: Csak törli a régi build fájlokat
```

---

### Hibaelhárítás

**`ModuleNotFoundError: No module named 'customtkinter'`**
```cmd
.venv\Scripts\activate
pip install customtkinter psutil pyinstaller
pyinstaller GameBooster.spec --noconfirm
```

**`Failed to execute script main`** indításkor
```
Futtasd CMD-ből hogy lásd a hibaüzenetet:
dist\GameBooster\GameBooster.exe
```

**Az exe mérete túl nagy (>150MB)**
- Normális — a Python runtime ~60MB, a customtkinter ~30MB
- Ha csökkenteni akarod: `pip install pyinstaller[encrypt]` + UPX telepítés

**`Access is denied` a registrynél**
- Az .exe nem kapott admin jogot
- Ellenőrizd: `GameBooster.spec` → `uac_admin=True`

**customtkinter témák nem töltődnek be (szürke ablak)**
```cmd
:: Ellenőrizd hogy a collect_data_files fut a .spec-ben:
python -c "from PyInstaller.utils.hooks import collect_data_files; print(collect_data_files('customtkinter'))"
```

---

### Verziókezelés (.exe-be égetve)

Ha az `.exe` verziószámát meg akarod jeleníteni a Windows Fájlkezelőben:

1. Hozz létre `version_info.txt` fájlt:
```python
# version_info.txt
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(2, 1, 0, 0),
    prodvers=(2, 1, 0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(u'040904B0', [
        StringStruct(u'CompanyName', u'GameBooster'),
        StringStruct(u'FileDescription', u'Universal Windows Game Optimizer'),
        StringStruct(u'FileVersion', u'2.1.0'),
        StringStruct(u'ProductName', u'GameBooster'),
        StringStruct(u'ProductVersion', u'2.1.0'),
      ])
    ]),
    VarFileInfo([VarStruct(u'Translation', [0x0409, 1200])])
  ]
)
```

2. A `GameBooster.spec`-ben add hozzá: `version_info="version_info.txt"`

---

## 🇬🇧 English

### Prerequisites

| Software | Version | Download |
|---|---|---|
| Python | 3.11 or newer | [python.org/downloads](https://python.org/downloads) |
| Windows | 10 (2004+) or 11 | — |

> ⚠ **Important during Python install:** check **"Add Python to PATH"**!

---

### Quick build — one click

```
Double-click: build.bat
```

The script will:
1. Check Python version
2. Create virtual environment (`.venv`)
3. Install `customtkinter`, `psutil`, `pyinstaller`
4. Delete old build
5. Run PyInstaller
6. Verify result

**Output:** `dist\GameBooster\GameBooster.exe`

---

### Manual build

```cmd
cd C:\GameBooster

python -m venv .venv
.venv\Scripts\activate
pip install customtkinter psutil pyinstaller
pyinstaller GameBooster.spec --noconfirm --clean
```

---

### Distribution

To share the app, give the **entire `dist\GameBooster\` folder**, not just the `.exe`. The DLLs in `_internal\` are required.

### Admin rights

With `uac_admin=True` in the spec file, Windows will **automatically show a UAC prompt** on launch. No need to right-click → "Run as administrator".

---

### Build options

```cmd
build.bat              :: Full build
build.bat --fast       :: Recompile only (no clean, no install)
build.bat --clean      :: Clean build artifacts only
```

---

### Troubleshooting

**App shows grey window / themes missing**
```cmd
python -c "from PyInstaller.utils.hooks import collect_data_files; print(collect_data_files('customtkinter'))"
```
If empty, manually add customtkinter's asset folder to `datas` in the spec.

**`Failed to execute script main` on launch**
Run from CMD to see the error:
```
dist\GameBooster\GameBooster.exe
```

**Registry access denied**
Verify `uac_admin=True` is set in `GameBooster.spec`.
