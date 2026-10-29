import customtkinter as ctk

from .. import theme
from ..widgets import Page, Spark, label

# (cím, mező(k), szín, skála maximuma, formázó)
_CHARTS = [
    ("CPU", ("cpu",), theme.ACCENT, 100, lambda s: f"{s.cpu:.0f}%"),
    ("Memória", ("ram_pct",), theme.INFO, 100, lambda s: f"{s.ram_pct:.0f}%"),
    ("GPU 3D motor", ("gpu",), theme.WARNING, 100,
     lambda s: "—" if s.gpu is None else f"{s.gpu:.0f}%"),
    ("GPU memória", ("gpu_mem_gb",), "#B48CF2", None,
     lambda s: "—" if s.gpu_mem_gb is None else f"{theme.fmt_num(s.gpu_mem_gb, 2)} GB"),
    ("Lemez (olvasás + írás)", ("disk_read_mbs", "disk_write_mbs"), "#F28CB4", None,
     lambda s: f"{theme.fmt_num(s.disk_read_mbs + s.disk_write_mbs)} MB/s"),
    ("Hálózat (le + fel)", ("net_down_mbs", "net_up_mbs"), "#8CE0F2", None,
     lambda s: f"{theme.fmt_num(s.net_down_mbs + s.net_up_mbs, 2)} MB/s"),
]


class MonitorPage(Page):
    title = "Monitor"
    subtitle = "Az elmúlt 2 perc, másodpercenként. A mérés egy háttérszálon fut, PowerShell nélkül."

    def build(self):
        grid = ctk.CTkFrame(self.body, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        self.charts = []
        for i, (title, fields, color, top, fmt) in enumerate(_CHARTS):
            grid.columnconfigure(i % 3, weight=1, uniform="c")
            grid.rowconfigure(i // 3, weight=1)
            box = ctk.CTkFrame(grid, fg_color=theme.SURFACE, corner_radius=12)
            box.grid(row=i // 3, column=i % 3, sticky="nsew", padx=6, pady=6)
            label(box, title, 12, muted=True, font=theme.font(12, "bold")).pack(anchor="w", padx=16, pady=(14, 0))
            value = label(box, "—", font=theme.font(22, "bold", mono=True))
            value.pack(anchor="w", padx=16)
            spark = Spark(box, color, height=110)
            spark.pack(fill="both", expand=True, padx=16, pady=(6, 14))
            self.charts.append((fields, top, fmt, value, spark))
        self.temp = label(self.body, "", 12, muted=True, wraplength=900)
        self.temp.pack(anchor="w", pady=(10, 0))

    def on_show(self):
        self.on_tick()

    def on_tick(self):
        s, h = self.app.sampler.latest, self.app.sampler.history
        for fields, top, fmt, value, spark in self.charts:
            series = [sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None
                      for vals in zip(*(h[f] for f in fields))]
            value.configure(text=fmt(s))
            spark.set(series, top)
        parts = []
        if s.gpu_temp_c is not None:
            parts.append(f"GPU: {s.gpu_temp_c:.0f} °C.")
        if s.temp_c is not None:
            parts.append(f"ACPI hőzóna: {theme.fmt_num(s.temp_c)} °C (alaplapi érzékelő, nem a CPU-mag; "
                         "sok gépen állandó érték).")
        parts.append("Pontos CPU-hőmérséklethez kernel-driver kellene; a GameBooster ilyet nem telepít.")
        self.temp.configure(text=" ".join(parts))
