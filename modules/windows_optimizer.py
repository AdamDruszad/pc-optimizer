"""
windows_optimizer.py
Windows szolgáltatások ideiglenes letiltása + High Performance energiaséma.
FONTOS: Admin jogok szükségesek a futtatáshoz.
"""

import subprocess
import ctypes
import logging
from utils.state_manager import (
    TARGET_SERVICES, save_original_state, load_original_state,
    has_saved_state, delete_saved_state
)

logger = logging.getLogger(__name__)

# Windows built-in power plan GUID-ok
POWER_PLANS = {
    "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "balanced":         "381b4222-f694-41f0-9685-ff5bb260df2e",
    "power_saver":      "a1841308-3541-4fab-bc81-f71556f20b4a",
}


def is_admin() -> bool:
    """Ellenőrzi, hogy admin jogokkal fut-e az alkalmazás."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def run_command(args: list[str], timeout: int = 10) -> tuple[bool, str]:
    """
    Futtat egy rendszerparancsot, visszaad (sikeres, kimenet) tuple-t.
    """
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW  # Ne villogjon cmd ablak
        )
        success = result.returncode == 0
        output = result.stdout + result.stderr
        return success, output
    except subprocess.TimeoutExpired:
        return False, "Timeout: a parancs nem válaszolt."
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────
#  ENERGIASÉMA
# ─────────────────────────────────────────────

def get_current_power_plan() -> str:
    """Visszaadja az aktív energiaséma GUID-ját."""
    ok, out = run_command(["powercfg", "/getactivescheme"])
    if ok:
        # Kimenet: "Power Scheme GUID: 8c5e7fda-... (High performance)"
        for part in out.split():
            if "-" in part and len(part) == 36:
                return part
    return "unknown"


def set_power_plan(plan_name: str = "high_performance") -> tuple[bool, str]:
    guid = POWER_PLANS.get(plan_name)
    if not guid:
        return False, f"Ismeretlen energiaséma: {plan_name}"
    ok, out = run_command(["powercfg", "/setactive", guid])
    if ok:
        return True, f"Energiaséma beállítva: {plan_name}"
    return False, f"Hiba az energiaséma beállításakor: {out}"


# ─────────────────────────────────────────────
#  SZOLGÁLTATÁSOK
# ─────────────────────────────────────────────

def stop_service(service_name: str) -> tuple[bool, str]:
    ok, out = run_command(["sc", "stop", service_name])
    return ok, out


def disable_service(service_name: str) -> tuple[bool, str]:
    """START_TYPE -> DISABLED"""
    ok, out = run_command(["sc", "config", service_name, "start=", "disabled"])
    return ok, out


def enable_service(service_name: str, start_type: str = "demand") -> tuple[bool, str]:
    """
    Visszaállítja a service-t.
    start_type: 'auto', 'demand' (manual), 'disabled'
    """
    # Fordítjuk az elmentett Windows-os formátumot sc parancs formátumra
    type_map = {
        "AUTO_START":     "auto",
        "DEMAND_START":   "demand",
        "DISABLED":       "disabled",
        "BOOT_START":     "boot",
        "SYSTEM_START":   "system",
    }
    sc_type = type_map.get(start_type, "demand")
    ok, out = run_command(["sc", "config", service_name, "start=", sc_type])
    return ok, out


def start_service(service_name: str) -> tuple[bool, str]:
    ok, out = run_command(["sc", "start", service_name])
    return ok, out


# ─────────────────────────────────────────────
#  BOOST & RESTORE FŐFUNKCIÓK
# ─────────────────────────────────────────────

def apply_boost(callback=None) -> list[str]:
    """
    1. Elmenti az eredeti állapotot
    2. High Performance energiaséma
    3. Letiltja a target service-eket
    
    callback(message: str) -> None  opcionális progress visszajelzés
    
    Visszaad egy log listát.
    """
    log = []

    def log_msg(msg: str):
        log.append(msg)
        logger.info(msg)
        if callback:
            callback(msg)

    if not is_admin():
        log_msg("❌ Admin jogok szükségesek! Indítsd újra rendszergazdaként.")
        return log

    # 1. Állapot mentése
    log_msg("💾 Eredeti állapot mentése...")
    save_original_state()
    log_msg("   ✓ Mentve: original_state.json")

    # 2. High Performance energiaséma
    log_msg("⚡ High Performance energiaséma beállítása...")
    ok, msg = set_power_plan("high_performance")
    log_msg(f"   {'✓' if ok else '✗'} {msg}")

    # 3. Szolgáltatások letiltása
    log_msg("🔧 Felesleges szolgáltatások leállítása...")
    for svc in TARGET_SERVICES:
        ok_stop, stop_out = stop_service(svc)
        ok_dis,  dis_out  = disable_service(svc)

        if ok_dis:
            # Disable sikerült — ez a fontos. Stop failure nem baj
            # (pl. már állt, vagy protected process volt)
            log_msg(f"   ✓ {svc}: letiltva")
        else:
            # Disable is meghiúsult — valódi hiba
            err = dis_out.strip().splitlines()[0] if dis_out.strip() else "ismeretlen hiba"
            log_msg(f"   ✗ {svc}: nem sikerült letiltani ({err})")

    log_msg("🚀 Boost aktív! Jó játékot!")
    return log


def restore_original(callback=None) -> list[str]:
    """
    Visszaállítja az eredeti Windows állapotot a mentett JSON alapján.
    """
    log = []

    def log_msg(msg: str):
        log.append(msg)
        logger.info(msg)
        if callback:
            callback(msg)

    if not is_admin():
        log_msg("❌ Admin jogok szükségesek!")
        return log

    if not has_saved_state():
        log_msg("⚠ Nincs mentett állapot. Először aktiváld a Boost módot!")
        return log

    state = load_original_state()
    log_msg("🔄 Visszaállítás az eredeti állapotra...")

    # Energiaséma visszaállítása Balanced-ra
    ok, msg = set_power_plan("balanced")
    log_msg(f"   {'✓' if ok else '✗'} Balanced energiaséma visszaállítva")

    # Szolgáltatások visszaállítása
    for svc, info in state.items():
        original_type = info.get("start_type", "DEMAND_START")
        original_running = info.get("running", "STOPPED")

        ok_en, _ = enable_service(svc, original_type)

        # Ha eredetileg futott, indítsuk el
        if original_running == "RUNNING" and original_type != "DISABLED":
            start_service(svc)

        status = "✓" if ok_en else "⚠"
        log_msg(f"   {status} {svc}: visszaállítva ({original_type})")

    delete_saved_state()
    log_msg("✅ Visszaállítás kész!")
    return log
