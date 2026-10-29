import os

import customtkinter as ctk

from ...core import restore_point, storage
from .. import theme
from ..widgets import Page, button, card, table


class HistoryPage(Page):
    title = "Előzmények"
    subtitle = ("Minden módosítás, amit a GameBooster végzett, az eredeti értékkel együtt. Innen tételesen "
                "vagy egyszerre is visszaállítható; a sikertelen tétel a listában marad.")

    def build(self):
        box = card(self.body)
        box.pack(fill="both", expand=True)
        self.tree = table(box, [("at", "Időpont", 160), ("source", "Forrás", 150), ("label", "Változás", 600)],
                          height=16)
        self.tree.frame.pack(fill="both", expand=True, padx=16, pady=(16, 0))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=16)
        button(row, "Kijelölt visszaállítása", self._revert_selected).pack(side="left")
        self.all_btn = button(row, "Mindent visszaállít", self._revert_all, kind="danger")
        self.all_btn.pack(side="left", padx=8)
        button(row, "Adatmappa megnyitása", lambda: os.startfile(storage.data_dir())).pack(side="right")
        button(row, "Visszaállítási pont most", self._restore_point).pack(side="right", padx=8)
        self.entries = []

    def on_show(self):
        self.entries = self.app.journal.entries()
        self.tree.delete(*self.tree.get_children())
        for i, c in enumerate(reversed(self.entries)):
            self.tree.insert("", "end", iid=str(len(self.entries) - 1 - i),
                             values=(c.at.replace("T", " "), theme.SOURCE_LABELS.get(c.source, c.source), c.label))
        self.all_btn.configure(state="normal" if self.entries else "disabled")

    def _revert_selected(self):
        sel = self.tree.selection()
        if sel:
            self.app.revert([self.entries[int(sel[0])]], done=lambda out: self.on_show())

    def _revert_all(self):
        self.app.revert(self.entries, "Mindent visszaállít", done=lambda out: self.on_show())

    def _restore_point(self):
        if not self.app.admin:
            self.app.toasts.show("Ehhez rendszergazdai jog kell.", "warning")
            return
        self.app.toasts.show("Visszaállítási pont készül…", "info")
        self.app.tasks.run(restore_point.create, lambda r: self.app.toasts.show(
            r[1], "success" if r[0] else "info", 7000))
