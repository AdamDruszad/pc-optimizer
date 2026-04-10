"""
ram_cleaner.py
RAM Working Set ürítése + folyamat prioritás beállítás CS2-höz.
ctypes-szal közvetlenül a Windows API-t hívjuk - psutil csak monitozásra.
"""

import ctypes
import ctypes.wintypes
import psutil
import os
import logging

logger = logging.getLogger(__name__)

# Windows API konstansok
PROCESS_ALL_ACCESS = 0x1F0FFF
SE_PRIVILEGE_ENABLED = 0x00000002
TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY = 0x0008


def get_ram_info() -> dict:
    """Visszaadja a RAM aktuális állapotát MB-ban."""
    mem = psutil.virtual_memory()
    return {
        "total_mb":     mem.total // (1024 * 1024),
        "available_mb": mem.available // (1024 * 1024),
        "used_mb":      mem.used // (1024 * 1024),
        "percent":      mem.percent,
    }


def empty_working_sets(callback=None) -> tuple[int, int]:
    """
    Üríti az összes folyamat Working Set-jét (lapozható memóriáját).
    Ez felszabadít RAM-ot anélkül, hogy folyamatokat ölne meg.
    
    Visszaad: (sikeres_folyamatok, hibás_folyamatok)
    """
    success_count = 0
    error_count = 0

    kernel32 = ctypes.windll.kernel32

    for proc in psutil.process_iter(['pid', 'name']):
        try:
            pid = proc.info['pid']
            if pid == 0:  # System Idle Process kihagyása
                continue

            handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
            if handle:
                # EmptyWorkingSet: a folyamat memóriáját lapozóba tolja
                result = kernel32.K32EmptyWorkingSet(handle)
                kernel32.CloseHandle(handle)
                if result:
                    success_count += 1
                else:
                    error_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            error_count += 1
        except Exception as e:
            logger.debug(f"Working set hiba: {e}")
            error_count += 1

    if callback:
        freed_estimate = (success_count * 2)  # Durva becslés MB-ban
        callback(f"✓ Working set ürítve: {success_count} folyamat ({freed_estimate}+ MB felszabadítva)")

    return success_count, error_count


# ─────────────────────────────────────────────
#  FOLYAMAT PRIORITÁS
# ─────────────────────────────────────────────

PRIORITY_CLASSES = {
    "idle":         0x00000040,
    "below_normal": 0x00004000,
    "normal":       0x00000020,
    "above_normal": 0x00008000,
    "high":         0x00000080,
    "realtime":     0x00000100,  # VESZÉLYES: rendszer lefagyhat!
}

# Folyamatok, amiket le kell lassítani gaming közben
BACKGROUND_THROTTLE_PROCESSES = [
    "OneDrive.exe",
    "SearchHost.exe",
    "SearchIndexer.exe",
    "MsMpEng.exe",       # Windows Defender (csak below_normal, NE tiltsuk!)
    "svchost.exe",       # Néhányat érintünk
    "RuntimeBroker.exe",
]

CS2_PROCESS_NAMES = ["cs2.exe", "csgo.exe"]


def set_process_priority(process_name: str, priority: str = "high") -> tuple[bool, str]:
    """Beállítja egy folyamat prioritását neve alapján."""
    priority_class = PRIORITY_CLASSES.get(priority)
    if not priority_class:
        return False, f"Ismeretlen prioritás: {priority}"

    found = False
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'].lower() == process_name.lower():
            try:
                handle = ctypes.windll.kernel32.OpenProcess(
                    PROCESS_ALL_ACCESS, False, proc.info['pid']
                )
                if handle:
                    ctypes.windll.kernel32.SetPriorityClass(handle, priority_class)
                    ctypes.windll.kernel32.CloseHandle(handle)
                    found = True
            except Exception as e:
                return False, str(e)

    if found:
        return True, f"{process_name} prioritás -> {priority}"
    return False, f"{process_name} nem fut jelenleg"


def boost_cs2_priority(callback=None) -> list[str]:
    """
    Ha fut a CS2, beállítja HIGH prioritásra.
    A háttér folyamatokat BELOW_NORMAL-ra teszi.
    """
    log = []

    def log_msg(msg):
        log.append(msg)
        if callback:
            callback(msg)

    # CS2 keresése
    cs2_found = False
    for name in CS2_PROCESS_NAMES:
        ok, msg = set_process_priority(name, "high")
        if ok:
            log_msg(f"🎮 {msg}")
            cs2_found = True

    if not cs2_found:
        log_msg("⚠ CS2 nem fut - prioritás nem állítható. Indítsd el a játékot!")

    # Háttér folyamatok lassítása
    for proc_name in BACKGROUND_THROTTLE_PROCESSES:
        ok, msg = set_process_priority(proc_name, "below_normal")
        if ok:
            log_msg(f"   ↓ {msg}")

    return log


def get_top_ram_consumers(n: int = 8) -> list[dict]:
    """Visszaadja a legtöbb RAM-ot fogyasztó folyamatokat."""
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            mem_mb = proc.info['memory_info'].rss // (1024 * 1024)
            procs.append({
                "name":   proc.info['name'],
                "pid":    proc.info['pid'],
                "mem_mb": mem_mb,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    procs.sort(key=lambda x: x['mem_mb'], reverse=True)
    return procs[:n]
