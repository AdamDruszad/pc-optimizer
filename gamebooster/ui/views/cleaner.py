import threading

from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    CheckBox,
    ExpandGroupSettingCard,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    StrongBodyLabel,
)
from qfluentwidgets import FluentIcon as FIF

from ...optimizers import cleaner
from .. import theme
from ..components import (
    ActionBar,
    HeroCard,
    Page,
    Surface,
    add_rows,
    badge,
    confirm,
    footnote,
    list_row,
    section,
    text,
)

STEPS = ("Vizsgálat", "Kijelölés", "Eredmény")


class CleanerPage(Page):
    def __init__(self, win):
        super().__init__(win, "cleanerInterface", "Tisztítás", "Szabadíts fel helyet, átláthatóan.")

    def build(self):
        self.step_row = QHBoxLayout()
        self.step_row.setSpacing(16)
        self.steps = []
        for i, name in enumerate(STEPS, 1):
            b = badge(str(i), "accent")
            label = text(CaptionLabel, name, "muted")
            self.step_row.addWidget(b)
            self.step_row.addWidget(label)
            self.steps.append((b, label))
        self.step_row.addStretch(1)
        self.body.addLayout(self.step_row)

        self.scan_button = PrimaryPushButton(FIF.SEARCH, "Vizsgálat indítása")
        self.scan_button.clicked.connect(self._scan)
        self.hero = HeroCard(action=self.scan_button)
        self.body.addWidget(self.hero)
        self.progress = ProgressBar()
        self.progress.hide()
        self.body.addWidget(self.progress)

        self.body.addSpacing(8)
        self.body.addLayout(section("Vizsgálati eredmények", text(CaptionLabel, "Méret", "muted")))
        card = Surface(padding=16, spacing=0)
        self.rows = {}
        rows = []
        for target in cleaner.TARGETS:
            box = CheckBox()
            box.setFixedWidth(28)  # felirat nélkül; különben 57 px-et foglal a szövegnek
            box.setEnabled(False)
            box.setAccessibleName(target.label)
            box.stateChanged.connect(lambda _: self._update_total())
            size = text(StrongBodyLabel, "—")
            rows.append(list_row(target.label, target.note or "Ismert gyorsítótár-mappa.", box, (size,)))
            self.rows[target.key] = (box, size)
        add_rows(card.box, rows)
        self.body.addWidget(card)

        self.clean_button = PrimaryPushButton(FIF.DELETE, "Kijelöltek törlése")
        self.clean_button.setEnabled(False)
        self.clean_button.clicked.connect(self._clean)
        self.bar = ActionBar("Nincs kijelölés", "A törlés előtt összefoglalót kapsz.", self.clean_button)
        self.body.addWidget(self.bar)

        system = ExpandGroupSettingCard(FIF.UPDATE, "Windows-frissítések maradványai",
                                        "Rendszergazdai jog kell; a komponenstár takarítása lassú lehet.")
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(48, 12, 48, 12)
        do_cache = PushButton(FIF.CLOUD, "Kézbesítésoptimalizálás gyorsítótár")
        do_cache.clicked.connect(lambda: self._system(
            "Kézbesítésoptimalizálás gyorsítótár törlése", cleaner.delivery_optimization_cleanup,
            "A frissítésekhez letöltött, más gépeknek megosztott fájlok törlése."))
        h.addWidget(do_cache)
        dism = PushButton(FIF.BROOM, "Komponenstár takarítása (DISM)")
        dism.clicked.connect(lambda: self._system(
            "Komponenstár takarítása", cleaner.component_cleanup,
            "A felülírt Windows-komponensek törlése. Akár 10–20 percig is tarthat; utána a régi frissítések "
            "nem távolíthatók el."))
        h.addWidget(dism)
        h.addStretch(1)
        system.addGroupWidget(box)
        self.body.addWidget(system)
        self.body.addLayout(footnote(FIF.INFO, "A tisztító a személyes dokumentumokat és a Lomtár tartalmát "
                                               "kihagyja, és nem követi a mappák közötti hivatkozásokat."))
        self.scans: dict[str, cleaner.Scan] = {}
        self._set_step(0, "Nézd meg, mi foglalja a helyet.",
                       "Az ideiglenes fájlok és gyorsítótárak méretét vizsgálja; törlés csak a jóváhagyásod után.")

    def _set_step(self, index: int, title: str, desc: str) -> None:
        for i, (b, label) in enumerate(self.steps):
            b.setVisible(True)
            label.setTextColor(*theme.pair("text" if i == index else "muted"))
        self.hero.set_state(title, f"{index + 1}. lépés · {STEPS[index]}", desc)

    def _scan(self):
        self.scan_button.setEnabled(False)
        self.scan_button.setText("Vizsgálat…")
        self.progress.setRange(0, 0)  # határozatlan
        self.progress.show()
        self.win.task(lambda: cleaner.scan(cleaner.TARGETS), self._scanned)

    def _scanned(self, results):
        self.progress.hide()
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Újravizsgálat")
        self.scans = {s.target.key: s for s in results}
        total = 0
        for key, (box, size) in self.rows.items():
            s = self.scans[key]
            total += s.size
            size.setText(theme.fmt_size(s.size) if s.files else "üres")
            box.setEnabled(bool(s.files))
            box.setChecked(bool(s.files) and "shader" not in key)
        self._set_step(1, "Válaszd ki, mi törlődjön.",
                       f"{theme.fmt_size(total)} találat. A shader-gyorsítótárak külön választhatók: törlésük után "
                       "az első játékindítás rövid ideig akadhat.")
        self._update_total()

    def _selected(self):
        return [self.scans[k] for k, (box, _) in self.rows.items() if box.isChecked() and k in self.scans]

    def _update_total(self):
        chosen = self._selected()
        total = sum(s.size for s in chosen)
        self.bar.title.setText(f"{theme.fmt_size(total)} kijelölve" if chosen else "Nincs kijelölés")
        self.clean_button.setText(f"Kijelöltek törlése · {theme.fmt_size(total)}" if chosen else "Kijelöltek törlése")
        self.clean_button.setEnabled(bool(chosen))

    def _clean(self):
        chosen = self._selected()
        lines = [f"{s.target.label}: {theme.fmt_size(s.size)} ({len(s.files)} fájl)" for s in chosen]
        if not confirm(self.win, "Törlés", lines, ok_text="Törlés", danger=True,
                       note="A törölt fájlok nem kerülnek a Lomtárba, és nem állíthatók vissza."):
            return
        self.clean_button.setEnabled(False)
        self.scan_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.show()
        self.win.task(lambda progress: cleaner.clean(chosen, threading.Event(), progress), self._cleaned,
                      progress=lambda f: self.progress.setValue(int(f * 100)))

    def _cleaned(self, result):
        self.progress.hide()
        self.scan_button.setEnabled(True)
        skipped = f", {result.skipped} zárolt fájl kihagyva" if result.skipped else ""
        self._set_step(2, f"{theme.fmt_size(result.freed)} felszabadítva.",
                       f"{result.deleted} fájl törölve{skipped}. Újravizsgálattal ellenőrizheted az eredményt.")
        self.win.toast(f"{theme.fmt_size(result.freed)} felszabadítva ({result.deleted} fájl{skipped}).", "success")
        for box, size in self.rows.values():
            box.setChecked(False)
            box.setEnabled(False)
            size.setText("—")
        self.scans = {}
        self._update_total()

    def _system(self, title, action, note):
        if not self.win.admin:
            self.win.toast("Ehhez rendszergazdai jog kell.", "warning")
            return
        if not confirm(self.win, title, [title], note=note, ok_text="Indítás"):
            return
        self.win.toast(f"{title} folyamatban…", "info")
        self.win.task(action, lambda r: self.win.toast(
            f"{title}: kész." if r[0] else f"{title}: sikertelen ({r[1][:160]})",
            "success" if r[0] else "warning", 8000))
