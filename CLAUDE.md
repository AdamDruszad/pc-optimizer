# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

GameBooster (repo name `pc-optimizer`): a Windows-only CustomTkinter desktop app that changes system state (services, power plan, registry, process priorities) to "boost" games. Python 3.11+, deps are only `customtkinter` and `psutil`; everything else is stdlib (`winreg`, `ctypes`, `subprocess`). UI text, comments and logs are Hungarian.

## Commands

```cmd
pip install -r requirements.txt
python main.py                      :: run from source; run the shell as Administrator or every write op is refused
build.bat                           :: venv + deps + PyInstaller -> dist\GameBooster\GameBooster.exe
build.bat --fast                    :: rebuild without clean/install
pyinstaller GameBooster.spec --noconfirm --clean
```

There are no tests and no linter config yet. `pyproject.toml` points pytest at `tests/` (does not exist). `GameBooster.spec` is the real build spec (onedir, `uac_admin=True`); `main.spec` is a stale auto-generated leftover.

## Architecture

`main.py` sets up logging and `sys.path`, then starts `gui.app.GameBoosterApp(app_dir=...)`. The GUI calls `gui.app_paths.init(app_dir)`; backend modules resolve their JSON state files through lazy `from gui.app_paths import ...` calls with a fallback to the module's own parent dir. In a frozen build `app_dir` is the folder next to the .exe, not `_MEIPASS`.

`gui/app.py` (one ~1600-line class) builds 7 tabs and wires everything. Work runs in `threading.Thread(daemon=True)` workers that report back via `self.after(0, ...)` callbacks; a few handlers still touch widgets directly from the worker thread.

Backend modules in `modules/` hold module-level singletons created at import time, and some start threads at import:
- `monitor.system_monitor`, `igpu_monitor.igpu_monitor`, `hardware_detector.hw_monitor`: polling threads that push snapshots to GUI callbacks. `igpu_monitor` spawns PowerShell (`Get-Counter`) every poll; `monitor` shells out to `wmic` for temperature.
- `profile_manager.profile_manager`: built-in profiles (`BUILTIN_PROFILES`) plus custom ones in `profiles/custom_profiles.json`.

Two independent apply/restore pipelines, each with its own state file:
1. **Boost** (`hw_optimizer.apply_boost` / `restore_original`): power plan, `sc stop` + `sc config start= disabled` on `profile.stop_services`, working-set flush, background process priority. Original service state goes to `original_state.json` via `utils/state_manager.py`, which only records the fixed `TARGET_SERVICES` list.
2. **Registry** (`registry_tweaks.apply_registry_tweaks` / `restore_registry_tweaks`): `RegistryTweakConfig` toggles; originals go to `registry_snapshot.json`.

Many `BoostProfile` fields (`registry_*`, `ram_clean_*`, `set_process_priority`, `auto_restore_on_exit`) are displayed in the UI but never read by `hw_optimizer`.

Dead code: `modules/registry_optimizer.py` (an older parallel registry implementation with different values and its own `registry_backup.json`) and `modules/windows_optimizer.py` are not imported anywhere. `osszes_kod.txt` is a 23 MB UTF-16 code dump (includes vendored pip sources) committed by mistake. Don't edit or grep through it.

## Working rules for this repo

- Anything that writes to the registry, services or power plans changes the developer's real machine. Don't run apply/boost paths to "test" them; read-only queries (`sc qc`, `powercfg /getactivescheme`, registry reads) are fine.
- Before a write, the original value must be captured; a second apply must not overwrite an existing snapshot.
- Keep UI strings Hungarian.
