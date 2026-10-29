"""Közös UI-elemek: feladatkezelő, toast, megerősítő ablak, kártyák, diagram, táblázat."""
import logging
import queue
import tkinter as tk
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk

import customtkinter as ctk

from . import theme

log = logging.getLogger(__name__)


class TaskRunner:
    """Háttérmunka szálkészleten; az eredmény a Tk-szálon, sorból érkezik. Widgethez csak a Tk-szál nyúl."""

    def __init__(self, root: tk.Misc, on_error: Callable[[Exception], None]):
        self.root = root
        self.on_error = on_error
        self._queue: queue.Queue = queue.Queue()
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="task")
        root.after(50, self._pump)

    def post(self, fn: Callable, *args) -> None:
        """Bármely szálról hívható: `fn(*args)` a Tk-szálon fut le."""
        self._queue.put((fn, args))

    def run(self, work: Callable, done: Callable | None = None) -> None:
        def task():
            try:
                result = work()
            except Exception as e:
                log.exception("Háttérfeladat hiba")
                self.post(self.on_error, e)
                return
            if done:
                self.post(done, result)
        self._pool.submit(task)

    def _pump(self) -> None:
        try:
            while True:
                fn, args = self._queue.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    log.exception("UI-callback hiba")
        except queue.Empty:
            pass
        self.root.after(50, self._pump)


class Toasts:
    """Jobb alsó sarokban, 4,5 mp után eltűnő üzenetek; a fókuszt nem veszik el."""

    def __init__(self, root: tk.Misc):
        self.root = root
        self._items: list[ctk.CTkFrame] = []

    def show(self, text: str, kind: str = "info", ms: int = 4500) -> None:
        color = theme.KIND_COLORS[kind]
        frame = ctk.CTkFrame(self.root, fg_color=theme.SURFACE_2, corner_radius=10,
                             border_width=1, border_color=color)
        ctk.CTkLabel(frame, text=theme.ICONS[kind], font=theme.icon_font(16), text_color=color
                     ).pack(side="left", padx=(14, 8), pady=12)
        ctk.CTkLabel(frame, text=text, font=theme.font(13), text_color=theme.TEXT,
                     wraplength=340, justify="left").pack(side="left", padx=(0, 16), pady=12)
        self._items.append(frame)
        self._layout()
        self.root.after(ms, lambda: self._close(frame))

    def _close(self, frame) -> None:
        if frame in self._items:
            self._items.remove(frame)
            frame.destroy()
            self._layout()

    def _layout(self) -> None:
        y = -16
        for frame in reversed(self._items):
            frame.update_idletasks()
            frame.place(relx=1.0, rely=1.0, anchor="se", x=-16, y=y)
            frame.lift()
            y -= frame.winfo_reqheight() + 8


def confirm(root: tk.Misc, title: str, lines: list[str], note: str = "",
            ok_text: str = "Alkalmazás", danger: bool = False) -> bool:
    """Modális megerősítés a változások listájával. Esc: mégse, Enter: rendben."""
    win = ctk.CTkToplevel(root, fg_color=theme.SURFACE)
    win.title(title)
    win.transient(root)
    win.resizable(False, False)
    result = [False]

    ctk.CTkLabel(win, text=title, font=theme.font(18, "bold"), text_color=theme.TEXT
                 ).pack(anchor="w", padx=24, pady=(20, 4))
    ctk.CTkLabel(win, text="Ez fog történni:", font=theme.font(13), text_color=theme.MUTED
                 ).pack(anchor="w", padx=24)
    box = ctk.CTkTextbox(win, width=520, height=min(260, 28 + 22 * len(lines)), font=theme.font(13),
                         fg_color=theme.BG, text_color=theme.TEXT, wrap="word")
    box.insert("1.0", "\n".join(f"•  {line}" for line in lines))
    box.configure(state="disabled")
    box.pack(fill="x", padx=24, pady=(8, 8))
    if note:
        ctk.CTkLabel(win, text=note, font=theme.font(12), text_color=theme.MUTED, wraplength=520,
                     justify="left").pack(anchor="w", padx=24)

    def close(ok: bool):
        result[0] = ok
        win.grab_release()
        win.destroy()

    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(fill="x", padx=24, pady=(16, 20))
    ok_btn = button(row, ok_text, lambda: close(True), kind="danger" if danger else "primary")
    ok_btn.pack(side="right")
    button(row, "Mégse", lambda: close(False), kind="secondary").pack(side="right", padx=(0, 8))
    win.bind("<Escape>", lambda e: close(False))
    win.bind("<Return>", lambda e: close(True))
    win.protocol("WM_DELETE_WINDOW", lambda: close(False))

    win.update_idletasks()
    x = root.winfo_rootx() + (root.winfo_width() - win.winfo_reqwidth()) // 2
    y = root.winfo_rooty() + (root.winfo_height() - win.winfo_reqheight()) // 3
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    win.after(50, lambda: (win.lift(), win.focus_force(), ok_btn.focus_set()))
    win.grab_set()
    root.wait_window(win)
    return result[0]


