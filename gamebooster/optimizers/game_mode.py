"""Játék mód munkamenet: a játék indulásakor alkalmaz, kilépésekor mindent visszaállít.

Csak valódi hatású lépések: teljesítmény energiaséma, a játék HIGH prioritása (REALTIME soha),
a felhasználó által kijelölt háttérappok BELOW_NORMAL prioritása. Rendszerfolyamathoz nem nyúl.
"""
import logging
import threading
from collections.abc import Callable

import psutil

from ..core.journal import Change, Journal, Outcome
from . import power

log = logging.getLogger(__name__)
SOURCE = "game_mode"

PRIORITY_LABELS = {
    psutil.IDLE_PRIORITY_CLASS: "Alacsony", psutil.BELOW_NORMAL_PRIORITY_CLASS: "Normál alatti",
    psutil.NORMAL_PRIORITY_CLASS: "Normál", psutil.ABOVE_NORMAL_PRIORITY_CLASS: "Normál feletti",
    psutil.HIGH_PRIORITY_CLASS: "Magas", psutil.REALTIME_PRIORITY_CLASS: "Valós idejű",
}
# Ezek prioritását akkor sem csökkentjük, ha a felhasználó felvenné őket
_PROTECTED = {"system", "svchost.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "lsass.exe",
              "services.exe", "smss.exe", "dwm.exe", "audiodg.exe", "msmpeng.exe", "explorer.exe"}


def priority_change(proc: psutil.Process, cls: int) -> Change | None:
    try:
        current, name, created = proc.nice(), proc.name(), proc.create_time()
    except psutil.Error:
        return None
    if current == cls:
        return None
    return Change("priority", f"priority:{proc.pid}:{created}", int(current), int(cls),
                  f"{name} prioritás: {PRIORITY_LABELS.get(current, current)} → "
                  f"{PRIORITY_LABELS.get(cls, cls)}",
                  SOURCE, meta={"pid": proc.pid, "create_time": created})


def find_running(exe_names: set[str]) -> psutil.Process | None:
    for proc in psutil.process_iter():
        try:
            if proc.name().lower() in exe_names:
                return proc
        except psutil.Error:
            continue
    return None


def plan(settings: dict, game: psutil.Process | None) -> list[Change]:
    changes = []
    if settings["game_power_plan"]:
        changes += power.plan(settings, SOURCE)
    if settings["game_priority"] and game:
        changes.append(priority_change(game, psutil.HIGH_PRIORITY_CLASS))
    background = {n.lower() for n in settings["background_apps"]} - _PROTECTED
    for proc in psutil.process_iter():
        try:
            if proc.name().lower() in background:
                changes.append(priority_change(proc, psutil.BELOW_NORMAL_PRIORITY_CLASS))
        except psutil.Error:
            continue
    return [c for c in changes if c]


class GameWatcher(threading.Thread):
    """3 mp-enként megnézi, fut-e beállított játék. Automatikus módban indít/leállít munkamenetet;
    a kézzel indított munkamenetet is lezárja, ha a hozzá tartozó játék kilép."""

    def __init__(self, journal: Journal, settings: Callable[[], dict],
                 on_change: Callable[[str, str, Outcome], None]):
        super().__init__(daemon=True, name="GameWatcher")
        self.journal = journal
        self.settings = settings
        self.on_change = on_change   # (esemény, játék neve, eredmény) — háttérszálról hívódik
        self.game: psutil.Process | None = None
        self.active = bool(journal.entries(SOURCE))
        self._dismissed: psutil.Process | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def start_session(self, game: psutil.Process | None, changes: list[Change] | None = None,
                      notify: bool = True) -> Outcome:
        with self._lock:
            out = self.journal.apply(plan(self.settings(), game) if changes is None else changes)
            self.game, self.active = game, True
        if notify:
            self.on_change("start", self._game_name(game), out)
        return out

    def end_session(self) -> Outcome:
        with self._lock:
            name = self._game_name(self.game)
            out = self.journal.revert(self.journal.entries(SOURCE))
            # Kézi leállítás után az automatika ne indítsa újra ugyanarra a futó játékra
            if self.game is not None and self.game.is_running():
                self._dismissed = self.game
            self.game, self.active = None, False
        self.on_change("stop", name, out)
        return out

    @staticmethod
    def _game_name(game) -> str:
        try:
            return game.name() if game else ""
        except psutil.Error:
            return ""

    def run(self) -> None:
        while not self._stop_event.wait(3):
            try:
                self._tick()
            except Exception as e:
                log.warning("GameWatcher hiba: %s", e)

    def _tick(self) -> None:
        settings = self.settings()
        if self.active and self.game is not None and not self.game.is_running():
            self.end_session()
        elif not self.active and settings["auto_game_mode"]:
            game = find_running({g["exe"].lower() for g in settings["games"]})
            if self._dismissed is not None and not self._dismissed.is_running():
                self._dismissed = None
            if game and game != self._dismissed:
                self.start_session(game)
