"""
app.py  —  GameBooster v2.0
Univerzális Windows Game Booster — CS2 modul eltávolítva.

Tabok:
  🖥 Hardver     — detektált specs, javaslatok, tápellátás, hálózat
  🚀 Boost       — profil választó, aktiválás, visszaállítás
  📋 Profilok    — beépített + egyéni profilok kezelése
  💾 RAM Kezelő  — working set, folyamat prioritás
  📊 Monitor     — élő CPU/RAM/hőmérséklet
  🖥 iGPU        — Intel/AMD iGPU memória (csak iGPU-n)
"""

import customtkinter as ctk
import tkinter as tk
import threading
import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.hardware_detector import (
    detect_hardware, hw_monitor,
    HardwareProfile, GpuType, PowerState, NetworkType,
    get_recommendations
)
from modules.profile_manager   import profile_manager, BoostProfile, BUILTIN_PROFILES
from modules.hw_optimizer      import apply_boost, restore_original, is_admin
from modules.ram_cleaner       import (
    get_ram_info, empty_working_sets, boost_cs2_priority, get_top_ram_consumers
)
from modules.monitor           import system_monitor, SystemSnapshot
from modules.igpu_monitor      import igpu_monitor, IgpuSnapshot, optimize_igpu_memory
from gui.sparkline             import SparklineChart
from gui.app_paths             import init as init_paths
from modules.registry_tweaks  import (
    apply_registry_tweaks, restore_registry_tweaks,
    get_current_registry_status, has_registry_snapshot,
    RegistryTweakConfig,
    get_hags_status, get_game_mode_status, get_xbox_gamebar_status,
)

# ─────────────────────────────────────────────
#  TÉMA
# ─────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

C_BG      = "#0D0F14"
C_PANEL   = "#141720"
C_ACCENT  = "#00FF88"
C_ACCENT2 = "#00C8FF"
C_WARNING = "#FF6B35"
C_TEXT    = "#E0E8F0"
C_MUTED   = "#4A5568"
C_CARD    = "#1A1F2E"
C_BOOST   = "#FF2D55"
C_PURPLE  = "#9B59FF"
C_GOLD    = "#FFC147"


# ─────────────────────────────────────────────
#  SEGÉD WIDGETEK
# ─────────────────────────────────────────────

class LogBox(ctk.CTkTextbox):
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent, font=("Consolas", 11),
            fg_color="#090B10", text_color=C_TEXT,
            border_color=C_MUTED, border_width=1, **kwargs
        )
        self.configure(state="disabled")

    def log(self, message: str):
        self.configure(state="normal")
        self.insert("end", message + "\n")
        self.see("end")
        self.configure(state="disabled")

    def clear(self):
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")


class StatCard(ctk.CTkFrame):
    def __init__(self, parent, title: str, unit: str = "",
                 max_val: float = 100, warn_at: float = 70,
                 crit_at: float = 90, **kwargs):
        super().__init__(parent, fg_color=C_CARD, corner_radius=10, **kwargs)
        self.max_val = max_val
        self.warn_at = warn_at
        self.crit_at = crit_at
        self.unit    = unit
        ctk.CTkLabel(self, text=title.upper(),
                     font=("Segoe UI Black", 9), text_color=C_MUTED
                     ).pack(pady=(10, 2), padx=12, anchor="w")
        self.value_lbl = ctk.CTkLabel(self, text="—",
                                      font=("Consolas", 28, "bold"), text_color=C_ACCENT)
        self.value_lbl.pack(padx=12, anchor="w")
        self.bar = ctk.CTkProgressBar(self, height=4,
                                      fg_color="#252D40", progress_color=C_ACCENT)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=12, pady=(4, 10))

    def update(self, value: float):
        ratio = min(value / self.max_val, 1.0) if self.max_val > 0 else 0
        color = ("#FF3B30" if value >= self.crit_at else
                 C_WARNING  if value >= self.warn_at else C_ACCENT)
        disp = f"{int(value)}" if value == int(value) else f"{value:.1f}"
        self.value_lbl.configure(text=f"{disp}{self.unit}", text_color=color)
        self.bar.configure(progress_color=color)
        self.bar.set(ratio)

    def set_na(self):
        self.value_lbl.configure(text="N/A", text_color=C_MUTED)
        self.bar.set(0)


