import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import BodyLabel, CaptionLabel, HyperlinkButton, IconWidget, PushButton, SubtitleLabel
from qfluentwidgets import FluentIcon as FIF

from ...core import restore_point, storage
from .. import theme
from ..components import ActionBar, Page, Surface, add_rows, clear, danger_button, list_row, section, text

SOURCE_ICONS = {"network": FIF.GLOBE, "services": FIF.APPLICATION, "startup": FIF.POWER_BUTTON,
                "game_mode": FIF.GAME, "gpu_pref": FIF.GAME, "tweaks": FIF.SETTING, "v2": FIF.HISTORY}


class HistoryPage(Page):
    def __init__(self, win):
        super().__init__(win, "historyInterface", "Előzmények", "Minden változásnak megvan az előzménye.")

    def build(self):
        top = QHBoxLayout()
        self.count = text(CaptionLabel, "", "muted")
        top.addWidget(self.count)
        top.addStretch(1)
        point = PushButton(FIF.SAVE, "Visszaállítási pont")
        point.clicked.connect(self._restore_point)
        top.addWidget(point)
        folder = PushButton(FIF.FOLDER, "Adatmappa")
        folder.clicked.connect(lambda: os.startfile(storage.data_dir()))
        top.addWidget(folder)
        self.body.addLayout(top)
        self.heading = section("Legutóbbi módosítások")
        self.body.addLayout(self.heading)
        self.card = Surface(padding=16, spacing=0)
        self.body.addWidget(self.card)
        self.revert_all = danger_button("Mind visszaállítása")
        self.revert_all.clicked.connect(lambda: self.win.revert(self.win.journal.entries(), "Mindent visszaállít",
                                                                done=lambda out: self.on_show()))
        self.bar = ActionBar("Visszaállítás átláthatóan", "Minden módosítás külön is visszavonható; a sikertelen "
                                                          "tétel a listában marad.", self.revert_all)
        self.body.addWidget(self.bar)

    def on_show(self):
        entries = self.win.journal.entries()
        self.count.setText(f"{len(entries)} visszaállítható módosítás")
        self.revert_all.setText(f"Mind a(z) {len(entries)} visszaállítása")
        self.bar.setVisible(bool(entries))
        clear(self.card.box)
        if not entries:
            icon = IconWidget(FIF.ACCEPT)
            icon.setFixedSize(32, 32)
            self.card.box.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
            self.card.box.addWidget(text(SubtitleLabel, "Minden a Windows eredeti beállításán van."), 0,
                                    Qt.AlignmentFlag.AlignHCenter)
            self.card.box.addWidget(text(BodyLabel, "Az új változtatások itt jelennek majd meg.", "muted"), 0,
                                    Qt.AlignmentFlag.AlignHCenter)
            back = HyperlinkButton("", "Vissza az áttekintéshez")
            back.clicked.connect(lambda: self.win.show_page("dashboard"))
            self.card.box.addWidget(back, 0, Qt.AlignmentFlag.AlignHCenter)
            return
        rows = []
        for c in reversed(entries):
            icon = IconWidget(SOURCE_ICONS.get(c.source, FIF.SETTING))
            icon.setFixedSize(20, 20)
            undo = PushButton(FIF.RETURN, "Visszaállítás")
            undo.clicked.connect(lambda _=False, ch=c: self.win.revert([ch], done=lambda out: self.on_show()))
            when = c.at.replace("T", " ")[:16]
            rows.append(list_row(c.label, f"{when} · {theme.SOURCE_LABELS.get(c.source, c.source)} · "
                                          "a korábbi érték megőrizve", icon, (undo,)))
        add_rows(self.card.box, rows)

    def _restore_point(self):
        if not self.win.admin:
            self.win.toast("Ehhez rendszergazdai jog kell.", "warning")
            return
        self.win.toast("Visszaállítási pont készül…", "info")
        self.win.task(restore_point.create, lambda r: self.win.toast(r[1], "success" if r[0] else "info", 7000))
