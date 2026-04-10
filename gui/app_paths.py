"""
app_paths.py  —  GameBooster v2.1
Globális elérési utak kezelése.
Egy helyen van definiálva hogy hova mentünk fájlokat.
"""
import os
import sys

# Inicializáláskor beállítjuk az app_dir-t
_APP_DIR: str = ""


def init(app_dir: str):
    """Beállítja az írható app mappát. main.py hívja."""
    global _APP_DIR
    _APP_DIR = app_dir


def app_dir() -> str:
    """Az .exe / main.py melletti mappa — ide írunk minden fájlt."""
    if _APP_DIR:
        return _APP_DIR
    # Fallback: a hívó fájl mappája
    return os.path.dirname(os.path.abspath(__file__))


def profiles_dir() -> str:
    p = os.path.join(app_dir(), "profiles")
    os.makedirs(p, exist_ok=True)
    return p


def log_file() -> str:
    return os.path.join(app_dir(), "gamebooster.log")


def registry_snapshot() -> str:
    return os.path.join(app_dir(), "registry_snapshot.json")


def registry_backup() -> str:
    return os.path.join(app_dir(), "registry_backup.json")


def original_state() -> str:
    return os.path.join(app_dir(), "original_state.json")


def custom_profiles() -> str:
    return os.path.join(profiles_dir(), "custom_profiles.json")


def active_profile() -> str:
    return os.path.join(profiles_dir(), "active_profile.json")
