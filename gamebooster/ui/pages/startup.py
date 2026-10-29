import customtkinter as ctk

from ...optimizers import startup
from ..widgets import Page, button, card, label, table


class StartupPage(Page):
    title = "Indítópult"
    subtitle = ("A Windows indulásakor automatikusan induló programok. A kikapcsolás ugyanaz, mint a "
                "Feladatkezelőben: a bejegyzés megmarad, bármikor visszakapcsolható.")

    def build(self):
        box = card(self.body)
        box.pack(fill="both", expand=True)
        self.tree = table(box, [("name", "Program", 240), ("state", "Állapot", 110),
                                ("where", "Hely", 260), ("cmd", "Parancs", 400)], height=16)
        self.tree.frame.pack(fill="both", expand=True, padx=16, pady=(16, 0))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=16)
        self.toggle_btn = button(row, "Kikapcsolás", self._toggle, kind="primary", state="disabled")
        self.toggle_btn.pack(side="left")
        button(row, "Frissítés", self.on_show).pack(side="left", padx=8)
        self.summary = label(row, "", 13, muted=True)
        self.summary.pack(side="right")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._selection_changed())
        self.items: list[startup.StartupItem] = []

    def on_show(self):
        self.app.tasks.run(startup.items, self._loaded)

    def _loaded(self, items):
        self.items = items
        self.tree.delete(*self.tree.get_children())
        for i, item in enumerate(items):
            self.tree.insert("", "end", iid=str(i), values=(
                item.name, "Bekapcsolva" if item.enabled else "Kikapcsolva", item.location, item.command))
        on = sum(i.enabled for i in items)
        self.summary.configure(text=f"{on} bekapcsolva, {len(items) - on} kikapcsolva")
        self._selection_changed()

    def _current(self):
        sel = self.tree.selection()
        return self.items[int(sel[0])] if sel else None

    def _selection_changed(self):
        item = self._current()
        self.toggle_btn.configure(state="normal" if item else "disabled",
                                  text="Bekapcsolás" if item and not item.enabled else "Kikapcsolás")

    def _toggle(self):
        item = self._current()
        if item:
            self.app.apply([startup.plan_toggle(item, not item.enabled)], "Indítópult módosítása",
                           done=lambda out: self.on_show())
