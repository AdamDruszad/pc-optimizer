"""
igpu_monitor.py  —  GameBooster v1.2
Intel UHD iGPU memória monitor és optimalizáló.

Miért különleges az iGPU memória kezelése?
─────────────────────────────────────────────
Az Intel UHD Graphics NEM rendelkezik saját fizikai VRAM-mal.
Ehelyett a rendszer RAM-ból vesz el egy dinamikus részt:

  ┌─────────────────────────────────────────┐
  │           32 GB System RAM              │
  │  ┌──────────┐  ┌──────────────────────┐ │
  │  │ Dedikált │  │  Shared (dinamikus)  │ │
  │  │ ~128 MB  │  │    max ~16 GB        │ │
  │  │  (BIOS)  │  │  (valós igény alap.) │ │
  │  └──────────┘  └──────────────────────┘ │
  └─────────────────────────────────────────┘

Ha más folyamatok lefoglalják a RAM-ot → a GPU kevesebbet kap
→ textúrák lapozóba kerülnek → FPS drop, stuttering.

Adatforrások:
  1. WMI Win32_VideoController → adapter névhez, driver verzióhoz
  2. PowerShell Get-Counter (PDH) → valós idejű GPU mem + engine %
  3. PowerShell DXGI query → max shared/dedicated értékek
"""

import subprocess
import threading
import time
import logging
import re
import psutil
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

HISTORY_SIZE    = 90          # 90 × 2 mp = 3 perc előzmény
POLL_INTERVAL   = 2.0         # másodperc
INTEL_VENDOR_ID = "8086"      # Intel PCI Vendor ID (hex)

# GPU memóriát evő folyamatok - ezek szüntethetők gaming közben
GPU_HUNGRY_PROCESSES = {
    "chrome.exe":      "Google Chrome (HW gyorsítás)",
    "msedge.exe":      "Microsoft Edge (HW gyorsítás)",
    "firefox.exe":     "Firefox (WebGL/WebGPU)",
    "Discord.exe":     "Discord (HW gyorsítás)",
    "Teams.exe":       "Microsoft Teams (GPU render)",
    "Slack.exe":       "Slack (Electron GPU)",
    "zoom.exe":        "Zoom (videó dekód)",
    "obs64.exe":       "OBS Studio (encode)",
    "photoshop.exe":   "Adobe Photoshop (GPU)",
    "explorer.exe":    "Windows Explorer (DWM)",
}


# ─────────────────────────────────────────────
#  ADATSTRUKTÚRÁK
# ─────────────────────────────────────────────

@dataclass
class IgpuAdapterInfo:
    """Statikus adapter adatok - csak egyszer kell lekérni."""
    name:            str   = "Intel UHD Graphics"
    driver_version:  str   = "N/A"
    driver_date:     str   = "N/A"
    dedicated_max_mb: int  = 128    # BIOS DVMT beállítás
    shared_max_mb:   int   = 16384  # Max shared (rendszer RAM fele)
    vendor_id:       str   = "8086"
    device_id:       str   = "N/A"
    is_intel:        bool  = True
    detected:        bool  = False


@dataclass
class IgpuSnapshot:
    """Egy időpillanat iGPU állapota."""
    dedicated_used_mb:  int   = 0     # Jelenleg használt dedikált mem
    dedicated_max_mb:   int   = 128   # Max dedikált (BIOS)
    shared_used_mb:     int   = 0     # Jelenleg használt shared mem
    shared_max_mb:      int   = 8192  # Max shared mem
    engine_3d_pct:      float = 0.0   # 3D motor kihasználtság %
    engine_copy_pct:    float = 0.0   # Copy engine %
    engine_video_pct:   float = 0.0   # Video decode %
    total_gpu_mem_used: int   = 0     # Összes GPU mem (ded + shared)
    pressure_level:     str   = "OK"  # "OK" | "MODERATE" | "HIGH" | "CRITICAL"
    gpu_hungry_procs:   list  = field(default_factory=list)
    timestamp:          float = field(default_factory=time.time)


# ─────────────────────────────────────────────
#  POWERSHELL SEGÉDFÜGGVÉNYEK
# ─────────────────────────────────────────────

