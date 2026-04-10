"""
registry_tweaks.py  —  GameBooster v2.1
Windows registry játék optimalizálási tweakek.

Minden tweak:
  - Pontos registry útvonallal dokumentálva
  - Az eredeti érték mentésével (visszaállítható!)
  - Forrással és mérhető hatással annotálva

Kategóriák:
  1. Játék ütemezési prioritás (Scheduling Category, GPU priority)
  2. HAGS — Hardware Accelerated GPU Scheduling
  3. Windows Game Mode
  4. Xbox Game Bar letiltás
  5. Nagle-algoritmus letiltás (TCP latencia)
  6. Mouse Input latencia (raw input jitter)
  7. FSO — Fullscreen Optimizations per-exe
"""

import winreg
import logging
import json
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

def _get_snapshot_file() -> str:
    try:
        from gui.app_paths import registry_snapshot
        return registry_snapshot()
    except Exception:
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "registry_snapshot.json"
        )

# Kompatibilitás
REGISTRY_SNAPSHOT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "registry_snapshot.json"
)


# ─────────────────────────────────────────────
#  SEGÉD FÜGGVÉNYEK
# ─────────────────────────────────────────────

def _reg_read(hive, key_path: str, value_name: str):
    """
    Registry értéket olvas. Visszaad (érték, típus) tuple-t,
    vagy (None, None)-t ha nem létezik.
    """
    try:
        hkey = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        val, typ = winreg.QueryValueEx(hkey, value_name)
        winreg.CloseKey(hkey)
        return val, typ
    except FileNotFoundError:
        return None, None
    except Exception as e:
        logger.debug(f"Registry olvasási hiba {key_path}\\{value_name}: {e}")
        return None, None


def _reg_write(hive, key_path: str, value_name: str,
               value, reg_type=winreg.REG_DWORD) -> bool:
    """Registry értéket ír. Létrehozza a kulcsot ha nem létezik."""
    try:
        hkey = winreg.CreateKeyEx(hive, key_path, 0,
                                   winreg.KEY_SET_VALUE | winreg.KEY_CREATE_SUB_KEY)
        winreg.SetValueEx(hkey, value_name, 0, reg_type, value)
        winreg.CloseKey(hkey)
        return True
    except Exception as e:
        logger.error(f"Registry írási hiba {key_path}\\{value_name}: {e}")
        return False


def _reg_delete_value(hive, key_path: str, value_name: str) -> bool:
    """Registry értéket töröl (ha létezik)."""
    try:
        hkey = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(hkey, value_name)
        winreg.CloseKey(hkey)
        return True
    except FileNotFoundError:
        return True   # Nem létezett — sikeres
    except Exception as e:
        logger.debug(f"Registry törlési hiba: {e}")
        return False


# ─────────────────────────────────────────────
#  SNAPSHOT (visszaállításhoz)
# ─────────────────────────────────────────────

def _save_snapshot(snapshot: dict):
    try:
        path = _get_snapshot_file()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Registry snapshot mentési hiba: {e}")


def _load_snapshot() -> dict | None:
    path = _get_snapshot_file()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _delete_snapshot():
    path = _get_snapshot_file()
    if os.path.exists(path):
        os.remove(path)


def has_registry_snapshot() -> bool:
    return os.path.exists(_get_snapshot_file())


# ─────────────────────────────────────────────
#  1. JÁTÉK ÜTEMEZÉSI PRIORITÁS
#
#  Forrás: Microsoft dokumentáció + Razer Cortex reverse engineering
#  Hatás: +3-10% FPS, stabilabb frame time
#
#  Registry kulcs:
#  HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games
#
#  Értékek:
#    Scheduling Category: "Medium" → "High"
#    GPU Priority:        2        → 8
#    Priority:            2        → 6
#    Background Only:     "True"   → "False"
#    SFIO Priority:       "Normal" → "High"
#    Clock Rate:          10000    → 10000 (marad)
#    Affinity:            0        → 0 (marad)
# ─────────────────────────────────────────────

_GAMES_KEY = (
    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    r"\Multimedia\SystemProfile\Tasks\Games"
)

