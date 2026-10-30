"""GameBooster belépési pont: forrásból (`python main.py`) és a PyInstaller .exe-ből is."""
import logging
import sys
from logging.handlers import RotatingFileHandler


def main() -> None:
    from gamebooster import __version__
    from gamebooster.core import storage, winapi

    log_file = storage.data_dir() / "gamebooster.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")],
    )
    log = logging.getLogger("gamebooster")
    log.info("GameBooster %s indul (Python %s, admin: %s)",
             __version__, sys.version.split()[0], winapi.is_admin())

    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    try:
        from gamebooster.ui.main_window import MainWindow
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        log.critical("Kritikus hiba", exc_info=True)
        from qfluentwidgets import MessageBox
        MessageBox("GameBooster", f"Váratlan hiba: {e}\n\nRészletek: {log_file}", None).exec()
        raise


if __name__ == "__main__":
    main()
