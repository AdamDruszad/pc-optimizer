"""
state_manager.py
Elmenti és visszaállítja a Windows szolgáltatások eredeti állapotát.
PyInstaller kompatibilis — dinamikus path kezelés.
"""

import json
import subprocess
import os
import logging
import winreg

logger = logging.getLogger(__name__)


def _get_state_file() -> str:
    """Állapot fájl útvonal — app_paths-ból ha elérhető."""
    try:
        from gui.app_paths import original_state
        return original_state()
    except Exception:
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "original_state.json"
        )


def write_json_atomic(path: str, data) -> None:
    """Átmeneti fájlba ír, majd cserél: megszakadt írás nem hagy sérült mentést."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


TARGET_SERVICES = [
    "SysMain",
    "WSearch",
    "DiagTrack",
    "MapsBroker",
    "RetailDemo",
]

_START_NAMES = {
    0: "BOOT_START",
    1: "SYSTEM_START",
    2: "AUTO_START",
    3: "DEMAND_START",
    4: "DISABLED",
}


def start_type_name(start: int, delayed: int) -> str:
    """Registry Start + DelayedAutostart → sc-szerű név (késleltetett indítással)."""
    if start == 2 and delayed:
        return "DELAYED_AUTO_START"
    return _START_NAMES.get(start, "UNKNOWN")


def get_service_status(service_name: str) -> str:
    """Indítási típus a registryből (az `sc qc` kimenet nem jelöli egyértelműen a késleltetést)."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            rf"SYSTEM\CurrentControlSet\Services\{service_name}") as key:
            start = winreg.QueryValueEx(key, "Start")[0]
            try:
                delayed = winreg.QueryValueEx(key, "DelayedAutostart")[0]
            except FileNotFoundError:
                delayed = 0
        return start_type_name(start, delayed)
    except OSError:
        return "UNKNOWN"


def get_service_running_state(service_name: str) -> str:
    try:
        result = subprocess.run(
            ["sc", "query", service_name],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "STATE" in line and "WIN32" not in line:
                parts = line.split()
                return parts[-1].strip()
    except Exception:
        pass
    return "UNKNOWN"


def save_original_state(services: list[str] = TARGET_SERVICES) -> dict:
    """
    Elmenti a szolgáltatások eredeti állapotát.
    A már mentett szolgáltatást nem írja felül: egy ismételt Boost idején
    a rendszerben már a módosított (letiltott) érték van.
    """
    state = load_original_state() or {}
    for svc in services:
        if svc in state:
            continue
        start_type = get_service_status(svc)
        if start_type == "UNKNOWN":
            continue  # nem létező szolgáltatás
        state[svc] = {
            "start_type": start_type,
            "running":    get_service_running_state(svc),
        }
    write_state(state)
    return state


def write_state(state: dict) -> None:
    write_json_atomic(_get_state_file(), state)


def load_original_state() -> dict | None:
    path = _get_state_file()
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def has_saved_state() -> bool:
    return os.path.exists(_get_state_file())


def delete_saved_state():
    path = _get_state_file()
    if os.path.exists(path):
        os.remove(path)
