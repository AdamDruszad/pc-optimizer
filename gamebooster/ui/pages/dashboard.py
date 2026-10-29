import customtkinter as ctk

from ...optimizers import game_mode, tweaks
from .. import theme
from ..widgets import Page, StatCard, autowrap, button, card, label


class DashboardPage(Page):
    title = "Áttekintés"
    subtitle = "A gép állapota, az aktív módosítások és a gyors műveletek."

    def build(self):
        stats = ctk.CTkFrame(self.body, fg_color="transparent")
        stats.pack(fill="x")
        self.cards = {}
        for i, (key, title, color) in enumerate([("cpu", "CPU", theme.ACCENT), ("ram", "MEMÓRIA", theme.INFO),
                                                 ("gpu", "GPU", theme.WARNING), ("net", "HÁLÓZAT", "#B48CF2")]):
            stats.columnconfigure(i, weight=1, uniform="stat")
            self.cards[key] = StatCard(stats, title, color)
            self.cards[key].grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 12, 0))

        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="both", expand=True, pady=(16, 0))
        for i in range(3):
            row.columnconfigure(i, weight=1, uniform="row")
        row.rowconfigure(0, weight=1)

        changes = card(row, "AKTÍV MÓDOSÍTÁSOK")
        changes.grid(row=0, column=0, sticky="nsew")
        self.changes_count = label(changes, "0", font=theme.font(32, "bold", mono=True))
        self.changes_count.pack(anchor="w", padx=16)
        self.changes_detail = autowrap(label(changes, "", 13, muted=True))
        self.changes_detail.pack(anchor="w", padx=16, pady=(0, 12))
        actions = ctk.CTkFrame(changes, fg_color="transparent")
        actions.pack(side="bottom", fill="x", padx=16, pady=16)
        button(actions, "Előzmények", lambda: self.app.show("history")).pack(side="left")
        self.revert_all = button(actions, "Mindent visszaállít", self._revert_all, kind="danger")
        self.revert_all.pack(side="right")

        session = card(row, "JÁTÉK MÓD")
        session.grid(row=0, column=1, sticky="nsew", padx=12)
        self.session_state = label(session, "", font=theme.font(20, "bold"))
        self.session_state.pack(anchor="w", padx=16)
        self.session_detail = autowrap(label(session, "", 13, muted=True))
        self.session_detail.pack(anchor="w", padx=16, pady=(4, 12))
        bottom = ctk.CTkFrame(session, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=16, pady=16)
        button(bottom, "Beállítások", lambda: self.app.show("game")).pack(side="left")
        self.session_btn = button(bottom, "Indítás", self._toggle_session, kind="primary")
        self.session_btn.pack(side="right")

        system = card(row, "RENDSZER")
        system.grid(row=0, column=2, sticky="nsew")
        self.system_text = autowrap(label(system, "Hardver felismerése…", 13))
        self.system_text.pack(anchor="w", padx=16, pady=(0, 16))

    def on_show(self):
        hw = self.app.hardware
        if hw:
            gpus = "\n".join(f"{g.name}" + (f" ({theme.fmt_num(g.vram_gb)} GB)" if g.vram_gb else "")
                             for g in hw.gpus) or "Nem azonosítható"
            hvci = tweaks.security_status()["memory_integrity"]
            lines = [hw.cpu, f"{hw.cores} mag, {hw.threads} szál", gpus,
                     f"{theme.fmt_num(hw.ram_gb, 0)} GB RAM", hw.windows]
            if hw.battery:
                lines.append(f"Akkumulátor: {hw.battery}")
            if hvci is not None:
                lines.append(f"Memóriaintegritás: {'bekapcsolva' if hvci else 'kikapcsolva'}")
            self.system_text.configure(text="\n".join(lines))
        self.on_tick()

    def on_tick(self):
        s, h = self.app.sampler.latest, self.app.sampler.history
        self.cards["cpu"].show(f"{s.cpu:.0f}%", f"{theme.fmt_num(s.cpu_mhz / 1000, 2)} GHz",
                               h["cpu"], 100)
        self.cards["ram"].show(f"{s.ram_pct:.0f}%",
                               f"{theme.fmt_num(s.ram_used_gb)} / {theme.fmt_num(s.ram_total_gb, 0)} GB",
                               h["ram_pct"], 100)
        if s.gpu is None:
            self.cards["gpu"].show("—", "Nem mérhető", ())
        else:
            mem = f"{theme.fmt_num(s.gpu_mem_gb)} GB VRAM" if s.gpu_mem_gb else "3D motor"
            self.cards["gpu"].show(f"{s.gpu:.0f}%", mem, h["gpu"], 100)
        self.cards["net"].show(f"{theme.fmt_num(s.net_down_mbs)} MB/s",
                               f"Feltöltés: {theme.fmt_num(s.net_up_mbs)} MB/s", h["net_down_mbs"])

        entries = self.app.journal.entries()
        self.changes_count.configure(text=str(len(entries)))
        by_source: dict[str, int] = {}
        for c in entries:
            by_source[c.source] = by_source.get(c.source, 0) + 1
        self.changes_detail.configure(
            text=", ".join(f"{theme.SOURCE_LABELS.get(k, k)}: {v}" for k, v in by_source.items())
            or "Nincs aktív módosítás. Minden a Windows eredeti beállításán van.")
        self.revert_all.configure(state="normal" if entries else "disabled")

        w = self.app.watcher
        if w.active:
            self.session_state.configure(text="Aktív", text_color=theme.ACCENT)
            name = w._game_name(w.game)
            self.session_detail.configure(
                text=f"{name or 'Kézi munkamenet'}; {len(self.app.journal.entries(game_mode.SOURCE))} "
                     "módosítás, kilépéskor visszaáll.")
            self.session_btn.configure(text="Leállítás")
        else:
            auto = self.app.settings["auto_game_mode"]
            self.session_state.configure(text="Inaktív", text_color=theme.TEXT)
            self.session_detail.configure(
                text="Automatikusan indul a beállított játékokkal." if auto
                else "Kézzel indítható, vagy kapcsold be az automatikus indítást.")
            self.session_btn.configure(text="Indítás")

    def _toggle_session(self):
        if self.app.watcher.active:
            self.app.end_game_session()
        else:
            self.app.start_game_session()

    def _revert_all(self):
        self.app.revert(self.app.journal.entries(), "Mindent visszaállít")