class Button(ctk.CTkButton):
    """Letiltva semleges színt kap, hogy ne tűnjön kattinthatónak."""

    def __init__(self, master, enabled_fg: str, **kw):
        self._enabled_fg = enabled_fg
        super().__init__(master, fg_color=enabled_fg, **kw)
        if kw.get("state") == "disabled":
            self.configure(state="disabled")

    def configure(self, require_redraw=False, **kw):
        if "fg_color" in kw:
            self._enabled_fg = kw["fg_color"]
        if "state" in kw:
            kw["fg_color"] = self._enabled_fg if kw["state"] == "normal" else theme.SURFACE_2
        super().configure(require_redraw, **kw)


def button(master, text: str, command: Callable, kind: str = "secondary", **kw) -> Button:
    styles = {
        "primary": {"enabled_fg": theme.ACCENT, "hover_color": theme.ACCENT_HOVER,
                    "text_color": theme.ON_ACCENT},
        "danger": {"enabled_fg": theme.DANGER, "hover_color": theme.DANGER_HOVER, "text_color": "#1A0A09"},
        "secondary": {"enabled_fg": theme.SURFACE_2, "hover_color": theme.BORDER, "text_color": theme.TEXT,
                      "border_width": 1, "border_color": theme.BORDER},
    }
    return Button(master, text=text, command=command, height=36, corner_radius=8,
                  font=theme.font(13, "bold" if kind != "secondary" else "normal"),
                  text_color_disabled=theme.MUTED, **{**styles[kind], **kw})


def card(master, title: str | None = None, **kw) -> ctk.CTkFrame:
    frame = ctk.CTkFrame(master, fg_color=theme.SURFACE, corner_radius=12, **kw)
    if title:
        ctk.CTkLabel(frame, text=title, font=theme.font(13, "bold"), text_color=theme.MUTED
                     ).pack(anchor="w", padx=16, pady=(14, 6))
    return frame


def badge(master, text: str, kind: str = "info") -> ctk.CTkLabel:
    return ctk.CTkLabel(master, text=f" {text} ", font=theme.font(12, "bold"),
                        text_color=theme.KIND_COLORS[kind], fg_color=theme.SURFACE_2, corner_radius=6)


def autowrap(lbl: ctk.CTkLabel, pad: int = 32) -> ctk.CTkLabel:
    """A felirat sortörése kövesse a szülő szélességét (keskeny kártyákon se vágódjon le)."""
    lbl.master.bind("<Configure>", lambda e: lbl.configure(wraplength=max(e.width - pad, 80)), add="+")
    return lbl


def label(master, text: str = "", size: int = 13, muted: bool = False, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(master, text=text, font=kw.pop("font", theme.font(size)),
                        text_color=kw.pop("text_color", theme.MUTED if muted else theme.TEXT),
                        justify="left", anchor="w", **kw)


class Spark(tk.Canvas):
    """Vonaldiagram az előzményekből. `max_value=None`: automatikus skála."""

    def __init__(self, master, color: str, height: int = 40, bg: str = theme.SURFACE):
        super().__init__(master, height=height, bg=bg, highlightthickness=0)
        self.color = color
        self.values: list[float] = []
        self.max_value: float | None = None
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, values, max_value: float | None = None) -> None:
        self.values = [v for v in values if v is not None]
        self.max_value = max_value
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if len(self.values) < 2 or w < 10:
            return
        top = self.max_value or max(max(self.values), 1e-6) * 1.15
        self.create_line(0, h / 2, w, h / 2, fill=theme.BORDER, dash=(2, 4))
        step = w / (len(self.values) - 1)
        points = []
        for i, v in enumerate(self.values):
            points += [i * step, h - 2 - (min(v, top) / top) * (h - 4)]
        self.create_line(*points, fill=self.color, width=2)


class StatCard(ctk.CTkFrame):
    def __init__(self, master, title: str, color: str):
        super().__init__(master, fg_color=theme.SURFACE, corner_radius=12)
        label(self, title, 12, muted=True, font=theme.font(12, "bold")).pack(anchor="w", padx=16, pady=(14, 0))
        self.value = label(self, "—", font=theme.font(26, "bold", mono=True))
        self.value.pack(anchor="w", padx=16)
        self.sub = label(self, "", 12, muted=True)
        self.sub.pack(anchor="w", padx=16)
        self.spark = Spark(self, color, height=42)
        self.spark.pack(fill="x", padx=16, pady=(6, 14))

    def show(self, value: str, sub: str, history=(), max_value: float | None = None) -> None:
        self.value.configure(text=value)
        self.sub.configure(text=sub)
        self.spark.set(history, max_value)