def apply_game_scheduling_priority(snapshot: dict, callback) -> bool:
    """
    Játék ütemezési prioritás maximalizálása.
    Az eredeti értékeket a snapshot-ba menti visszaállításhoz.
    """
    callback("   🎯 Játék ütemezési prioritás beállítása...")

    tweaks = [
        # (value_name, new_value, reg_type, leírás)
        ("Scheduling Category", "High",   winreg.REG_SZ,   "Scheduling: Medium → High"),
        ("GPU Priority",        8,        winreg.REG_DWORD, "GPU Priority: 2 → 8"),
        ("Priority",            6,        winreg.REG_DWORD, "Priority: 2 → 6"),
        ("Background Only",     "False",  winreg.REG_SZ,   "Background Only: True → False"),
        ("SFIO Priority",       "High",   winreg.REG_SZ,   "SFIO Priority: Normal → High"),
    ]

    snap_section = {}
    all_ok = True

    for name, new_val, reg_type, desc in tweaks:
        # Eredeti érték mentése
        orig_val, orig_type = _reg_read(winreg.HKEY_LOCAL_MACHINE, _GAMES_KEY, name)
        snap_section[name] = {
            "value": orig_val,
            "type":  orig_type,
            "key":   _GAMES_KEY,
            "hive":  "HKLM"
        }
        # Új érték beírása
        ok = _reg_write(winreg.HKEY_LOCAL_MACHINE, _GAMES_KEY, name, new_val, reg_type)
        status = "✓" if ok else "✗"
        callback(f"      {status} {desc}")
        if not ok:
            all_ok = False

    snapshot["game_scheduling"] = snap_section
    return all_ok


# ─────────────────────────────────────────────
#  2. SYSTEM PROFILE TWEAKS
#
#  Forrás: Windows Multimedia Class Scheduler
#  Hatás: CPU prioritás finomhangolás gaming közben
#
#  HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile
#    SystemResponsiveness: 20 → 0  (0 = maximum gaming, 20 = default)
#    NetworkThrottlingIndex: 10 → 0xffffffff (ffffffff = letiltja a throttling-ot)
# ─────────────────────────────────────────────

_SYSTEM_PROFILE_KEY = (
    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
)

def apply_system_profile_tweaks(snapshot: dict, callback) -> bool:
    callback("   ⚙ Rendszer profil optimalizálás...")

    tweaks = [
        ("SystemResponsiveness",    0,          winreg.REG_DWORD, "SystemResponsiveness: 20 → 0"),
        ("NetworkThrottlingIndex",  0xffffffff, winreg.REG_DWORD, "NetworkThrottling: letiltva"),
    ]

    snap_section = {}
    all_ok = True

    for name, new_val, reg_type, desc in tweaks:
        orig_val, orig_type = _reg_read(
            winreg.HKEY_LOCAL_MACHINE, _SYSTEM_PROFILE_KEY, name)
        snap_section[name] = {"value": orig_val, "type": orig_type,
                               "key": _SYSTEM_PROFILE_KEY, "hive": "HKLM"}
        ok = _reg_write(winreg.HKEY_LOCAL_MACHINE, _SYSTEM_PROFILE_KEY,
                        name, new_val, reg_type)
        callback(f"      {'✓' if ok else '✗'} {desc}")
        if not ok:
            all_ok = False

    snapshot["system_profile"] = snap_section
    return all_ok


# ─────────────────────────────────────────────
#  3. HAGS — Hardware Accelerated GPU Scheduling
#
#  Forrás: Microsoft DirectX blog, prosettings.net 2025
#  Hatás: +2-8% FPS, kisebb frame time jitter
#  Követelmény: Windows 10 2004+, WDDM 2.7+ driver
#
#  HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers
#    HwSchMode: 1 (letiltva) → 2 (engedélyezve)
#
#  MEGJEGYZÉS: Újraindítás szükséges a hatáshoz!
# ─────────────────────────────────────────────

_GRAPHICS_KEY = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"

def get_hags_status() -> str:
    """
    Visszaadja a HAGS aktuális állapotát.
    "enabled" | "disabled" | "unknown"
    """
    val, _ = _reg_read(winreg.HKEY_LOCAL_MACHINE, _GRAPHICS_KEY, "HwSchMode")
    if val == 2:
        return "enabled"
    elif val == 1:
        return "disabled"
    return "unknown"


