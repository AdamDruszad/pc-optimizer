from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    HorizontalSeparator,
    HyperlinkButton,
    IconWidget,
    StrongBodyLabel,
)
from qfluentwidgets import FluentIcon as FIF

from ...optimizers import game_mode, tweaks
from .. import theme
from ..components import (
    HeroCard,
    Initials,
    MetricCard,
    Page,
    Surface,
    add_rows,
    clear,
    list_row,
    section,
    text,
)


def hero_state(win, hero: HeroCard, ready_title: str) -> None:
    """A Játék mód állapota a hős panelen (Áttekintés és Játék mód oldalon közös)."""
    w = win.watcher
    if w.active:
        n = len(win.journal.entries(game_mode.SOURCE))
        hero.set_state("A játéké a rendszer.", "Játék mód aktív",
                       f"{w._game_name(w.game) or 'Kézi munkamenet'}: {n} módosítás. "
                       "A játék bezárásakor és kilépéskor minden visszaáll.",
                       True, "Aktív · Kikapcsolás")
    else:
        auto = win.settings["auto_game_mode"]
        hero.set_state(ready_title, "Játék mód · Készenlét",
                       "Energiaséma és játékprioritás egy mozdulattal. "
                       + ("A felvett játékokkal automatikusan indul." if auto else "Kilépéskor visszaáll."),
                       False, "Bekapcsolás")


def game_rows(win, layout: QVBoxLayout) -> None:
    clear(layout)
    games = win.settings["games"]
    if not games:
        layout.addWidget(text(BodyLabel, "Még nincs felvett játék. A Játék mód oldalon adhatsz hozzá.", "muted",
                              wrap=True))
        return
    rows = []
    for g in games:
        details = HyperlinkButton("", "Részletek")
        details.setIcon(FIF.LINK)
        details.clicked.connect(lambda: win.show_page("game"))
        name = g["exe"].removesuffix(".exe").removesuffix(".EXE")
        rows.append(list_row(name, g.get("path", ""), Initials(name), (details,)))
    add_rows(layout, rows)


class DashboardPage(Page):
    def __init__(self, win):
        super().__init__(win, "dashboardInterface", "Műszerfal", "A géped teljesítménye. Közvetlenül a kezedben.")

    def build(self):
        self.hero = HeroCard("Játék mód beállításai", lambda: self.win.show_page("game"), with_toggle=True)
        self.hero.toggled.connect(self._toggle)
        self.body.addWidget(self.hero)

        self.body.addSpacing(8)
        self.body.addLayout(section("Rendszerterhelés", text(CaptionLabel, "Elmúlt 2 perc · élő", "muted")))
        grid = QGridLayout()
        grid.setSpacing(16)
        self.cards = {}
        for i, (key, name, icon) in enumerate([("cpu", "CPU", FIF.SPEED_HIGH), ("ram", "Memória", FIF.LIBRARY),
                                                ("gpu", "GPU", FIF.GAME), ("net", "Hálózat", FIF.WIFI)]):
            self.cards[key] = MetricCard(name, icon)
            grid.addWidget(self.cards[key], 0, i)
            grid.setColumnStretch(i, 1)
        self.body.addLayout(grid)

        self.body.addSpacing(8)
        bottom = QHBoxLayout()
        bottom.setSpacing(24)
        games = QVBoxLayout()
        games.setSpacing(12)
        add = HyperlinkButton("", "Játék hozzáadása")
        add.setIcon(FIF.ADD)
        add.clicked.connect(lambda: self.win.show_page("game"))
        games.addLayout(section("Játékprofilok", add))
        card = Surface(padding=16, spacing=0)
        self.games = card.box
        games.addWidget(card)
        games.addStretch(1)
        bottom.addLayout(games, 3)

        system = QVBoxLayout()
        system.setSpacing(12)
        system.addLayout(section("Konfiguráció"))
        card = Surface(padding=20, spacing=10)
        self.cpu = text(StrongBodyLabel, "Hardver felismerése…")
        card.box.addWidget(self.cpu)
        self.specs = {}
        for key in ("Memória", "Grafika", "Rendszer", "Memóriaintegritás"):
            row = QHBoxLayout()
            row.addWidget(text(CaptionLabel, key, "muted"))
            row.addStretch(1)
            self.specs[key] = text(StrongBodyLabel, "—")
            row.addWidget(self.specs[key])
            card.box.addLayout(row)
        card.box.addWidget(HorizontalSeparator())
        changes = QHBoxLayout()
        icon = IconWidget(FIF.HISTORY)
        icon.setFixedSize(16, 16)
        changes.addWidget(icon)
        self.changes = text(CaptionLabel, "", "muted")
        changes.addWidget(self.changes, 1)
        card.box.addLayout(changes)
        link = HyperlinkButton("", "Módosítások áttekintése")
        link.setIcon(FIF.LINK)
        link.clicked.connect(lambda: self.win.show_page("history"))
        card.box.addWidget(link)
        system.addWidget(card)
        system.addStretch(1)
        bottom.addLayout(system, 2)
        self.body.addLayout(bottom)

    def _toggle(self):
        self.hero.toggle.setChecked(self.win.watcher.active)  # a valódi állapotot az eredmény frissíti
        self.win.toggle_game_session()

    def on_show(self):
        game_rows(self.win, self.games)
        hw = self.win.hardware
        if hw:
            self.cpu.setText(hw.cpu)
            self.specs["Memória"].setText(f"{theme.fmt_num(hw.ram_gb, 0)} GB")
            self.specs["Grafika"].setText(", ".join(g.name for g in hw.gpus) or "Nem azonosítható")
            self.specs["Rendszer"].setText(hw.windows)
        hvci = tweaks.security_status()["memory_integrity"]
        self.specs["Memóriaintegritás"].setText({None: "Alapérték", True: "Bekapcsolva", False: "Kikapcsolva"}[hvci])
        self.on_tick()

    def on_tick(self):
        hero_state(self.win, self.hero, "Játékra készen.")
        s, h = self.win.sampler.latest, self.win.sampler.history
        self.cards["cpu"].show_value(f"{s.cpu:.0f} %", f"{theme.fmt_num(s.cpu_mhz / 1000, 2)} GHz", h["cpu"], 100)
        self.cards["ram"].show_value(f"{s.ram_pct:.0f} %",
                                     f"{theme.fmt_num(s.ram_used_gb)} / {theme.fmt_num(s.ram_total_gb, 0)} GB",
                                     h["ram_pct"], 100)
        if s.gpu is None:
            self.cards["gpu"].show_value("—", "Nem mérhető")
        else:
            mem = f"{theme.fmt_num(s.gpu_mem_gb)} GB VRAM" if s.gpu_mem_gb else "3D motor"
            self.cards["gpu"].show_value(f"{s.gpu:.0f} %", mem, h["gpu"], 100)
        self.cards["net"].show_value(f"{theme.fmt_num(s.net_down_mbs)} MB/s",
                                     f"Feltöltés: {theme.fmt_num(s.net_up_mbs)} MB/s", h["net_down_mbs"])
        n = len(self.win.journal.entries())
        self.changes.setText(f"{n} alkalmazott módosítás" if n else "Nincs aktív módosítás")
