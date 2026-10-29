"""A v2.x állapotfájljainak átvétele a változásnaplóba, hogy a régi módosítások is visszaállíthatók legyenek."""
import logging
import os
import winreg
from pathlib import Path

from . import winapi
from .journal import Change, Journal
from .storage import read_json

log = logging.getLogger(__name__)

_V2_START = {
    "AUTO_START": "auto", "DELAYED_AUTO_START": "delayed-auto", "(DELAYED)": "delayed-auto",
    "DEMAND_START": "demand", "DISABLED": "disabled", "BOOT_START": "boot", "SYSTEM_START": "system",
}
_V2_HIVE_INT = {winreg.HKEY_LOCAL_MACHINE: "HKLM", winreg.HKEY_CURRENT_USER: "HKCU"}


def _service_changes(state: dict) -> list[Change]:
    changes = []
    for name, info in state.items():
        before = _V2_START.get(info.get("start_type"))
        if before is None:
            continue  # a v2 nem tudta kiolvasni, nincs ismert eredeti érték
        changes.append(Change(
            "service", f"service:{name}", before, winapi.service_start_type(name),
            f"{name} szolgáltatás (v2 Boost)", "v2",
            meta={"name": name, "was_running": info.get("running") == "RUNNING"}))
    return changes


def _registry_change(hive: str, path: str, name: str, before, reg_type) -> Change:
    after, _ = winapi.reg_read(hive, path, name)
    return Change("registry", f"{hive}\\{path}\\{name}", before, after,
                  f"{name} (v2 registry tweak)", "v2",
                  meta={"hive": hive, "path": path, "name": name,
                        "type": reg_type or winreg.REG_DWORD})


def _snapshot_changes(snapshot: dict) -> list[Change]:
    changes = []
    for section, values in snapshot.items():
        for key, info in (values.items() if isinstance(values, dict) else []):
            # A v2 a Nagle-értékeket "GUID_Név" kulccsal mentette
            name = key.rsplit("_", 1)[-1] if section == "nagle" else key
            changes.append(_registry_change(info.get("hive", "HKLM"), info["key"], name,
                                            info.get("value"), info.get("type")))
    return changes


def _backup_changes(backup: dict) -> list[Change]:
    # A régi registry_optimizer.py formátuma (a v2.1 nem használta, de létezhet)
    return [_registry_change(_V2_HIVE_INT.get(e["hive"], "HKLM"), e["path"], e["name"],
                             e["value"] if e.get("existed", True) else None, e.get("reg_type"))
            for e in backup.values()]


def import_v2(journal: Journal, folder: Path) -> int:
    """Átveszi a v2 állapotfájlokat, majd átnevezi őket. Visszaadja az átvett tételek számát."""
    readers = {
        "original_state.json": _service_changes,
        "registry_snapshot.json": _snapshot_changes,
        "registry_backup.json": _backup_changes,
    }
    added = 0
    for filename, reader in readers.items():
        path = folder / filename
        if not path.exists():
            continue
        try:
            added += journal.adopt(reader(read_json(path, {})))
            os.replace(path, path.with_name(filename + ".imported"))
        except Exception as e:
            log.error("A v2 fájl nem vehető át (%s): %s", path, e)
    return added