def apply_hags(snapshot: dict, callback, enable: bool = True) -> bool:
    """
    HAGS engedélyezése/letiltása.
    enable=True → 2 (on), enable=False → 1 (off)
    """
    new_val = 2 if enable else 1
    action  = "bekapcsolás" if enable else "kikapcsolás"
    callback(f"   🖥 HAGS {action}...")

    orig_val, orig_type = _reg_read(
        winreg.HKEY_LOCAL_MACHINE, _GRAPHICS_KEY, "HwSchMode")
    snapshot["hags"] = {
        "HwSchMode": {"value": orig_val, "type": orig_type,
                      "key": _GRAPHICS_KEY, "hive": "HKLM"}
    }

    ok = _reg_write(winreg.HKEY_LOCAL_MACHINE, _GRAPHICS_KEY,
                    "HwSchMode", new_val, winreg.REG_DWORD)
    if ok:
        callback(f"      ✓ HAGS {'engedélyezve' if enable else 'letiltva'}"
                 f" (újraindítás szükséges!)")
    else:
        callback(f"      ✗ HAGS beállítás sikertelen")
    return ok


# ─────────────────────────────────────────────
#  4. WINDOWS GAME MODE
#
#  Hatás: Windows automatikusan prioritizálja az aktív játékot,
#  korlátozza a háttér folyamatok erőforrás-használatát.
#
#  HKCU\Software\Microsoft\GameBar
#    AutoGameModeEnabled: 0/1
#    AllowAutoGameMode:   0/1
# ─────────────────────────────────────────────

_GAMEBAR_KEY = r"Software\Microsoft\GameBar"

def get_game_mode_status() -> bool:
    val, _ = _reg_read(winreg.HKEY_CURRENT_USER, _GAMEBAR_KEY, "AutoGameModeEnabled")
    return val == 1


def apply_game_mode(snapshot: dict, callback, enable: bool = True) -> bool:
    callback("   🎮 Windows Game Mode beállítása...")

    snap_section = {}
    all_ok = True

    for name in ["AutoGameModeEnabled", "AllowAutoGameMode"]:
        orig_val, orig_type = _reg_read(winreg.HKEY_CURRENT_USER, _GAMEBAR_KEY, name)
        snap_section[name] = {"value": orig_val, "type": orig_type,
                               "key": _GAMEBAR_KEY, "hive": "HKCU"}
        ok = _reg_write(winreg.HKEY_CURRENT_USER, _GAMEBAR_KEY,
                        name, 1 if enable else 0, winreg.REG_DWORD)
        if not ok:
            all_ok = False

    snapshot["game_mode"] = snap_section
    action = "engedélyezve" if enable else "letiltva"
    callback(f"      {'✓' if all_ok else '✗'} Windows Game Mode {action}")
    return all_ok


# ─────────────────────────────────────────────
#  5. XBOX GAME BAR LETILTÁS
#
#  Forrás: TechPowerUp, Digital Foundry
#  Hatás: +2-5% FPS (háttérben fut, erőforrást eszik)
#
#  HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR
#    AppCaptureEnabled: 1 → 0
#  HKLM\SOFTWARE\Policies\Microsoft\Windows\GameDVR
#    AllowGameDVR: 1 → 0
# ─────────────────────────────────────────────

_GAMEDVR_HKCU_KEY  = r"Software\Microsoft\Windows\CurrentVersion\GameDVR"
_GAMEDVR_HKLM_KEY  = r"SOFTWARE\Policies\Microsoft\Windows\GameDVR"
_GAMEBAR_HKCU_KEY2 = r"Software\Microsoft\GameBar"

def get_xbox_gamebar_status() -> bool:
    """True = engedélyezve (default), False = letiltva."""
    val, _ = _reg_read(winreg.HKEY_CURRENT_USER, _GAMEDVR_HKCU_KEY, "AppCaptureEnabled")
    return val != 0  # 0 = letiltva


