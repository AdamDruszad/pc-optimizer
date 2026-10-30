from PySide6.QtCore import Qt
from qfluentwidgets import CheckBox, InfoBar, InfoBarIcon, InfoBarPosition, PrimaryPushButton, PushButton

from ...optimizers import services
from ..components import ActionBar, Page, Surface, add_rows, badge, clear, list_row


class ServicesPage(Page):
    def __init__(self, win):
        super().__init__(win, "servicesInterface", "Szolgáltatások", "Lásd a következményt, mielőtt változtatsz.")

    def build(self):
        warning = InfoBar(InfoBarIcon.WARNING, "",
                          "A szolgáltatások más programokat is érinthetnek. A legtöbb „Kézi” indításra kerül, így ha "
                          "egy program igényli, a Windows elindítja. Minden módosítás visszaállítható.",
                          orient=Qt.Orientation.Horizontal, isClosable=False, duration=-1, position=InfoBarPosition.NONE,
                          parent=self.content)
        self.body.addWidget(warning)
        card = Surface(padding=16, spacing=0)
        self.list = card.box
        self.body.addWidget(card)
        self.review = PrimaryPushButton("Változtatások áttekintése")
        self.review.setEnabled(False)
        self.review.clicked.connect(self._apply)
        self.bar = ActionBar("0 szolgáltatás kijelölve", "A következő lépésben áttekintheted a változást.",
                             self.review)
        self.body.addWidget(self.bar)
        self.boxes: dict[str, CheckBox] = {}

    def on_show(self):
        self.win.task(services.status, self._loaded)

    def _loaded(self, status):
        clear(self.list)
        self.boxes.clear()
        rows = []
        for info, current, running in status:
            journaled = self.win.journal.find(f"service:{info.name}")
            done = current is not None and not services.needs_change(current, info.target)
            box = CheckBox()
            box.setFixedWidth(28)  # felirat nélkül; különben 57 px-et foglal a szövegnek
            box.setEnabled(current is not None and not done)
            box.setAccessibleName(info.label)
            box.stateChanged.connect(lambda _: self._update())
            self.boxes[info.name] = box
            state = services.START_LABELS[current] + (", fut" if running else "")
            trailing = [badge(f"kockázat: {info.risk}", "success" if info.risk == "alacsony" else "warning"),
                        badge(state, "success" if done else "accent")]
            if journaled:
                undo = PushButton("Visszaállítás")
                undo.clicked.connect(lambda _=False, c=journaled: self.win.revert([c], done=lambda out: self.on_show()))
                trailing.append(undo)
            rows.append(list_row(info.label, f"{info.name} · {info.note}", box, tuple(trailing)))
        add_rows(self.list, rows)
        self._update()

    def _update(self):
        n = sum(b.isChecked() for b in self.boxes.values())
        self.bar.title.setText(f"{n} szolgáltatás kijelölve")
        self.review.setEnabled(n > 0)

    def _apply(self):
        names = [n for n, b in self.boxes.items() if b.isChecked()]
        self.win.task(lambda: services.plan(names), lambda changes: self.win.apply(
            changes, "Szolgáltatások módosítása", done=lambda out: self.on_show(),
            note="A futó szolgáltatások leállnak; visszaállításkor újraindulnak."))
