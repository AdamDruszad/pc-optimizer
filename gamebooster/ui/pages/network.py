import customtkinter as ctk

from ...optimizers import network
from .. import theme
from ..widgets import Page, button, card, label


class NetworkPage(Page):
    title = "Hálózat"
    subtitle = ("DNS-szerver választása visszaállítható módon, és a késleltetés mérése. A régi "
                "„Nagle-tweaket” kivettük: a mai Windows és a játékok többsége nem használja.")

    def build(self):
        dns = card(self.body, "DNS")
        dns.pack(fill="x")
        row = ctk.CTkFrame(dns, fg_color="transparent")
        row.pack(fill="x", padx=16)
        label(row, "Adapter:", 13).pack(side="left")
        self.adapter_menu = ctk.CTkOptionMenu(row, values=["Betöltés…"], width=200, font=theme.font(13),
                                              fg_color=theme.SURFACE_2, button_color=theme.BORDER,
                                              command=lambda _: self._show_adapter())
        self.adapter_menu.pack(side="left", padx=(8, 16))
        label(row, "DNS:", 13).pack(side="left")
        self.preset = ctk.CTkOptionMenu(row, values=list(network.DNS_PRESETS), width=220,
                                        font=theme.font(13), fg_color=theme.SURFACE_2,
                                        button_color=theme.BORDER)
        self.preset.pack(side="left", padx=8)
        button(row, "Alkalmazás", self._apply_dns, kind="primary").pack(side="left", padx=8)
        button(row, "DNS-gyorsítótár ürítése", self._flush).pack(side="left")
        self.current = label(dns, "", 12, muted=True)
        self.current.pack(anchor="w", padx=16, pady=(8, 16))

        lat = card(self.body, "KÉSLELTETÉS")
        lat.pack(fill="x", pady=12)
        row = ctk.CTkFrame(lat, fg_color="transparent")
        row.pack(fill="x", padx=16)
        self.host = ctk.CTkEntry(row, width=260, font=theme.font(13), fg_color=theme.BG,
                                 border_color=theme.BORDER)
        self.host.insert(0, "1.1.1.1")
        self.host.pack(side="left")
        self.measure_btn = button(row, "Mérés (10 próba)", self._measure, kind="primary")
        self.measure_btn.pack(side="left", padx=8)
        self.result = label(lat, "TCP-kapcsolódási idő a 443-as portra; a jitter az egymást követő "
                                 "mérések átlagos eltérése.", 13, muted=True, wraplength=900)
        self.result.pack(anchor="w", padx=16, pady=(8, 16))
        self.adapters: list[network.Adapter] = []

    def on_show(self):
        self.app.tasks.run(network.adapters, self._loaded)

    def _loaded(self, adapters):
        self.adapters = adapters
        names = [a.name for a in adapters] or ["Nincs aktív adapter"]
        self.adapter_menu.configure(values=names)
        if self.adapter_menu.get() not in names:
            self.adapter_menu.set(names[0])
        self._show_adapter()

    def _adapter(self):
        return next((a for a in self.adapters if a.name == self.adapter_menu.get()), None)

    def _show_adapter(self):
        a = self._adapter()
        if not a:
            self.current.configure(text="Nincs csatlakoztatott fizikai hálózati adapter.")
            return
        source = "kézi" if a.static_dns else "automatikus (DHCP)"
        self.current.configure(text=f"Jelenlegi DNS: {', '.join(a.dns) or '—'} ({source})")
        preset = next((k for k, v in network.DNS_PRESETS.items() if v == a.static_dns), None)
        if preset:
            self.preset.set(preset)

    def _apply_dns(self):
        a = self._adapter()
        if a:
            self.app.apply([network.plan_dns(a, network.DNS_PRESETS[self.preset.get()])], "DNS módosítása",
                           done=lambda out: self.on_show())

    def _flush(self):
        self.app.tasks.run(network.flush_dns, lambda r: self.app.toasts.show(
            "DNS-gyorsítótár ürítve." if r[0] else f"Sikertelen: {r[1][:120]}",
            "success" if r[0] else "warning"))

    def _measure(self):
        host = self.host.get().strip()
        if not host:
            return
        self.measure_btn.configure(state="disabled", text="Mérés…")

        def done(result):
            self.measure_btn.configure(state="normal", text="Mérés (10 próba)")
            self.result.configure(text=result.summary, text_color=theme.TEXT)
        self.app.tasks.run(lambda: network.tcp_latency(host), done)
