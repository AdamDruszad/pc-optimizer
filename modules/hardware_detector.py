"""
hardware_detector.py  —  GameBooster v2.0
Univerzális hardver detektáló modul.

Felismeri:
  - GPU típus és gyártó (Intel iGPU / AMD iGPU / AMD dedikált / Nvidia)
  - CPU márka, modell, mag/szál szám, órajel
  - RAM mennyiség
  - Tápellátás állapot (töltő / akkumulátor + töltöttség %)
  - Hálózati kapcsolat típusa (Wi-Fi / Ethernet / Nincs)

Az eredmény egy HardwareProfile dataclass, amit az optimizer
és a GUI felhasználhat.
"""

import subprocess
import psutil
import re
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  ENUMERÁCIÓK
# ─────────────────────────────────────────────

class GpuType(Enum):
    INTEL_IGPU  = "Intel iGPU"
    AMD_IGPU    = "AMD iGPU (Radeon Graphics)"
    AMD_DEDIC   = "AMD Radeon (dedikált)"
    NVIDIA      = "Nvidia (dedikált)"
    UNKNOWN     = "Ismeretlen GPU"


class PowerState(Enum):
    AC_CHARGING = "Töltő csatlakoztatva"
    BATTERY     = "Akkumulátorról fut"
    NO_BATTERY  = "Nincs akkumulátor (asztali)"
    UNKNOWN     = "Ismeretlen"


class NetworkType(Enum):
    ETHERNET = "Ethernet (kábelel)"
    WIFI     = "Wi-Fi (vezeték nélküli)"
    NONE     = "Nincs kapcsolat"
    UNKNOWN  = "Ismeretlen"


# ─────────────────────────────────────────────
#  HARDVER PROFIL ADATSTRUKTÚRA
# ─────────────────────────────────────────────

@dataclass
class HardwareProfile:
    # GPU
    gpu_name:       str     = "Ismeretlen GPU"
    gpu_type:       GpuType = GpuType.UNKNOWN
    gpu_vram_mb:    int     = 0       # Dedikált VRAM (iGPU-nál DVMT)
    gpu_shared_mb:  int     = 0       # Megosztott memória max

    # CPU
    cpu_name:       str     = "Ismeretlen CPU"
    cpu_brand:      str     = "Unknown"   # "Intel" / "AMD"
    cpu_cores_p:    int     = 0           # Teljesítmény magok (P-core)
    cpu_cores_e:    int     = 0           # Hatékonysági magok (E-core, Intel 12. gen+)
    cpu_threads:    int     = 0           # Összes szál
    cpu_freq_max_mhz: float = 0.0

    # RAM
    ram_total_mb:   int     = 0
    ram_total_gb:   float   = 0.0

    # Tápellátás
    power_state:    PowerState = PowerState.UNKNOWN
    battery_pct:    int        = -1    # -1 = nincs akkumulátor

    # Hálózat
    network_type:   NetworkType = NetworkType.UNKNOWN
    network_name:   str         = ""   # Interfész neve (pl. "Wi-Fi", "Ethernet")

    # Metaadatok
    windows_version: str = ""
    detected:        bool = False


# ─────────────────────────────────────────────
#  POWERSHELL SEGÉD
# ─────────────────────────────────────────────

def _ps(script: str, timeout: int = 8) -> str:
    """PowerShell parancs futtatása, stdout visszaadása."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return r.stdout.strip()
    except Exception as e:
        logger.debug(f"PS hiba: {e}")
        return ""


# ─────────────────────────────────────────────
#  GPU DETEKTÁLÁS
# ─────────────────────────────────────────────

def detect_gpu() -> tuple[str, GpuType, int, int]:
    """
    Visszaad: (gpu_name, gpu_type, vram_mb, shared_mb)
    WMI Win32_VideoController alapján.
    """
    out = _ps("""
$gpus = Get-WmiObject Win32_VideoController |
        Select-Object Name, AdapterRAM, PNPDeviceID, VideoProcessor