def apply_xbox_gamebar(snapshot: dict, callback, disable: bool = True) -> bool:
    """
    disable=True → letiltja az Xbox Game Bar-t
    disable=False → visszaengedélyezi
    """
    callback("   🎮 Xbox Game Bar / DVR beállítása...")
    snap_section = {}
    all_ok = True

    new_capture = 0 if disable else 1
    new_bar     = 0 if disable else 1

    # AppCaptureEnabled (HKCU)
    orig, otyp = _reg_read(winreg.HKEY_CURRENT_USER, _GAMEDVR_HKCU_KEY, "AppCaptureEnabled")
    snap_section["AppCaptureEnabled"] = {"value": orig, "type": otyp,
                                          "key": _GAMEDVR_HKCU_KEY, "hive": "HKCU"}
    ok = _reg_write(winreg.HKEY_CURRENT_USER, _GAMEDVR_HKCU_KEY,
                    "AppCaptureEnabled", new_capture, winreg.REG_DWORD)
    if not ok:
        all_ok = False

    # AllowGameDVR (HKLM — policy)
    orig, otyp = _reg_read(winreg.HKEY_LOCAL_MACHINE, _GAMEDVR_HKLM_KEY, "AllowGameDVR")
    snap_section["AllowGameDVR"] = {"value": orig, "type": otyp,
                                     "key": _GAMEDVR_HKLM_KEY, "hive": "HKLM"}
    ok = _reg_write(winreg.HKEY_LOCAL_MACHINE, _GAMEDVR_HKLM_KEY,
                    "AllowGameDVR", new_capture, winreg.REG_DWORD)
    if not ok:
        all_ok = False

    # UseNexusForGameBarEnabled (HKCU)
    orig, otyp = _reg_read(winreg.HKEY_CURRENT_USER, _GAMEBAR_HKCU_KEY2,
                            "UseNexusForGameBarEnabled")
    snap_section["UseNexusForGameBarEnabled"] = {"value": orig, "type": otyp,
                                                  "key": _GAMEBAR_HKCU_KEY2, "hive": "HKCU"}
    ok = _reg_write(winreg.HKEY_CURRENT_USER, _GAMEBAR_HKCU_KEY2,
                    "UseNexusForGameBarEnabled", new_bar, winreg.REG_DWORD)

    snapshot["xbox_gamebar"] = snap_section
    action = "letiltva" if disable else "visszaengedélyezve"
    callback(f"      {'✓' if all_ok else '✗'} Xbox Game Bar / DVR {action}")
    return all_ok


# ─────────────────────────────────────────────
#  6. NAGLE-ALGORITMUS LETILTÁS (TCP latencia)
#
#  Forrás: Battlestate Games (Tarkov), Valve network guide
#  Hatás: -5-15ms online játék latencia
#
#  Mi a Nagle-algoritmus?
#  TCP alapból kis csomagokat összegyűjt mielőtt elküldi (buffering).
#  Online játéknál ez késleltetést okoz. Letiltással minden csomag
#  azonnal el van küldve.
#
#  Registry:
#  HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\{adapter_GUID}\
#    TcpAckFrequency: 1 → 1 (immediate ACK)
#    TCPNoDelay:      0 → 1 (Nagle letiltva)
# ─────────────────────────────────────────────

_TCPIP_INTERFACES_KEY = (
    r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
)

def _get_network_adapter_guids() -> list[str]:
    """Az összes TCP/IP interfész GUID-ját adja vissza."""
    guids = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             _TCPIP_INTERFACES_KEY, 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, i)
                guids.append(subkey_name)
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)
    except Exception as e:
        logger.debug(f"Adapter GUID lekérdezési hiba: {e}")
    return guids


