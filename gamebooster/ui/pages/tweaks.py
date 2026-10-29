import customtkinter as ctk

from ...optimizers import tweaks
from .. import theme
from ..widgets import Page, badge, card, label


class TweaksPage(Page):
    title = "Tweakek"
    subtitle = ("Csak dokumentált, ellenőrizhető hatású beállítások. A régi verzió FPS-ígéretes registry-"
                "tweakjeit (MMCSS, Nagle, egérpuffer) kivettük: a Windows figyelmen kívül hagyja vagy "
                "felülírja őket.")

    def build(self):
        self.rows = card(self.body)
        self.rows.pack(fill="x")
        self.switches: dict[str, tuple[ctk.BooleanVar, ctk.CTkSwitch]] = {}
        for t in tweaks.TWEAKS:
            r = ctk.CTkFrame(self.rows, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=(12, 0))
            head = ctk.CTkFrame(r, fg_color="transparent")
            head.pack(fill="x")
            var = ctk.BooleanVar()
            sw = ctk.CTkSwitch(head, text=t.label, variable=var, font=theme.font(14, "bold"),
                               text_color=theme.TEXT, progress_color=theme.ACCENT,
                               command=lambda tw=t, v=var: self._toggle(tw, v.get()))
            sw.pack(side="left")
            badge(head, f"hatás: {t.impact}", "success" if t.impact == "mérhető" else "info").pack(
                side="left", padx=(12, 0))
            if t.restart:
                badge(head, "újraindítás kell", "warning").pack(side="left", padx=(6, 0))
            label(r, t.description, 12, muted=True, wraplength=860).pack(anchor="w", padx=(50, 0), pady=(2, 0))
            self.switches[t.key] = (var, sw)
        ctk.CTkFrame(self.rows, fg_color="transparent", height=12).pack()

        info = card(self.body, "BIZTONSÁG ÉS TELJESÍTMÉNY")
        info.pack(fill="x", pady=12)
        self.hvci = label(info, "", 13, wraplength=900)
        self.hvci.pack(anchor="w", padx=16, pady=(0, 16))

    def on_show(self):
        self.app.tasks.run(lambda: ({t.key: tweaks.is_on(t) for t in tweaks.TWEAKS},
                                    tweaks.security_status()), self._loaded)

    def _loaded(self, result):
        states, security = result
        for key, (var, _) in self.switches.items():
            var.set(states[key])
        hvci = security["memory_integrity"]
        text = {None: "Memóriaintegritás: nincs beállítva (a Windows alapértéke érvényes).",
                True: "Memóriaintegritás: bekapcsolva.",
                False: "Memóriaintegritás: kikapcsolva."}[hvci]
        self.hvci.configure(text=text + " Egyes játékokban mérhetően lassít, de a kernel védelmét adja, "
                                        "ezért a GameBooster nem kapcsolja. Helye: Windows Biztonság → "
                                        "Eszközbiztonság → Magelkülönítés.")

    def _toggle(self, tweak, on: bool):
        if on:
            self.app.apply(tweaks.plan(tweak), tweak.label, done=lambda out: self.on_show(),
                           note="Újraindítás után lép életbe." if tweak.restart else "")
            self.on_show()  # megerősítés megszakításakor a kapcsoló visszaáll
            return
        journaled = [c for c in self.app.journal.entries() if c.target in tweaks.targets(tweak)]
        if journaled:
            self.app.revert(journaled, f"{tweak.label}: visszaállítás", done=lambda out: self.on_show())
        else:
            self.app.toasts.show("Ez a beállítás már a GameBooster előtt is így volt; a Windows "
                                 "Beállításokban módosíthatod.", "info")
        self.on_show()
