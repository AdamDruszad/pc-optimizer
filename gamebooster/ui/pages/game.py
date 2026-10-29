import os
from tkinter import filedialog

import customtkinter as ctk

from ...optimizers import power, tweaks
from .. import theme
from ..widgets import Page, autowrap, button, card, label, table


class GamePage(Page):
    title = "Játék mód"
    subtitle = ("A játék indulásakor teljesítmény energiasémára vált és magas prioritást ad a játéknak; "
                "a játék bezárásakor minden automatikusan visszaáll.")

    def build(self):
        self.body.columnconfigure(0, weight=3)
        self.body.columnconfigure(1, weight=2)
        self.body.rowconfigure(0, weight=1)

        games = card(self.body, "JÁTÉKOK")
        games.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.games = table(games, [("exe", "Játék", 180), ("gpu", "GPU", 150), ("path", "Útvonal", 300)])
        self.games.frame.pack(fill="both", expand=True, padx=16)
        row = ctk.CTkFrame(games, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=16)
        button(row, "Játék hozzáadása…", self._add_game, kind="primary").pack(side="left")
        button(row, "Eltávolítás", self._remove_game).pack(side="left", padx=8)
        self.gpu_btn = button(row, "Nagy teljesítményű GPU", self._toggle_gpu)
        self.gpu_btn.pack(side="right")

        right = ctk.CTkFrame(self.body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")

        opts = card(right, "BEÁLLÍTÁSOK")
        opts.pack(fill="x")
        self.switches = {}
        for key, text in [("auto_game_mode", "Automatikus indítás a játékkal"),
                          ("game_power_plan", "Teljesítmény energiaséma"),
                          ("game_priority", "Magas prioritás a játéknak")]:
            var = ctk.BooleanVar(value=self.app.settings[key])
            ctk.CTkSwitch(opts, text=text, variable=var, font=theme.font(13), text_color=theme.TEXT,
                          progress_color=theme.ACCENT,
                          command=lambda k=key, v=var: self._set(k, v.get())).pack(anchor="w", padx=16, pady=4)
            self.switches[key] = var
        autowrap(label(opts, "Háttérappok, amelyek prioritása csökken (pl. OneDrive.exe):", 12,
                       muted=True)).pack(anchor="w", padx=16, pady=(12, 4))
        add = ctk.CTkFrame(opts, fg_color="transparent")
        add.pack(fill="x", padx=16)
        self.bg_entry = ctk.CTkEntry(add, placeholder_text="program.exe", font=theme.font(13),
                                     fg_color=theme.BG, border_color=theme.BORDER)
        self.bg_entry.pack(side="left", fill="x", expand=True)
        self.bg_entry.bind("<Return>", lambda e: self._add_background())
        button(add, "Hozzáadás", self._add_background).pack(side="left", padx=(8, 0))
        self.bg_list = autowrap(label(opts, "", 12, muted=True))
        self.bg_list.pack(anchor="w", padx=16, pady=(6, 4))
        button(opts, "Lista törlése", self._clear_background).pack(anchor="w", padx=16, pady=(0, 12))
        button(opts, "Ultimate Performance séma hozzáadása", self._add_ultimate).pack(
            anchor="w", padx=16, pady=(0, 16))

        session = card(right, "MUNKAMENET")
        session.pack(fill="both", expand=True, pady=(12, 0))
        self.state = label(session, "", font=theme.font(20, "bold"))
        self.state.pack(anchor="w", padx=16)
        self.detail = autowrap(label(session, "", 13, muted=True))
        self.detail.pack(anchor="w", padx=16, pady=(4, 0))
        self.session_btn = button(session, "Indítás most", self._toggle_session, kind="primary")
        self.session_btn.pack(anchor="w", padx=16, pady=16)
        self.games.bind("<<TreeviewSelect>>", lambda e: self._update_gpu_btn())

    def on_show(self):
        self.games.delete(*self.games.get_children())
        for i, g in enumerate(self.app.settings["games"]):
            gpu = "Nagy teljesítményű" if g.get("path") and self._gpu_high(g["path"]) else "Windows dönt"
            self.games.insert("", "end", iid=str(i), values=(g["exe"], gpu, g.get("path", "")))
        if not self.app.settings["games"]:
            self.games.insert("", "end", iid="empty", values=(
                "Még nincs felvett játék", "", "Add hozzá a játék .exe fájlját a lenti gombbal."))
        apps = self.app.settings["background_apps"]
        self.bg_list.configure(text=", ".join(apps) if apps else "Nincs megadva.")
        self._update_gpu_btn()
        self.on_tick()

    def on_tick(self):
        w = self.app.watcher
        if w.active:
            self.state.configure(text="Aktív", text_color=theme.ACCENT)
            self.detail.configure(text=f"{w._game_name(w.game) or 'Kézi munkamenet'}: "
                                       f"{len(self.app.journal.entries('game_mode'))} módosítás.")
            self.session_btn.configure(text="Leállítás és visszaállítás", fg_color=theme.DANGER,
                                       hover_color=theme.DANGER_HOVER)
        else:
            self.state.configure(text="Inaktív", text_color=theme.TEXT)
            self.detail.configure(text="Ha fut egy felvett játék, annak ad magas prioritást; "
                                       "különben csak az energiasémát és a háttérappokat állítja.")
            self.session_btn.configure(text="Indítás most", fg_color=theme.ACCENT,
                                       hover_color=theme.ACCENT_HOVER)

    def _set(self, key, value):
        self.app.settings[key] = value
        self.app.save_settings()

    def _toggle_session(self):
        self.app.end_game_session() if self.app.watcher.active else self.app.start_game_session()

    def _selected(self):
        sel = self.games.selection()
        return self.app.settings["games"][int(sel[0])] if sel and sel[0] != "empty" else None

    def _add_game(self):
        path = filedialog.askopenfilename(parent=self, title="Játék kiválasztása",
                                          filetypes=[("Program", "*.exe")])
        if not path:
            return
        path = os.path.normpath(path)
        games = self.app.settings["games"]
        if any(g.get("path", "").lower() == path.lower() for g in games):
            return
        games.append({"exe": os.path.basename(path), "path": path})
        self.app.save_settings()
        self.on_show()

    def _remove_game(self):
        game = self._selected()
        if game:
            self.app.settings["games"].remove(game)
            self.app.save_settings()
            self.on_show()

    @staticmethod
    def _gpu_high(path: str) -> bool:
        current, _ = tweaks.winapi.reg_read("HKCU", tweaks._DX_PREFS, path)
        return "GpuPreference=2;" in (current or "")

    def _update_gpu_btn(self):
        game = self._selected()
        high = bool(game and game.get("path") and self._gpu_high(game["path"]))
        self.gpu_btn.configure(state="normal" if game and game.get("path") else "disabled",
                               text="Windows döntsön a GPU-ról" if high else "Nagy teljesítményű GPU")

    def _toggle_gpu(self):
        game = self._selected()
        if not game or not game.get("path"):
            return
        high = not self._gpu_high(game["path"])
        self.app.apply([tweaks.gpu_preference_change(game["path"], high)], "GPU-választás",
                       note="Hibrid (integrált + dedikált GPU-s) gépen számít; a Windows Grafika "
                            "beállításával azonos.", done=lambda out: self.on_show())

    def _add_background(self):
        name = self.bg_entry.get().strip()
        if not name.lower().endswith(".exe"):
            self.app.toasts.show("Programnevet adj meg .exe végződéssel, pl. OneDrive.exe.", "warning")
            return
        apps = self.app.settings["background_apps"]
        if name.lower() not in (a.lower() for a in apps):
            apps.append(name)
            self.app.save_settings()
        self.bg_entry.delete(0, "end")
        self.on_show()

    def _clear_background(self):
        self.app.settings["background_apps"] = []
        self.app.save_settings()
        self.on_show()

    def _add_ultimate(self):
        def work():
            guid = power.add_ultimate(self.app.settings)
            self.app.save_settings()
            return guid
        self.app.tasks.run(work, lambda g: self.app.toasts.show(
            "Ultimate Performance séma hozzáadva; a Játék mód ezt használja.", "success"))