def apply_nagle_disable(snapshot: dict, callback, disable: bool = True) -> bool:
    """
    Nagle-algoritmus letiltása az összes aktív hálózati adapteren.
    disable=True → TCPNoDelay=1, TcpAckFrequency=1
    disable=False → töröl (Windows default-ra visszaáll)
    """
    callback("   🌐 Nagle-algoritmus letiltása (TCP latencia csökkentés)...")

    guids = _get_network_adapter_guids()
    if not guids:
        callback("      ⚠ Nem találhatók hálózati adapterek")
        return False

    snap_section = {}
    affected = 0

    for guid in guids:
        iface_key = f"{_TCPIP_INTERFACES_KEY}\\{guid}"

        # Csak azokat az adaptereket kezeljük amiknek van IP-jük
        dh_ip, _ = _reg_read(winreg.HKEY_LOCAL_MACHINE, iface_key, "DhcpIPAddress")
        st_ip, _ = _reg_read(winreg.HKEY_LOCAL_MACHINE, iface_key, "IPAddress")
        has_ip   = (dh_ip and dh_ip != "0.0.0.0") or (st_ip and st_ip not in [None, "0.0.0.0", ""])

        if not has_ip:
            continue

        for val_name in ["TcpAckFrequency", "TCPNoDelay"]:
            orig, otyp = _reg_read(winreg.HKEY_LOCAL_MACHINE, iface_key, val_name)
            snap_key   = f"{guid}_{val_name}"
            snap_section[snap_key] = {"value": orig, "type": otyp,
                                       "key": iface_key, "hive": "HKLM"}

            if disable:
                _reg_write(winreg.HKEY_LOCAL_MACHINE, iface_key,
                           val_name, 1, winreg.REG_DWORD)
            else:
                _reg_delete_value(winreg.HKEY_LOCAL_MACHINE, iface_key, val_name)
        affected += 1

    snapshot["nagle"] = snap_section
    if affected > 0:
        action = "letiltva" if disable else "visszaállítva (default)"
        callback(f"      ✓ Nagle {action} — {affected} adapteren")
        return True
    else:
        callback("      ⚠ Nem találhatók aktív hálózati adapterek IP-vel")
        return False


# ─────────────────────────────────────────────
#  7. MOUSE INPUT LATENCIA CSÖKKENTÉS
#
#  Forrás: Mark Russinovich (MouseDataQueueSize),
#          prosettings.net egér latencia guide
#  Hatás: Kisebb egér input jitter (1-2ms)
#
#  HKLM\SYSTEM\CurrentControlSet\Services\mouclass\Parameters
#    MouseDataQueueSize: 100 (default) → 20 (kisebb buffer = kisebb latencia)
# ─────────────────────────────────────────────

_MOUSE_KEY = r"SYSTEM\CurrentControlSet\Services\mouclass\Parameters"

def apply_mouse_latency(snapshot: dict, callback) -> bool:
    callback("   🖱 Egér input latencia optimalizálás...")

    orig, otyp = _reg_read(winreg.HKEY_LOCAL_MACHINE, _MOUSE_KEY, "MouseDataQueueSize")
    snapshot["mouse_latency"] = {
        "MouseDataQueueSize": {"value": orig, "type": otyp,
                               "key": _MOUSE_KEY, "hive": "HKLM"}
    }
    ok = _reg_write(winreg.HKEY_LOCAL_MACHINE, _MOUSE_KEY,
                    "MouseDataQueueSize", 20, winreg.REG_DWORD)
    callback(f"      {'✓' if ok else '✗'} MouseDataQueueSize: 100 → 20"
             " (kisebb buffer = gyorsabb input)")
    return ok


# ─────────────────────────────────────────────
#  8. WIN32 ELŐTÉR PRIORITÁS BOOST
#
#  Forrás: Microsoft KB315827, djdallmann/GamingPCSetup
#  Hatás: +3-8% FPS — az előtér folyamat (játék) több CPU időt kap
#
#  HKLM\SYSTEM\ControlSet001\Control\PriorityControl
#    Win32PrioritySeparation:
#      0x02 = szerver mód (nincs boost)
#      0x18 = 24 = Windows desktop default
#      0x26 = 38 = maximum előtér boost (gaming optimális)
# ─────────────────────────────────────────────

_PRIORITY_CONTROL_KEY = r"SYSTEM\ControlSet001\Control\PriorityControl"

