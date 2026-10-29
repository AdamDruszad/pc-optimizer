import threading

import customtkinter as ctk

from ...optimizers import cleaner
from .. import theme
from ..widgets import Page, button, card, confirm, label


class CleanerPage(Page):
    title = "Tisztítás"
    subtitle = ("Ideiglenes fájlok és cache-ek törlése előnézettel. Felhasználói dokumentumokhoz és a "
                "Lomtárhoz nem nyúl; a zárolt fájlokat kihagyja.")

    def build(self):
        top = card(self.body)
        top.pack(fill="x")
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=16)
        self.scan_btn = button(row, "Szkennelés", self._scan, kind="primary")
        self.scan_btn.pack(side="left")
        self.clean_btn = button(row, "Kijelöltek törlése", self._clean, kind="danger", state="disabled")
        self.clean_btn.pack(side="left", padx=8)
        self.total = label(row, "Indítsd a szkennelést, utána jelöld ki, mit törölj.", 13, muted=True)
        self.total.pack(side="left", padx=12)
        self.progress = ctk.CTkProgressBar(top, progress_color=theme.ACCENT, fg_color=theme.SURFACE_2)
        self.progress.set(0)

        self.list = card(self.body, "KATEGÓRIÁK")
        self.list.pack(fill="both", expand=True, pady=12)
        self.rows = {}
        for target in cleaner.TARGETS:
            r = ctk.CTkFrame(self.list, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=3)
            var = ctk.BooleanVar(value=False)
            box = ctk.CTkCheckBox(r, text=target.label, variable=var, font=theme.font(13), state="disabled",
                                  text_color=theme.TEXT, fg_color=theme.ACCENT,
                                  hover_color=theme.ACCENT_HOVER, command=self._update_total, width=320)
            box.pack(side="left")
            size = label(r, "—", font=theme.font(13, mono=True), width=150)
            size.pack(side="left")
            label(r, target.note, 12, muted=True).pack(side="left", padx=12)
            self.rows[target.key] = (var, size, box)
        self.scans: dict[str, cleaner.Scan] = {}

        system = card(self.body, "WINDOWS UPDATE MARADVÁNYOK")
        system.pack(fill="x")
        row = ctk.CTkFrame(system, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 16))
        button(row, "Kézbesítésoptimalizálás cache", lambda: self._system(
            "Kézbesítésoptimalizálás cache törlése", cleaner.delivery_optimization_cleanup,
            "A frissítésekhez letöltött, más gépeknek megosztott fájlok törlése.")).pack(side="left")
        button(row, "Komponenstár takarítása (DISM)", lambda: self._system(
            "Komponenstár takarítása", cleaner.component_cleanup,
            "A felülírt Windows-komponensek törlése. Akár 10-20 percig is tarthat; "
            "utána a régi frissítések nem távolíthatók el.")).pack(side="left", padx=8)

    def _scan(self):
        self.scan_btn.configure(state="disabled", text="Szkennelés…")
        self.clean_btn.configure(state="disabled")
        self.progress.pack(fill="x", padx=16, pady=(0, 16))
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.app.tasks.run(lambda: cleaner.scan(cleaner.TARGETS), self._scanned)

    def _scanned(self, results):
        self.progress.stop()
        self.progress.pack_forget()
        self.scan_btn.configure(state="normal", text="Újraszkennelés")
        self.scans = {s.target.key: s for s in results}
        for key, (var, size, box) in self.rows.items():
            s = self.scans[key]
            size.configure(text=f"{theme.fmt_size(s.size)} ({len(s.files)} fájl)" if s.files else "üres")
            box.configure(state="normal" if s.files else "disabled")
            var.set(bool(s.files) and "shader" not in key)
        self._update_total()

    def _selected(self):
        return [self.scans[k] for k, (var, _, _) in self.rows.items() if var.get() and k in self.scans]

    def _update_total(self):
        chosen = self._selected()
        total = sum(s.size for s in chosen)
        self.total.configure(text=f"Kijelölve: {theme.fmt_size(total)}" if self.scans else self.total.cget("text"))
        self.clean_btn.configure(state="normal" if chosen else "disabled")

    def _clean(self):
        chosen = self._selected()
        lines = [f"{s.target.label}: {theme.fmt_size(s.size)} ({len(s.files)} fájl)" for s in chosen]
        if not confirm(self.app, "Törlés", lines, ok_text="Törlés", danger=True,
                       note="A törölt fájlok nem kerülnek a Lomtárba, és nem állíthatók vissza."):
            return
        self.clean_btn.configure(state="disabled")
        self.scan_btn.configure(state="disabled")
        self.progress.configure(mode="determinate")
        self.progress.set(0)
        self.progress.pack(fill="x", padx=16, pady=(0, 16))
        progress = lambda f: self.app.tasks.post(self.progress.set, f)
        self.app.tasks.run(lambda: cleaner.clean(chosen, threading.Event(), progress), self._cleaned)

    def _cleaned(self, result):
        self.progress.pack_forget()
        skipped = f", {result.skipped} zárolt fájl kihagyva" if result.skipped else ""
        self.app.toasts.show(f"{theme.fmt_size(result.freed)} felszabadítva ({result.deleted} fájl{skipped}).",
                             "success")
        self.scans = {}
        self._scan()

    def _system(self, title, action, note):
        if not self.app.admin:
            self.app.toasts.show("Ehhez rendszergazdai jog kell.", "warning")
            return
        if not confirm(self.app, title, [title], note=note, ok_text="Indítás"):
            return
        self.app.toasts.show(f"{title} folyamatban…", "info")
        self.app.tasks.run(action, lambda r: self.app.toasts.show(
            f"{title}: kész." if r[0] else f"{title}: sikertelen ({r[1][:160]})",
            "success" if r[0] else "warning", 8000))