class InfoRow(ctk.CTkFrame):
    """Egyszerű sor: label + érték, hardware info megjelenítéséhez."""
    def __init__(self, parent, label: str, value: str = "—",
                 value_color: str = C_TEXT, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        ctk.CTkLabel(self, text=label, font=("Segoe UI", 11),
                     text_color=C_MUTED, width=160, anchor="w").pack(side="left")
        self.val_lbl = ctk.CTkLabel(self, text=value, font=("Consolas", 11),
                                    text_color=value_color, anchor="w")
        self.val_lbl.pack(side="left", fill="x", expand=True)

    def set(self, value: str, color: str = C_TEXT):
        self.val_lbl.configure(text=value, text_color=color)


# ─────────────────────────────────────────────
#  FŐ ALKALMAZÁS
# ─────────────────────────────────────────────

class GameBoosterApp(ctk.CTk):
    def __init__(self, app_dir: str | None = None):
        super().__init__()

        # Útvonalak inicializálása (PyInstaller + normál futás)
        if app_dir:
            init_paths(app_dir)

        self.title("GameBooster v2.1 — Universal Windows Optimizer")
        self.geometry("980x760")
        self.minsize(860, 660)
        self.configure(fg_color=C_BG)

        self.is_admin      = is_admin()
        self._hw: HardwareProfile | None = None
        self._boost_active = False
        self._igpu_tab_built = False

        self._build_ui()
        self._start_monitors()
        self._detect_hardware_async()

    # ─────────────────────────────────────────
    #  UI FELÉPÍTÉS
    # ─────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=C_PANEL, height=60, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="⚡  GAME BOOSTER",
                     font=("Segoe UI Black", 20), text_color=C_ACCENT).pack(side="left", padx=20)
        ctk.CTkLabel(hdr, text="v2.0 — Universal Optimizer",
                     font=("Segoe UI", 11), text_color=C_MUTED).pack(side="left", padx=4)

        # Státusz badge-ek (jobb oldal)
        self.net_badge = ctk.CTkLabel(hdr, text="🌐 —",
                                       font=("Segoe UI", 11), text_color=C_MUTED,
                                       fg_color=C_CARD, corner_radius=6, padx=8, pady=4)
        self.net_badge.pack(side="right", padx=4)

        self.power_badge = ctk.CTkLabel(hdr, text="⚡ —",
                                         font=("Segoe UI", 11), text_color=C_MUTED,
                                         fg_color=C_CARD, corner_radius=6, padx=8, pady=4)
        self.power_badge.pack(side="right", padx=4)

        admin_col = C_ACCENT if self.is_admin else C_WARNING
        admin_bg  = "#0A2E1A" if self.is_admin else "#2E1A0A"
        ctk.CTkLabel(hdr, text="🛡 Admin" if self.is_admin else "⚠ Nem Admin",
                     font=("Segoe UI", 11), text_color=admin_col,
                     fg_color=admin_bg, corner_radius=6, padx=8, pady=4
                     ).pack(side="right", padx=4)

        # Monitor sáv
        self._build_monitor_bar()

        # Tabok
        self.tabview = ctk.CTkTabview(
            self, fg_color=C_BG,
            segmented_button_fg_color=C_PANEL,
            segmented_button_selected_color=C_ACCENT,
            segmented_button_selected_hover_color="#00CC6A",
            segmented_button_unselected_color=C_PANEL,
            segmented_button_unselected_hover_color="#1E2535",
            text_color=C_TEXT,
        )
        self.tabview.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        for tab in ["🖥  Hardver", "🚀  Boost", "📋  Profilok",
                    "💾  RAM Kezelő", "📊  Monitor", "🔷  iGPU", "🔑  Registry"]:
            self.tabview.add(tab)

        self._build_hardware_tab(self.tabview.tab("🖥  Hardver"))
        self._build_boost_tab(self.tabview.tab("🚀  Boost"))
        self._build_profiles_tab(self.tabview.tab("📋  Profilok"))
        self._build_ram_tab(self.tabview.tab("💾  RAM Kezelő"))
        self._build_monitor_tab(self.tabview.tab("📊  Monitor"))
        self._build_igpu_tab(self.tabview.tab("🔷  iGPU"))
        self._build_registry_tab(self.tabview.tab("🔑  Registry"))

    def _build_monitor_bar(self):
        bar = ctk.CTkFrame(self, fg_color=C_PANEL, height=112, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=12, pady=8)

        self.stat_cpu_pct   = StatCard(inner, "CPU kihasználtság", " %",
                                        max_val=100, warn_at=70, crit_at=90)
        self.stat_cpu_pct.pack(side="left", fill="both", expand=True, padx=(0,5))
        self.stat_cpu_temp  = StatCard(inner, "CPU hőmérséklet", " °C",
                                        max_val=100, warn_at=75, crit_at=90)
        self.stat_cpu_temp.pack(side="left", fill="both", expand=True, padx=(0,5))
        self.stat_cpu_freq  = StatCard(inner, "CPU órajel", " MHz",
                                        max_val=4800, warn_at=4000, crit_at=4500)
        self.stat_cpu_freq.pack(side="left", fill="both", expand=True, padx=(0,5))
        self.stat_ram_pct   = StatCard(inner, "RAM foglaltság", " %",
                                        max_val=100, warn_at=70, crit_at=85)
        self.stat_ram_pct.pack(side="left", fill="both", expand=True, padx=(0,5))
        self.stat_igpu_sh   = StatCard(inner, "iGPU shared mem", " MB",
                                        max_val=4096, warn_at=2048, crit_at=3500)
        self.stat_igpu_sh.pack(side="left", fill="both", expand=True)

    # ══════════════════════════════════════════
    #  TAB 1 — HARDVER
    # ══════════════════════════════════════════

    def _build_hardware_tab(self, parent):
        parent.configure(fg_color=C_BG)

        # Bal: specs
        left = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=10, width=340)
        left.pack(side="left", fill="y", padx=(0,8), pady=4)
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="RENDSZER SPECIFIKÁCIÓK",
                     font=("Segoe UI Black", 11), text_color=C_MUTED
                     ).pack(pady=(14,8), padx=16, anchor="w")

        self.hw_detect_lbl = ctk.CTkLabel(
            left, text="⏳ Detektálás folyamatban...",
            font=("Segoe UI", 12), text_color=C_GOLD
        )
        self.hw_detect_lbl.pack(pady=(0,10), padx=16, anchor="w")

        def section(text):
            ctk.CTkFrame(left, fg_color=C_MUTED, height=1
                         ).pack(fill="x", padx=16, pady=(6,4))
            ctk.CTkLabel(left, text=text, font=("Segoe UI Black", 9),
                         text_color=C_MUTED).pack(padx=16, anchor="w")

        section("GPU")
        self.hw_gpu_name = InfoRow(left, "Típus:", "—", C_ACCENT2)
        self.hw_gpu_name.pack(fill="x", padx=16, pady=1)
        self.hw_gpu_type = InfoRow(left, "Kategória:", "—", C_TEXT)
        self.hw_gpu_type.pack(fill="x", padx=16, pady=1)
        self.hw_gpu_vram = InfoRow(left, "Dedikált VRAM:", "—", C_TEXT)
        self.hw_gpu_vram.pack(fill="x", padx=16, pady=1)
        self.hw_gpu_shared = InfoRow(left, "Shared max:", "—", C_TEXT)
        self.hw_gpu_shared.pack(fill="x", padx=16, pady=1)

        section("CPU")
        self.hw_cpu_name   = InfoRow(left, "Modell:", "—", C_ACCENT2)
        self.hw_cpu_name.pack(fill="x", padx=16, pady=1)
        self.hw_cpu_cores  = InfoRow(left, "Magok:", "—", C_TEXT)
        self.hw_cpu_cores.pack(fill="x", padx=16, pady=1)
        self.hw_cpu_freq   = InfoRow(left, "Max órajel:", "—", C_TEXT)
        self.hw_cpu_freq.pack(fill="x", padx=16, pady=1)

        section("RAM")
        self.hw_ram_total  = InfoRow(left, "Összesen:", "—", C_ACCENT2)
        self.hw_ram_total.pack(fill="x", padx=16, pady=1)

        section("TÁPELLÁTÁS")
        self.hw_power      = InfoRow(left, "Állapot:", "—", C_TEXT)
        self.hw_power.pack(fill="x", padx=16, pady=1)
        self.hw_battery    = InfoRow(left, "Töltöttség:", "—", C_TEXT)
        self.hw_battery.pack(fill="x", padx=16, pady=1)

        section("HÁLÓZAT")
        self.hw_network    = InfoRow(left, "Kapcsolat:", "—", C_TEXT)
        self.hw_network.pack(fill="x", padx=16, pady=1)
        self.hw_net_name   = InfoRow(left, "Interfész:", "—", C_TEXT)
        self.hw_net_name.pack(fill="x", padx=16, pady=1)

        section("WINDOWS")
        self.hw_win_ver    = InfoRow(left, "Verzió:", "—", C_TEXT)
        self.hw_win_ver.pack(fill="x", padx=16, pady=(1,14))

        # Jobb: javaslatok
        right = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=10)
        right.pack(side="left", fill="both", expand=True, pady=4)

        ctk.CTkLabel(right, text="JAVASLATOK ÉS OPTIMALIZÁLÁSI TIPPEK",
                     font=("Segoe UI Black", 11), text_color=C_MUTED
                     ).pack(pady=(14,6), padx=16, anchor="w")

        self.hw_recs_box = LogBox(right)
        self.hw_recs_box.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self.hw_recs_box.log("⏳ Várakozás a hardware detektálásra...")

        ctk.CTkButton(
            right, text="↻  Újradetektálás",
            font=("Segoe UI", 12), fg_color=C_PANEL, hover_color="#252D40",
            text_color=C_TEXT, border_color=C_MUTED, border_width=1,
            height=34, corner_radius=8,
            command=self._detect_hardware_async
        ).pack(fill="x", padx=12, pady=(0,12))

    # ══════════════════════════════════════════
    #  TAB 2 — BOOST
    # ══════════════════════════════════════════

    def _build_boost_tab(self, parent):
        parent.configure(fg_color=C_BG)

        # Bal: profil választó + gombok
        left = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=10, width=240)
        left.pack(side="left", fill="y", padx=(0,8), pady=4)
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="AKTÍV PROFIL",
                     font=("Segoe UI Black", 11), text_color=C_MUTED
                     ).pack(pady=(14,6), padx=16, anchor="w")

        # Profil választó
        all_profiles = profile_manager.all_profiles()
        active_key, active_prof = profile_manager.get_active()

        self.boost_profile_var = ctk.StringVar(value=active_key)
        profile_names = {k: f"{v.icon}  {v.name}" for k, v in all_profiles.items()}
        self.boost_profile_menu = ctk.CTkOptionMenu(
            left,
            values=list(profile_names.values()),
            fg_color=C_PANEL, button_color=active_prof.color_accent,
            button_hover_color="#252D40", font=("Segoe UI", 12),
            command=self._on_boost_profile_change
        )
        self.boost_profile_menu.set(profile_names.get(active_key, list(profile_names.values())[0]))
        self.boost_profile_menu.pack(fill="x", padx=16, pady=(0,8))

        # Profil leírás
        self.boost_profile_desc = ctk.CTkLabel(
            left, text=active_prof.description,
            font=("Segoe UI", 10), text_color=C_MUTED,
            wraplength=200, justify="left"
        )
        self.boost_profile_desc.pack(fill="x", padx=16, pady=(0,12))

        # Boost státusz
        self.boost_badge_lbl = ctk.CTkLabel(
            left, text="○  INAKTÍV",
            font=("Segoe UI", 12, "bold"), text_color=C_MUTED,
            fg_color=C_PANEL, corner_radius=6, padx=12, pady=6
        )
        self.boost_badge_lbl.pack(fill="x", padx=16, pady=(0,10))

        # BOOST gomb
        self.boost_btn = ctk.CTkButton(
            left, text="⚡  BOOST AKTIVÁLÁS",
            font=("Segoe UI Black", 13),
            fg_color=C_BOOST, hover_color="#CC2244",
            text_color="white", height=50, corner_radius=8,
            command=self._on_boost_click
        )
        self.boost_btn.pack(fill="x", padx=16, pady=4)

        # Visszaállítás gomb
        self.restore_btn = ctk.CTkButton(
            left, text="↩  VISSZAÁLLÍTÁS",
            font=("Segoe UI", 12),
            fg_color=C_PANEL, hover_color="#252D40",
            text_color=C_TEXT, border_color=C_MUTED, border_width=1,
            height=40, corner_radius=8,
            command=self._on_restore_click
        )
        self.restore_btn.pack(fill="x", padx=16, pady=4)

        # RAM tisztítás gyorsgomb
        ctk.CTkButton(
            left, text="🧹  RAM Tisztítás",
            font=("Segoe UI", 12),
            fg_color=C_PANEL, hover_color="#252D40",
            text_color=C_ACCENT2, border_color=C_ACCENT2, border_width=1,
            height=36, corner_radius=8, command=self._quick_ram_clean
        ).pack(fill="x", padx=16, pady=(12,4))

        # Aktív profil részletek
        ctk.CTkLabel(left, text="PROFIL RÉSZLETEK",
                     font=("Segoe UI Black", 9), text_color=C_MUTED
                     ).pack(pady=(16,4), padx=16, anchor="w")

        self.boost_profile_details = ctk.CTkTextbox(
            left, height=120, font=("Consolas", 9),
            fg_color="#090B10", text_color=C_TEXT, border_width=0
        )
        self.boost_profile_details.pack(fill="x", padx=16, pady=(0,14))
        self._update_boost_profile_details(active_prof)

        # Jobb: log
        right = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=10)
        right.pack(side="left", fill="both", expand=True, pady=4)
        ctk.CTkLabel(right, text="MŰVELETI NAPLÓ",
                     font=("Segoe UI Black", 11), text_color=C_MUTED
                     ).pack(pady=(14,4), padx=16, anchor="w")
        self.boost_log = LogBox(right)
        self.boost_log.pack(fill="both", expand=True, padx=12, pady=(0,12))

        if not self.is_admin:
            self.boost_log.log("⚠ FIGYELEM: Nem admin jogokkal fut!")
            self.boost_log.log("   Megoldás: Jobb klikk → Futtatás rendszergazdaként")
        else:
            self.boost_log.log("✓ Admin jogok: OK")
            self.boost_log.log("✓ Élő monitor: aktív")
            self.boost_log.log("► Válassz profilt és nyomd meg a BOOST gombot!")

    def _update_boost_profile_details(self, profile: BoostProfile):
        self.boost_profile_details.configure(state="normal")
        self.boost_profile_details.delete("1.0", "end")
        lines = [
            f"Energiaséma:   {profile.power_plan}",
            f"RAM tisztítás: {'igen (agresszív)' if profile.ram_clean_aggressive else 'igen' if profile.ram_clean_on_boost else 'nem'}",
            f"CPU prioritás: {'igen' if profile.set_process_priority else 'nem'}",
            f"BG throttle:   {'igen' if profile.throttle_background else 'nem'}",
            f"Auto restore:  {'igen' if profile.auto_restore_on_exit else 'nem'}",
            f"Szolgáltatások: {len(profile.stop_services)} db leáll",
        ]
        self.boost_profile_details.insert("1.0", "\n".join(lines))
        self.boost_profile_details.configure(state="disabled")

    # ══════════════════════════════════════════
    #  TAB 3 — PROFILOK
    # ══════════════════════════════════════════

    def _build_profiles_tab(self, parent):
        parent.configure(fg_color=C_BG)

        # Bal: profil lista
        left = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=10, width=220)
        left.pack(side="left", fill="y", padx=(0,8), pady=4)
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="PROFILOK",
                     font=("Segue UI Black", 11), text_color=C_MUTED
                     ).pack(pady=(14,8), padx=14, anchor="w")

        # Profil lista scroll frame
        self.profile_list_frame = ctk.CTkScrollableFrame(
            left, fg_color="transparent", height=300
        )
        self.profile_list_frame.pack(fill="both", expand=True, padx=8, pady=(0,8))

        # Gombok
        ctk.CTkButton(
            left, text="＋  Új egyéni profil",
            font=("Segoe UI", 11),
            fg_color=C_ACCENT, hover_color="#00CC6A",
            text_color="#000000", height=34, corner_radius=8,
            command=self._create_custom_profile
        ).pack(fill="x", padx=14, pady=4)

        self.prof_delete_btn = ctk.CTkButton(
            left, text="🗑  Profil törlése",
            font=("Segoe UI", 11),
            fg_color=C_PANEL, hover_color="#252D40",
            text_color=C_WARNING, border_color=C_WARNING, border_width=1,
            height=34, corner_radius=8,
            command=self._delete_selected_profile,
            state="disabled"
        )
        self.prof_delete_btn.pack(fill="x", padx=14, pady=(0,14))

        # Jobb: profil részletek szerkesztő
        right = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=10)
        right.pack(side="left", fill="both", expand=True, pady=4)

        ctk.CTkLabel(right, text="PROFIL RÉSZLETEK",
                     font=("Segoe UI Black", 11), text_color=C_MUTED
                     ).pack(pady=(14,8), padx=16, anchor="w")

        self.prof_detail_box = LogBox(right, height=300)
        self.prof_detail_box.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self.prof_detail_box.log("← Válassz profilt a listából")

        self._selected_profile_key: str | None = None
        self._refresh_profile_list()

    def _refresh_profile_list(self):
        for w in self.profile_list_frame.winfo_children():
            w.destroy()

        all_p = profile_manager.all_profiles()
        active_key, _ = profile_manager.get_active()

        for key, prof in all_p.items():
            is_active = (key == active_key)
            btn_color = prof.color_accent if is_active else C_PANEL
            txt_color = "#000000" if is_active and prof.color_accent != C_PANEL else C_TEXT

            btn = ctk.CTkButton(
                self.profile_list_frame,
                text=f"{prof.icon}  {prof.name}",
                font=("Segoe UI", 12, "bold" if is_active else "normal"),
                fg_color=btn_color,
                hover_color="#252D40",
                text_color=txt_color,
                height=36, corner_radius=8, anchor="w",
                command=lambda k=key: self._select_profile(k)
            )
            btn.pack(fill="x", pady=2)

            if prof.is_builtin:
                ctk.CTkLabel(
                    self.profile_list_frame,
                    text="  beépített", font=("Segoe UI", 9),
                    text_color=C_MUTED
                ).pack(anchor="w", padx=4)

    def _select_profile(self, key: str):
        self._selected_profile_key = key
        prof = profile_manager.get(key)
        if not prof:
            return

        self.prof_detail_box.clear()
        lines = [
            f"Név:          {prof.icon} {prof.name}",
            f"Leírás:       {prof.description}",
            f"Beépített:    {'Igen (nem törölhető)' if prof.is_builtin else 'Nem (törölhető)'}",
            f"",
            f"Energiaséma:  {prof.power_plan}",
            f"RAM tisztítás:{' igen (agresszív)' if prof.ram_clean_aggressive else ' igen' if prof.ram_clean_on_boost else ' nem'}",
            f"BG throttle:  {'igen' if prof.throttle_background else 'nem'}",
            f"Auto restore: {'igen' if prof.auto_restore_on_exit else 'nem'}",
            f"",
            f"Leállítandó szolgáltatások ({len(prof.stop_services)} db):",
        ]
        for svc in prof.stop_services:
            lines.append(f"  • {svc}")

        for line in lines:
            self.prof_detail_box.log(line)

        # Törlés gomb csak egyéni profiloknál
        self.prof_delete_btn.configure(
            state="normal" if not prof.is_builtin else "disabled"
        )

        # Aktív profil váltása
        profile_manager.set_active(key)
        self._refresh_profile_list()
        self._sync_boost_tab_profile()

    def _sync_boost_tab_profile(self):
        """Boost tab profil választóját szinkronizálja."""
        active_key, active_prof = profile_manager.get_active()
        all_profiles = profile_manager.all_profiles()
        profile_names = {k: f"{v.icon}  {v.name}" for k, v in all_profiles.items()}
        display = profile_names.get(active_key, "")
        if display:
            self.boost_profile_menu.set(display)
        self.boost_profile_desc.configure(text=active_prof.description)
        self._update_boost_profile_details(active_prof)

    def _create_custom_profile(self):
        dialog = ctk.CTkInputDialog(
            text="Új profil neve:", title="Új egyéni profil"
        )
        name = dialog.get_input()
        if name and name.strip():
            key = profile_manager.create_custom(name.strip())
            self._refresh_profile_list()
            self._select_profile(key)

    def _delete_selected_profile(self):
        if not self._selected_profile_key:
            return
        ok = profile_manager.delete_custom(self._selected_profile_key)
        if ok:
            self._selected_profile_key = None
            self.prof_detail_box.clear()
            self.prof_detail_box.log("✓ Profil törölve.")
            self._refresh_profile_list()

    # ══════════════════════════════════════════
    #  TAB 4 — RAM KEZELŐ
    # ══════════════════════════════════════════

    def _build_ram_tab(self, parent):
        parent.configure(fg_color=C_BG)

        top = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=10, height=88)
        top.pack(fill="x", pady=(0,8))
        top.pack_propagate(False)
        ti = ctk.CTkFrame(top, fg_color="transparent")
        ti.pack(fill="both", expand=True, padx=16, pady=8)

        ctk.CTkLabel(ti, text="RAM ÁLLAPOT",
                     font=("Segoe UI Black", 11), text_color=C_MUTED).pack(side="left", padx=(0,16))
        self.ram_total_lbl = ctk.CTkLabel(ti, text="Összes: —",
                                           font=("Segoe UI", 13), text_color=C_TEXT)
        self.ram_total_lbl.pack(side="left", padx=10)
        self.ram_used_lbl = ctk.CTkLabel(ti, text="Használt: —",
                                          font=("Segoe UI", 13), text_color=C_WARNING)
        self.ram_used_lbl.pack(side="left", padx=10)
        self.ram_free_lbl = ctk.CTkLabel(ti, text="Szabad: —",
                                          font=("Segoe UI", 13), text_color=C_ACCENT)
        self.ram_free_lbl.pack(side="left", padx=10)

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0,8))

        ctk.CTkButton(
            btn_row, text="🧹  WORKING SET ÜRÍTÉS",
            font=("Segoe UI Black", 13),
            fg_color=C_ACCENT2, hover_color="#009ACC",
            text_color="#000000", height=44, corner_radius=8,
            command=self._clean_ram
        ).pack(side="left", fill="x", expand=True, padx=(0,6))

        ctk.CTkButton(
            btn_row, text="🎮  FOLYAMAT PRIORITÁS",
            font=("Segoe UI Black", 13),
            fg_color=C_PURPLE, hover_color="#7A3FCC",
            text_color="white", height=44, corner_radius=8,
            command=self._set_process_priority
        ).pack(side="left", fill="x", expand=True, padx=(0,6))

        ctk.CTkButton(
            btn_row, text="↻",
            font=("Segoe UI", 14),
            fg_color=C_PANEL, hover_color="#252D40",
            text_color=C_TEXT, border_color=C_MUTED, border_width=1,
            height=44, corner_radius=8, width=52,
            command=self._refresh_proc_list
        ).pack(side="left")

        bottom = ctk.CTkFrame(parent, fg_color="transparent")
        bottom.pack(fill="both", expand=True)

        proc = ctk.CTkFrame(bottom, fg_color=C_CARD, corner_radius=10, width=260)
        proc.pack(side="left", fill="y", padx=(0,8))
        proc.pack_propagate(False)
        ctk.CTkLabel(proc, text="TOP RAM FOGYASZTÓK",
                     font=("Segoe UI Black", 10), text_color=C_MUTED
                     ).pack(pady=(12,6), padx=14, anchor="w")
        self.proc_labels = []
        for _ in range(8):
            r = ctk.CTkFrame(proc, fg_color="transparent")
            r.pack(fill="x", padx=10, pady=1)
            n = ctk.CTkLabel(r, text="", font=("Consolas", 10),
                              text_color=C_TEXT, width=150, anchor="w")
            n.pack(side="left")
            m = ctk.CTkLabel(r, text="", font=("Consolas", 10),
                              text_color=C_ACCENT, width=55, anchor="e")
            m.pack(side="right")
            self.proc_labels.append((n, m))

        logf = ctk.CTkFrame(bottom, fg_color=C_CARD, corner_radius=10)
        logf.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(logf, text="MŰVELETI NAPLÓ",
                     font=("Segoe UI Black", 11), text_color=C_MUTED
                     ).pack(pady=(12,4), padx=16, anchor="w")
        self.ram_log = LogBox(logf)
        self.ram_log.pack(fill="both", expand=True, padx=12, pady=(0,12))

        self._refresh_proc_list()
        self._refresh_ram_display()

    # ══════════════════════════════════════════
    #  TAB 5 — MONITOR (SPARKLINE CHART)
    # ══════════════════════════════════════════

    def _build_monitor_tab(self, parent):
        parent.configure(fg_color=C_BG)

        # 2×2 sparkline grid
        top_row = ctk.CTkFrame(parent, fg_color="transparent")
        top_row.pack(fill="both", expand=True, pady=(0,6))
        bot_row = ctk.CTkFrame(parent, fg_color="transparent")
        bot_row.pack(fill="both", expand=True)

        def spark_card(parent_frame, title, color, unit, max_val):
            card = ctk.CTkFrame(parent_frame, fg_color=C_CARD, corner_radius=10)
            card.pack(side="left", fill="both", expand=True, padx=(0,6))
            ctk.CTkLabel(card, text=title, font=("Segoe UI Black", 10),
                         text_color=C_MUTED).pack(pady=(10,4), padx=12, anchor="w")
            chart = SparklineChart(card, color_primary=color, unit=unit,
                                   max_val=max_val, show_secondary=False, height=120)
            chart.pack(fill="both", expand=True, padx=8, pady=(0,8))
            return chart

        self.spark_cpu  = spark_card(top_row, "CPU kihasználtság (%)", C_ACCENT,  "%",   100)
        self.spark_temp = spark_card(top_row, "CPU hőmérséklet (°C)",  C_WARNING, "°C",  100)
        self.spark_ram  = spark_card(bot_row, "RAM foglaltság (%)",    C_ACCENT2, "%",   100)
        self.spark_freq = spark_card(bot_row, "CPU órajel (MHz)",      C_PURPLE,  "MHz", 5000)

    # ══════════════════════════════════════════
    #  TAB 6 — iGPU MONITOR
    # ══════════════════════════════════════════

    def _build_igpu_tab(self, parent):
        parent.configure(fg_color=C_BG)

        info_bar = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=10, height=72)
        info_bar.pack(fill="x", pady=(0,8))
        info_bar.pack_propagate(False)
        info_i = ctk.CTkFrame(info_bar, fg_color="transparent")
        info_i.pack(fill="both", expand=True, padx=16, pady=10)

        left_i = ctk.CTkFrame(info_i, fg_color="transparent")
        left_i.pack(side="left", fill="y")
        ctk.CTkLabel(left_i, text="ADAPTER",
                     font=("Segoe UI Black", 9), text_color=C_MUTED).pack(anchor="w")
        self.igpu_adapter_lbl = ctk.CTkLabel(left_i, text="Detektálás...",
                                              font=("Segoe UI", 13, "bold"), text_color=C_ACCENT2)
        self.igpu_adapter_lbl.pack(anchor="w")
        self.igpu_driver_lbl = ctk.CTkLabel(left_i, text="Driver: —",
                                             font=("Segoe UI", 10), text_color=C_MUTED)
        self.igpu_driver_lbl.pack(anchor="w")

        ctk.CTkFrame(info_i, fg_color=C_MUTED, width=1).pack(side="left", fill="y", padx=20)

        mid_i = ctk.CTkFrame(info_i, fg_color="transparent")
        mid_i.pack(side="left", fill="y")
        ctk.CTkLabel(mid_i, text="MEMÓRIA KONFIGURÁCIÓ",
                     font=("Segoe UI Black", 9), text_color=C_MUTED).pack(anchor="w")
        self.igpu_mem_cfg_lbl = ctk.CTkLabel(mid_i, text="Detektálás...",
                                              font=("Consolas", 11), text_color=C_TEXT)
        self.igpu_mem_cfg_lbl.pack(anchor="w", pady=2)
        self.igpu_bios_hint_lbl = ctk.CTkLabel(mid_i, text="",
                                                font=("Segoe UI", 10), text_color=C_MUTED)
        self.igpu_bios_hint_lbl.pack(anchor="w")

        right_i = ctk.CTkFrame(info_i, fg_color="transparent")
        right_i.pack(side="right", fill="y")
        ctk.CTkLabel(right_i, text="GPU MEM NYOMÁS",
                     font=("Segoe UI Black", 9), text_color=C_MUTED).pack(anchor="e")
        self.igpu_pressure_badge = ctk.CTkLabel(
            right_i, text="○  DETEKTÁLÁS...",
            font=("Segoe UI", 13, "bold"), text_color=C_MUTED,
            fg_color=C_PANEL, corner_radius=8, padx=14, pady=6
        )
        self.igpu_pressure_badge.pack(anchor="e", pady=4)

        # StatCard-ok
        cards_row = ctk.CTkFrame(parent, fg_color="transparent", height=100)
        cards_row.pack(fill="x", pady=(0,8))
        cards_row.pack_propagate(False)
        self.igpu_stat_ded    = StatCard(cards_row, "Dedikált (használt)", " MB",
                                          max_val=256, warn_at=180, crit_at=220)
        self.igpu_stat_ded.pack(side="left", fill="both", expand=True, padx=(0,5))
        self.igpu_stat_ded_max = StatCard(cards_row, "Dedikált (max)", " MB",
                                           max_val=256, warn_at=999, crit_at=999)
        self.igpu_stat_ded_max.pack(side="left", fill="both", expand=True, padx=(0,5))
        self.igpu_stat_shared = StatCard(cards_row, "Shared (használt)", " MB",
                                          max_val=8192, warn_at=4096, crit_at=6500)
        self.igpu_stat_shared.pack(side="left", fill="both", expand=True, padx=(0,5))
        self.igpu_stat_engine = StatCard(cards_row, "GPU 3D engine", " %",
                                          max_val=100, warn_at=70, crit_at=90)
        self.igpu_stat_engine.pack(side="left", fill="both", expand=True)

        mid_row = ctk.CTkFrame(parent, fg_color="transparent")
        mid_row.pack(fill="both", expand=True, pady=(0,8))

        chart_frame = ctk.CTkFrame(mid_row, fg_color=C_CARD, corner_radius=10)
        chart_frame.pack(side="left", fill="both", expand=True, padx=(0,8))
        chart_hdr = ctk.CTkFrame(chart_frame, fg_color="transparent")
        chart_hdr.pack(fill="x", padx=14, pady=(10,4))
        ctk.CTkLabel(chart_hdr, text="GPU MEMÓRIA ELŐZMÉNY (3 perc)",
                     font=("Segoe UI Black", 11), text_color=C_MUTED).pack(side="left")
        legend = ctk.CTkFrame(chart_hdr, fg_color="transparent")
        legend.pack(side="right")
        ctk.CTkFrame(legend, fg_color=C_ACCENT, width=18, height=3,
                     corner_radius=2).pack(side="left", pady=6)
        ctk.CTkLabel(legend, text=" Shared", font=("Segoe UI", 10),
                     text_color=C_ACCENT).pack(side="left")
        ctk.CTkFrame(legend, fg_color="transparent", width=12).pack(side="left")
        ctk.CTkFrame(legend, fg_color=C_ACCENT2, width=18, height=3,
                     corner_radius=2).pack(side="left", pady=6)
        ctk.CTkLabel(legend, text=" Dedikált", font=("Segoe UI", 10),
                     text_color=C_ACCENT2).pack(side="left")

        self.igpu_sparkline = SparklineChart(chart_frame,
                                             color_primary=C_ACCENT,
                                             color_secondary=C_ACCENT2,
                                             unit="MB", max_val=4096, height=160)
        self.igpu_sparkline.pack(fill="both", expand=True, padx=10, pady=(0,10))

        right_col = ctk.CTkFrame(mid_row, fg_color=C_CARD, corner_radius=10, width=270)
        right_col.pack(side="left", fill="y")
        right_col.pack_propagate(False)
        ctk.CTkLabel(right_col, text="GPU-EVŐK",
                     font=("Segoe UI Black", 11), text_color=C_MUTED
                     ).pack(pady=(12,6), padx=14, anchor="w")
        self.igpu_proc_frame = ctk.CTkScrollableFrame(
            right_col, fg_color="transparent", height=120)
        self.igpu_proc_frame.pack(fill="x", padx=10, pady=(0,8))
        ctk.CTkLabel(right_col, text="MŰVELETEK",
                     font=("Segoe UI Black", 11), text_color=C_MUTED
                     ).pack(pady=(4,6), padx=14, anchor="w")
        self.igpu_opt_btn = ctk.CTkButton(
            right_col, text="🖥  iGPU MEM OPTIMALIZÁLÁS",
            font=("Segoe UI Black", 12),
            fg_color=C_GOLD, hover_color="#CC9A00",
            text_color="#1A1000", height=42, corner_radius=8,
            command=self._on_igpu_optimize
        )
        self.igpu_opt_btn.pack(fill="x", padx=12, pady=(0,6))
        ctk.CTkButton(
            right_col, text="💡  HW gyorsítás letiltása (útmutató)",
            font=("Segoe UI", 11),
            fg_color=C_PANEL, hover_color="#252D40",
            text_color=C_ACCENT2, border_color=C_ACCENT2, border_width=1,
            height=34, corner_radius=8, command=self._show_hw_accel_tips
        ).pack(fill="x", padx=12, pady=(0,6))
        ctk.CTkButton(
            right_col, text="🔧  BIOS DVMT útmutató",
            font=("Segoe UI", 11),
            fg_color=C_PANEL, hover_color="#252D40",
            text_color=C_MUTED, border_color=C_MUTED, border_width=1,
            height=34, corner_radius=8, command=self._show_bios_tips
        ).pack(fill="x", padx=12, pady=(0,6))

        log_frame = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=10, height=130)
        log_frame.pack(fill="x")
        log_frame.pack_propagate(False)
        ctk.CTkLabel(log_frame, text="OPTIMALIZÁLÁSI NAPLÓ",
                     font=("Segoe UI Black", 11), text_color=C_MUTED
                     ).pack(pady=(10,4), padx=16, anchor="w")
        self.igpu_log = LogBox(log_frame)
        self.igpu_log.pack(fill="both", expand=True, padx=12, pady=(0,10))
        self.igpu_log.log("🔷 iGPU Monitor aktív — adatok gyűjtése...")
        self.after(3000, self._refresh_igpu_adapter_info)
        self._igpu_tab_built = True

    # ─────────────────────────────────────────
    #  MONITOR INDÍTÁS
    # ─────────────────────────────────────────

    def _start_monitors(self):
        system_monitor.add_callback(self._on_monitor_update)
        system_monitor.start()
        igpu_monitor.add_callback(self._on_igpu_update)
        igpu_monitor.start()
        hw_monitor.add_callback(self._on_hw_change)
        hw_monitor.start()

    def _on_monitor_update(self, snap: SystemSnapshot):
        self.after(0, self._apply_snapshot, snap)

    def _on_igpu_update(self, snap: IgpuSnapshot):
        self.after(0, self._apply_igpu_snapshot, snap)

    def _on_hw_change(self, power, batt, net, net_name):
        """Tápellátás vagy hálózat változás callback."""
        self.after(0, self._update_hw_badges, power, batt, net, net_name)
        # Auto-boost töltőn
        if power == PowerState.AC_CHARGING and not self._boost_active:
            self.after(0, self._auto_boost_on_charger)

    def _update_hw_badges(self, power, batt, net, net_name):
        # Tápellátás badge
        if power == PowerState.AC_CHARGING:
            p_text = f"⚡ Töltő ({batt}%)" if batt >= 0 else "⚡ Töltő"
            self.power_badge.configure(text=p_text, text_color=C_ACCENT, fg_color="#0A2E1A")
        elif power == PowerState.BATTERY:
            color = C_WARNING if batt < 30 else C_TEXT
            p_text = f"🔋 Akksi ({batt}%)"
            self.power_badge.configure(text=p_text, text_color=color, fg_color=C_CARD)
        else:
            self.power_badge.configure(text="⚡ —", text_color=C_MUTED, fg_color=C_CARD)

        # Hálózat badge
        from modules.hardware_detector import NetworkType
        if net == NetworkType.ETHERNET:
            self.net_badge.configure(text="🔌 Ethernet",
                                      text_color=C_ACCENT, fg_color="#0A2E1A")
        elif net == NetworkType.WIFI:
            self.net_badge.configure(text="📶 Wi-Fi",
                                      text_color=C_GOLD, fg_color="#2E2000")
        else:
            self.net_badge.configure(text="🌐 —", text_color=C_MUTED, fg_color=C_CARD)

    def _auto_boost_on_charger(self):
        """Töltőre csatlakozáskor automatikus boost."""
        if self._boost_active or not self.is_admin:
            return
        self.boost_log.log("\n⚡ Töltő csatlakoztatva — automatikus Boost aktiválás...")
        self._on_boost_click()

    def _apply_snapshot(self, snap: SystemSnapshot):
        self.stat_cpu_pct.update(snap.cpu_percent)
        self.stat_cpu_freq.update(snap.cpu_freq_mhz)
        self.stat_ram_pct.update(snap.ram_percent)
        if snap.cpu_temp_c > 0:
            self.stat_cpu_temp.update(snap.cpu_temp_c)
        else:
            self.stat_cpu_temp.set_na()

        # Monitor tab sparkline-ok
        if hasattr(self, "spark_cpu"):
            from modules.monitor import system_monitor as sm
            self.spark_cpu.update_data(
                [snap.cpu_percent] if not hasattr(sm, '_cpu_hist') else sm.shared_history
                if hasattr(sm, 'shared_history') else [snap.cpu_percent]
            )

        self.ram_total_lbl.configure(text=f"Összes: {snap.ram_total_mb} MB")
        self.ram_used_lbl.configure(
            text=f"Használt: {snap.ram_used_mb} MB ({snap.ram_percent:.0f}%)")
        self.ram_free_lbl.configure(text=f"Szabad: {snap.ram_available_mb} MB")

    def _apply_igpu_snapshot(self, snap: IgpuSnapshot):
        self.stat_igpu_sh.update(snap.shared_used_mb)
        if not self._igpu_tab_built:
            return
        self.igpu_stat_ded.update(snap.dedicated_used_mb)
        self.igpu_stat_shared.update(snap.shared_used_mb)
        self.igpu_stat_engine.update(snap.engine_3d_pct)
        pressure_styles = {
            "OK":       ("●  OK",           C_ACCENT,  "#0A2E1A"),
            "MODERATE": ("●  MÉRSÉKELT",     C_GOLD,    "#2E2000"),
            "HIGH":     ("●  MAGAS",         C_WARNING, "#2E1400"),
            "CRITICAL": ("●  KRITIKUS!",     C_BOOST,   "#2E0010"),
        }
        txt, col, bg = pressure_styles.get(snap.pressure_level, ("○  ?", C_MUTED, C_PANEL))
        self.igpu_pressure_badge.configure(text=txt, text_color=col, fg_color=bg)
        self.igpu_sparkline.update_data(
            igpu_monitor.shared_history, igpu_monitor.dedicated_history)
        for w in self.igpu_proc_frame.winfo_children():
            w.destroy()
        if snap.gpu_hungry_procs:
            for p in snap.gpu_hungry_procs[:6]:
                row = ctk.CTkFrame(self.igpu_proc_frame, fg_color="transparent")
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(row, text=f"⚠ {p['name'][:20]}",
                             font=("Consolas", 10), text_color=C_WARNING,
                             width=155, anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=f"{p['ram_mb']} MB",
                             font=("Consolas", 10), text_color=C_MUTED,
                             anchor="e").pack(side="right")
        else:
            ctk.CTkLabel(self.igpu_proc_frame,
                         text="✓ Nincs GPU-evő folyamat",
                         font=("Segoe UI", 11), text_color=C_ACCENT).pack(anchor="w", pady=4)

    # ─────────────────────────────────────────
    #  HARDVER DETEKTÁLÁS
    # ─────────────────────────────────────────

    def _detect_hardware_async(self):
        self.hw_detect_lbl.configure(text="⏳ Detektálás...", text_color=C_GOLD)
        self.hw_recs_box.clear()
        self.hw_recs_box.log("⏳ Hardware detektálás folyamatban (5-10 mp)...")

        def run():
            hw = detect_hardware()
            self._hw = hw
            self.after(0, self._apply_hardware_profile, hw)

        threading.Thread(target=run, daemon=True).start()

    def _apply_hardware_profile(self, hw: HardwareProfile):
        if not hw.detected:
            self.hw_detect_lbl.configure(text="⚠ Részleges detektálás", text_color=C_WARNING)
        else:
            self.hw_detect_lbl.configure(text="✓ Hardver detektálva", text_color=C_ACCENT)

        # GPU
        self.hw_gpu_name.set(hw.gpu_name, C_ACCENT2)
        self.hw_gpu_type.set(hw.gpu_type.value)
        self.hw_gpu_vram.set(f"{hw.gpu_vram_mb} MB")
        if hw.gpu_shared_mb > 0:
            self.hw_gpu_shared.set(f"{hw.gpu_shared_mb:,} MB ({hw.gpu_shared_mb//1024} GB)")
        # CPU
        self.hw_cpu_name.set(hw.cpu_name, C_ACCENT2)
        cores_str = f"{hw.cpu_cores_p} P-mag"
        if hw.cpu_cores_e > 0:
            cores_str += f" + {hw.cpu_cores_e} E-mag ({hw.cpu_threads} szál)"
        else:
            cores_str += f" ({hw.cpu_threads} szál)"
        self.hw_cpu_cores.set(cores_str)
        if hw.cpu_freq_max_mhz > 0:
            self.hw_cpu_freq.set(f"{hw.cpu_freq_max_mhz:.0f} MHz")
        # RAM
        self.hw_ram_total.set(f"{hw.ram_total_gb} GB ({hw.ram_total_mb:,} MB)", C_ACCENT2)
        # Tápellátás
        self.hw_power.set(hw.power_state.value,
                          C_ACCENT if hw.power_state == PowerState.AC_CHARGING else C_WARNING)
        if hw.battery_pct >= 0:
            self.hw_battery.set(f"{hw.battery_pct}%",
                                C_ACCENT if hw.battery_pct > 50 else C_WARNING)
        else:
            self.hw_battery.set("Nincs akkumulátor")
        # Hálózat
        self.hw_network.set(hw.network_type.value,
                            C_ACCENT if hw.network_type == NetworkType.ETHERNET else C_GOLD)
        self.hw_net_name.set(hw.network_name or "—")
        # Windows
        self.hw_win_ver.set(hw.windows_version)

        # Badge-ek frissítése
        self._update_hw_badges(hw.power_state, hw.battery_pct,
                                hw.network_type, hw.network_name)

        # iGPU adapter info frissítése
        if igpu_monitor.adapter_info:
            self._refresh_igpu_adapter_info()

        # Javaslatok
        self.hw_recs_box.clear()
        recs = get_recommendations(hw)
        for rec in recs:
            self.hw_recs_box.log(rec)
        if not recs:
            self.hw_recs_box.log("✓ Minden hardver konfiguráció optimálisnak tűnik!")

    def _refresh_igpu_adapter_info(self):
        info = igpu_monitor.adapter_info
        if not info:
            self.after(2000, self._refresh_igpu_adapter_info)
            return
        self.igpu_adapter_lbl.configure(text=info.name)
        self.igpu_driver_lbl.configure(
            text=f"Driver: {info.driver_version}  |  {info.driver_date}")
        self.igpu_mem_cfg_lbl.configure(
            text=f"Dedikált: {info.dedicated_max_mb} MB  |  Shared max: {info.shared_max_mb:,} MB")
        if info.dedicated_max_mb <= 64:
            self.igpu_bios_hint_lbl.configure(
                text=f"DVMT: {info.dedicated_max_mb} MB — ⚠ Növeld 256MB-ra a BIOS-ban!",
                text_color=C_WARNING)
        elif info.dedicated_max_mb <= 128:
            self.igpu_bios_hint_lbl.configure(
                text=f"DVMT: {info.dedicated_max_mb} MB — Elfogadható, 256MB jobb lenne",
                text_color=C_GOLD)
        else:
            self.igpu_bios_hint_lbl.configure(
                text=f"DVMT: {info.dedicated_max_mb} MB — ✓ Optimális",
                text_color=C_ACCENT)
        self.igpu_stat_ded.max_val = info.dedicated_max_mb
        self.igpu_stat_ded_max.update(info.dedicated_max_mb)
        self.igpu_stat_shared.max_val = info.shared_max_mb
        self.igpu_sparkline.max_val = max(info.shared_max_mb // 4, 512)
        if info.detected:
            self.igpu_log.log(f"✓ Adapter: {info.name}")
            self.igpu_log.log(f"   Dedikált: {info.dedicated_max_mb} MB  Shared: {info.shared_max_mb:,} MB")

    # ─────────────────────────────────────────
    #  ESEMÉNYKEZELŐK
    # ─────────────────────────────────────────

    def _on_boost_profile_change(self, display_name: str):
        all_p = profile_manager.all_profiles()
        for key, prof in all_p.items():
            if f"{prof.icon}  {prof.name}" == display_name:
                profile_manager.set_active(key)
                self.boost_profile_desc.configure(text=prof.description)
                self._update_boost_profile_details(prof)
                break

    def _on_boost_click(self):
        if not self.is_admin:
            self.boost_log.log("❌ Admin jogok szükségesek!")
            return
        hw = self._hw
        if hw is None:
            self.boost_log.log("⏳ Hardver detektálás folyamatban, kérlek várj...")
            return
        _, profile = profile_manager.get_active()
        self.boost_btn.configure(state="disabled", text="⏳  Dolgozom...")
        self.boost_badge_lbl.configure(text="⏳  FOLYAMATBAN",
                                        text_color=C_GOLD, fg_color="#2E2000")

        def run():
            apply_boost(hw, profile,
                        callback=lambda m: self.after(0, self.boost_log.log, m))
            self.after(0, self._boost_done)

        threading.Thread(target=run, daemon=True).start()

    def _boost_done(self):
        self._boost_active = True
        _, profile = profile_manager.get_active()
        self.boost_btn.configure(state="normal", text="⚡  BOOST AKTIVÁLÁS")
        self.boost_badge_lbl.configure(
            text=f"●  {profile.name.upper()} AKTÍV",
            text_color=profile.color_accent, fg_color="#0A2E1A")

    def _on_restore_click(self):
        if not self.is_admin:
            self.boost_log.log("❌ Admin jogok szükségesek!")
            return
        self.restore_btn.configure(state="disabled", text="⏳  Visszaállítás...")

        def run():
            restore_original(callback=lambda m: self.after(0, self.boost_log.log, m))
            self.after(0, self._restore_done)

        threading.Thread(target=run, daemon=True).start()

    def _restore_done(self):
        self._boost_active = False
        self.restore_btn.configure(state="normal", text="↩  VISSZAÁLLÍTÁS")
        self.boost_badge_lbl.configure(text="○  INAKTÍV",
                                        text_color=C_MUTED, fg_color=C_PANEL)

    def _quick_ram_clean(self):
        def run():
            self.boost_log.log("\n🧹 RAM tisztítás...")
            empty_working_sets(callback=lambda m: self.after(0, self.boost_log.log, m))
        threading.Thread(target=run, daemon=True).start()

    def _clean_ram(self):
        def run():
            snap = system_monitor.last_snapshot
            before = snap.ram_available_mb if snap else 0
            self.ram_log.log(f"🧹 Working Set ürítés (szabad: {before} MB)...")
            empty_working_sets(callback=lambda m: self.after(0, self.ram_log.log, m))
            time.sleep(0.8)
            after = get_ram_info()
            freed = after["available_mb"] - before
            self.after(0, self.ram_log.log,
                       f"✓ Szabad most: {after['available_mb']} MB  (+~{max(0,freed)} MB)")
            self.after(0, self._refresh_proc_list)
        threading.Thread(target=run, daemon=True).start()

    def _set_process_priority(self):
        def run():
            self.ram_log.log("\n🎮 Folyamat prioritás beállítása...")
            boost_cs2_priority(callback=lambda m: self.after(0, self.ram_log.log, m))
        threading.Thread(target=run, daemon=True).start()

    def _refresh_proc_list(self):
        procs = get_top_ram_consumers(8)
        for i, (nl, ml) in enumerate(self.proc_labels):
            if i < len(procs):
                p = procs[i]
                n = p["name"][:23] if len(p["name"]) > 23 else p["name"]
                nl.configure(text=n)
                ml.configure(text=f"{p['mem_mb']} MB")
            else:
                nl.configure(text="")
                ml.configure(text="")

    def _refresh_ram_display(self):
        info = get_ram_info()
        self.ram_total_lbl.configure(text=f"Összes: {info['total_mb']} MB")
        self.ram_used_lbl.configure(
            text=f"Használt: {info['used_mb']} MB ({info['percent']:.0f}%)")
        self.ram_free_lbl.configure(text=f"Szabad: {info['available_mb']} MB")

    def _on_igpu_optimize(self):
        self.igpu_opt_btn.configure(state="disabled", text="⏳  Optimalizálás...")

        def run():
            info = igpu_monitor.adapter_info
            if info:
                optimize_igpu_memory(
                    info, callback=lambda m: self.after(0, self.igpu_log.log, m))
            self.after(0, self.igpu_opt_btn.configure,
                       {"state": "normal", "text": "🖥  iGPU MEM OPTIMALIZÁLÁS"})

        threading.Thread(target=run, daemon=True).start()

    def _show_hw_accel_tips(self):
        self.igpu_log.log("\n💡 HW gyorsítás letiltása:")
        for tip in [
            "Chrome/Edge: Beállítások → Rendszer → Hardveres gyorsítás KI",
            "Discord: Beállítások → Megjelenés → Hardveres gyorsítás KI",
            "Firefox: about:config → layers.acceleration.force-enabled = false",
            "Teams: Beállítások → Általános → GPU hardver gyorsítás KI",
        ]:
            self.igpu_log.log(f"  → {tip}")

    def _show_bios_tips(self):
        self.igpu_log.log("\n🔧 BIOS DVMT növelés:")
        for tip in [
            "1. Újraindítás → F2/Del/F10 a BIOS-ba",
            "2. Advanced → System Agent Configuration",
            "3. Graphics Configuration → DVMT Pre-Allocated",
            "4. Módosítsd: 64M/128M → 256M",
            "5. Save & Exit (F10)",
        ]:
            self.igpu_log.log(f"  {tip}")

    # ══════════════════════════════════════════
    #  TAB 7 — REGISTRY OPTIMALIZÁLÓ
    # ══════════════════════════════════════════

    def _build_registry_tab(self, parent):
        parent.configure(fg_color=C_BG)

        # ── Felső: státusz + gombok ──
        top = ctk.CTkFrame(parent, fg_color=C_CARD, corner_radius=10, height=80)
        top.pack(fill="x", pady=(0, 8))
        top.pack_propagate(False)
        top_i = ctk.CTkFrame(top, fg_color="transparent")
        top_i.pack(fill="both", expand=True, padx=16, pady=10)

        ctk.CTkLabel(top_i, text="REGISTRY JÁTÉK OPTIMALIZÁLÓ",
                     font=("Segoe UI Black", 12), text_color=C_MUTED).pack(side="left")

        self.reg_status_badge = ctk.CTkLabel(
            top_i, text="○  NINCS ALKALMAZVA",
            font=("Segoe UI", 12, "bold"), text_color=C_MUTED,
            fg_color=C_PANEL, corner_radius=6, padx=12, pady=5
        )
        self.reg_status_badge.pack(side="right", padx=(8, 0))

        self.reg_refresh_btn = ctk.CTkButton(
            top_i, text="↻  Állapot frissítés",
            font=("Segoe UI", 11), fg_color=C_PANEL, hover_color="#252D40",
            text_color=C_TEXT, border_color=C_MUTED, border_width=1,
            height=32, corner_radius=6, width=150,
            command=self._refresh_registry_status
        )
        self.reg_refresh_btn.pack(side="right")

        # ── Közép: bal tweak lista, jobb log ──
        mid = ctk.CTkFrame(parent, fg_color="transparent")
        mid.pack(fill="both", expand=True, pady=(0, 8))

        # Bal: tweak kapcsolók
        left = ctk.CTkFrame(mid, fg_color=C_CARD, corner_radius=10, width=300)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="TWEAKEK — MIT ALKALMAZZON",
                     font=("Segoe UI Black", 10), text_color=C_MUTED
                     ).pack(pady=(14, 8), padx=16, anchor="w")

        # Tweak toggle-ok + státusz indikátorok
        # Formátum: (attribútum neve, megjelenítési név, leírás, default)
        TWEAKS = [
            ("reg_tw_scheduling", "Játék ütemezési prioritás",
             "Scheduling: Medium→High · GPU Priority: 8→18 · SFIO: High",
             True, "#FF2D55"),    # piros = nagy hatás

            ("reg_tw_sysprof",    "Rendszer profil (MMCSS)",
             "SystemResponsiveness: 20→0 · NetworkThrottling letiltva",
             True, "#FF2D55"),

            ("reg_tw_win32",      "Win32 előtér CPU boost",
             "Win32PrioritySeparation: 0x18→0x26 (játék kap max CPU időt)",
             True, "#FF2D55"),

            ("reg_tw_gamemode",   "Windows Game Mode",
             "AutoGameModeEnabled · AllowAutoGameMode bekapcsolás",
             True, "#00C8FF"),

            ("reg_tw_hags",       "HAGS — GPU ütemezés ⚡",
             "HwSchMode: 1→2 · ÚJRAINDÍTÁS SZÜKSÉGES a hatáshoz!",
             True, "#FFC147"),

            ("reg_tw_gamebar",    "Xbox Game Bar letiltás",
             "AppCaptureEnabled: 1→0 · AllowGameDVR: 1→0 (+2-5% FPS)",
             True, "#00C8FF"),

            ("reg_tw_nagle",      "Nagle-algoritmus letiltás",
             "TCPNoDelay: 1 · TcpAckFrequency: 1  (-5-15ms latencia)",
             True, "#9B59FF"),

            ("reg_tw_mouse",      "Egér input latencia ⚡",
             "MouseDataQueueSize: 100→20 · ÚJRAINDÍTÁS szükséges!",
             False, "#4A5568"),
        ]

        self._reg_tweak_vars   = {}
        self._reg_status_rows  = {}

        scroll = ctk.CTkScrollableFrame(left, fg_color="transparent",
                                         scrollbar_button_color=C_MUTED)
        scroll.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        for attr, name, desc, default, color in TWEAKS:
            var = ctk.BooleanVar(value=default)
            self._reg_tweak_vars[attr] = var

            row_outer = ctk.CTkFrame(scroll, fg_color="#0D1117", corner_radius=8)
            row_outer.pack(fill="x", padx=8, pady=3)

            # Fejléc sor: toggle + státusz körök
            row_hdr = ctk.CTkFrame(row_outer, fg_color="transparent")
            row_hdr.pack(fill="x", padx=10, pady=(8, 2))

            ctk.CTkSwitch(
                row_hdr, text=name, variable=var,
                progress_color=color, width=44,
                font=("Segoe UI", 11, "bold"), text_color=C_TEXT
            ).pack(side="left")

            # Státusz kör (zöld = aktív, szürke = nem)
            status_dot = ctk.CTkLabel(
                row_hdr, text="○",
                font=("Segoe UI", 14), text_color=C_MUTED
            )
            status_dot.pack(side="right")
            self._reg_status_rows[attr] = status_dot

            # Leírás
            ctk.CTkLabel(
                row_outer, text=desc,
                font=("Segoe UI", 9), text_color=C_MUTED,
                wraplength=240, justify="left"
            ).pack(padx=10, pady=(0, 8), anchor="w")

        # Alsó gombok
        btn_f = ctk.CTkFrame(left, fg_color="transparent")
        btn_f.pack(fill="x", padx=12, pady=(4, 12))

        self.reg_apply_btn = ctk.CTkButton(
            btn_f, text="🔑  TWEAKEK ALKALMAZÁSA",
            font=("Segoe UI Black", 12),
            fg_color=C_BOOST, hover_color="#CC2244",
            text_color="white", height=44, corner_radius=8,
            command=self._on_reg_apply
        )
        self.reg_apply_btn.pack(fill="x", pady=(0, 4))

        self.reg_restore_btn = ctk.CTkButton(
            btn_f, text="↩  REGISTRY VISSZAÁLLÍTÁS",
            font=("Segoe UI", 11),
            fg_color=C_PANEL, hover_color="#252D40",
            text_color=C_TEXT, border_color=C_MUTED, border_width=1,
            height=36, corner_radius=8,
            command=self._on_reg_restore
        )
        self.reg_restore_btn.pack(fill="x")

        # Jobb: részletes log + élő állapot tábla
        right = ctk.CTkFrame(mid, fg_color=C_CARD, corner_radius=10)
        right.pack(side="left", fill="both", expand=True)

        # Élő állapot tábla (felül)
        status_frame = ctk.CTkFrame(right, fg_color="#090B10", corner_radius=8)
        status_frame.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(status_frame, text="JELENLEGI REGISTRY ÁLLAPOT",
                     font=("Segoe UI Black", 9), text_color=C_MUTED
                     ).pack(pady=(8, 4), padx=12, anchor="w")

        status_grid = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_grid.pack(fill="x", padx=12, pady=(0, 8))

        STATUS_ITEMS = [
            ("Scheduling Category",    "scheduling_category", "High"),
            ("GPU Priority",           "gpu_priority",         18),
            ("SystemResponsiveness",   "system_responsiveness", 0),
            ("Win32PrioritySep.",      "win32_priority_ok",    True),
            ("HAGS",                   "hags",                 "Bekapcsolva"),
            ("Windows Game Mode",      "game_mode",            "Aktív"),
            ("Xbox Game Bar",          "gamebar_disabled",     True),
            ("Nagle-algoritmus",       "nagle_disabled",       True),
        ]
        self._reg_live_labels = {}

        for i, (label, key, good_val) in enumerate(STATUS_ITEMS):
            col = i % 2
            row = i // 2
            cell = ctk.CTkFrame(status_grid, fg_color="transparent")
            cell.grid(row=row, column=col, sticky="ew", padx=4, pady=1)
            status_grid.columnconfigure(col, weight=1)

            ctk.CTkLabel(cell, text=f"{label}:",
                         font=("Segoe UI", 9), text_color=C_MUTED,
                         width=130, anchor="w").pack(side="left")
            val_lbl = ctk.CTkLabel(cell, text="—",
                                   font=("Consolas", 9), text_color=C_MUTED,
                                   anchor="w")
            val_lbl.pack(side="left")
            self._reg_live_labels[key] = (val_lbl, good_val)

        # Log panel
        ctk.CTkLabel(right, text="MŰVELETI NAPLÓ",
                     font=("Segoe UI Black", 11), text_color=C_MUTED
                     ).pack(pady=(4, 4), padx=16, anchor="w")
        self.reg_log = LogBox(right)
        self.reg_log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.reg_log.log("🔑 Registry Optimalizáló készen áll.")
        self.reg_log.log("")
        self.reg_log.log("Mit csinál minden tweak:")
        self.reg_log.log("  🔴 Játék prioritás  — MMCSS Games task: Scheduling=High,")
        self.reg_log.log("                        GPU Priority=18, SFIO=High (+3-10% FPS)")
        self.reg_log.log("  🔴 MMCSS rendszer   — SystemResponsiveness 20→0")
        self.reg_log.log("                        (100% CPU a játéknak, nem 80%)")
        self.reg_log.log("  🔴 Win32 CPU boost  — előtér folyamat max prioritás (+3-8%)")
        self.reg_log.log("  🔵 Game Mode        — Windows automatikus prioritizálás")
        self.reg_log.log("  🟡 HAGS             — GPU ütemezés hardveren (RESTART kell!)")
        self.reg_log.log("  🔵 Game Bar         — Xbox overlay kikapcsolás (+2-5%)")
        self.reg_log.log("  🟣 Nagle            — TCP azonnali csomag küldés (-5-15ms)")
        self.reg_log.log("  ⚪ Egér latencia    — input buffer csökkentés (RESTART kell!)")
        self.reg_log.log("")
        self.reg_log.log("► Válaszd ki a kívánt tweakeket és nyomd meg az ALKALMAZÁS gombot.")

        # Kezdeti állapot betöltése
        self.after(500, self._refresh_registry_status)

    # ─── Registry eseménykezelők ─────────────

    def _refresh_registry_status(self):
        """Lekérdezi a jelenlegi registry állapotot és frissíti a GUI-t."""
        def run():
            try:
                status = get_current_registry_status()
                self.after(0, self._apply_registry_status_to_gui, status)
            except Exception as e:
                self.after(0, self.reg_log.log, f"⚠ Állapot lekérdezési hiba: {e}")

        threading.Thread(target=run, daemon=True).start()

    def _apply_registry_status_to_gui(self, status: dict):
        """Registry státusz adatok kiírása a GUI-ba."""

        # Élő állapot tábla frissítése
        checks = {
            "scheduling_category": (
                status.get("scheduling_category", "—"),
                status.get("scheduling_category") == "High"
            ),
            "gpu_priority": (
                str(status.get("gpu_priority", "—")),
                status.get("gpu_priority") == 18
            ),
            "system_responsiveness": (
                str(status.get("system_responsiveness", "—")),
                status.get("system_responsiveness") == 0
            ),
            "win32_priority_ok": (
                status.get("win32_priority", "—"),
                status.get("win32_priority_ok", False)
            ),
            "hags": (
                status.get("hags", "—"),
                status.get("hags") == "Bekapcsolva"
            ),
            "game_mode": (
                status.get("game_mode", "—"),
                status.get("game_mode") == "Aktív"
            ),
            "gamebar_disabled": (
                "Letiltva" if status.get("gamebar_disabled") else "Aktív",
                status.get("gamebar_disabled", False)
            ),
            "nagle_disabled": (
                "Letiltva" if status.get("nagle_disabled") else "Aktív",
                status.get("nagle_disabled", False)
            ),
        }

        all_good = True
        for key, (val_lbl, _) in self._reg_live_labels.items():
            if key in checks:
                display, is_good = checks[key]
                color = C_ACCENT if is_good else C_WARNING
                val_lbl.configure(text=str(display), text_color=color)
                if not is_good:
                    all_good = False

        # Státusz badge frissítése
        if all_good:
            self.reg_status_badge.configure(
                text="●  MINDEN TWEAK AKTÍV",
                text_color=C_ACCENT, fg_color="#0A2E1A"
            )
        elif status.get("snapshot_exists"):
            self.reg_status_badge.configure(
                text="●  RÉSZBEN ALKALMAZVA",
                text_color=C_GOLD, fg_color="#2E2000"
            )
        else:
            self.reg_status_badge.configure(
                text="○  NINCS ALKALMAZVA",
                text_color=C_MUTED, fg_color=C_PANEL
            )

        # Tweak toggle státusz körök frissítése
        tweak_key_map = {
            "reg_tw_scheduling": checks["scheduling_category"][1],
            "reg_tw_sysprof":    checks["system_responsiveness"][1],
            "reg_tw_win32":      checks["win32_priority_ok"][1],
            "reg_tw_gamemode":   checks["game_mode"][1],
            "reg_tw_hags":       checks["hags"][1],
            "reg_tw_gamebar":    checks["gamebar_disabled"][1],
            "reg_tw_nagle":      checks["nagle_disabled"][1],
            "reg_tw_mouse":      False,  # mindig manuálisan ellenőrzendő
        }
        for attr, is_active in tweak_key_map.items():
            dot = self._reg_status_rows.get(attr)
            if dot:
                dot.configure(
                    text="●" if is_active else "○",
                    text_color=C_ACCENT if is_active else C_MUTED
                )

    def _on_reg_apply(self):
        if not self.is_admin:
            self.reg_log.log("❌ Admin jogok szükségesek!")
            return

        # Config összeállítása a toggle-ok alapján
        config = RegistryTweakConfig(
            game_scheduling = self._reg_tweak_vars["reg_tw_scheduling"].get(),
            system_profile  = self._reg_tweak_vars["reg_tw_sysprof"].get(),
            win32_priority  = self._reg_tweak_vars["reg_tw_win32"].get(),
            hags            = self._reg_tweak_vars["reg_tw_hags"].get(),
            game_mode       = self._reg_tweak_vars["reg_tw_gamemode"].get(),
            disable_gamebar = self._reg_tweak_vars["reg_tw_gamebar"].get(),
            nagle           = self._reg_tweak_vars["reg_tw_nagle"].get(),
            mouse_latency   = self._reg_tweak_vars["reg_tw_mouse"].get(),
        )

        self.reg_apply_btn.configure(state="disabled", text="⏳  Alkalmazás...")
        self.reg_log.log("\n" + "─" * 52)
        self.reg_log.log("🔑 Registry tweakek alkalmazása...")

        def run():
            log = apply_registry_tweaks(
                config,
                callback=lambda m: self.after(0, self.reg_log.log, m)
            )
            self.after(0, self._on_reg_apply_done)

        threading.Thread(target=run, daemon=True).start()

    def _on_reg_apply_done(self):
        self.reg_apply_btn.configure(
            state="normal", text="🔑  TWEAKEK ALKALMAZÁSA")
        self._refresh_registry_status()

    def _on_reg_restore(self):
        if not self.is_admin:
            self.reg_log.log("❌ Admin jogok szükségesek!")
            return

        self.reg_restore_btn.configure(state="disabled", text="⏳  Visszaállítás...")
        self.reg_log.log("\n" + "─" * 52)

        def run():
            restore_registry_tweaks(
                callback=lambda m: self.after(0, self.reg_log.log, m)
            )
            self.after(0, self._on_reg_restore_done)

        threading.Thread(target=run, daemon=True).start()

    def _on_reg_restore_done(self):
        self.reg_restore_btn.configure(
            state="normal", text="↩  REGISTRY VISSZAÁLLÍTÁS")
        self._refresh_registry_status()

    def destroy(self):
        system_monitor.stop()
        igpu_monitor.stop()
        hw_monitor.stop()
        super().destroy()
