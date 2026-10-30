from PySide6.QtCore import Qt
from qfluentwidgets import (
    BodyLabel,
    HyperlinkButton,
    InfoBar,
    StrongBodyLabel,
)
from qfluentwidgets import FluentIcon as FIF

from ...optimizers import tweaks
from ..components import Page, Surface, SwitchRow, badge, footnote, section, text

ICONS = {"game_dvr_off": FIF.VIDEO, "windowed_opt": FIF.FIT_PAGE, "hags": FIF.GAME, "game_mode": FIF.PLAY}


class TweaksPage(Page):
    def __init__(self, win):
        super().__init__(win, "tweaksInterface", "Játékbeállítások", "Átlátható kapcsolók. Pontosan leírt változások.")

    def build(self):
        self.cards: dict[str, tuple[SwitchRow, object]] = {}
        for t in tweaks.TWEAKS:
            state = badge("—", "accent")
            tags = [state, badge(f"hatás: {t.impact}", "success" if t.impact == "mérhető" else "accent")]
            if t.restart:
                tags.append(badge("újraindítás kell", "warning"))
            card = SwitchRow(ICONS.get(t.key, FIF.SETTING), t.label, t.description, tags)
            card.switch.checkedChanged.connect(lambda on, tw=t: self._toggle(tw, on))
            self.cards[t.key] = (card, state)
            self.body.addWidget(card)

        self.body.addSpacing(8)
        security = Surface(padding=20, spacing=10)
        security.box.addLayout(section("Biztonság és teljesítmény"))
        security.box.addWidget(text(BodyLabel, "A memóriaintegritás a rendszer védelmét szolgálja. Egyes játékokban "
                                               "mérhetően lassít, de a GameBooster ezt a biztonsági beállítást nem "
                                               "kapcsolja át.", "muted", wrap=True))
        self.hvci = text(StrongBodyLabel, "—")
        security.box.addWidget(self.hvci)
        where = HyperlinkButton("", "Hol találom a Windowsban?")
        where.setIcon(FIF.INFO)
        where.clicked.connect(lambda: InfoBar.info(
            "", "Windows Biztonság → Eszközbiztonság → Magelkülönítés → Memóriaintegritás",
            orient=Qt.Orientation.Horizontal, isClosable=True, duration=6000, parent=self.win))
        security.box.addWidget(where, 0, Qt.AlignmentFlag.AlignLeft)
        self.body.addWidget(security)
        self.body.addLayout(footnote(FIF.INFO, "A beállítások hatása hardvertől és játéktól függ; FPS-növekedést "
                                               "nem ígérünk."))

    def on_show(self):
        self.win.task(lambda: ({t.key: tweaks.is_on(t) for t in tweaks.TWEAKS}, tweaks.security_status()),
                      self._loaded)

    def _loaded(self, result):
        states, security = result
        for key, (card, state) in self.cards.items():
            card.switch.blockSignals(True)
            card.switch.setChecked(states[key])
            card.switch.blockSignals(False)
            state.setText("Bekapcsolva" if states[key] else "Kikapcsolva")
        hvci = security["memory_integrity"]
        self.hvci.setText({None: "Memóriaintegritás: nincs beállítva (Windows-alapérték)",
                           True: "Memóriaintegritás: bekapcsolva",
                           False: "Memóriaintegritás: kikapcsolva"}[hvci])

    def _toggle(self, tweak, on):
        self.on_show()  # megszakított megerősítésnél a kapcsoló visszaáll
        if on:
            self.win.apply(tweaks.plan(tweak), tweak.label, done=lambda out: self.on_show(),
                           note="Újraindítás után lép életbe." if tweak.restart else "")
            return
        journaled = [c for c in self.win.journal.entries() if c.target in tweaks.targets(tweak)]
        if journaled:
            self.win.revert(journaled, f"{tweak.label}: visszaállítás", done=lambda out: self.on_show())
        else:
            self.win.toast("Ez a beállítás már a GameBooster előtt is így volt; a Windows Beállításokban "
                           "módosíthatod.", "info")
