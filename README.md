# ⚡ PC Optimizer — Windows Game Booster

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D4?style=for-the-badge&logo=windows&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active-00FF88?style=for-the-badge)

**A hardware-aware Windows game optimizer built with Python.**  
Automatically detects your CPU, GPU and RAM — then applies the right optimizations for your specific setup.

[Features](#features) · [Installation](#installation) · [How It Works](#how-it-works) · [Build](#build-from-source)

</div>

---

## Overview

PC Optimizer is a desktop application that optimizes Windows for gaming by detecting your hardware profile and applying targeted tweaks — not generic one-size-fits-all changes.

Unlike tools like Razer Cortex, it distinguishes between Intel iGPU, AMD iGPU, and Nvidia dedicated GPU setups, and applies different optimizations for each. It also monitors your system in real time.

**Built as a portfolio project** to demonstrate Python desktop app development, Windows API integration, and hardware-aware software design.

---

## Features

### 🖥 Hardware Detection
- Automatically identifies GPU type: Intel iGPU / AMD iGPU / AMD dedicated / Nvidia
- Detects CPU brand and P+E core layout (Intel 12th gen hybrid architecture)
- Recognizes power state (charger vs. battery) — auto-boosts on AC power
- Identifies active network type (Wi-Fi / Ethernet) with latency warning

### 🚀 Boost Profiles
- **Gaming** — stops non-essential services, High Performance power plan, max process priority
- **Office** — minimal intervention, Balanced power plan
- **Battery Saver** — extends battery life, suppresses background activity
- **Custom profiles** — create and save your own (JSON persistence)
- Auto-boost when charger is plugged in

### 🔑 Registry Optimizer
8 proven registry tweaks with full backup/restore:

| Tweak | Effect |
|---|---|
| MMCSS Games task priority | +3-10% FPS — Scheduling: Medium → High |
| SystemResponsiveness | 100% CPU to the game (default: 80%) |
| Win32PrioritySeparation | Max foreground CPU boost (+3-8% FPS) |
| HAGS | Hardware Accelerated GPU Scheduling |
| Windows Game Mode | Automatic resource prioritization |
| Xbox Game Bar disable | +2-5% FPS (runs in background by default) |
| Nagle algorithm disable | -5-15ms online game latency |
| Mouse input buffer | Reduced input jitter |

Every tweak saves the original value before applying — fully reversible.

### 📊 Real-Time Monitoring
- CPU utilization, temperature, clock speed — live sparkline charts
- RAM usage and top memory consumers
- Intel/AMD iGPU dedicated + shared memory via Windows PDH counters
- GPU 3D engine utilization

### 💾 RAM Manager
- Working Set flush (frees RAM without killing processes)
- Process priority elevation

---

## Installation

### Requirements
- Python 3.11+
- Windows 10 (build 2004+) or Windows 11

### Run from source

```bash
git clone https://github.com/AdamDruszad/pc-optimizer.git
cd pc-optimizer

pip install -r requirements.txt

# Run as Administrator for full functionality
python main.py
```

### Pre-built .exe

Download from [Releases](https://github.com/AdamDruszad/pc-optimizer/releases).  
The `.exe` requests Administrator rights automatically via UAC.

> ⚠ **Antivirus note:** PyInstaller-compiled executables may trigger heuristic AV detection (false positive). The source code is fully open — build it yourself with `build.bat`.

---

## How It Works

```
main.py
├── hardware_detector.py    # WMI + psutil → GPU/CPU/RAM/Power/Network detection
├── profile_manager.py      # JSON-based profile storage
├── hw_optimizer.py         # Hardware-aware boost logic
├── registry_tweaks.py      # 8 registry tweaks with snapshot/restore
├── monitor.py              # Background system monitoring thread
├── igpu_monitor.py         # Intel/AMD iGPU PDH counter monitoring
├── ram_cleaner.py          # Working set flush via Windows API (ctypes)
└── windows_optimizer.py    # Service management + power plans
gui/
├── app.py                  # CustomTkinter UI — 7 tabs
└── app_paths.py            # PyInstaller-compatible path management
```

**Key technical decisions:**

- **WMI over psutil for GPU detection** — psutil doesn't distinguish iGPU from dedicated GPU; WMI's `Win32_VideoController` does
- **PDH counters for iGPU memory** — the only reliable way to read Intel UHD shared VRAM without a vendor SDK
- **Registry snapshot before every tweak** — all changes saved to `registry_snapshot.json`, one-click restore
- **Dynamic path management** — `app_paths.py` ensures writable files go next to the `.exe` when PyInstaller-frozen, not into the temp `_MEIPASS` directory

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| GUI | CustomTkinter (modern dark-themed tkinter wrapper) |
| System monitoring | psutil, WMI via PowerShell subprocess |
| Windows API | ctypes, winreg, subprocess (sc.exe, powercfg) |
| Performance counters | Windows PDH API |
| Persistence | JSON |
| Build | PyInstaller (onedir, UAC manifest) |

---

## Build from Source

```cmd
build.bat           :: Full build (venv + install + compile)
build.bat --fast    :: Recompile only
build.bat --clean   :: Clean build artifacts
```

Output: `dist\GameBooster\GameBooster.exe`

Full instructions: [BUILD_GUIDE.md](BUILD_GUIDE.md)

---

## Project Background

Built for my own laptop (Intel i7-12650H, 32GB RAM, Intel UHD Graphics) and evolved into a full portfolio project. The iGPU-specific optimizations — particularly the working set flush to increase shared GPU memory — came from diagnosing my own frame drops in CS2.

---

## License

MIT — free to use, modify and distribute.

---

<div align="center">
Made by <a href="https://github.com/AdamDruszad">AdamDruszad</a>
</div>
