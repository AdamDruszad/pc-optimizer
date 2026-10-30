from PySide6.QtWidgets import QGridLayout, QHBoxLayout
from qfluentwidgets import CaptionLabel, ExpandGroupSettingCard
from qfluentwidgets import FluentIcon as FIF

from .. import theme
from ..components import MetricCard, Page, text

# (cím, mező(k), ikon, skála maximuma, skála felirat, formázó)
CHARTS = [
    ("CPU", ("cpu",), FIF.SPEED_HIGH, 100, "0–100 %", lambda s: f"{s.cpu:.0f} %"),
    ("Memória", ("ram_pct",), FIF.LIBRARY, 100, "0–100 %", lambda s: f"{s.ram_pct:.0f} %"),
    ("GPU 3D motor", ("gpu",), FIF.GAME, 100, "0–100 %",
     lambda s: "—" if s.gpu is None else f"{s.gpu:.0f} %"),
    ("GPU memória", ("gpu_mem_gb",), FIF.ALBUM, None, "automatikus",
     lambda s: "—" if s.gpu_mem_gb is None else f"{theme.fmt_num(s.gpu_mem_gb, 2)} GB"),
    ("Lemez (olvasás + írás)", ("disk_read_mbs", "disk_write_mbs"), FIF.FOLDER, None, "automatikus",
     lambda s: f"{theme.fmt_num(s.disk_read_mbs + s.disk_write_mbs)} MB/s"),
    ("Hálózat (le + fel)", ("net_down_mbs", "net_up_mbs"), FIF.WIFI, None, "automatikus",
     lambda s: f"{theme.fmt_num(s.net_down_mbs + s.net_up_mbs, 2)} MB/s"),
]


class MonitorPage(Page):
    def __init__(self, win):
        super().__init__(win, "monitorInterface", "Teljesítményfigyelő", "A terhelés alakulása, olvasható léptékben.")

    def build(self):
        self.body.addWidget(text(CaptionLabel, "Élő mérés másodpercenként · 2 perces időablak · PowerShell nélkül",
                                 "muted"))
        grid = QGridLayout()
        grid.setSpacing(16)
        self.cards = []
        for i, (name, fields, icon, top, scale, fmt) in enumerate(CHARTS):
            card = MetricCard(name, icon, chart_height=120)
            axis = QHBoxLayout()
            for label in ("−2 perc", scale, "Most"):
                axis.addWidget(text(CaptionLabel, label, "subtle"))
                axis.addStretch(1)
            axis.takeAt(axis.count() - 1)  # az utolsó felirat a jobb szélre kerül
            card.box.addLayout(axis)
            grid.addWidget(card, i // 3, i % 3)
            grid.setColumnStretch(i % 3, 1)
            self.cards.append((card, fields, top, fmt))
        self.body.addLayout(grid)
        self.temperature = ExpandGroupSettingCard(FIF.INFO, "Hőmérsékleti adatok",
                                                  "CPU-maghőmérséklet kernel-driver nélkül nem mérhető")
        self.temp_text = text(CaptionLabel, "", "muted", wrap=True)
        self.temp_text.setContentsMargins(48, 12, 48, 12)
        self.temperature.addGroupWidget(self.temp_text)
        self.body.addWidget(self.temperature)

    def on_show(self):
        self.on_tick()

    def on_tick(self):
        s, h = self.win.sampler.latest, self.win.sampler.history
        for card, fields, top, fmt in self.cards:
            series = [sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None
                      for vals in zip(*(h[f] for f in fields))]
            card.show_value(fmt(s), card.meta.text(), series, top)
        parts = []
        if s.gpu_temp_c is not None:
            parts.append(f"GPU: {s.gpu_temp_c:.0f} °C.")
        if s.temp_c is not None:
            parts.append(f"ACPI hőzóna: {theme.fmt_num(s.temp_c)} °C (alaplapi érzékelő, nem a CPU-mag; sok gépen "
                         "állandó érték).")
        parts.append("Pontos CPU-hőmérséklethez kernel-driver kellene; a GameBooster ilyet nem telepít.")
        self.temp_text.setText(" ".join(parts))
