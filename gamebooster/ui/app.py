"""Az alkalmazás kerete: oldalsáv, oldalváltás, napló, alkalmaz/visszaállít folyamat."""
import logging
from collections.abc import Callable

import customtkinter as ctk

from .. import __version__
from ..core import legacy, restore_point, storage, winapi
from ..core.journal import Change, Journal, Outcome
from ..monitoring import hardware
from ..monitoring.sampler import Sampler
from ..optimizers import game_mode
from . import theme
from .pages import cleaner, dashboard, game, history, monitor, network, services, startup, tweaks
from .widgets import NavItem, TaskRunner, Toasts, button, confirm, label

log = logging.getLogger(__name__)

PAGES = [
    ("dashboard", "Áttekintés", "home", dashboard.DashboardPage),
    ("game", "Játék mód", "game", game.GamePage),
    ("cleaner", "Tisztítás", "clean", cleaner.CleanerPage),
    ("startup", "Indítópult", "startup", startup.StartupPage),
    ("services", "Szolgáltatások", "services", services.ServicesPage),
    ("tweaks", "Tweakek", "tweaks", tweaks.TweaksPage),
    ("network", "Hálózat", "network", network.NetworkPage),
    ("monitor", "Monitor", "monitor", monitor.MonitorPage),
    ("history", "Előzmények", "history", history.HistoryPage),
]


