"""Smaragd paletta sötét és világos változattal, valamint a közös formázók.

A szövegpárok WCAG AA kontrasztját a tests/test_ui_theme.py ellenőrzi.
"""
import sys
from pathlib import Path

from PySide6.QtGui import QColor
from qfluentwidgets import Theme, isDarkTheme, qconfig, setTheme, setThemeColor

DARK = {
    "bg": "#0B1512", "surface": "#12231D", "surface_alt": "#162B24", "border": "#23473B",
    "accent": "#10B981", "accent_hi": "#34D399",
    "text": "#F0FDF4", "muted": "#A7F3D0", "subtle": "#94B8A8",
    # A hős panel fordított felület: sötét témában világos menta
    "hero": "#E8FBF1", "hero_text": "#06281E", "hero_muted": "#1E4D3B", "hero_link": "#047857",
    "hero_track": "#B7E4CF",
    "success": "#34D399", "warning": "#FBBF24", "danger": "#F87171", "on_status": "#06281E",
}
LIGHT = {
    "bg": "#F4FBF7", "surface": "#FFFFFF", "surface_alt": "#ECFDF5", "border": "#A7F3D0",
    "accent": "#047857", "accent_hi": "#059669",
    "text": "#06281E", "muted": "#1E4D3B", "subtle": "#3F6B5A",
    # Világos témában a hős panel mély fenyőzöld
    "hero": "#0F2E24", "hero_text": "#F0FDF4", "hero_muted": "#A7F3D0", "hero_link": "#6EE7B7",
    "hero_track": "#2C5A4B",
    "success": "#047857", "warning": "#B45309", "danger": "#DC2626", "on_status": "#FFFFFF",
}

SOURCE_LABELS = {
    "tweaks": "Játékbeállítások", "services": "Szolgáltatások", "startup": "Automatikus indítás",
    "game_mode": "Játék mód", "network": "Hálózat", "gpu_pref": "GPU-választás", "v2": "Régi verzió (v2)",
}

# Az alkalmazásikon: a PyInstaller-csomagban a _MEIPASS alatt, forrásból a repó gyökerében
APP_ICON = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets" / "icon.ico"


def tok(name: str) -> QColor:
    """A jelenlegi témához tartozó szín."""
    return QColor((DARK if isDarkTheme() else LIGHT)[name])


def pair(name: str) -> tuple[QColor, QColor]:
    """(világos, sötét) pár a qfluentwidgets setTextColor/InfoBadge.custom sorrendjében."""
    return QColor(LIGHT[name]), QColor(DARK[name])


def _apply_accent() -> None:
    setThemeColor((DARK if isDarkTheme() else LIGHT)["accent"])


def init_theme() -> None:
    """Az OS témáját követi; az akcentus témánként más, hogy a gombfelirat kontrasztja AA legyen."""
    setTheme(Theme.AUTO)
    _apply_accent()
    qconfig.themeChanged.connect(lambda _: _apply_accent())


def toggle_theme() -> None:
    setTheme(Theme.LIGHT if isDarkTheme() else Theme.DARK)


def fmt_num(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{fmt_num(n, 0 if unit == 'B' else 1)} {unit}"
        n /= 1024
    return ""