def apply_win32_priority(snapshot: dict, callback) -> bool:
    callback("   🚀 Win32 előtér prioritás boost (CPU gaming mód)...")

    orig, otyp = _reg_read(
        winreg.HKEY_LOCAL_MACHINE, _PRIORITY_CONTROL_KEY, "Win32PrioritySeparation")
    snapshot["win32_priority"] = {
        "Win32PrioritySeparation": {
            "value": orig, "type": otyp,
            "key": _PRIORITY_CONTROL_KEY, "hive": "HKLM"
        }
    }
    # 0x26 = 38 = maximum előtér boost
    ok = _reg_write(winreg.HKEY_LOCAL_MACHINE, _PRIORITY_CONTROL_KEY,
                    "Win32PrioritySeparation", 0x26, winreg.REG_DWORD)
    old_str = f"0x{orig:02X} ({orig})" if isinstance(orig, int) else str(orig)
    callback(f"      {'✓' if ok else '✗'} Win32PrioritySeparation: "
             f"{old_str} → 0x26 (38) — max előtér CPU boost")
    return ok


# ─────────────────────────────────────────────
#  FŐ APPLY / RESTORE FÜGGVÉNYEK
# ─────────────────────────────────────────────

@dataclass
class RegistryTweakConfig:
    """Melyik tweakeket alkalmazzuk."""
    game_scheduling:  bool = True   # Játék ütemezési prioritás (MMCSS Games)
    system_profile:   bool = True   # SystemResponsiveness, NetworkThrottling
    win32_priority:   bool = True   # Win32PrioritySeparation CPU boost
    hags:             bool = True   # Hardware Accelerated GPU Scheduling
    game_mode:        bool = True   # Windows Game Mode
    disable_gamebar:  bool = True   # Xbox Game Bar letiltás
    nagle:            bool = True   # Nagle-algoritmus letiltás
    mouse_latency:    bool = False  # Egér latencia (újraindítás kell)


def apply_registry_tweaks(
    config: RegistryTweakConfig,
    callback=None
) -> list[str]:
    """
    Registry tweakek alkalmazása a megadott konfiguráció szerint.
    Minden módosítás előtt snapshot-ot ment visszaállításhoz.
    Visszaad egy log listát.
    """
    log  = []
    snap = _load_snapshot() or {}

    def msg(m: str):
        log.append(m)
        logger.info(m)
        if callback:
            callback(m)

    msg("🔧 Registry játék optimalizálás...")

    results = []

    if config.game_scheduling:
        ok = apply_game_scheduling_priority(snap, msg)
        results.append(("Játék ütemezési prioritás", ok))

    if config.system_profile:
        ok = apply_system_profile_tweaks(snap, msg)
        results.append(("Rendszer profil tweakek", ok))

    if config.win32_priority:
        ok = apply_win32_priority(snap, msg)
        results.append(("Win32 előtér CPU boost", ok))

    if config.hags:
        current = get_hags_status()
        if current != "enabled":
            ok = apply_hags(snap, msg, enable=True)
            results.append(("HAGS bekapcsolás", ok))
        else:
            msg("   ✓ HAGS már be van kapcsolva")

    if config.game_mode:
        if not get_game_mode_status():
            ok = apply_game_mode(snap, msg, enable=True)
            results.append(("Windows Game Mode", ok))
        else:
            msg("   ✓ Windows Game Mode már aktív")

    if config.disable_gamebar:
        if get_xbox_gamebar_status():
            ok = apply_xbox_gamebar(snap, msg, disable=True)
            results.append(("Xbox Game Bar letiltás", ok))
        else:
            msg("   ✓ Xbox Game Bar már le van tiltva")

    if config.nagle:
        ok = apply_nagle_disable(snap, msg, disable=True)
        results.append(("Nagle letiltás", ok))

    if config.mouse_latency:
        ok = apply_mouse_latency(snap, msg)
        results.append(("Egér latencia", ok))

    # Snapshot mentése
    _save_snapshot(snap)

    # Összesítés
    ok_count  = sum(1 for _, ok in results if ok)
    all_count = len(results)
    msg(f"\n✅ Registry tweakek kész: {ok_count}/{all_count} sikeres")

    hags_applied = any(n == "HAGS bekapcsolás" for n, _ in results)
    mouse_applied = any(n == "Egér latencia" for n, _ in results)
    if hags_applied or mouse_applied:
        msg("⚠ Néhány tweak újraindítást igényel a teljes hatáshoz!")

    return log


