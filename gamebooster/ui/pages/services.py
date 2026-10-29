import customtkinter as ctk

from ...optimizers import services
from .. import theme
from ..widgets import Page, badge, button, card, label


class ServicesPage(Page):
    title = "Szolgáltatások"
    subtitle = ("Ismert, otthoni gépen ritkán szükséges szolgáltatások. A legtöbb „Kézi” indításra kerül, "
                "így ha egy program igényli, a Windows elindítja. Minden módosítás visszaállítható.")

    def build(self):
        self.box = card(self.body)
        self.box.pack(fill="both", expand=True)
        self.rows_frame = ctk.CTkFrame(self.box, fg_color="transparent")
        self.rows_frame.pack(fill="both", expand=True, padx=16, pady=(16, 0))
        row = ctk.CTkFrame(self.box, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=16)
        self.apply_btn = button(row, "Kijelöltek optimalizálása", self._apply, kind="primary")
        self.apply_btn.pack(side="left")
        self.vars: dict[str, ctk.BooleanVar] = {}

    def on_show(self):
        self.app.tasks.run(services.status, self._loaded)

    def _loaded(self, status):
        for w in self.rows_frame.winfo_children():
            w.destroy()
        self.vars.clear()
        for info, current, running in status:
            r = ctk.CTkFrame(self.rows_frame, fg_color=theme.SURFACE_2, corner_radius=8)
            r.pack(fill="x", pady=3)
            r.columnconfigure(3, weight=1)
            journaled = self.app.journal.find(f"service:{info.name}")
            done = current == info.target
            var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(r, text=info.label, variable=var, font=theme.font(13, "bold"), width=300,
                            text_color=theme.TEXT, fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                            state="disabled" if current is None or done else "normal"
                            ).grid(row=0, column=0, sticky="w", padx=12, pady=10)
            self.vars[info.name] = var
            badge(r, f"kockázat: {info.risk}", "info" if info.risk == "alacsony" else "warning"
                  ).grid(row=0, column=1, sticky="w")
            state = services.START_LABELS[current] + (", fut" if running else "")
            label(r, state, 12, muted=True, width=170).grid(row=0, column=2, sticky="w", padx=12)
            label(r, info.note, 12, muted=True, wraplength=210).grid(row=0, column=3, sticky="ew")
            if journaled:
                button(r, "Visszaállítás", lambda c=journaled: self.app.revert(
                    [c], done=lambda out: self.on_show()), width=110).grid(row=0, column=4, padx=12)
            elif done:
                label(r, "optimalizálva", 12, text_color=theme.ACCENT).grid(row=0, column=4, padx=12)

    def _apply(self):
        names = [n for n, v in self.vars.items() if v.get()]
        if not names:
            self.app.toasts.show("Jelölj ki legalább egy szolgáltatást.", "info")
            return
        self.app.tasks.run(lambda: services.plan(names), lambda changes: self.app.apply(
            changes, "Szolgáltatások optimalizálása", done=lambda out: self.on_show(),
            note="A futó szolgáltatások leállnak; visszaállításkor újraindulnak."))
