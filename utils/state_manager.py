"""
state_manager.py
Elmenti és visszaállítja a Windows szolgáltatások eredeti állapotát.
PyInstaller kompatibilis — dinamikus path kezelés.
"""

import json
import subprocess
import os
import logging

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


TARGET_SERVICES = [
    "SysMain",
    "WSearch",
    "DiagTrack",
    "wuauserv",
    "MapsBroker",
    "RetailDemo",
    "WbioSrvc",
]


def get_service_status(service_name: str) -> str:
    try:
        result = subprocess.run(
            ["sc", "qc", service_name],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "START_TYPE" in line:
                parts = line.split()
                return parts[-1].strip()
    except Exception:
        pass
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


def save_original_state() -> dict:
    state = {}
    for svc in TARGET_SERVICES:
        state[svc] = {
            "start_type": get_service_status(svc),
            "running":    get_service_running_state(svc),
        }
    path = _get_state_file()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    return state


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
