"""Írható adatok helye és JSON-mentés.

Az adatok a %LOCALAPPDATA%\\GameBooster mappába kerülnek, nem az exe mellé: az emelt jogú
folyamat így nem olvas be olyan fájlt, amelyet egy nem-admin folyamat átírhatott volna.
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

_data_dir: Path | None = None


def data_dir() -> Path:
    global _data_dir
    if _data_dir is None:
        _data_dir = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "GameBooster"
    _data_dir.mkdir(parents=True, exist_ok=True)
    return _data_dir


def set_data_dir(path) -> None:
    global _data_dir
    _data_dir = Path(path)


def legacy_dir() -> Path:
    """A v2.x az exe (forrásból futtatva a main.py) mellé írta az állapotfájlokat."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def read_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as e:
        # A sérült fájlt félretesszük, hogy kézzel még vissza lehessen nyerni
        backup = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
        log.error("Sérült fájl: %s (%s), félretéve: %s", path, e, backup)
        try:
            os.replace(path, backup)
        except OSError:
            pass
        return default


def write_json_atomic(path: Path, data) -> None:
    """Átmeneti fájlba ír, majd cserél: megszakadt írás nem hagy sérült fájlt."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


SETTINGS_DEFAULTS = {
    "games": [],                 # [{"exe": "cs2.exe", "path": "C:\\...\\cs2.exe"}]
    "auto_game_mode": False,     # játék indulásakor automatikus Játék mód
    "game_power_plan": True,
    "game_priority": True,
    "background_apps": [],       # ezek prioritása csökken Játék módban
    "performance_scheme": None,  # a létrehozott Ultimate Performance séma GUID-ja
}


def load_settings() -> dict:
    return {**SETTINGS_DEFAULTS, **read_json(data_dir() / "settings.json", {})}


def save_settings(settings: dict) -> None:
    write_json_atomic(data_dir() / "settings.json", settings)
