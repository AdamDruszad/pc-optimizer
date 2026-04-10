"""
registry_optimizer.py  —  GameBooster v2.1
Windows registry alapú játék teljesítmény optimalizálás.

TARTALOM:
  1. MMCSS (Multimedia Class Scheduler Service) tweaks
  2. HAGS (Hardware Accelerated GPU Scheduling)
  3. Win32PrioritySeparation (előtér CPU boost)
  4. Windows Game Mode automatika

BIZTONSÁG:
  - Minden kulcs eredeti értéke mentve boost előtt
  - Teljes visszaállítás egyetlen függvényhívással
  - HAGS-nál explicit restart figyelmeztetés
  - Típushelyes írás (DWORD vs REG_SZ különbséget tartjuk)

FORRÁS: Microsoft MMCSS doc, howtogeek.com (2025),
        djdallmann/GamingPCSetup (mért adatok), wiredcolony.com (2025)
"""

import winreg
import logging
import json
import os

logger = logging.getLogger(__name__)

BACKUP_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "registry_backup.json"
)

# ─────────────────────────────────────────────────────────────
#  ÚTVONAL KONSTANSOK
# ─────────────────────────────────────────────────────────────

_MMCSS  = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
_GAMES  = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
_GFXDRV = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
_PRICTL = r"SYSTEM\ControlSet001\Control\PriorityControl"
_GAMEBAR = r"SOFTWARE\Microsoft\GameBar"

HKLM = winreg.HKEY_LOCAL_MACHINE
HKCU = winreg.HKEY_CURRENT_USER
DWORD = winreg.REG_DWORD
SZ    = winreg.REG_SZ

# ─────────────────────────────────────────────────────────────
#  TWEAK DEFINÍCIÓK
#  Formátum: (hive, path, name, type, gaming_val, default_val, leírás)
# ─────────────────────────────────────────────────────────────

MMCSS_SYSTEM = [
    # NetworkThrottlingIndex: hálózati throttling tiltása
    # Default: 0x0A (10) → Gaming: 0xffffffff (korlátlan)
    (HKLM, _MMCSS, "NetworkThrottlingIndex", DWORD,
     0xffffffff, 0x0A,
     "Hálózati throttling tiltása (UDP játékokhoz, pl. CS2)"),

    # SystemResponsiveness: háttér CPU tartalék
    # Default: 20 (20% CPU háttér folyamatoknak) → Gaming: 0 (100% a játéknak)
    # ⚠ OBS streameléshez ne 0-ra állítsd, 10 biztonságosabb
    (HKLM, _MMCSS, "SystemResponsiveness", DWORD,
     0, 20,
     "CPU háttér tartalék: 20% → 0% (max CPU a játéknak)"),
]

MMCSS_GAMES = [
    # Affinity: összes CPU mag elérhető (0 = nincs kötés)
    (HKLM, _GAMES, "Affinity", DWORD,
     0x00000000, 0x00000000,
     "CPU affinitás: összes mag elérhető"),

    # Background Only: nem csak háttérben fut
    (HKLM, _GAMES, "Background Only", SZ,
     "False", "False",
     "Előtér mód engedélyezve"),

    # Clock Rate: 1ms MMCSS időzítő (standard, nem változik)
    (HKLM, _GAMES, "Clock Rate", DWORD,
     0x00002710, 0x00002710,
     "1ms időzítő (standard érték)"),

    # GPU Priority: 8 → 18 (0x12) — magasabb GPU ütemezési elsőbbség
    # Skála: 0-31
    (HKLM, _GAMES, "GPU Priority", DWORD,
     0x00000012, 0x00000008,
     "GPU prioritás: 8 → 18 (magasabb GPU elsőbbség)"),

    # Priority: 2 → 6 — magasabb CPU szál prioritás
    (HKLM, _GAMES, "Priority", DWORD,
     0x00000006, 0x00000002,
     "CPU szál prioritás: 2 → 6"),

    # Scheduling Category: Medium → High
    (HKLM, _GAMES, "Scheduling Category", SZ,
     "High", "Medium",
     "Ütemezési kategória: Medium → High"),

    # SFIO Priority: Normal → High (gyorsabb textúra/asset betöltés)
    (HKLM, _GAMES, "SFIO Priority", SZ,
     "High", "Normal",
     "Fájl I/O prioritás: Normal → High"),
]