foreach ($g in $gpus) {
    $ram = if ($g.AdapterRAM) { [math]::Round($g.AdapterRAM/1MB) } else { 0 }
    "$($g.Name)|$ram|$($g.PNPDeviceID)"
}
""")

    gpu_name   = "Ismeretlen GPU"
    gpu_type   = GpuType.UNKNOWN
    vram_mb    = 0
    shared_mb  = 0

    if not out:
        return gpu_name, gpu_type, vram_mb, shared_mb

    lines = [l.strip() for l in out.splitlines() if "|" in l]

    # Preferencia sorrend: Nvidia > AMD dedikált > Intel iGPU > AMD iGPU
    best = None
    for line in lines:
        parts = line.split("|")
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        try:
            ram = int(parts[1]) if parts[1].strip().isdigit() else 0
        except ValueError:
            ram = 0

        name_lower = name.lower()

        if "nvidia" in name_lower:
            if best is None or best[2] != GpuType.NVIDIA:
                best = (name, ram, GpuType.NVIDIA)
        elif "radeon" in name_lower and "graphics" not in name_lower:
            # AMD dedikált (pl. "Radeon RX 6600")
            if best is None or best[2] not in (GpuType.NVIDIA,):
                best = (name, ram, GpuType.AMD_DEDIC)
        elif "intel" in name_lower and "uhd" in name_lower:
            if best is None or best[2] not in (GpuType.NVIDIA, GpuType.AMD_DEDIC):
                best = (name, ram, GpuType.INTEL_IGPU)
        elif "intel" in name_lower and "iris" in name_lower:
            if best is None or best[2] not in (GpuType.NVIDIA, GpuType.AMD_DEDIC):
                best = (name, ram, GpuType.INTEL_IGPU)
        elif "radeon" in name_lower and "graphics" in name_lower:
            # AMD iGPU (pl. "AMD Radeon Graphics")
            if best is None or best[2] not in (GpuType.NVIDIA, GpuType.AMD_DEDIC, GpuType.INTEL_IGPU):
                best = (name, ram, GpuType.AMD_IGPU)
        elif "intel" in name_lower:
            if best is None:
                best = (name, ram, GpuType.INTEL_IGPU)

    if best:
        gpu_name, vram_mb, gpu_type = best
        # Shared memory = rendszer RAM fele (Intel/AMD iGPU esetén)
        if gpu_type in (GpuType.INTEL_IGPU, GpuType.AMD_IGPU):
            try:
                total_ram_mb = psutil.virtual_memory().total // (1024 * 1024)
                shared_mb    = total_ram_mb // 2
            except Exception:
                shared_mb = 8192

    return gpu_name, gpu_type, vram_mb, shared_mb


# ─────────────────────────────────────────────
#  CPU DETEKTÁLÁS
# ─────────────────────────────────────────────

def detect_cpu() -> tuple[str, str, int, int, int, float]:
    """
    Visszaad: (cpu_name, brand, p_cores, e_cores, threads, max_freq_mhz)

    Intel 12. generáció óta P-core és E-core külön van.
    A psutil összesített mag számot ad, a WMI adja a pontos adatot.
    """
    out = _ps("""
