import os

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ExpandGroupSettingCard,
    LineEdit,
    PushButton,
    TransparentToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from ...optimizers import power, tweaks
from ..components import (
    HeroCard,
    Initials,
    Page,
    Surface,
    SwitchRow,
    add_rows,
    clear,
    footnote,
    list_row,
    section,
    text,
)
from .dashboard import hero_state


def _gpu_high(path: str) -> bool:
    current, _ = tweaks.winapi.reg_read("HKCU", tweaks._DX_PREFS, path)
    return "GpuPreference=2;" in (current or "")


class GamePage(Page):
    def __init__(self, win):
        super().__init__(win, "gameInterface", "Játék mód", "A rendszer a játékhoz igazítva.")

    def build(self):
        self.hero = HeroCard("Munkamenet részletei", lambda: self.win.show_page("history"), with_toggle=True)
        self.hero.toggled.connect(self._toggle)
        self.body.addWidget(self.hero)
        self.body.addSpacing(8)

        columns = QHBoxLayout()
        columns.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(12)
        add = PushButton(FIF.ADD, "Hozzáadás")
        add.clicked.connect(self._add_game)
        left.addLayout(section("Játékaid", add))
        card = Surface(padding=16, spacing=0)
        self.games = card.box
        left.addWidget(card)
        left.addLayout(footnote(FIF.INFO, "A felvett programokat a GameBooster felismeri induláskor "
                                          "(ha be van kapcsolva az automatikus indítás)."))
        left.addStretch(1)
        columns.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addLayout(section("Így működjön"))
        self.switches = {}
        for key, icon, title, content in [
                ("auto_game_mode", FIF.PLAY, "Automatikus indítás", "A felvett játékokkal együtt."),
                ("game_power_plan", FIF.SPEED_HIGH, "Nagy teljesítményű energiaséma", "A munkamenet idejére."),
                ("game_priority", FIF.GAME, "Játék előnyben részesítése", "Magasabb folyamatprioritás.")]:
            card = SwitchRow(icon, title, content)
            card.switch.setChecked(self.win.settings[key])
            card.switch.checkedChanged.connect(lambda on, k=key: self._set(k, on))
            self.switches[key] = card
            right.addWidget(card)

        advanced = ExpandGroupSettingCard(FIF.DEVELOPER_TOOLS, "Haladó beállítások",
                                          "Háttérappok prioritása és Ultimate séma")
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(48, 12, 48, 12)
        v.setSpacing(8)
        row = QHBoxLayout()
        self.bg_entry = LineEdit()
        self.bg_entry.setPlaceholderText("program.exe")
        self.bg_entry.setClearButtonEnabled(True)
        self.bg_entry.returnPressed.connect(self._add_background)
        row.addWidget(self.bg_entry, 1)
        add_bg = PushButton(FIF.ADD, "Alkalmazás hozzáadása")
        add_bg.clicked.connect(self._add_background)
        row.addWidget(add_bg)
        v.addLayout(row)
        self.bg_list = text(CaptionLabel, "", "muted", wrap=True)
        v.addWidget(self.bg_list)
        buttons = QHBoxLayout()
        clear_bg = PushButton(FIF.DELETE, "Lista törlése")
        clear_bg.clicked.connect(self._clear_background)
        buttons.addWidget(clear_bg)
        ultimate = PushButton(FIF.SPEED_HIGH, "Ultimate Performance séma hozzáadása")
        ultimate.clicked.connect(self._add_ultimate)
        buttons.addWidget(ultimate)
        buttons.addStretch(1)
        v.addLayout(buttons)
        advanced.addGroupWidget(box)
        right.addWidget(advanced)
        right.addStretch(1)
        columns.addLayout(right, 1)
        self.body.addLayout(columns)
        self.body.addLayout(footnote(FIF.HISTORY, "A visszaállítás a munkamenet által módosított beállításokra "
                                                  "vonatkozik."))

    def _toggle(self):
        self.hero.toggle.setChecked(self.win.watcher.active)
        self.win.toggle_game_session()

    def on_show(self):
        clear(self.games)
        games = self.win.settings["games"]
        if not games:
            self.games.addWidget(text(BodyLabel, "Még nincs felvett játék. A Hozzáadás gombbal válaszd ki "
                                                 "a játék .exe fájlját.", "muted", wrap=True))
        rows = []
        for g in games:
            path = g.get("path", "")
            high = bool(path) and _gpu_high(path)
            gpu = PushButton("Windows döntsön" if high else "Nagy teljesítményű GPU")
            gpu.setEnabled(bool(path))
            gpu.clicked.connect(lambda _=False, p=path, h=high: self._toggle_gpu(p, not h))
            remove = TransparentToolButton(FIF.DELETE)
            remove.setToolTip("Eltávolítás a listából")
            remove.clicked.connect(lambda _=False, game=g: self._remove(game))
            name = g["exe"].removesuffix(".exe").removesuffix(".EXE")
            sub = ("Nagy teljesítményű GPU" if high else "Windows választ GPU-t") + (f" · {path}" if path else "")
            rows.append(list_row(name, sub, Initials(name), (gpu, remove)))
        add_rows(self.games, rows)
        apps = self.win.settings["background_apps"]
        self.bg_list.setText(", ".join(apps) if apps else "Még nincs hozzáadott háttéralkalmazás.")
        for key, card in self.switches.items():
            card.switch.blockSignals(True)
            card.switch.setChecked(self.win.settings[key])
            card.switch.blockSignals(False)
        self.on_tick()

    def on_tick(self):
        hero_state(self.win, self.hero, "Játékra készen.")

    def _set(self, key, value):
        self.win.settings[key] = value
        self.win.save_settings()

    def _add_game(self):
        path, _ = QFileDialog.getOpenFileName(self, "Játék kiválasztása", "", "Program (*.exe)")
        if not path:
            return
        path = os.path.normpath(path)
        games = self.win.settings["games"]
        if not any(g.get("path", "").lower() == path.lower() for g in games):
            games.append({"exe": os.path.basename(path), "path": path})
            self.win.save_settings()
        self.on_show()

    def _remove(self, game):
        self.win.settings["games"].remove(game)
        self.win.save_settings()
        self.on_show()

    def _toggle_gpu(self, path, high):
        self.win.apply([tweaks.gpu_preference_change(path, high)], "GPU-választás",
                       note="Hibrid (integrált + dedikált GPU-s) gépen számít; a Windows Grafika beállításával "
                            "azonos.", done=lambda out: self.on_show())

    def _add_background(self):
        name = self.bg_entry.text().strip()
        if not name.lower().endswith(".exe"):
            self.win.toast("Programnevet adj meg .exe végződéssel, pl. OneDrive.exe.", "warning")
            return
        apps = self.win.settings["background_apps"]
        if name.lower() not in (a.lower() for a in apps):
            apps.append(name)
            self.win.save_settings()
        self.bg_entry.clear()
        self.on_show()

    def _clear_background(self):
        self.win.settings["background_apps"] = []
        self.win.save_settings()
        self.on_show()

    def _add_ultimate(self):
        def work():
            power.add_ultimate(self.win.settings)
            self.win.save_settings()
        self.win.task(work, lambda _: self.win.toast("Ultimate Performance séma hozzáadva; a Játék mód ezt "
                                                     "használja.", "success"))
