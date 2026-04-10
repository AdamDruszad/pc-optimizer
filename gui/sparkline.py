"""
sparkline.py
Egyedi Sparkline widget CustomTkinter-hez, tkinter Canvas alapon.
GPU memória és engine % előzmény megjelenítéséhez.
"""

import tkinter as tk
import customtkinter as ctk
from collections import deque


class SparklineChart(tk.Canvas):
    """
    Minimális, gyors sparkline chart.
    Két vonal sorozatot tud egyszerre megjeleníteni (pl. shared + dedicated).
    Automatikusan skálázza a tengelyeket.
    """

    def __init__(self, parent,
                 color_primary:   str = "#00FF88",
                 color_secondary: str = "#00C8FF",
                 color_bg:        str = "#090B10",
                 color_grid:      str = "#1A2030",
                 unit:            str = "MB",
                 max_val:         int = 8192,
                 show_secondary:  bool = True,
                 **kwargs):
        super().__init__(parent,
                         bg=color_bg,
                         highlightthickness=1,
                         highlightbackground="#2A3040",
                         **kwargs)

        self.color_primary   = color_primary
        self.color_secondary = color_secondary
        self.color_bg        = color_bg
        self.color_grid      = color_grid
        self.unit            = unit
        self.max_val         = max_val
        self.show_secondary  = show_secondary

        self._data_primary:   deque = deque(maxlen=90)
        self._data_secondary: deque = deque(maxlen=90)

        # Szöveg elemek (egyszer létrehozzuk, csak frissítjük)
        self._label_cur  = None
        self._label_max  = None
        self._label_min  = None

        self.bind("<Configure>", lambda e: self._redraw())

    def update_data(self, primary_vals, secondary_vals=None):
        """
        Frissíti a chart adatait és újrarajzolja.
        primary_vals: deque vagy list
        secondary_vals: deque vagy list (opcionális)
        """
        self._data_primary   = deque(primary_vals, maxlen=90)
        if secondary_vals is not None:
            self._data_secondary = deque(secondary_vals, maxlen=90)
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10 or not self._data_primary:
            return

        pad_l, pad_r = 50, 12
        pad_t, pad_b = 10, 24
        chart_w = w - pad_l - pad_r
        chart_h = h - pad_t - pad_b

        # Dinamikus max érték (10%-os padding fölé)
        all_vals = list(self._data_primary)
        if self._data_secondary and self.show_secondary:
            all_vals += list(self._data_secondary)
        data_max = max(all_vals) if all_vals else 1
        display_max = max(data_max * 1.15, self.max_val * 0.1)

        # Rács vonalak (4 vízszintes)
        for i in range(5):
            y = pad_t + chart_h - (i / 4) * chart_h
            self.create_line(pad_l, y, w - pad_r, y,
                             fill=self.color_grid, width=1, dash=(3, 5))
            val = (i / 4) * display_max
            label = f"{int(val):,}" if val >= 1000 else f"{val:.0f}"
            self.create_text(pad_l - 4, y,
                             text=label, anchor="e",
                             fill="#4A5568", font=("Consolas", 8))

        # Egység felső sarokba
        self.create_text(pad_l, pad_t - 2,
                         text=self.unit, anchor="sw",
                         fill="#4A5568", font=("Consolas", 8))

        # Adatvonalak kirajzolása
        def make_points(data):
            pts = []
            n = len(data)
            if n < 2:
                return pts
            for i, v in enumerate(data):
                x = pad_l + (i / (max(n - 1, 1))) * chart_w
                y = pad_t + chart_h - (v / display_max) * chart_h
                y = max(pad_t, min(pad_t + chart_h, y))
                pts.extend([x, y])
            return pts

        # Secondary vonal (halványabb)
        if self.show_secondary and len(self._data_secondary) >= 2:
            pts2 = make_points(self._data_secondary)
            if pts2:
                self.create_line(*pts2, fill=self.color_secondary,
                                 width=1, smooth=True)

        # Primary vonal (vastag)
        pts1 = make_points(self._data_primary)
        if pts1:
            # Terület kitöltés (fill poly)
            if len(self._data_primary) >= 2:
                fill_pts = [pad_l, pad_t + chart_h] + pts1 + [pts1[-2], pad_t + chart_h]
                self.create_polygon(*fill_pts,
                                    fill=self._hex_alpha(self.color_primary, 0.12),
                                    outline="")
            self.create_line(*pts1, fill=self.color_primary,
                             width=2, smooth=True)

        # Aktuális érték marker (utolsó pont)
        if len(self._data_primary) >= 1:
            last_v = list(self._data_primary)[-1]
            lx = pad_l + chart_w
            ly = pad_t + chart_h - (last_v / display_max) * chart_h
            ly = max(pad_t, min(pad_t + chart_h, ly))
            self.create_oval(lx - 4, ly - 4, lx + 4, ly + 4,
                             fill=self.color_primary, outline="#0D0F14", width=2)

        # X tengely időcímkék
        self.create_text(pad_l, h - 4,
                         text="−3 perc", anchor="sw",
                         fill="#4A5568", font=("Consolas", 8))
        self.create_text(w - pad_r, h - 4,
                         text="most", anchor="se",
                         fill="#4A5568", font=("Consolas", 8))

        # Aktuális érték (nagy szöveg jobb felső sarokba)
        if self._data_primary:
            cur = list(self._data_primary)[-1]
            unit_str = self.unit
            if unit_str == "MB" and cur >= 1000:
                disp = f"{cur/1024:.2f} GB"
            elif unit_str == "%":
                disp = f"{cur:.1f}%"
            else:
                disp = f"{int(cur)} {unit_str}"
            self.create_text(w - pad_r, pad_t,
                             text=disp, anchor="ne",
                             fill=self.color_primary,
                             font=("Consolas", 11, "bold"))

    @staticmethod
    def _hex_alpha(hex_color: str, alpha: float) -> str:
        """
        Hex színt kever a háttérrel az alpha értéknek megfelelően.
        Mivel tkinter nem támogat RGBA-t, manuálisan keverünk.
        """
        try:
            r1 = int(hex_color[1:3], 16)
            g1 = int(hex_color[3:5], 16)
            b1 = int(hex_color[5:7], 16)
            # Háttér: #090B10
            r2, g2, b2 = 9, 11, 16
            r = int(r2 + (r1 - r2) * alpha)
            g = int(g2 + (g1 - g2) * alpha)
            b = int(b2 + (b1 - b2) * alpha)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color
