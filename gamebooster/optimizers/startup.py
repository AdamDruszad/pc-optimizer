"""Indítópult: ki/bekapcsolás a StartupApproved kulcsokon, ugyanúgy, ahogy a Feladatkezelő teszi.
A bejegyzést nem töröljük, így bármikor visszakapcsolható."""
import os
import struct
import time
import winreg
from dataclasses import dataclass
from pathlib import Path

from ..core import winapi
from ..core.journal import Change, registry_change

_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"

# (hive, Run kulcs, 32 bites nézet, StartupApproved alkulcs, megjelenített hely)
_RUN_SOURCES = [
    ("HKCU", _RUN, False, "Run", "Registry (felhasználó)"),
    ("HKLM", _RUN, False, "Run", "Registry (minden felhasználó)"),
    ("HKLM", _RUN, True, "Run32", "Registry (minden felhasználó, 32 bites)"),
]
_FOLDER_SOURCES = [
    ("HKCU", r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup", "Indítópult mappa"),
    ("HKLM", r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\StartUp",
     "Indítópult mappa (minden felhasználó)"),
]


@dataclass
class StartupItem:
    name: str
    command: str
    location: str
    hive: str
    approved_key: str
    enabled: bool


def _enabled(hive: str, approved_key: str, name: str) -> bool:
    value, _ = winapi.reg_read(hive, approved_key, name)
    # Hiányzó érték: engedélyezett; a Feladatkezelő az első bájt páratlanságával jelöli a tiltást
    return not (isinstance(value, bytes) and value and value[0] & 1)


def items() -> list[StartupItem]:
    result = []
    for hive, key, wow32, sub, location in _RUN_SOURCES:
        approved = f"{_APPROVED}\\{sub}"
        for name, command, _ in winapi.reg_values(hive, key, wow32):
            result.append(StartupItem(name, str(command), location, hive, approved,
                                      _enabled(hive, approved, name)))
    for hive, folder, location in _FOLDER_SOURCES:
        path = Path(os.path.expandvars(folder))
        approved = f"{_APPROVED}\\StartupFolder"
        for entry in sorted(path.iterdir()) if path.is_dir() else []:
            if entry.name.lower() != "desktop.ini" and entry.is_file():
                result.append(StartupItem(entry.name, str(entry), location, hive, approved,
                                          _enabled(hive, approved, entry.name)))
    return sorted(result, key=lambda i: i.name.lower())


def approved_value(enable: bool) -> bytes:
    if enable:
        return bytes([2]) + bytes(11)
    # 03 00 00 00 + a letiltás ideje FILETIME-ként, ahogy a Feladatkezelő írja
    filetime = int(time.time() * 10_000_000) + 116444736000000000
    return bytes([3, 0, 0, 0]) + struct.pack("<Q", filetime)


def plan_toggle(item: StartupItem, enable: bool) -> Change | None:
    return registry_change(item.hive, item.approved_key, item.name, approved_value(enable),
                           winreg.REG_BINARY,
                           f"{item.name}: indítás {'bekapcsolva' if enable else 'kikapcsolva'}",
                           "startup")
