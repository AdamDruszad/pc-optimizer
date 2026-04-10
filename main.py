"""
main.py  —  GameBooster v2.1
Belépési pont — Python script ÉS PyInstaller .exe kompatibilis.

PyInstaller futáskor a sys.frozen attribútum True,
és a sys._MEIPASS tartalmazza a kicsomagolt fájlok mappáját.
"""
import sys
import os
import ctypes
import logging


def get_base_dir() -> str:
    """
    Visszaadja az alkalmazás gyökérmappáját.
    - Python script: a main.py könyvtára
    - PyInstaller .exe: a _MEIPASS ideiglenes mappa
    """
    if getattr(sys, "frozen", False):
        # PyInstaller bundle — kicsomagolt fájlok helye
        return sys._MEIPASS
    else:
        # Normál Python futtatás
        return os.path.dirname(os.path.abspath(__file__))


def get_app_dir() -> str:
    """
    Az írható alkalmazás mappa (log, profilok, backup fájlok).
    .exe esetén az .exe melletti mappa, nem a temp _MEIPASS.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def setup_logging(app_dir: str):
    """Logging beállítása — az .exe melletti mappába ír."""
    log_file = os.path.join(app_dir, "gamebooster.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ]
    )


def setup_paths(base_dir: str, app_dir: str):
    """
    Beállítja a Python keresési útvonalakat.
    base_dir: ahol a modulok vannak (frozen: _MEIPASS)
    app_dir:  ahol az írható fájlok lesznek (log, profil, backup)
    """
    # Modulok elérése
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    # Írható mappák létrehozása az app_dir-ben
    for folder in ["profiles", "utils"]:
        p = os.path.join(app_dir, folder)
        os.makedirs(p, exist_ok=True)

    # Az app_dir-t is hozzáadjuk a path-hoz ha különbözik
    if app_dir != base_dir and app_dir not in sys.path:
        sys.path.insert(0, app_dir)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def request_admin() -> bool:
    """
    UAC prompt megjelenítése — újraindítja az alkalmazást admin jogokkal.
    Visszaad True-t ha a kérés elindult (az aktuális példány kilép).
    """
    try:
        if getattr(sys, "frozen", False):
            exe = sys.executable
            params = " ".join(f'"{a}"' for a in sys.argv[1:])
        else:
            exe = sys.executable
            params = " ".join(f'"{a}"' for a in sys.argv)

        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, None, 1
        )
        return int(ret) > 32
    except Exception:
        return False


def main():
    base_dir = get_base_dir()
    app_dir  = get_app_dir()

    setup_logging(app_dir)
    setup_paths(base_dir, app_dir)

    logger = logging.getLogger("GameBooster")
    logger.info("=" * 55)
    logger.info("GameBooster v2.1 indul...")
    logger.info(f"Python:   {sys.version.split()[0]}")
    logger.info(f"Frozen:   {getattr(sys, 'frozen', False)}")
    logger.info(f"base_dir: {base_dir}")
    logger.info(f"app_dir:  {app_dir}")
    logger.info(f"Admin:    {is_admin()}")

    try:
        # Az app_dir-t átadjuk a GUI-nak hogy írható helyre mentsen
        from gui.app import GameBoosterApp
        app = GameBoosterApp(app_dir=app_dir)
        app.mainloop()

    except ImportError as e:
        logger.critical(f"Hiányzó könyvtár: {e}")
        import tkinter.messagebox as mb
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        mb.showerror(
            "GameBooster — Hiányzó könyvtár",
            f"Hiányzó modul: {e}\n\n"
            "Telepítsd a szükséges csomagokat:\n"
            "pip install customtkinter psutil"
        )
        root.destroy()
        sys.exit(1)

    except Exception as e:
        logger.critical(f"Kritikus hiba: {e}", exc_info=True)
        import tkinter.messagebox as mb
        import tkinter as tk
        try:
            root = tk.Tk()
            root.withdraw()
            mb.showerror(
                "GameBooster — Kritikus hiba",
                f"Váratlan hiba:\n{e}\n\n"
                f"Részletek: {app_dir}\\gamebooster.log"
            )
            root.destroy()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