def window_geometry(screen_w: int, screen_h: int, scale: float) -> tuple[int, int, int, int]:
    """Ablakméret (CTk-pontban) és hely (pixelben), hogy kis kijelzőn se lógjon a tálca alá.
    A képernyő fizikai pixelben jön, a CTk a méretet a skálázással szorozza, a helyet nem;
    a címsor (~30) és a tálca (~50 pont) nincs benne a geometriában."""
    width = min(1240, int((screen_w - 40 * scale) / scale))
    height = min(800, int((screen_h - 120 * scale) / scale))
    x = (screen_w - round(width * scale)) // 2
    y = max(0, (screen_h - round(height * scale)) // 2 - round(30 * scale))
    return width, height, x, y


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=theme.BG)
        theme.init(self)
        self.title("GameBooster")
        width, height, x, y = window_geometry(self.winfo_screenwidth(), self.winfo_screenheight(),
                                              self._get_window_scaling())
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(1040, width), min(680, height))

        self.admin = winapi.is_admin()
        self.settings = storage.load_settings()
        self.journal = Journal(storage.data_dir() / "journal.json")
        self.toasts = Toasts(self)
        self.tasks = TaskRunner(self, lambda e: self.toasts.show(f"Hiba: {e}", "danger"))
        self.hardware: hardware.HardwareInfo | None = None
        self._restore_point_tried = False

        self.sampler = Sampler()
        self.sampler.start()
        self.watcher = game_mode.GameWatcher(
            self.journal, lambda: self.settings,
            lambda event, name, out: self.tasks.post(self._on_game_event, event, name, out))
        self.watcher.start()

        self._build()
        self.show("dashboard")
        self.tasks.run(hardware.detect, self._hardware_ready)
        imported = legacy.import_v2(self.journal, storage.legacy_dir())
        if imported:
            self.toasts.show(f"A régi verzió {imported} módosítását átvettem az Előzményekbe; "
                             "onnan visszaállíthatók.", "info", 8000)
        elif self.journal.entries("game_mode"):
            self.toasts.show("Az előző Játék mód munkamenet módosításai még aktívak "
                             "(Előzmények).", "warning", 8000)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(1000, self._tick)

    # ── Felépítés ──────────────────────────────────────────

    def _build(self) -> None:
        side = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=0, width=232)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        label(side, "GameBooster", font=theme.font(20, "bold")).pack(anchor="w", padx=20, pady=(22, 0))
        label(side, f"v{__version__}", 12, muted=True).pack(anchor="w", padx=20, pady=(0, 18))

        self.nav: dict[str, NavItem] = {}
        for key, text, icon, _ in PAGES:
            item = NavItem(side, icon, text, lambda k=key: self.show(k))
            item.pack(fill="x", padx=10, pady=1)
            self.nav[key] = item

        foot = ctk.CTkFrame(side, fg_color="transparent")
        foot.pack(side="bottom", fill="x", padx=16, pady=16)
        if self.admin:
            label(foot, "Rendszergazdai mód", 12, muted=True).pack(anchor="w")
        else:
            label(foot, "Nincs rendszergazdai jog: a módosítások le vannak tiltva.", 12,
                  wraplength=196, text_color=theme.WARNING).pack(anchor="w", pady=(0, 8))
            button(foot, "Újraindítás adminként", self._relaunch, kind="primary").pack(fill="x")

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True, padx=28, pady=24)
        self.pages = {}
        self.current: str | None = None

    def show(self, key: str) -> None:
        if self.current:
            self.pages[self.current].pack_forget()
            self.nav[self.current].set_active(False)
        if key not in self.pages:
            cls = next(p[3] for p in PAGES if p[0] == key)
            self.pages[key] = cls(self.content, self)
        self.current = key
        self.nav[key].set_active(True)
        self.pages[key].pack(fill="both", expand=True)
        self.pages[key].on_show()

    def _tick(self) -> None:
        if self.current:
            try:
                self.pages[self.current].on_tick()
            except Exception:
                log.exception("Oldalfrissítési hiba")
        self.nav["history"].set_count(len(self.journal.entries()))
        self.after(1000, self._tick)

    def _hardware_ready(self, info) -> None:
        self.hardware = info
        if self.current:
            self.pages[self.current].on_show()

    def _relaunch(self) -> None:
        if winapi.relaunch_as_admin():
            self._on_close()

    # ── Módosítás és visszaállítás ─────────────────────────

    def apply(self, changes: list[Change], title: str, done: Callable[[Outcome], None] | None = None,
              note: str = "", run: Callable[[list[Change]], Outcome] | None = None,
              restore_point_first: bool = True) -> None:
        """Megerősítés után háttérben alkalmaz; az első módosítás előtt visszaállítási pontot kér."""
        changes = [c for c in changes if c]
        if not self.admin:
            self.toasts.show("A módosításhoz rendszergazdai jog kell (bal alul: Újraindítás adminként).",
                             "warning")
            return
        if not changes:
            self.toasts.show("Nincs mit módosítani: már ez a beállítás van érvényben.", "info")
            return
        if not confirm(self, title, [c.label for c in changes], note=note):
            return

        def work():
            notes = []
            if restore_point_first and not self._restore_point_tried:
                self._restore_point_tried = True
                self.tasks.post(self.toasts.show, "Visszaállítási pont készül…", "info")
                ok, message = restore_point.create()
                notes.append((message, "success" if ok else "info"))
            return (run or self.journal.apply)(changes), notes

        def finished(result):
            out, notes = result
            for message, kind in notes:
                self.toasts.show(message, kind, 7000)
            self.toasts.show(out.summary("alkalmazva"), "warning" if out.failed else "success")
            if done:
                done(out)

        self.tasks.run(work, finished)

    def revert(self, entries: list[Change], title: str = "Visszaállítás",
               done: Callable[[Outcome], None] | None = None) -> None:
        if not self.admin:
            self.toasts.show("A visszaállításhoz rendszergazdai jog kell.", "warning")
            return
        if not entries or not confirm(self, title, [f"Vissza: {c.label}" for c in entries],
                                      ok_text="Visszaállítás"):
            return

        def finished(out: Outcome):
            self.toasts.show(out.summary("visszaállítva"), "warning" if out.failed else "success")
            if done:
                done(out)

        self.tasks.run(lambda: self.journal.revert(entries), finished)

    def start_game_session(self) -> None:
        exes = {g["exe"].lower() for g in self.settings["games"]}

        def plan():
            game = game_mode.find_running(exes) if exes else None
            return game, game_mode.plan(self.settings, game)

        def planned(result):
            game, changes = result
            self.apply(changes, "Játék mód indítása",
                       note="A Játék mód leállításakor, a játék bezárásakor és kilépéskor minden visszaáll.",
                       run=lambda ch: self.watcher.start_session(game, ch, notify=False),
                       restore_point_first=False, done=lambda out: self._refresh())

        self.tasks.run(plan, planned)

    def end_game_session(self) -> None:
        self.tasks.run(self.watcher.end_session)

    def _refresh(self) -> None:
        if self.current:
            self.pages[self.current].on_show()

    def save_settings(self) -> None:
        storage.save_settings(self.settings)

    def _on_game_event(self, event: str, name: str, out: Outcome) -> None:
        if event == "start":
            self.toasts.show(f"Játék mód elindult{': ' + name if name else ''} ({out.summary('alkalmazva')}).",
                             "warning" if out.failed else "success")
        else:
            self.toasts.show(f"Játék mód leállt, {out.summary('visszaállítva')}.",
                             "warning" if out.failed else "success")
        self._refresh()

    def _on_close(self) -> None:
        # A Játék mód csak munkamenetre szól: kilépéskor visszaáll; a többi módosítás marad
        self.watcher.stop()
        self.sampler.stop()
        if self.admin and self.journal.entries("game_mode"):
            self.protocol("WM_DELETE_WINDOW", lambda: None)
            self.toasts.show("Játék mód visszaállítása kilépés előtt…", "info")
            self.tasks.run(lambda: self.journal.revert(self.journal.entries("game_mode")),
                           lambda out: self.destroy())
        else:
            self.destroy()