def restore_registry_tweaks(callback=None) -> list[str]:
    """
    Registry tweakek visszaállítása a mentett snapshot alapján.
    """
    log = []

    def msg(m: str):
        log.append(m)
        logger.info(m)
        if callback:
            callback(m)

    snap = _load_snapshot()
    if not snap:
        msg("⚠ Nincs registry snapshot — először alkalmazd a tweakeket!")
        return log

    msg("🔄 Registry tweakek visszaállítása...")

    HIVE_MAP = {
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKCU": winreg.HKEY_CURRENT_USER,
    }

    restored = 0
    errors   = 0

    for section_name, section_data in snap.items():
        if not isinstance(section_data, dict):
            continue
        for val_name, val_info in section_data.items():
            hive_str  = val_info.get("hive", "HKLM")
            key_path  = val_info.get("key", "")
            orig_val  = val_info.get("value")
            orig_type = val_info.get("type")

            hive = HIVE_MAP.get(hive_str, winreg.HKEY_LOCAL_MACHINE)

            if orig_val is None:
                # Eredeti érték nem létezett — töröljük a mi értékünket
                _reg_delete_value(hive, key_path, val_name)
                restored += 1
            else:
                # Eredeti értékre visszaírjuk
                reg_type = orig_type if orig_type else winreg.REG_DWORD
                ok = _reg_write(hive, key_path, val_name, orig_val, reg_type)
                if ok:
                    restored += 1
                else:
                    errors += 1
                    msg(f"   ⚠ Visszaállítási hiba: {val_name}")

    _delete_snapshot()
    msg(f"✅ Visszaállítva: {restored} érték, {errors} hiba")
    return log


# ─────────────────────────────────────────────
#  STÁTUSZ LEKÉRDEZÉS
# ─────────────────────────────────────────────

def get_current_registry_status() -> dict:
    """
    Visszaadja az összes tweak jelenlegi állapotát egy dict-ben.
    A GUI-ban való megjelenítéshez.
    """
    # Játék ütemezési prioritás
    sched_cat, _ = _reg_read(winreg.HKEY_LOCAL_MACHINE, _GAMES_KEY, "Scheduling Category")
    gpu_prio, _  = _reg_read(winreg.HKEY_LOCAL_MACHINE, _GAMES_KEY, "GPU Priority")

    # SystemResponsiveness
    sys_resp, _  = _reg_read(
        winreg.HKEY_LOCAL_MACHINE, _SYSTEM_PROFILE_KEY, "SystemResponsiveness")

    # HAGS
    hags_val, _  = _reg_read(winreg.HKEY_LOCAL_MACHINE, _GRAPHICS_KEY, "HwSchMode")

    # Game Mode
    gm_val, _    = _reg_read(winreg.HKEY_CURRENT_USER, _GAMEBAR_KEY, "AutoGameModeEnabled")

    # Game Bar
    dvr_val, _   = _reg_read(
        winreg.HKEY_CURRENT_USER, _GAMEDVR_HKCU_KEY, "AppCaptureEnabled")

    # Nagle (első adapter)
    nagle_set = False
    for guid in _get_network_adapter_guids()[:3]:
        iface_key = f"{_TCPIP_INTERFACES_KEY}\\{guid}"
        nd_val, _ = _reg_read(winreg.HKEY_LOCAL_MACHINE, iface_key, "TCPNoDelay")
        if nd_val == 1:
            nagle_set = True
            break

    # Win32 előtér prioritás
    w32_val, _   = _reg_read(
        winreg.HKEY_LOCAL_MACHINE, _PRIORITY_CONTROL_KEY, "Win32PrioritySeparation")

    return {
        "scheduling_category": sched_cat or "Medium (default)",
        "gpu_priority":        gpu_prio or 2,
        "system_responsiveness": sys_resp if sys_resp is not None else 20,
        "win32_priority":      f"0x{w32_val:02X}" if isinstance(w32_val, int) else "—",
        "win32_priority_ok":   w32_val == 0x26,
        "hags":                "Bekapcsolva" if hags_val == 2 else "Kikapcsolva",
        "game_mode":           "Aktív" if gm_val == 1 else "Inaktív",
        "gamebar_disabled":    dvr_val == 0,
        "nagle_disabled":      nagle_set,
        "snapshot_exists":     has_registry_snapshot(),
    }