def _run_ps(script: str, timeout: int = 8) -> str:
    """PowerShell parancs futtatása, visszaadja a stdout-ot."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.debug("PowerShell timeout")
        return ""
    except FileNotFoundError:
        logger.warning("PowerShell nem található")
        return ""
    except Exception as e:
        logger.debug(f"PS hiba: {e}")
        return ""


# ─────────────────────────────────────────────
#  ADAPTER INFORMÁCIÓK (statikus, egyszer fut)
# ─────────────────────────────────────────────

def detect_igpu_adapter() -> IgpuAdapterInfo:
    """
    WMI-n keresztül megkeresi az Intel iGPU adaptert.
    Fallback: alapértelmezett értékek.
    """
    info = IgpuAdapterInfo()

    # 1. WMI adapter adatok
    ps_adapter = """
$gpu = Get-WmiObject Win32_VideoController |
       Where-Object { $_.Name -like '*Intel*' -or $_.PNPDeviceID -like '*VEN_8086*' } |
       Select-Object -First 1
if ($gpu) {
    $ram = if ($gpu.AdapterRAM) { [math]::Round($gpu.AdapterRAM / 1MB) } else { 0 }
    Write-Output "$($gpu.Name)|$ram|$($gpu.DriverVersion)|$($gpu.DriverDate)|$($gpu.PNPDeviceID)"
}
"""
    out = _run_ps(ps_adapter)
    if out and "|" in out:
        parts = out.split("|")
        if len(parts) >= 4:
            info.name           = parts[0].strip() or "Intel UHD Graphics"
            dedicated_mb        = int(parts[1]) if parts[1].strip().isdigit() else 128
            info.dedicated_max_mb = max(dedicated_mb, 64)
            info.driver_version = parts[2].strip()
            # WMI dátum formátum: 20230815000000.000000+060 → "2023-08-15"
            raw_date = parts[3].strip()
            if len(raw_date) >= 8 and raw_date[:8].isdigit():
                d = raw_date
                info.driver_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            if len(parts) > 4:
                pnp = parts[4].strip()
                # PNP Device ID: PCI\VEN_8086&DEV_4C8A&...
                ven_match = re.search(r"VEN_([0-9A-Fa-f]{4})", pnp)
                dev_match = re.search(r"DEV_([0-9A-Fa-f]{4})", pnp)
                if ven_match:
                    info.vendor_id = ven_match.group(1).upper()
                    info.is_intel  = info.vendor_id == "8086"
                if dev_match:
                    info.device_id = dev_match.group(1).upper()
            info.detected = True
            logger.info(f"iGPU adapter: {info.name} | Driver: {info.driver_version}")

    # 2. Shared max = rendszer RAM fele (Windows politika)
    try:
        total_ram_mb = psutil.virtual_memory().total // (1024 * 1024)
        info.shared_max_mb = total_ram_mb // 2
    except Exception:
        info.shared_max_mb = 16384  # 16 GB fallback 32 GB-os gépen

    return info


# ─────────────────────────────────────────────
#  VALÓS IDEJŰ GPU MEMÓRIA (PDH COUNTERS)
# ─────────────────────────────────────────────

def _read_gpu_counters() -> dict:
    """
    PDH (Performance Data Helper) GPU counter-eket olvas PowerShell-en keresztül.
    Visszaad egy dict-et MB értékekkel és % értékekkel.

    Elérhető counterek (Windows 10 1903+, WDDM 2.4+):
      \\GPU Adapter Memory(*)\\Dedicated Usage   → dedikált mem bytes
      \\GPU Adapter Memory(*)\\Shared Usage      → shared mem bytes
      \\GPU Engine(*engtype_3D*)\\Utilization Percentage
    """
    ps_counters = r"""
