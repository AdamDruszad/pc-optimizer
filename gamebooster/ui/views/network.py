from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    HorizontalSeparator,
    HyperlinkButton,
    LargeTitleLabel,
    LineEdit,
    PrimaryPushButton,
    PushButton,
)
from qfluentwidgets import FluentIcon as FIF

from ...optimizers import network
from ..components import Page, Sparkline, Surface, badge, footnote, section, text


class NetworkPage(Page):
    def __init__(self, win):
        super().__init__(win, "networkInterface", "Hálózat", "Mérés és DNS-beállítások egy helyen.")

    def build(self):
        columns = QHBoxLayout()
        columns.setSpacing(24)

        latency = Surface(padding=20, spacing=10)
        latency.box.addLayout(section("Kapcsolódási idő", badge("TCP · 443-as port", "accent")))
        latency.box.addWidget(text(CaptionLabel, "10 kapcsolatfelépítés a megadott célhoz.", "muted"))
        value = QHBoxLayout()
        self.value = text(LargeTitleLabel, "—")
        value.addWidget(self.value)
        value.addWidget(text(BodyLabel, "ms", "muted"), 0, Qt.AlignmentFlag.AlignBottom)
        value.addStretch(1)
        latency.box.addLayout(value)
        self.summary = text(CaptionLabel, "Indíts mérést az eredmény megjelenítéséhez.", "muted", wrap=True)
        latency.box.addWidget(self.summary)
        self.chart = Sparkline(64)
        latency.box.addWidget(self.chart)
        latency.box.addWidget(text(CaptionLabel, "Cím vagy IP-cím", "muted"))
        self.host = LineEdit()
        self.host.setText("1.1.1.1")
        self.host.setClearButtonEnabled(True)
        latency.box.addWidget(self.host)
        self.measure = PrimaryPushButton(FIF.SPEED_HIGH, "10 mérés indítása")
        self.measure.clicked.connect(self._measure)
        latency.box.addWidget(self.measure, 0, Qt.AlignmentFlag.AlignLeft)
        latency.box.addLayout(footnote(FIF.INFO, "A TCP-kapcsolódási idő nem a játékbeli ping, de jól mutatja a "
                                                 "hálózat késleltetését és ingadozását."))
        latency.box.addStretch(1)
        columns.addWidget(latency, 1)

        dns = Surface(padding=20, spacing=10)
        dns.box.addLayout(section("DNS-beállítások"))
        dns.box.addWidget(text(CaptionLabel, "Hálózati adapter", "muted"))
        self.adapter = ComboBox()
        self.adapter.currentIndexChanged.connect(lambda _: self._show_adapter())
        dns.box.addWidget(self.adapter)
        dns.box.addWidget(text(CaptionLabel, "DNS-szolgáltató", "muted"))
        self.preset = ComboBox()
        self.preset.addItems(list(network.DNS_PRESETS))
        dns.box.addWidget(self.preset)
        self.current = text(CaptionLabel, "", "muted", wrap=True)
        dns.box.addWidget(self.current)
        apply = PushButton(FIF.ACCEPT, "Beállítás alkalmazása")
        apply.clicked.connect(self._apply_dns)
        dns.box.addWidget(apply, 0, Qt.AlignmentFlag.AlignLeft)
        dns.box.addWidget(HorizontalSeparator())
        flush = HyperlinkButton("", "DNS-gyorsítótár ürítése")
        flush.setIcon(FIF.SYNC)
        flush.clicked.connect(self._flush)
        dns.box.addWidget(flush, 0, Qt.AlignmentFlag.AlignLeft)
        dns.box.addWidget(text(CaptionLabel, "Az alkalmazott változás az Előzményekben visszaállítható.", "muted"))
        dns.box.addStretch(1)
        columns.addWidget(dns, 1)
        self.body.addLayout(columns)
        self.adapters: list[network.Adapter] = []

    def on_show(self):
        self.win.task(network.adapters, self._loaded)

    def _loaded(self, adapters):
        self.adapters = adapters
        self.adapter.blockSignals(True)
        self.adapter.clear()
        self.adapter.addItems([a.name for a in adapters] or ["Nincs aktív adapter"])
        self.adapter.blockSignals(False)
        self._show_adapter()

    def _selected(self):
        i = self.adapter.currentIndex()
        return self.adapters[i] if 0 <= i < len(self.adapters) else None

    def _show_adapter(self):
        a = self._selected()
        if not a:
            self.current.setText("Nincs csatlakoztatott fizikai hálózati adapter.")
            return
        source = "kézi" if a.static_dns else "automatikus (DHCP)"
        self.current.setText(f"Jelenlegi DNS: {', '.join(a.dns) or '—'} ({source})")
        preset = next((k for k, v in network.DNS_PRESETS.items() if v == a.static_dns), None)
        if preset:
            self.preset.setCurrentText(preset)

    def _apply_dns(self):
        a = self._selected()
        if a:
            self.win.apply([network.plan_dns(a, network.DNS_PRESETS[self.preset.currentText()])],
                           "DNS-beállítás módosítása", done=lambda out: self.on_show())

    def _flush(self):
        self.win.task(network.flush_dns, lambda r: self.win.toast(
            "DNS-gyorsítótár ürítve." if r[0] else f"Sikertelen: {r[1][:120]}", "success" if r[0] else "warning"))

    def _measure(self):
        host = self.host.text().strip()
        if not host:
            return
        self.measure.setEnabled(False)
        self.measure.setText("Mérés folyamatban…")
        self.win.task(lambda: network.tcp_latency(host), self._measured)

    def _measured(self, result):
        self.measure.setEnabled(True)
        self.measure.setText("10 mérés indítása")
        self.value.setText(f"{sum(result.samples) / len(result.samples):.0f}" if result.samples else "—")
        self.summary.setText(result.summary)
        self.chart.set_values(result.samples)
