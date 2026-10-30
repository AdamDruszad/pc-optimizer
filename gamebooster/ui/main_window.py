"""A főablak: Fluent navigáció, közös állapot, és az alkalmaz/visszaállít folyamat."""
import logging
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import (
    FluentWindow,
    InfoBadge,
    InfoBadgePosition,
    InfoBar,
    InfoBarPosition,
    NavigationItemPosition,
)

from ..core import legacy, restore_point, storage, winapi
from ..core.journal import Change, Journal, Outcome
from ..monitoring import hardware
from ..monitoring.sampler import Sampler
from ..optimizers import game_mode
from . import theme
from .components import confirm
from .tasks import run_task
from .views import cleaner, dashboard, game, history, monitor, network, services, startup, tweaks

log = logging.getLogger(__name__)


class MainWindow(FluentWindow):
    gameEvent = Signal(str, str, object)  # a GameWatcher szálából érkezik, a GUI-szálon fut le

    def __init__(self):
        super().__init__()
        theme.init_theme()
        # A Mica a háttérképből színez és átlátszóvá teszi a hátteret; a mélyzöld paletta helyett
        # semleges szürkét adna, ezért ki van kapcsolva
        self.setMicaEffectEnabled(False)
        self.setCustomBackgroundColor(theme.LIGHT["bg"], theme.DARK["bg"])
        self.setWindowTitle("GameBooster")
        if theme.APP_ICON.exists():
            self.setWindowIcon(QIcon(str(theme.APP_ICON)))

        self.admin = winapi.is_admin()
        self.settings = storage.load_settings()
        self.journal = Journal(storage.data_dir() / "journal.json")
        self.hardware: hardware.HardwareInfo | None = None
        self._restore_point_tried = False
        self._closing = False

        self.sampler = Sampler()
        self.sampler.start()
        self.gameEvent.connect(self._on_game_event)
        self.watcher = game_mode.GameWatcher(self.journal, lambda: self.settings,
                                             lambda event, name, out: self.gameEvent.emit(event, name, out))
        self.watcher.start()

        self._build_navigation()
        self.stackedWidget.currentChanged.connect(lambda _: self._refresh())
        self._fit_to_screen()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        QTimer.singleShot(0, self._tick)  # megjelenítés után azonnal (a jelvényt az ablak megjelenése láthatóvá teszi)
        run_task(hardware.detect, self._hardware_ready)
        QTimer.singleShot(500, self._startup_notes)

    # ── Felépítés ──────────────────────────────────────────

    def _build_navigation(self) -> None:
        nav = self.navigationInterface
        nav.setExpandWidth(248)
        nav.setCollapsible(False)  # a terv szerint állandóan kinyitott oldalsáv, csoportfejlécekkel
        self.pages = {
            "dashboard": dashboard.DashboardPage(self), "game": game.GamePage(self),
            "cleaner": cleaner.CleanerPage(self), "startup": startup.StartupPage(self),
            "services": services.ServicesPage(self), "tweaks": tweaks.TweaksPage(self),
            "network": network.NetworkPage(self), "monitor": monitor.MonitorPage(self),
            "history": history.HistoryPage(self),
        }
        self.addSubInterface(self.pages["dashboard"], FIF.HOME, "Áttekintés")
        self.addSubInterface(self.pages["game"], FIF.GAME, "Játék mód")
        self.addSubInterface(self.pages["cleaner"], FIF.BROOM, "Tisztítás")
        nav.addItemHeader("Rendszer")
        self.addSubInterface(self.pages["startup"], FIF.POWER_BUTTON, "Automatikus indítás")
        self.addSubInterface(self.pages["services"], FIF.APPLICATION, "Szolgáltatások")
        self.addSubInterface(self.pages["tweaks"], FIF.SETTING, "Játékbeállítások")
        self.addSubInterface(self.pages["network"], FIF.GLOBE, "Hálózat")
        nav.addItemHeader("Megfigyelés")
        self.addSubInterface(self.pages["monitor"], FIF.SPEED_HIGH, "Teljesítményfigyelő")
        history_item = self.addSubInterface(self.pages["history"], FIF.HISTORY, "Előzmények")
        self.history_badge = InfoBadge.custom("0", *theme.pair("accent"), parent=nav, target=history_item,
                                              position=InfoBadgePosition.NAVIGATION_ITEM)
        nav.addItem("theme", FIF.CONSTRACT, "Világos / sötét téma", onClick=theme.toggle_theme,
                    selectable=False, position=NavigationItemPosition.BOTTOM)
        if self.admin:
            nav.addItem("admin", FIF.CERTIFICATE, "Rendszergazdai mód", selectable=False,
                        position=NavigationItemPosition.BOTTOM)
        else:
            nav.addItem("admin", FIF.CERTIFICATE, "Újraindítás adminként", onClick=self._relaunch,
                        selectable=False, position=NavigationItemPosition.BOTTOM)

    def _fit_to_screen(self) -> None:
        # Az elérhető terület már a tálca nélkül értendő, a Qt a DPI-skálázást is kezeli
        area = self.screen().availableGeometry()
        self.resize(min(1240, area.width() - 32), min(820, area.height() - 32))
        frame = self.frameGeometry()
        frame.moveCenter(area.center())
        self.move(frame.topLeft())

    def show_page(self, key: str) -> None:
        self.switchTo(self.pages[key])

    def current_page(self):
        return self.stackedWidget.currentWidget()

    def _refresh(self) -> None:
        page = self.current_page()
        if page is not None:
            page.on_show()

    def _tick(self) -> None:
        page = self.current_page()
        if page is not None:
            try:
                page.on_tick()
            except Exception:
                log.exception("Oldalfrissítési hiba")
        count = len(self.journal.entries())
        self.history_badge.setText(str(count))
        self.history_badge.setVisible(count > 0)

    def _hardware_ready(self, info) -> None:
        self.hardware = info
        self._refresh()

    def _startup_notes(self) -> None:
        imported = legacy.import_v2(self.journal, storage.legacy_dir())
        if imported:
            self.toast(f"A régi verzió {imported} módosítását átvettem az Előzményekbe; onnan visszaállíthatók.",
                       "info", 8000)
        elif self.journal.entries("game_mode"):
            self.toast("Az előző Játék mód munkamenet módosításai még aktívak (Előzmények).", "warning", 8000)
        if not self.admin:
            self.toast("Rendszergazdai jog nélkül fut: a módosítások le vannak tiltva. "
                       "Bal alul: Újraindítás adminként.", "warning", 8000)

    def _relaunch(self) -> None:
        if winapi.relaunch_as_admin():
            self.close()

    # ── Visszajelzés ───────────────────────────────────────

    def toast(self, message: str, kind: str = "info", duration: int = 4500) -> None:
        show = {"success": InfoBar.success, "warning": InfoBar.warning,
                "danger": InfoBar.error, "info": InfoBar.info}[kind]
        show("", message, orient=Qt.Orientation.Horizontal, isClosable=True, duration=duration,
             position=InfoBarPosition.TOP_RIGHT, parent=self)

    def task(self, work: Callable, done: Callable | None = None, progress: Callable | None = None) -> None:
        run_task(work, done, lambda error: self.toast(f"Hiba: {error}", "danger", 8000), progress)

    # ── Módosítás és visszaállítás ─────────────────────────

    def apply(self, changes: list[Change], title: str, done: Callable[[Outcome], None] | None = None,
              note: str = "", run: Callable[[list[Change]], Outcome] | None = None,
              restore_point_first: bool = True) -> None:
        """Megerősítés után háttérben alkalmaz; az első módosítás előtt visszaállítási pontot kér."""
        changes = [c for c in changes if c]
        if not self.admin:
            self.toast("A módosításhoz rendszergazdai jog kell (bal alul: Újraindítás adminként).", "warning")
            return
        if not changes:
            self.toast("Nincs mit módosítani: már ez a beállítás van érvényben.", "info")
            return
        if not confirm(self, title, [c.label for c in changes], note=note):
            return

        def work():
            notes = []
            if restore_point_first and not self._restore_point_tried:
                self._restore_point_tried = True
                ok, message = restore_point.create()
                notes.append((message, "success" if ok else "info"))
            return (run or self.journal.apply)(changes), notes

        def finished(result):
            out, notes = result
            for message, kind in notes:
                self.toast(message, kind, 7000)
            self.toast(out.summary("alkalmazva"), "warning" if out.failed else "success")
            if done:
                done(out)
            self._refresh()

        if restore_point_first and not self._restore_point_tried:
            self.toast("Visszaállítási pont készül…", "info")
        self.task(work, finished)

    def revert(self, entries: list[Change], title: str = "Visszaállítás",
               done: Callable[[Outcome], None] | None = None) -> None:
        if not self.admin:
            self.toast("A visszaállításhoz rendszergazdai jog kell.", "warning")
            return
        if not entries or not confirm(self, title, [f"Vissza: {c.label}" for c in entries],
                                      ok_text="Visszaállítás"):
            return

        def finished(out: Outcome):
            self.toast(out.summary("visszaállítva"), "warning" if out.failed else "success")
            if done:
                done(out)
            self._refresh()

        self.task(lambda: self.journal.revert(entries), finished)

    def save_settings(self) -> None:
        storage.save_settings(self.settings)

    # ── Játék mód ──────────────────────────────────────────

    def toggle_game_session(self) -> None:
        self.end_game_session() if self.watcher.active else self.start_game_session()

    def start_game_session(self) -> None:
        exes = {g["exe"].lower() for g in self.settings["games"]}

        def plan():
            found = game_mode.find_running(exes) if exes else None
            return found, game_mode.plan(self.settings, found)

        def planned(result):
            found, changes = result
            self.apply(changes, "Játék mód indítása",
                       note="A Játék mód leállításakor, a játék bezárásakor és kilépéskor minden visszaáll.",
                       run=lambda ch: self.watcher.start_session(found, ch, notify=False),
                       restore_point_first=False)

        self.task(plan, planned)

    def end_game_session(self) -> None:
        self.task(self.watcher.end_session)

    def _on_game_event(self, event: str, name: str, out: Outcome) -> None:
        if event == "start":
            self.toast(f"Játék mód elindult{': ' + name if name else ''} ({out.summary('alkalmazva')}).",
                       "warning" if out.failed else "success")
        else:
            self.toast(f"Játék mód leállt, {out.summary('visszaállítva')}.", "warning" if out.failed else "success")
        self._refresh()

    def closeEvent(self, e):
        # A Játék mód csak munkamenetre szól: kilépéskor visszaáll; a többi módosítás marad
        if not self._closing and self.admin and self.journal.entries("game_mode"):
            e.ignore()
            self._closing = True
            self.toast("Játék mód visszaállítása kilépés előtt…", "info")
            run_task(lambda: self.journal.revert(self.journal.entries("game_mode")),
                     lambda _: self.close(), lambda _: self.close())
            return
        self.timer.stop()
        self.watcher.stop()
        self.sampler.stop()
        super().closeEvent(e)
