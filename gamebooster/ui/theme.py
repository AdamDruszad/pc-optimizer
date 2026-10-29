"""Színek, betűk és ikonok egy helyen. A widgetek csak ezeket a tokeneket használják."""
import tkinter.font as tkfont

import customtkinter as ctk

BG = "#0F1115"
SURFACE = "#171A21"
SURFACE_2 = "#1F232C"
BORDER = "#2A2F3A"
TEXT = "#E6E9EF"
MUTED = "#9AA3B2"        # kb. 6,8:1 a SURFACE-en
ACCENT = "#3DDC97"
ACCENT_HOVER = "#33B97F"
ON_ACCENT = "#0B1A13"
WARNING = "#F5B84B"
DANGER = "#F2665E"
DANGER_HOVER = "#D2554E"
INFO = "#5AB0F2"
SOURCE_LABELS = {
    "tweaks": "Tweakek", "services": "Szolgáltatások", "startup": "Indítópult",
    "game_mode": "Játék mód", "network": "Hálózat", "gpu_pref": "GPU-választás", "v2": "Régi verzió (v2)",
}
KIND_COLORS = {"success": ACCENT, "warning": WARNING, "danger": DANGER, "info": INFO}

# Segoe Fluent Icons (Windows 11) / Segoe MDL2 Assets (Windows 10) kódpontjai
ICONS = {
    "home": "\uE80F", "game": "\uE7FC", "clean": "\uE74D", "startup": "\uE768",
    "services": "\uE912", "tweaks": "\uE90F", "network": "\uE774", "monitor": "\uE9D9",
    "history": "\uE81C", "shield": "\uEA18", "info": "\uE946", "warning": "\uE7BA",
    "success": "\uE73E", "danger": "\uE783", "undo": "\uE7A7", "refresh": "\uE72C",
}

_families = {"ui": "Segoe UI", "mono": "Consolas", "icon": "Segoe MDL2 Assets"}


def init(root) -> None:
    available = set(tkfont.families(root))
    if "Segoe UI Variable Text" in available:
        _families["ui"] = "Segoe UI Variable Text"
    if "Cascadia Mono" in available:
        _families["mono"] = "Cascadia Mono"
    if "Segoe Fluent Icons" in available:
        _families["icon"] = "Segoe Fluent Icons"
    ctk.set_appearance_mode("dark")


def font(size: int = 14, weight: str = "normal", mono: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(_families["mono" if mono else "ui"], size, weight)


def icon_font(size: int = 16) -> ctk.CTkFont:
    return ctk.CTkFont(_families["icon"], size)


def fmt_num(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{fmt_num(n, 0 if unit == 'B' else 1)} {unit}"
        n /= 1024
    return ""
