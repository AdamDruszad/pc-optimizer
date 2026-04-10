"""
monitor.py
Valós idejű rendszer monitor: CPU hőmérséklet, RAM, órajel, folyamat CPU %.
Windows WMIC + psutil kombináció - külső driver nélkül.
"""

import psutil
import subprocess
import threading
import time
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SystemSnapshot:
    """Egy pillanatfelvétel a rendszer állapotáról."""
    cpu_percent: float = 0.0          # CPU kihasználtság %
    cpu_freq_mhz: float = 0.0         # Aktuális CPU órajel MHz-ben
    cpu_freq_max_mhz: float = 0.0     # Max órajel
    cpu_temp_c: float = 0.0           # CPU hőmérséklet °C (0 ha nem elérhető)
    ram_used_mb: int = 0
    ram_total_mb: int = 0
    ram_percent: float = 0.0
    ram_available_mb: int = 0
    cs2_cpu_percent: float = 0.0      # CS2 folyamat CPU %
    cs2_ram_mb: int = 0               # CS2 RAM foglalás
    cs2_running: bool = False
    timestamp: float = field(default_factory=time.time)


# ─────────────────────────────────────────────
#  HŐMÉRSÉKLET OLVASÁS
# ─────────────────────────────────────────────

def _read_temp_wmi() -> float:
    """
    CPU hőmérséklet WMIC-en keresztül (MSAcpi_ThermalZoneTemperature).
    Windows 10/11-en általában elérhető, de néha 0-t ad vissza.
    Kelvin -> Celsius konverzió: (kelvin / 10) - 273.15
    """
    try:
        result = subprocess.run(
            ["wmic", "/namespace:\\\\root\\wmi", "PATH",
             "MSAcpi_ThermalZoneTemperature", "GET", "CurrentTemperature", "/VALUE"],
            capture_output=True, text=True, timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in result.stdout.splitlines():
            if "CurrentTemperature=" in line:
                val = line.split("=")[1].strip()
                if val.isdigit():
                    kelvin_tenths = int(val)
                    celsius = (kelvin_tenths / 10.0) - 273.15
                    if 0 < celsius < 120:  # Sanity check
                        return round(celsius, 1)
    except Exception as e:
        logger.debug(f"WMIC temp hiba: {e}")
    return 0.0


def _read_temp_psutil() -> float:
    """psutil hőmérséklet olvasás (Windows 11-en néha működik)."""
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return 0.0
        # Keressük a CPU/Core hőmérőt
        for key in ["coretemp", "k10temp", "cpu_thermal", "acpitz"]:
            if key in temps:
                entries = temps[key]
                if entries:
                    return round(entries[0].current, 1)
        # Ha semmi nem stimmel, az első elérhető
        for entries in temps.values():
            if entries:
                return round(entries[0].current, 1)
    except Exception:
        pass
    return 0.0


def get_cpu_temp() -> float:
    """
    CPU hőmérséklet °C-ban.
    Sorban próbálja: psutil -> WMIC -> 0.0 (nem elérhető)
    """
    temp = _read_temp_psutil()
    if temp > 0:
        return temp
    return _read_temp_wmi()


# ─────────────────────────────────────────────
#  CS2 FOLYAMAT FIGYELÉS
# ─────────────────────────────────────────────

CS2_NAMES = {"cs2.exe", "csgo.exe"}


def get_cs2_stats() -> tuple[bool, float, int]:
    """
    Visszaadja a CS2 folyamat adatait: (fut, cpu%, ram_mb)
    """
    for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_info']):
        try:
            if proc.info['name'].lower() in CS2_NAMES:
                cpu = proc.cpu_percent(interval=None)
                ram = proc.info['memory_info'].rss // (1024 * 1024)
                return True, round(cpu, 1), ram
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False, 0.0, 0


# ─────────────────────────────────────────────
#  SNAPSHOT GYŰJTÉS
# ─────────────────────────────────────────────

def take_snapshot() -> SystemSnapshot:
    """Egy teljes rendszer pillanatfelvétel."""
    snap = SystemSnapshot()

    # CPU
    snap.cpu_percent = psutil.cpu_percent(interval=None)
    freq = psutil.cpu_freq()
    if freq:
        snap.cpu_freq_mhz = round(freq.current, 0)
        snap.cpu_freq_max_mhz = round(freq.max, 0)

    # Hőmérséklet (külön, mert lassabb lehet)
    snap.cpu_temp_c = get_cpu_temp()

    # RAM
    mem = psutil.virtual_memory()
    snap.ram_used_mb     = mem.used // (1024 * 1024)
    snap.ram_total_mb    = mem.total // (1024 * 1024)
    snap.ram_percent     = mem.percent
    snap.ram_available_mb = mem.available // (1024 * 1024)

    # CS2
    snap.cs2_running, snap.cs2_cpu_percent, snap.cs2_ram_mb = get_cs2_stats()

    snap.timestamp = time.time()
    return snap


# ─────────────────────────────────────────────
#  HÁTTÉR MONITOR SZÁL
# ─────────────────────────────────────────────

class SystemMonitor:
    """
    Háttérszálon fut, megadott intervallumonként frissíti az adatokat.
    Thread-safe callback rendszer a GUI frissítéséhez.
    """

    def __init__(self, interval_sec: float = 2.0):
        self.interval = interval_sec
        self._running = False
        self._thread: threading.Thread | None = None
        self._callbacks: list = []
        self._last_snapshot: SystemSnapshot | None = None
        self._lock = threading.Lock()

        # psutil CPU % első mérése inicializálás (különben 0-t ad)
        psutil.cpu_percent(interval=None)

    def add_callback(self, cb):
        """Hozzáad egy callback függvényt, amit minden frissítéskor meghív."""
        with self._lock:
            self._callbacks.append(cb)

    def remove_callback(self, cb):
        with self._lock:
            self._callbacks = [c for c in self._callbacks if c != cb]

    @property
    def last_snapshot(self) -> SystemSnapshot | None:
        return self._last_snapshot

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("SystemMonitor elindult.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("SystemMonitor leállt.")

    def _loop(self):
        while self._running:
            try:
                snap = take_snapshot()
                self._last_snapshot = snap
                with self._lock:
                    cbs = list(self._callbacks)
                for cb in cbs:
                    try:
                        cb(snap)
                    except Exception as e:
                        logger.debug(f"Monitor callback hiba: {e}")
            except Exception as e:
                logger.error(f"Monitor loop hiba: {e}")
            time.sleep(self.interval)


# Globális monitor példány (az app importálja)
system_monitor = SystemMonitor(interval_sec=2.0)