class NavItem(ctk.CTkFrame):
    """Ikon + felirat az oldalsávban; billentyűzettel is kezelhető (Tab, Enter, Szóköz)."""

    def __init__(self, master, icon: str, text: str, command: Callable):
        super().__init__(master, fg_color="transparent", corner_radius=8, height=40,
                         border_width=1, border_color=theme.SURFACE)
        self.command = command
        self.active = False
        self.icon = ctk.CTkLabel(self, text=theme.ICONS[icon], font=theme.icon_font(16), width=28,
                                 text_color=theme.MUTED)
        self.icon.pack(side="left", padx=(10, 6), pady=8)
        self.text = ctk.CTkLabel(self, text=text, font=theme.font(14), text_color=theme.MUTED, anchor="w")
        self.text.pack(side="left", fill="x", expand=True)
        self.count = ctk.CTkLabel(self, text="", font=theme.font(11, "bold"), text_color=theme.ON_ACCENT,
                                  fg_color=theme.ACCENT, corner_radius=8, width=22, height=18)
        tk.Frame.configure(self, takefocus=1)
        for w in (self, self.icon, self.text):
            w.bind("<Button-1>", lambda e: command())
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<Return>", lambda e: command())
        self.bind("<space>", lambda e: command())
        self.bind("<FocusIn>", lambda e: self.configure(border_color=theme.ACCENT))
        self.bind("<FocusOut>", lambda e: self.configure(border_color=theme.SURFACE))

    def _hover(self, on: bool) -> None:
        if not self.active:
            self.configure(fg_color=theme.SURFACE_2 if on else "transparent")

    def set_active(self, active: bool) -> None:
        self.active = active
        self.configure(fg_color=theme.SURFACE_2 if active else "transparent")
        self.icon.configure(text_color=theme.ACCENT if active else theme.MUTED)
        self.text.configure(text_color=theme.TEXT if active else theme.MUTED)

    def set_count(self, n: int) -> None:
        if n:
            self.count.configure(text=str(n))
            self.count.pack(side="right", padx=10)
        else:
            self.count.pack_forget()


_table_style_ready = False


def table(master, columns: list[tuple[str, str, int]], height: int = 12) -> ttk.Treeview:
    """Sötét ttk.Treeview görgetősávval. columns: (azonosító, fejléc, szélesség)."""
    global _table_style_ready
    if not _table_style_ready:
        style = ttk.Style(master)
        style.theme_use("clam")
        style.configure("GB.Treeview", background=theme.SURFACE, fieldbackground=theme.SURFACE,
                        foreground=theme.TEXT, rowheight=30, borderwidth=0, bordercolor=theme.SURFACE,
                        lightcolor=theme.SURFACE, darkcolor=theme.SURFACE,
                        font=(theme.font(13).cget("family"), 11))
        style.configure("GB.Treeview.Heading", background=theme.SURFACE_2, foreground=theme.MUTED,
                        relief="flat", bordercolor=theme.SURFACE_2, lightcolor=theme.SURFACE_2,
                        darkcolor=theme.SURFACE_2, font=(theme.font(13).cget("family"), 10, "bold"))
        style.map("GB.Treeview", background=[("selected", "#24453A")],
                  foreground=[("selected", theme.TEXT)])
        style.map("GB.Treeview.Heading", background=[("active", theme.BORDER)])
        _table_style_ready = True
    frame = ctk.CTkFrame(master, fg_color=theme.SURFACE, corner_radius=0)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=height,
                        style="GB.Treeview", selectmode="browse")
    for cid, heading, width in columns:
        tree.heading(cid, text=heading, anchor="w")
        tree.column(cid, width=width, anchor="w", stretch=cid == columns[-1][0])
    bar = ctk.CTkScrollbar(frame, command=tree.yview)
    tree.configure(yscrollcommand=bar.set)
    tree.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    tree.frame = frame
    return tree


class Page(ctk.CTkFrame):
    title = ""
    subtitle = ""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        label(self, self.title, font=theme.font(24, "bold")).pack(anchor="w")
        if self.subtitle:
            label(self, self.subtitle, 13, muted=True, wraplength=860).pack(anchor="w", pady=(2, 0))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, pady=(16, 0))
        self.build()

    def build(self) -> None: ...

    def on_show(self) -> None: ...

    def on_tick(self) -> None: ...
