"""
hw_optimizer.py  —  GameBooster v2.0
Hardware-tudatos optimalizáló.

A detektált hardver + aktív profil alapján alkalmazza a megfelelő
Windows-szintű optimalizálásokat. Különbséget tesz Intel iGPU,
AMD iGPU és Nvidia GPU között.
"""

import subprocess
import ctypes
import logging
import time
from modules.hardware_detector import HardwareProfile, GpuType, PowerState
from modules.profile_manager   import BoostProfile
from utils.state_manager       import save_original_state, load_original_state
from utils.state_manager       import has_saved_state, delete_saved_state

logger = logging.getLogger(__name__)

# Windows energiaséma GUID-ok
POWER_PLANS = {
    "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "balanced":         "381b4222-f694-41f0-9685-ff5bb260df2e",
    "power_saver":      "a1841308-3541-4fab-bc81-f71556f20b4a",
}

# Háttér folyamatok amiket lelassítunk (below_normal prioritás)
BG_THROTTLE = [
    "OneDrive.exe", "SearchHost.exe", "SearchIndexer.exe",
    "MsMpEng.exe", "RuntimeBroker.exe", "SgrmBroker.exe",
]


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run(args: list[str], timeout: int = 10) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            args, capture_output=True, text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return r.returncode == 0, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def _set_power_plan(plan_name: str) -> tuple[bool, str]:
    guid = POWER_PLANS.get(plan_name, POWER_PLANS["high_performance"])
    ok, out = _run(["powercfg", "/setactive", guid])
    plan_display = {
        "high_performance": "High Performance",
        "balanced":         "Balanced",
        "power_saver":      "Power Saver",
    }.get(plan_name, plan_name)
    return ok, f"Energiaséma → {plan_display}"


def _stop_service(svc: str) -> tuple[bool, str]:
    _run(["sc", "stop", svc])
    ok, _ = _run(["sc", "config", svc, "start=", "disabled"])
    return ok, svc


def _restore_service(svc: str, start_type: str) -> tuple[bool, str]:
    TYPE_MAP = {
        "AUTO_START":   "auto",
        "DEMAND_START": "demand",
        "DISABLED":     "disabled",
        "BOOT_START":   "boot",
        "SYSTEM_START": "system",
    }
    sc_type = TYPE_MAP.get(start_type, "demand")
    ok, _   = _run(["sc", "config", svc, "start=", sc_type])
    if ok and start_type != "DISABLED":
        _run(["sc", "start", svc])
    return ok, svc


def _set_proc_priority(name: str, level: str) -> bool:
    import psutil
    LEVELS = {
        "below_normal": 0x00004000,
        "normal":       0x00000020,
        "high":         0x00000080,
    }
    pclass = LEVELS.get(level, 0x00000020)
    found  = False
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"].lower() == name.lower():
                h = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, proc.info["pid"])
                if h:
                    ctypes.windll.kernel32.SetPriorityClass(h, pclass)
                    ctypes.windll.kernel32.CloseHandle(h)
                    found = True
        except Exception:
            pass
    return found


# ─────────────────────────────────────────────
#  HARDWARE-SPECIFIKUS EXTRA LÉPÉSEK
# ─────────────────────────────────────────────

def _apply_igpu_extras(hw: HardwareProfile, callback):
    """Intel iGPU-specifikus optimalizálás."""
    callback("   🖥 Intel iGPU — Working Set ürítés GPU shared pool növeléséhez...")
    import psutil as _psutil
    kernel32 = ctypes.windll.kernel32
    freed = 0
    for proc in _psutil.process_iter(["pid"]):
        try:
            h = kernel32.OpenProcess(0x1F0FFF, False, proc.info["pid"])
            if h:
                kernel32.K32EmptyWorkingSet(h)
                kernel32.CloseHandle(h)
                freed += 1
        except Exception:
            pass
    callback(f"   ✓ {freed} folyamat working set ürítve (GPU shared pool növelve)")


def _apply_amd_igpu_extras(hw: HardwareProfile, callback):
    """AMD iGPU-specifikus optimalizálás."""
    callback("   🖥 AMD iGPU — RAM felszabadítás a GPU shared pool számára...")
    _apply_igpu_extras(hw, callback)