$cpu = Get-WmiObject Win32_Processor | Select-Object -First 1
"$($cpu.Name)|$($cpu.NumberOfCores)|$($cpu.NumberOfLogicalProcessors)|$($cpu.MaxClockSpeed)"
""")

    cpu_name   = "Ismeretlen CPU"
    brand      = "Unknown"
    p_cores    = psutil.cpu_count(logical=False) or 4
    e_cores    = 0
    threads    = psutil.cpu_count(logical=True)  or 8
    max_freq   = 0.0

    if out and "|" in out:
        parts = out.split("|")
        if len(parts) >= 4:
            cpu_name = parts[0].strip()
            try:
                wmi_cores   = int(parts[1])
                wmi_threads = int(parts[2])
                max_freq    = float(parts[3])
                p_cores     = wmi_cores
                threads     = wmi_threads
            except ValueError:
                pass

    cpu_lower = cpu_name.lower()
    if "intel" in cpu_lower:
        brand = "Intel"
        # Intel 12. gen+ hibrid architektúra (P + E magok)
        # A névből próbáljuk megállapítani
        if any(gen in cpu_lower for gen in ["12th", "13th", "14th", "1265", "1250",
                                             "1260", "1270", "1280", "12650", "13600",
                                             "13700", "14600", "14700", "ultra"]):
            # Hibrid architektúra — psutil az összes magot adja
            # Az E-magok száma = összes mag - P-magok (tipikusan 50/50 vagy 4/8)
            # i7-12650H: 6 P + 4 E = 10 mag, 16 szál
            if threads > p_cores * 2:
                # Valószínűleg hibrid
                e_cores = threads // 2 - p_cores // 2
                e_cores = max(0, e_cores)
    elif "amd" in cpu_lower or "ryzen" in cpu_lower:
        brand = "AMD"

    return cpu_name, brand, p_cores, e_cores, threads, max_freq


# ─────────────────────────────────────────────
#  TÁPELLÁTÁS DETEKTÁLÁS
# ─────────────────────────────────────────────

def detect_power() -> tuple[PowerState, int]:
    """
    Visszaad: (power_state, battery_pct)
    psutil.sensors_battery() az elsődleges forrás.
    """
    try:
        batt = psutil.sensors_battery()
        if batt is None:
            return PowerState.NO_BATTERY, -1

        pct = int(batt.percent)
        if batt.power_plugged:
            return PowerState.AC_CHARGING, pct
        else:
            return PowerState.BATTERY, pct
    except Exception as e:
        logger.debug(f"Tápellátás hiba: {e}")
        return PowerState.UNKNOWN, -1


# ─────────────────────────────────────────────
#  HÁLÓZAT DETEKTÁLÁS
# ─────────────────────────────────────────────

def detect_network() -> tuple[NetworkType, str]:
    """
    Visszaad: (network_type, interface_name)
    Az aktív hálózati kapcsolat típusát állapítja meg.
    """
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()

        for iface_name, stat in stats.items():
            if not stat.isup:
                continue
            # Kihagyjuk a loopback és virtuális interfészeket
            iface_lower = iface_name.lower()
            if any(skip in iface_lower for skip in ["loopback", "lo", "virtual",
                                                      "vmware", "vethernet", "hyper"]):
                continue
            # Csak ha van IP cím
            if iface_name not in addrs:
                continue
            has_ip = any(
                a.family.name in ("AF_INET", "2")  # IPv4
                for a in addrs[iface_name]
            )
            if not has_ip:
                continue

            # Típus meghatározása a névből
            if any(kw in iface_lower for kw in ["wi-fi", "wifi", "wlan", "wireless",
                                                  "802.11", "wifi"]):
                return NetworkType.WIFI, iface_name
            elif any(kw in iface_lower for kw in ["ethernet", "eth", "local area",
                                                    "lan", "realtek", "intel"]):
                return NetworkType.ETHERNET, iface_name

        # Ha egyiket sem találtuk, de van aktív kapcsolat
        return NetworkType.UNKNOWN, ""
    except Exception as e:
        logger.debug(f"Hálózat hiba: {e}")
        return NetworkType.UNKNOWN, ""


# ─────────────────────────────────────────────
#  WINDOWS VERZIÓ
# ─────────────────────────────────────────────

def detect_windows_version() -> str:
    try:
        import platform
        v = platform.version()
        r = platform.release()
        return f"Windows {r} ({v})"
    except Exception:
        return "Windows (ismeretlen verzió)"


# ─────────────────────────────────────────────
#  FŐ DETEKTÁLÓ FÜGGVÉNY
# ─────────────────────────────────────────────

def detect_hardware() -> HardwareProfile:
    """
    Teljes hardver detektálás. Visszaad egy HardwareProfile-t.
    Általában 3-8 másodpercet vesz igénybe (WMI lassú).
    """
    profile = HardwareProfile()

    try:
        # GPU
        logger.info("GPU detektálás...")
        (profile.gpu_name, profile.gpu_type,
         profile.gpu_vram_mb, profile.gpu_shared_mb) = detect_gpu()

        # CPU
        logger.info("CPU detektálás...")
        (profile.cpu_name, profile.cpu_brand,
         profile.cpu_cores_p, profile.cpu_cores_e,
         profile.cpu_threads, profile.cpu_freq_max_mhz) = detect_cpu()

        # RAM
        mem = psutil.virtual_memory()
        profile.ram_total_mb = mem.total // (1024 * 1024)
        profile.ram_total_gb = round(profile.ram_total_mb / 1024, 1)

        # Tápellátás
        profile.power_state, profile.battery_pct = detect_power()

        # Hálózat
        profile.network_type, profile.network_name = detect_network()

        # Windows
        profile.windows_version = detect_windows_version()

        profile.detected = True
        logger.info(
            f"Hardver detektálva: {profile.gpu_type.value} | "
            f"{profile.cpu_brand} {profile.cpu_cores_p}P+{profile.cpu_cores_e}E | "
            f"{profile.ram_total_gb}GB RAM | {profile.power_state.value}"
        )

    except Exception as e:
        logger.error(f"Hardver detektálás hiba: {e}", exc_info=True)

    return profile


# ─────────────────────────────────────────────
#  AJÁNLÁS MOTOR
# ─────────────────────────────────────────────

def get_recommendations(hw: HardwareProfile) -> list[str]:
    """
    A detektált hardver alapján javaslatokat ad.
    Visszaad egy lista stringet.
    """
    recs = []

    # GPU alapú javaslatok
    if hw.gpu_type == GpuType.INTEL_IGPU:
        if hw.gpu_vram_mb < 128:
            recs.append("⚠ BIOS: DVMT Pre-Allocated növelése ajánlott (64MB → 256MB)")
        elif hw.gpu_vram_mb < 256:
            recs.append("💡 BIOS: DVMT növelése 256MB-ra javítaná az iGPU teljesítményt")
        recs.append("✓ Intel iGPU: -dx11 launch option ajánlott (DX12 instabil iGPU-n)")
        recs.append("✓ Intel iGPU: iGPU Monitor tab figyelése javasolt gaming közben")

    elif hw.gpu_type == GpuType.AMD_IGPU:
        recs.append("💡 AMD iGPU: Smart Access Memory (SAM) ellenőrzése BIOS-ban")
        recs.append("✓ AMD iGPU: Radeon Software-ben Performance Mode bekapcsolása")

    elif hw.gpu_type == GpuType.NVIDIA:
        recs.append("✓ Nvidia: Nvidia Control Panel → Power Management → Maximum Performance")
        recs.append("✓ Nvidia: Shader Cache méret növelése ajánlott (10GB+)")

    # RAM javaslatok
    if hw.ram_total_gb < 8:
        recs.append("⚠ RAM: 8GB alatt erősen korlátozott — RAM bővítés erősen ajánlott")
    elif hw.ram_total_gb < 16:
        recs.append("💡 RAM: 16GB ajánlott modern játékokhoz — bővítés mérlegelendő")
    elif hw.ram_total_gb >= 32:
        recs.append("✓ RAM: 32GB+ — bőséges, iGPU-nál nagy shared pool áll rendelkezésre")

    # Hálózat javaslat
    if hw.network_type == NetworkType.WIFI:
        recs.append("⚠ Wi-Fi: Online játéknál Ethernet kábel jobb latenciát ad")

    # Tápellátás javaslat
    if hw.power_state == PowerState.BATTERY:
        recs.append("⚠ Akkumulátor: Teljesítmény korlátozott — csatlakoztass töltőt!")

    return recs


# ─────────────────────────────────────────────
#  HÁTTÉR FIGYELŐ (tápellátás + hálózat változás)
# ─────────────────────────────────────────────

class HardwareMonitor:
    """
    Háttérszálon figyeli a tápellátás és hálózat változásait.
    Callback-en értesíti a GUI-t.
    """

    def __init__(self, interval_sec: float = 5.0):
        self.interval       = interval_sec
        self._running       = False
        self._thread        = None
        self._callbacks     = []
        self._lock          = threading.Lock()
        self.last_power     = PowerState.UNKNOWN
        self.last_network   = NetworkType.UNKNOWN
        self.last_battery   = -1

    def add_callback(self, cb):
        with self._lock:
            self._callbacks.append(cb)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                power, batt   = detect_power()
                net, net_name = detect_network()

                changed = (power   != self.last_power  or
                           net     != self.last_network or
                           abs(batt - self.last_battery) >= 2)

                if changed:
                    self.last_power   = power
                    self.last_network = net
                    self.last_battery = batt
                    with self._lock:
                        cbs = list(self._callbacks)
                    for cb in cbs:
                        try:
                            cb(power, batt, net, net_name)
                        except Exception as e:
                            logger.debug(f"HW monitor callback hiba: {e}")
            except Exception as e:
                logger.error(f"HW monitor loop hiba: {e}")
            time.sleep(self.interval)


# Globális monitor példány
hw_monitor = HardwareMonitor(interval_sec=10.0)
