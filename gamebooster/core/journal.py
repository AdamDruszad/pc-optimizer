"""Változásnapló: minden rendszermódosítás eredeti értéke, egységes visszaállításhoz.

Az optimalizálók csak tervet (Change-listát) készítenek; a módosítást a napló végzi.
A tervezett változást a napló a módosítás ELŐTT lemezre írja, és egy célpont eredeti
értékét csak az első alkalmazáskor rögzíti, így az ismételt alkalmazás nem írja felül.
"""
import logging
import threading
import winreg
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

from . import winapi
from .storage import read_json, write_json_atomic

log = logging.getLogger(__name__)


@dataclass
class Change:
    kind: str           # registry | service | power | power_overlay | priority | dns
    target: str         # egyedi azonosító, pl. "HKCU\\Software\\...\\Név"
    before: Any         # eredeti érték (None: nem létezett)
    after: Any
    label: str          # ember számára olvasható leírás
    source: str         # melyik funkció: tweaks, services, startup, game_mode, network, v2
    meta: dict = field(default_factory=dict)
    at: str = ""


@dataclass
class Outcome:
    ok: list[Change] = field(default_factory=list)
    failed: list[tuple[Change, str]] = field(default_factory=list)

    def summary(self, verb: str) -> str:
        if not self.failed:
            return f"{len(self.ok)} változás {verb}"
        return f"{len(self.ok)} {verb}, {len(self.failed)} sikertelen: {self.failed[0][1]}"


# ── Típusonkénti alkalmazás és visszaállítás ────────────────

def _reg_value(value, reg_type):
    # A JSON nem tud bájtot: a REG_BINARY értéket hex szövegként tároljuk
    if reg_type == winreg.REG_BINARY and isinstance(value, str):
        return bytes.fromhex(value)
    return value


def _reg_set(c: Change, value) -> None:
    m = c.meta
    wow = m.get("wow64_32", False)
    if value is None:
        winapi.reg_delete(m["hive"], m["path"], m["name"], wow)
    else:
        winapi.reg_write(m["hive"], m["path"], m["name"], _reg_value(value, m["type"]), m["type"], wow)


def _service_apply(c: Change) -> None:
    if c.meta.get("stop"):
        winapi.stop_service(c.meta["name"])
    winapi.set_service_start(c.meta["name"], c.after)


def _service_revert(c: Change) -> None:
    winapi.set_service_start(c.meta["name"], c.before)
    if "delayed" in c.meta:  # a v2-ből átvett tételeknél nincs rögzítve
        winapi.set_service_delayed_flag(c.meta["name"], c.meta["delayed"])
    if c.meta.get("was_running") and c.before != "disabled":
        winapi.start_service(c.meta["name"])


def _set_priority(c: Change, value: int) -> None:
    try:
        proc = psutil.Process(c.meta["pid"])
        if abs(proc.create_time() - c.meta["create_time"]) > 0.01:
            return  # a PID-et azóta másik folyamat kapta meg
        proc.nice(value)
    except psutil.NoSuchProcess:
        return  # a folyamat kilépett, nincs mit visszaállítani


def _dns_set(c: Change, servers) -> None:
    winapi.set_dns(c.meta["index"], servers)


HANDLERS: dict[str, tuple[Callable[[Change], None], Callable[[Change], None]]] = {
    "registry":      (lambda c: _reg_set(c, c.after), lambda c: _reg_set(c, c.before)),
    "service":       (_service_apply, _service_revert),
    "power":         (lambda c: winapi.set_power_scheme(c.after),
                      lambda c: winapi.set_power_scheme(c.before)),
    "power_overlay": (lambda c: winapi.set_power_overlay(c.after),
                      lambda c: winapi.set_power_overlay(c.before)),
    "priority":      (lambda c: _set_priority(c, c.after), lambda c: _set_priority(c, c.before)),
    "dns":           (lambda c: _dns_set(c, c.after), lambda c: _dns_set(c, c.before)),
}


def registry_change(hive: str, path: str, name: str, after, reg_type: int, label: str,
                    source: str, wow64_32: bool = False) -> Change | None:
    """Registry-változás terve; None, ha az érték már a kívánt."""
    before, before_type = winapi.reg_read(hive, path, name, wow64_32)
    if isinstance(before, bytes):
        before = before.hex()
    if isinstance(after, bytes):
        after = after.hex()
    if before == after and (before is None or before_type == reg_type):
        return None
    return Change("registry", f"{hive}\\{path}\\{name}", before, after, label, source,
                  meta={"hive": hive, "path": path, "name": name, "type": reg_type,
                        "wow64_32": wow64_32})


# ── Napló ───────────────────────────────────────────────────

class Journal:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._entries = [Change(**d) for d in read_json(path, [])]

    def _save(self) -> None:
        write_json_atomic(self.path, [asdict(c) for c in self._entries])

    def entries(self, source: str | None = None) -> list[Change]:
        with self._lock:
            return [c for c in self._entries if source is None or c.source == source]

    def find(self, target: str) -> Change | None:
        with self._lock:
            return next((c for c in self._entries if c.target == target), None)

    def apply(self, changes: list[Change]) -> Outcome:
        out = Outcome()
        for change in changes:
            with self._lock:
                existing = self.find(change.target)
                if existing:
                    previous_after = existing.after
                    existing.after = change.after  # az eredeti `before` és `meta` marad
                    entry = existing
                else:
                    change.at = datetime.now().isoformat(timespec="seconds")
                    self._entries.append(change)
                    entry = change
                self._save()
            try:
                HANDLERS[change.kind][0](change)
                out.ok.append(entry)
            except Exception as e:
                log.warning("Alkalmazás sikertelen (%s): %s", change.label, e)
                with self._lock:
                    if existing:
                        existing.after = previous_after
                    else:
                        self._entries.remove(change)
                    self._save()
                out.failed.append((change, str(e)))
        return out

    def revert(self, entries: list[Change] | None = None) -> Outcome:
        """Fordított sorrendben állít vissza; a sikertelen tételek a naplóban maradnak."""
        out = Outcome()
        todo = self.entries() if entries is None else list(entries)
        for change in reversed(todo):
            try:
                handler = HANDLERS.get(change.kind)
                if handler is None:
                    raise ValueError(f"ismeretlen változástípus: {change.kind}")
                handler[1](change)
            except Exception as e:
                log.warning("Visszaállítás sikertelen (%s): %s", change.label, e)
                out.failed.append((change, str(e)))
                continue
            with self._lock:
                if change in self._entries:
                    self._entries.remove(change)
                    self._save()
            out.ok.append(change)
        return out

    def adopt(self, changes: list[Change]) -> int:
        """Már végrehajtott (pl. a v2 által végzett) változások felvétele a naplóba."""
        added = 0
        with self._lock:
            for change in changes:
                if self.find(change.target) is None:
                    change.at = change.at or datetime.now().isoformat(timespec="seconds")
                    self._entries.append(change)
                    added += 1
            if added:
                self._save()
        return added