PRIORITY_SEPARATION = [
    # Win32PrioritySeparation: előtér folyamat (játék) CPU boost
    # 0x02 = szerver mód (nincs boost)
    # 0x18 = 24 = Windows alapértelmezett
    # 0x26 = 38 = max előtér boost (gaming optimális)
    (HKLM, _PRICTL, "Win32PrioritySeparation", DWORD,
     0x26, 0x02,
     "Előtér CPU boost: maximum (0x26) — játék kap legtöbb CPU időt"),
]

GAME_MODE = [
    (HKCU, _GAMEBAR, "AutoGameModeEnabled", DWORD,
     1, 0,
     "Windows Game Mode: automatikus bekapcsolás"),

    (HKCU, _GAMEBAR, "AllowAutoGameMode", DWORD,
     1, 0,
     "Windows Game Mode: engedélyezés"),
]

HAGS = [
    # HwSchMode: 1=letiltva, 2=engedélyezve
    # RESTART SZÜKSÉGES az életbe lépéshez!
    # Intel UHD: Windows 11 + megfelelő driver szükséges
    # Nvidia GTX 10xx+: támogatott
    (HKLM, _GFXDRV, "HwSchMode", DWORD,
     2, 1,
     "HAGS: Hardware Accelerated GPU Scheduling BE (RESTART KELL!)"),
]

TWEAK_GROUPS = {
    "mmcss_system": {
        "name":    "MMCSS rendszer beállítások",
        "entries": MMCSS_SYSTEM,
        "restart": False,
    },
    "mmcss_games": {
        "name":    "MMCSS Games task prioritás",
        "entries": MMCSS_GAMES,
        "restart": False,
    },
    "priority_sep": {
        "name":    "Win32 előtér prioritás boost",
        "entries": PRIORITY_SEPARATION,
        "restart": False,
    },
    "game_mode": {
        "name":    "Windows Game Mode automatika",
        "entries": GAME_MODE,
        "restart": False,
    },
    "hags": {
        "name":    "HAGS — Hardware Accelerated GPU Scheduling",
        "entries": HAGS,
        "restart": True,
    },
}


# ─────────────────────────────────────────────────────────────
#  ALACSONY SZINTŰ REGISTRY I/O
# ─────────────────────────────────────────────────────────────

def _hive_name(hive: int) -> str:
    return {HKLM: "HKLM", HKCU: "HKCU"}.get(hive, str(hive))


