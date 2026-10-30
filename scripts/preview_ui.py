"""Felület-előnézet: végiglépked a fő nézeteken, a végén az Áttekintésről képet ment, majd kilép.

    python scripts\\preview_ui.py [kimenet.png] [--theme dark|light]

Csak olvas, módosítást nem alkalmaz. A valódi adatmappát a LOCALAPPDATA átirányításával lehet kímélni.
"""
import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gamebooster.ui.main_window import MainWindow

STEP_MS = 700


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default="refined_green_preview.png")
    parser.add_argument("--theme", choices=("dark", "light"))
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = MainWindow()
    if args.theme:
        setTheme(Theme.DARK if args.theme == "dark" else Theme.LIGHT)
    window.resize(1280, 800)
    window.show()

    keys = list(window.pages)
    for i, key in enumerate(keys, 1):
        QTimer.singleShot(i * STEP_MS, lambda k=key: window.show_page(k))

    def capture() -> None:
        window.grab().save(args.out)
        print(Path(args.out).resolve())
        window.close()

    QTimer.singleShot((len(keys) + 1) * STEP_MS, lambda: window.show_page("dashboard"))
    QTimer.singleShot((len(keys) + 2) * STEP_MS, capture)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