try {
    $result = @{}

    # GPU memória (összes adapter összegzése)
    $dedCtr = Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage' -ErrorAction SilentlyContinue
    $shrCtr = Get-Counter '\GPU Adapter Memory(*)\Shared Usage'    -ErrorAction SilentlyContinue

    if ($dedCtr) {
        $ded = ($dedCtr.CounterSamples |
                Where-Object { $_.InstanceName -notmatch '_total' } |
                Measure-Object -Property CookedValue -Sum).Sum
        $result['ded'] = [math]::Round($ded / 1MB)
    }
    if ($shrCtr) {
        $shr = ($shrCtr.CounterSamples |
                Where-Object { $_.InstanceName -notmatch '_total' } |
                Measure-Object -Property CookedValue -Sum).Sum
        $result['shr'] = [math]::Round($shr / 1MB)
    }

    # GPU Engine kihasználtság
    $eng3d  = Get-Counter '\GPU Engine(*engtype_3D*)\Utilization Percentage'    -ErrorAction SilentlyContinue
    $engCpy = Get-Counter '\GPU Engine(*engtype_Copy*)\Utilization Percentage'   -ErrorAction SilentlyContinue
    $engVid = Get-Counter '\GPU Engine(*engtype_VideoDecode*)\Utilization Percentage' -ErrorAction SilentlyContinue

    if ($eng3d) {
        $v = ($eng3d.CounterSamples | Measure-Object -Property CookedValue -Sum).Sum
        $result['eng3d'] = [math]::Round($v, 1)
    }
    if ($engCpy) {
        $v = ($engCpy.CounterSamples | Measure-Object -Property CookedValue -Sum).Sum
        $result['engcpy'] = [math]::Round($v, 1)
    }
    if ($engVid) {
        $v = ($engVid.CounterSamples | Measure-Object -Property CookedValue -Sum).Sum
        $result['engvid'] = [math]::Round($v, 1)
    }

    # Kiírás
    foreach ($k in $result.Keys) {
        Write-Output "$k=$($result[$k])"
    }
} catch {
    Write-Output "error=$($_.Exception.Message)"
}
"""
    out = _run_ps(ps_counters, timeout=10)
    parsed = {}
    for line in out.splitlines():
        line = line.strip()
        if "=" in line:
            k, _, v = line.partition("=")
            try:
                parsed[k.strip()] = float(v.strip())
            except ValueError:
                pass
    return parsed


# ─────────────────────────────────────────────
#  GPU-T FOGYASZTÓ FOLYAMATOK
# ─────────────────────────────────────────────

def find_gpu_hungry_processes() -> list[dict]:
    """
    Megkeresi a futó GPU-memóriát evő folyamatokat.
    Visszaad egy listát {"name", "display", "pid", "ram_mb"} dict-ekkel.
    """
    found = []
    running = {p.info['name'].lower(): p for p in
               psutil.process_iter(['name', 'pid', 'memory_info'])
               if p.info['name']}
    for proc_name, display in GPU_HUNGRY_PROCESSES.items():
        proc = running.get(proc_name.lower())
        if proc:
            try:
                ram_mb = proc.info['memory_info'].rss // (1024 * 1024)
                found.append({
                    "name":    proc_name,
                    "display": display,
                    "pid":     proc.info['pid'],
                    "ram_mb":  ram_mb,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return found


# ─────────────────────────────────────────────
#  NYOMÁSSZINT SZÁMÍTÁS
# ─────────────────────────────────────────────

def _calc_pressure(shared_used_mb: int, shared_max_mb: int,
                   dedicated_used_mb: int, dedicated_max_mb: int) -> str:
    """
    Meghatározza a GPU memória nyomásszintjét.
    Az iGPU-nál a shared memória az kritikus.
    """
    if shared_max_mb == 0:
        return "OK"
    ratio = shared_used_mb / shared_max_mb

    # Dedikált is számít - ha tele van, shared-be spill over
    ded_ratio = dedicated_used_mb / max(dedicated_max_mb, 1)

    if ratio >= 0.85 or ded_ratio >= 0.90:
        return "CRITICAL"
    elif ratio >= 0.65 or ded_ratio >= 0.75:
        return "HIGH"
    elif ratio >= 0.40:
        return "MODERATE"
    return "OK"


# ─────────────────────────────────────────────
#  SNAPSHOT ÖSSZEÁLLÍTÁS
# ─────────────────────────────────────────────

def take_igpu_snapshot(adapter_info: IgpuAdapterInfo) -> IgpuSnapshot:
    """Egy teljes iGPU pillanatfelvétel."""
    snap = IgpuSnapshot()
    snap.dedicated_max_mb = adapter_info.dedicated_max_mb
    snap.shared_max_mb    = adapter_info.shared_max_mb

    counters = _read_gpu_counters()

    snap.dedicated_used_mb = int(counters.get("ded", 0))
    snap.shared_used_mb    = int(counters.get("shr", 0))
    snap.engine_3d_pct     = min(float(counters.get("eng3d",  0.0)), 100.0)
    snap.engine_copy_pct   = min(float(counters.get("engcpy", 0.0)), 100.0)
    snap.engine_video_pct  = min(float(counters.get("engvid", 0.0)), 100.0)

    snap.total_gpu_mem_used = snap.dedicated_used_mb + snap.shared_used_mb
    snap.pressure_level = _calc_pressure(
        snap.shared_used_mb, snap.shared_max_mb,
        snap.dedicated_used_mb, snap.dedicated_max_mb
    )
    snap.gpu_hungry_procs = find_gpu_hungry_processes()
    snap.timestamp = time.time()
    return snap


# ─────────────────────────────────────────────
#  OPTIMALIZÁLÓ MŰVELETEK
# ─────────────────────────────────────────────

def disable_hw_acceleration_hint() -> list[str]:
    """
    Visszaad egy listát a HW gyorsítás letiltásának lépéseiről
    a legfőbb GPU-evő alkalmazásokhoz. (Nem csinálja meg automatikusan
    - ezeket a felhasználónak kell megtenni az alkalmazásokban.)
    """
    return [
        "Chrome/Edge: Beállítások → Rendszer → 'Hardveres gyorsítás' KI",
        "Discord: Beállítások → Megjelenés → 'Hardveres gyorsítás' KI",
        "Firefox: about:config → layers.acceleration.force-enabled = false",
        "Zoom: Beállítások → Videó → 'GPU videó feldolgozás' KI",
    ]


def optimize_igpu_memory(adapter_info: IgpuAdapterInfo,
                          callback=None) -> list[str]:
    """
    iGPU memória optimalizálása:
    1. Working set ürítés (GPU-evő folyamatok is)
    2. GPU-evő háttérfolyamatok azonosítása
    3. Tanácsadás a tartós megoldásokhoz
    """
    log = []

    def msg(m: str):
        log.append(m)
        if callback:
            callback(m)

    msg("🖥 iGPU memória optimalizálás indítása...")
    msg(f"   Adapter: {adapter_info.name}")
    msg(f"   Shared max: {adapter_info.shared_max_mb:,} MB")

    # 1. GPU memória stat mérés előtte
    before = take_igpu_snapshot(adapter_info)
    msg(f"\n📊 Jelenlegi állapot:")
    msg(f"   Dedikált:  {before.dedicated_used_mb:4} MB / {before.dedicated_max_mb} MB")
    msg(f"   Shared:    {before.shared_used_mb:4} MB / {before.shared_max_mb:,} MB")
    msg(f"   Nyomás:    {before.pressure_level}")

    # 2. Working set ürítés (ez felszabadítja a RAM-ot amit a GPU kaphat)
    msg("\n🧹 Working Set ürítés (GPU shared pool növelése)...")
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        import psutil as _psutil
        freed = 0
        for proc in _psutil.process_iter(['pid', 'name']):
            try:
                handle = kernel32.OpenProcess(0x1F0FFF, False, proc.info['pid'])
                if handle:
                    kernel32.K32EmptyWorkingSet(handle)
                    kernel32.CloseHandle(handle)
                    freed += 1
            except Exception:
                pass
        msg(f"   ✓ {freed} folyamat working set ürítve")
    except Exception as e:
        msg(f"   ⚠ Working set ürítés: {e}")

    time.sleep(1.0)  # Várjuk meg hogy a memória visszakerüljön a poolba

    # 3. GPU-evő folyamatok listázása
    hungry = find_gpu_hungry_processes()
    if hungry:
        msg(f"\n⚠ GPU-memóriát foglaló folyamatok ({len(hungry)} db):")
        for p in hungry:
            msg(f"   • {p['display']:<35} {p['ram_mb']:>4} MB RAM")
        msg("")
        msg("   💡 Tipp: Zárd be ezeket játék közben:")
        for hint in disable_hw_acceleration_hint():
            msg(f"   → {hint}")
    else:
        msg("\n✓ Nem fut GPU-evő háttérfolyamat.")

    # 4. Mérés utána
    time.sleep(0.5)
    after = take_igpu_snapshot(adapter_info)
    shared_freed = before.shared_used_mb - after.shared_used_mb
    msg(f"\n📊 Optimalizálás után:")
    msg(f"   Shared: {after.shared_used_mb:,} MB  (Δ {'+' if shared_freed > 0 else ''}{shared_freed} MB)")
    msg(f"   Nyomás: {after.pressure_level}")

    # 5. Konfiguráció javaslat
    msg("\n🔧 Tartós javítások (BIOS beállítások):")
    msg("   → BIOS → Advanced → DVMT Pre-Allocated: 128MB → 256MB")
    msg("   → Ez növeli a dedikált GPU memóriát, csökkenti shared igényt")

    msg("\n✅ iGPU optimalizálás kész!")
    return log


# ─────────────────────────────────────────────
#  HÁTTÉR MONITOR OSZTÁLY
# ─────────────────────────────────────────────

class IgpuMonitor:
    """
    Háttérszálon fut, 2 másodpercenként frissíti az iGPU adatokat.
    Körkörös puffert tart fenn a sparkline chart-hoz.
    Thread-safe callback rendszer a GUI-hoz.
    """

    def __init__(self, interval_sec: float = POLL_INTERVAL):
        self.interval      = interval_sec
        self._running      = False
        self._thread: threading.Thread | None = None
        self._lock         = threading.Lock()
        self._callbacks: list = []

        # Előzménypuffer a sparkline-hoz
        self.shared_history:    deque[int]   = deque(maxlen=HISTORY_SIZE)
        self.dedicated_history: deque[int]   = deque(maxlen=HISTORY_SIZE)
        self.engine_history:    deque[float] = deque(maxlen=HISTORY_SIZE)

        self.adapter_info:  IgpuAdapterInfo | None = None
        self.last_snapshot: IgpuSnapshot    | None = None

        # Adapter detektálás egy külön szálban (lassabb, ne blokkoljuk az UI-t)
        threading.Thread(target=self._init_adapter, daemon=True).start()

    def _init_adapter(self):
        logger.info("iGPU adapter detektálás...")
        self.adapter_info = detect_igpu_adapter()
        logger.info(f"iGPU: {self.adapter_info.name} | "
                    f"Dedikált max: {self.adapter_info.dedicated_max_mb} MB | "
                    f"Shared max: {self.adapter_info.shared_max_mb} MB")

    def add_callback(self, cb):
        with self._lock:
            self._callbacks.append(cb)

    def remove_callback(self, cb):
        with self._lock:
            self._callbacks = [c for c in self._callbacks if c != cb]

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("IgpuMonitor elindult.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=8)

    def _loop(self):
        # Várjuk meg az adapter detektálást (max 10 mp)
        for _ in range(50):
            if self.adapter_info is not None:
                break
            time.sleep(0.2)
        if self.adapter_info is None:
            self.adapter_info = IgpuAdapterInfo()  # Fallback

        while self._running:
            try:
                snap = take_igpu_snapshot(self.adapter_info)
                self.last_snapshot = snap

                # Előzmény frissítés
                self.shared_history.append(snap.shared_used_mb)
                self.dedicated_history.append(snap.dedicated_used_mb)
                self.engine_history.append(snap.engine_3d_pct)

                with self._lock:
                    cbs = list(self._callbacks)
                for cb in cbs:
                    try:
                        cb(snap)
                    except Exception as e:
                        logger.debug(f"IgpuMonitor callback hiba: {e}")
            except Exception as e:
                logger.error(f"IgpuMonitor loop hiba: {e}")
            time.sleep(self.interval)


# Globális példány
igpu_monitor = IgpuMonitor()