def _apply_nvidia_extras(hw: HardwareProfile, callback):
    """Nvidia GPU-specifikus javaslat."""
    callback("   🎮 Nvidia dedikált GPU detektálva")
    callback("   💡 Javaslat: Nvidia Control Panel → Power Management → Maximum Performance")


# ─────────────────────────────────────────────
#  BOOST ALKALMAZÁSA
# ─────────────────────────────────────────────

def apply_boost(
    hw: HardwareProfile,
    profile: BoostProfile,
    callback=None
) -> list[str]:
    """
    Alkalmazza a Boost-ot a megadott hardver profil és Boost profil alapján.
    
    hw:       Detektált hardver (HardwareProfile)
    profile:  Aktív Boost profil (BoostProfile)
    callback: GUI frissítő callback (opcionális)
    """
    log = []

    def msg(m: str):
        log.append(m)
        logger.info(m)
        if callback:
            callback(m)

    if not is_admin():
        msg("❌ Admin jogok szükségesek! Indítsd újra rendszergazdaként.")
        return log

    msg(f"⚡ Boost aktiválás — profil: {profile.name}")
    msg(f"   Hardver: {hw.gpu_type.value} | {hw.cpu_brand} | {hw.ram_total_gb}GB RAM")

    # 1. Állapot mentése
    msg("\n💾 Eredeti Windows állapot mentése...")
    try:
        save_original_state()
        msg("   ✓ Mentve: original_state.json")
    except Exception as e:
        msg(f"   ⚠ Mentési hiba: {e}")

    # 2. Energiaséma
    msg(f"\n⚡ Energiaséma beállítása...")
    ok, info = _set_power_plan(profile.power_plan)
    msg(f"   {'✓' if ok else '✗'} {info}")

    # 3. Szolgáltatások leállítása
    if profile.stop_services:
        msg(f"\n🔧 Szolgáltatások leállítása ({len(profile.stop_services)} db)...")
        for svc in profile.stop_services:
            ok, name = _stop_service(svc)
            msg(f"   {'✓' if ok else '⚠'} {name}")

    # 4. Hardware-specifikus lépések
    msg(f"\n🖥 GPU-specifikus optimalizálás ({hw.gpu_type.value})...")
    if hw.gpu_type == GpuType.INTEL_IGPU:
        _apply_igpu_extras(hw, msg)
    elif hw.gpu_type == GpuType.AMD_IGPU:
        _apply_amd_igpu_extras(hw, msg)
    elif hw.gpu_type == GpuType.NVIDIA:
        _apply_nvidia_extras(hw, msg)

    # 5. Háttér folyamatok lassítása
    if profile.throttle_background:
        msg("\n🐢 Háttér folyamatok lassítása...")
        for proc in BG_THROTTLE:
            if _set_proc_priority(proc, "below_normal"):
                msg(f"   ↓ {proc} → below_normal")

    msg(f"\n✅ Boost aktív! [{profile.icon} {profile.name}]")
    return log


# ─────────────────────────────────────────────
#  VISSZAÁLLÍTÁS
# ─────────────────────────────────────────────

def restore_original(callback=None) -> list[str]:
    """Visszaállítja az eredeti Windows állapotot."""
    log = []

    def msg(m: str):
        log.append(m)
        logger.info(m)
        if callback:
            callback(m)

    if not is_admin():
        msg("❌ Admin jogok szükségesek!")
        return log

    if not has_saved_state():
        msg("⚠ Nincs mentett állapot — előbb aktiváld a Boost-ot!")
        return log

    state = load_original_state()
    msg("🔄 Visszaállítás az eredeti Windows állapotra...")

    # Balanced energiaséma
    ok, info = _set_power_plan("balanced")
    msg(f"   {'✓' if ok else '✗'} {info}")

    # Szolgáltatások visszaállítása
    for svc, info in state.items():
        ok, name = _restore_service(svc, info.get("start_type", "DEMAND_START"))
        msg(f"   {'✓' if ok else '⚠'} {name} visszaállítva")

    delete_saved_state()
    msg("✅ Visszaállítás kész!")
    return log
