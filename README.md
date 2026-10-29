# GameBooster: Windows game optimizer you can undo

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

A desktop app that applies only documented, checkable Windows optimizations, shows you the exact
change list before it touches anything, and records every original value in a change journal so
you can revert one change or all of them later.

![Overview](docs/screenshots/overview.png)

## What it does

| Page | What it changes | How it is undone |
|---|---|---|
| **Game mode** | Performance power plan (Ultimate/High, or the Windows 11 "Best performance" power mode on Modern Standby laptops), HIGH priority for the game, BELOW_NORMAL for background apps you pick | Automatically when the game exits, when you stop the session, or when the app closes |
| **Cleaner** | Deletes temp files older than 24 h, DirectX/NVIDIA/AMD shader caches, crash dumps, error reports, Delivery Optimization cache, component store cleanup (DISM) | Not revertable, so it scans first and shows sizes; never follows junctions, never touches documents or the Recycle Bin |
| **Startup** | Turns startup apps on/off through `StartupApproved`, the same mechanism Task Manager uses | Journal, or toggle back |
| **Services** | A fixed, risk-labelled allowlist (telemetry, Maps, Fax, SysMain, Search…) set to Manual instead of Disabled | Journal restores the original start type, including delayed start, and restarts services that were running |
| **Tweaks** | Background recording off, windowed-game optimizations, HAGS, Windows Game Mode | Journal |
| **Network** | DNS presets per adapter, DNS cache flush, TCP latency/jitter test | Journal |
| **Monitor** | Nothing: CPU, RAM, GPU, VRAM, disk and network history from in-process PDH counters | — |

Before the first change of a session the app asks Windows for a System Restore point as an extra,
independent safety net.

### What it deliberately does not do

Version 2 shipped several tweaks that Windows ignores or overrides, or that hurt more than they
help. Version 3 removed them:

- **"RAM cleaning"** (`EmptyWorkingSet` on every process): Windows pages the memory straight back
  in, which causes stutter.
- **MMCSS `GPU Priority`, `SFIO Priority`**: Microsoft documents both as unused.
- **`SystemResponsiveness = 0`**: values below 10 are reset to 20 by Windows.
- **Nagle / `TCPNoDelay`, `MouseDataQueueSize`, `Win32PrioritySeparation`**: no measurable effect
  for modern games.
- **Disabling Windows Update or biometrics.**

CPU core temperature needs a kernel driver (the WinRing0 driver used by many tools is flagged by
Microsoft Defender). GameBooster installs no driver: it shows the ACPI thermal zone, and the GPU
temperature on NVIDIA if `nvidia-ml-py` is installed.

## Install and run

```bash
pip install -r requirements.txt
python main.py
```

Modifying features need Administrator rights; without them the app runs read-only and offers a
"restart as admin" button. Data (journal, settings, log) lives in `%LOCALAPPDATA%\GameBooster`.

Upgrading from 2.x: on first start, v3 imports the old `original_state.json` and
`registry_snapshot.json` into the journal, so changes made by v2 can be reverted from **History**.

## Build

```cmd
build.bat           :: venv + dependencies + PyInstaller -> dist\GameBooster\GameBooster.exe
```

Details: [BUILD_GUIDE.md](BUILD_GUIDE.md)

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check gamebooster tests main.py
```

Tests never touch the real system: Windows calls are replaced with fakes. Don't run apply paths on
your development machine to "try" them; use Windows Sandbox or a VM.

```
gamebooster/
├── core/          journal (change records + revert), winapi, storage, restore point, v2 import
├── optimizers/    each module only *plans* changes: power, tweaks, services, game_mode,
│                  cleaner, startup, network
├── monitoring/    sampler thread (psutil + PDH), hardware info from the registry
└── ui/            CustomTkinter shell, design tokens, task runner, pages/
```

## Screenshots

| Cleaner | Tweaks | Monitor |
|---|---|---|
| ![Cleaner](docs/screenshots/cleaner.png) | ![Tweaks](docs/screenshots/tweaks.png) | ![Monitor](docs/screenshots/monitor.png) |

## License

MIT. Made by [AdamDruszad](https://github.com/AdamDruszad).
