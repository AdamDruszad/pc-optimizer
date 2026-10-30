from PySide6.QtWidgets import QGridLayout, QHBoxLayout
from qfluentwidgets import BodyLabel, CaptionLabel, SearchLineEdit, SegmentedWidget, SwitchButton, TitleLabel
from qfluentwidgets import FluentIcon as FIF

from ...optimizers import startup
from ..components import Initials, Page, Surface, add_rows, clear, footnote, list_row, text

FILTERS = {"all": "Összes", "on": "Bekapcsolt", "off": "Kikapcsolt"}


class StartupPage(Page):
    def __init__(self, win):
        super().__init__(win, "startupInterface", "Automatikus indítás", "Döntsd el, mi induljon el a Windowszal.")

    def build(self):
        stats = QGridLayout()
        stats.setSpacing(16)
        self.counts = {}
        for i, (key, label) in enumerate([("on", "Automatikusan indul"), ("off", "Kikapcsolva")]):
            card = Surface(padding=16, spacing=2)
            self.counts[key] = text(TitleLabel, "—")
            card.box.addWidget(self.counts[key])
            card.box.addWidget(text(CaptionLabel, label, "muted"))
            stats.addWidget(card, 0, i)
            stats.setColumnStretch(i, 1)
        self.body.addLayout(stats)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.search = SearchLineEdit()
        self.search.setPlaceholderText("Alkalmazás keresése…")
        self.search.textChanged.connect(lambda _: self._render())
        row.addWidget(self.search, 1)
        self.filter = SegmentedWidget()
        for key, label in FILTERS.items():
            self.filter.addItem(key, label, onClick=lambda k=key: self._set_filter(k))
        self.filter.setCurrentItem("all")
        row.addWidget(self.filter)
        self.body.addLayout(row)

        card = Surface(padding=16, spacing=0)
        head = QHBoxLayout()
        head.addWidget(text(CaptionLabel, "Alkalmazás", "muted"))
        head.addStretch(1)
        head.addWidget(text(CaptionLabel, "Indul a Windowszal", "muted"))
        card.box.addLayout(head)
        self.list = card.box
        self.body.addWidget(card)
        self.body.addLayout(footnote(FIF.INFO, "A kikapcsolás csak az automatikus indulást érinti, ugyanúgy, mint "
                                               "a Feladatkezelőben; az alkalmazás kézzel továbbra is elindítható."))
        self.items: list[startup.StartupItem] = []
        self.mode = "all"

    def _set_filter(self, key):
        self.mode = key
        self._render()

    def on_show(self):
        self.win.task(startup.items, self._loaded)

    def _loaded(self, items):
        self.items = items
        on = sum(i.enabled for i in items)
        self.counts["on"].setText(str(on))
        self.counts["off"].setText(str(len(items) - on))
        self._render()

    def _render(self):
        # A fejléc (0. elem) marad, a sorok újraépülnek
        while self.list.count() > 1:
            item = self.list.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                clear(item.layout())
        query = self.search.text().lower()
        visible = [i for i in self.items
                   if (self.mode == "all" or (self.mode == "on") == i.enabled)
                   and query in f"{i.name} {i.command}".lower()]
        if not visible:
            self.list.addWidget(text(BodyLabel, "Nincs találat. Próbálj rövidebb nevet vagy másik szűrőt.",
                                     "muted"))
            return
        rows = []
        for item in visible:
            switch = SwitchButton()
            switch.setOnText("Be")
            switch.setOffText("Ki")
            switch.setChecked(item.enabled)
            switch.setAccessibleName(f"{item.name} automatikus indítása")
            switch.checkedChanged.connect(lambda on, it=item, sw=switch: self._toggle(it, on, sw))
            rows.append(list_row(item.name, f"{item.location} · {item.command}", Initials(item.name), (switch,)))
        add_rows(self.list, rows)

    def _toggle(self, item, enable, switch):
        # A kapcsoló a megerősítés és az eredmény után áll be a valódi állapotra
        switch.blockSignals(True)
        switch.setChecked(item.enabled)
        switch.blockSignals(False)
        self.win.apply([startup.plan_toggle(item, enable)], "Automatikus indítás módosítása",
                       done=lambda out: self.on_show())