def _read_value(hive, path, name):
    """Visszaad (value, type) vagy (None, None)-t."""
    try:
        with winreg.OpenKey(hive, path, 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            val, rtype = winreg.QueryValueEx(k, name)
            return val, rtype
    except FileNotFoundError:
        return None, None
    except Exception as e:
        logger.debug(f"Reg olvasás ({path}\\{name}): {e}")
        return None, None


def _write_value(hive, path, name, value, reg_type) -> bool:
    try:
        with winreg.CreateKeyEx(hive, path, 0,
                                winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            winreg.SetValueEx(k, name, 0, reg_type, value)
        return True
    except PermissionError:
        logger.warning(f"Reg írás: hozzáférés megtagadva ({path}\\{name})")
        return False
    except Exception as e:
        logger.error(f"Reg írás hiba ({path}\\{name}): {e}")
        return False


def _delete_value(hive, path, name) -> bool:
    try:
        with winreg.OpenKey(hive, path, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            winreg.DeleteValue(k, name)
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        logger.debug(f"Reg törlés ({path}\\{name}): {e}")
        return False


def _vals_equal(v1, v2, reg_type) -> bool:
    if v1 is None or v2 is None:
        return False
    if reg_type == SZ:
        return str(v1).lower() == str(v2).lower()
    return int(v1) == int(v2)


# ─────────────────────────────────────────────────────────────
#  BACKUP / RESTORE
# ─────────────────────────────────────────────────────────────

def backup_registry(group_keys: list | None = None) -> dict:
    """
    Elmenti az összes (vagy megadott) tweak eredeti értékét JSON-ba.
    Visszaadja a backup dict-et.
    """
    backup = {}
    groups = group_keys or list(TWEAK_GROUPS.keys())

    for gk in groups:
        group = TWEAK_GROUPS.get(gk)
        if not group:
            continue
        for hive, path, name, reg_type, gaming_val, default_val, desc in group["entries"]:
            current, current_type = _read_value(hive, path, name)
            key = f"{_hive_name(hive)}|{path}|{name}"
            backup[key] = {
                "hive":     hive,
                "path":     path,
                "name":     name,
                "reg_type": current_type if current_type is not None else reg_type,
                "value":    current if current is not None else default_val,
                "existed":  current is not None,
            }

    try:
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(backup, f, indent=2, ensure_ascii=False)
        logger.info(f"Registry backup: {len(backup)} kulcs → {BACKUP_FILE}")
    except Exception as e:
        logger.error(f"Registry backup mentési hiba: {e}")

    return backup


def load_backup() -> dict | None:
    if not os.path.exists(BACKUP_FILE):
        return None
    try:
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Registry backup betöltési hiba: {e}")
        return None


def has_backup() -> bool:
    return os.path.exists(BACKUP_FILE)


def delete_backup():
    if os.path.exists(BACKUP_FILE):
        os.remove(BACKUP_FILE)


# ─────────────────────────────────────────────────────────────
#  AKTUÁLIS ÁLLAPOT LEKÉRDEZÉS
# ─────────────────────────────────────────────────────────────

def get_current_state() -> dict:
    """
    Az összes tweak jelenlegi állapota — GUI státusz panelhez.
    Visszaad: {group_key: {name, applied, restart_req, items}}
    """
    result = {}
    for gk, group in TWEAK_GROUPS.items():
        items = []
        all_applied = True
        any_readable = False

        for hive, path, name, reg_type, gaming_val, default_val, desc in group["entries"]:
            current, _ = _read_value(hive, path, name)
            if current is None:
                match = False
                all_applied = False
            else:
                any_readable = True
                match = _vals_equal(current, gaming_val, reg_type)
                if not match:
                    all_applied = False

            items.append({
                "name":    name,
                "current": current,
                "gaming":  gaming_val,
                "default": default_val,
                "desc":    desc,
                "match":   match if current is not None else None,
            })

        result[gk] = {
            "name":        group["name"],
            "applied":     all_applied and any_readable,
            "restart_req": group["restart"],
            "items":       items,
        }
    return result


# ─────────────────────────────────────────────────────────────
#  OPTIMALIZÁLÁS ALKALMAZÁSA
# ─────────────────────────────────────────────────────────────

def apply_registry_tweaks(
    groups: list | None = None,
    callback=None,
    apply_hags: bool = True,
) -> tuple:
    """
    Alkalmazza a kiválasztott registry tweakeket.

    groups:     None = minden csoport
    apply_hags: Ha False, HAGS kihagyva (restart nélküli módhoz)

    Visszaad: (log_lista, restart_szukseges: bool)
    """
    log = []
    restart_needed = False

    def msg(m):
        log.append(m)
        logger.info(m)
        if callback:
            callback(m)

    selected = list(groups or TWEAK_GROUPS.keys())
    if not apply_hags and "hags" in selected:
        selected = [g for g in selected if g != "hags"]

    msg("💾 Registry eredeti értékek mentése...")
    backup = backup_registry(selected)
    msg(f"   ✓ {len(backup)} kulcs mentve → registry_backup.json")

    total_ok = 0
    total_err = 0

    for gk in selected:
        group = TWEAK_GROUPS.get(gk)
        if not group:
            continue

        msg(f"\n🔑 {group['name']}...")
        if group["restart"]:
            msg("   ⚡ Ez a módosítás ÚJRAINDÍTÁST igényel!")
            restart_needed = True

        for hive, path, name, reg_type, gaming_val, default_val, desc in group["entries"]:
            current, _ = _read_value(hive, path, name)

            # Ha már gaming értéken van, kihagyjuk
            if _vals_equal(current, gaming_val, reg_type):
                msg(f"   ✓ {name}: már optimális")
                total_ok += 1
                continue

            ok = _write_value(hive, path, name, gaming_val, reg_type)
            if ok:
                old_str = str(current) if current is not None else "(nem létezett)"
                msg(f"   ✓ {name}: {old_str} → {gaming_val}")
                msg(f"      {desc}")
                total_ok += 1
            else:
                msg(f"   ✗ {name}: HIBA — admin jog szükséges?")
                total_err += 1

    msg(f"\n📊 Összesítés: ✓ {total_ok} sikeres | ✗ {total_err} hiba")
    if restart_needed:
        msg("⚡ ÚJRAINDÍTÁS SZÜKSÉGES a HAGS aktiválásához!")
        msg("   (A többi módosítás azonnal érvényes)")

    return log, restart_needed


# ─────────────────────────────────────────────────────────────
#  VISSZAÁLLÍTÁS
# ─────────────────────────────────────────────────────────────

def restore_registry_tweaks(callback=None) -> list:
    """Visszaállítja az összes registry értéket a backup alapján."""
    log = []

    def msg(m):
        log.append(m)
        logger.info(m)
        if callback:
            callback(m)

    backup = load_backup()
    if not backup:
        msg("⚠ Nincs registry backup — nem volt registry optimalizálás")
        return log

    msg(f"🔄 Registry visszaállítás ({len(backup)} kulcs)...")
    ok_count = err_count = 0

    for key, entry in backup.items():
        hive     = entry["hive"]
        path     = entry["path"]
        name     = entry["name"]
        reg_type = entry["reg_type"]
        value    = entry["value"]
        existed  = entry.get("existed", True)

        if not existed:
            _delete_value(hive, path, name)
            msg(f"   ✓ {name}: törölve")
            ok_count += 1
        else:
            ok = _write_value(hive, path, name, value, reg_type)
            if ok:
                msg(f"   ✓ {name}: → {value}")
                ok_count += 1
            else:
                msg(f"   ✗ {name}: HIBA")
                err_count += 1

    delete_backup()
    msg(f"\n✅ Visszaállítás kész: {ok_count} OK, {err_count} hiba")
    return log


# ─────────────────────────────────────────────────────────────
#  HAGS TÁMOGATOTTSÁG ELLENŐRZÉS
# ─────────────────────────────────────────────────────────────

def check_hags_support() -> tuple:
    """
    Visszaad: (supported: bool, info: str)
    """
    import platform
    try:
        ver = platform.version()
        build = int(ver.split(".")[2]) if ver.count(".") >= 2 else 0
        if build < 19041:
            return False, f"Windows build {build} < 19041 szükséges"
    except Exception:
        pass

    current, _ = _read_value(HKLM, _GFXDRV, "HwSchMode")
    if current == 2:
        return True, "HAGS már BE van kapcsolva"

    try:
        with winreg.OpenKey(HKLM, _GFXDRV, 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
            return True, "HAGS kapcsolható (jelenleg: KI)"
    except FileNotFoundError:
        return False, "GraphicsDrivers kulcs nem található"
    except Exception as e:
        return False, f"Ellenőrzési hiba: {e}"


# ─────────────────────────────────────────────────────────────
#  STÁTUSZ ÖSSZEFOGLALÓ — GUI-hoz
# ─────────────────────────────────────────────────────────────

def get_status_summary() -> list:
    """
    Rövid státusz lista a GUI-hoz.
    Visszaad: [{"key", "label", "status", "color", "restart_req"}]
    """
    state = get_current_state()
    labels = {
        "mmcss_system": "MMCSS rendszer",
        "mmcss_games":  "MMCSS Games prioritás",
        "priority_sep": "Előtér CPU boost",
        "game_mode":    "Windows Game Mode",
        "hags":         "HAGS (GPU scheduling)",
    }
    result = []
    for gk, info in state.items():
        applied = info["applied"]
        result.append({
            "key":         gk,
            "label":       labels.get(gk, gk),
            "status":      "✓ Aktív" if applied else "○ Inaktív",
            "color":       "#00FF88" if applied else "#4A5568",
            "restart_req": info["restart_req"],
        })
    return result
