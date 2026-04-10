"""
profile_manager.py  —  GameBooster v2.0
Profil kezelő: beépített + egyéni profilok JSON tárolással.

Minden profil egy teljes snapshot:
  - Mely Windows szolgáltatások álljanak le
  - Energiaséma
  - RAM tisztítás erőssége
  - Process prioritás beállítások
  - Monitoring intervallum
  - Leírás és ikon
"""

import json
import os
import copy
import logging
from dataclasses import dataclass, field, asdict
from typing import Any

logger = logging.getLogger(__name__)


def _get_profiles_file() -> str:
    """Profil fájl útvonal — app_paths-ból ha elérhető, különben default."""
    try:
        from gui.app_paths import custom_profiles
        return custom_profiles()
    except Exception:
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "profiles", "custom_profiles.json"
        )


def _get_active_file() -> str:
    try:
        from gui.app_paths import active_profile
        return active_profile()
    except Exception:
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "profiles", "active_profile.json"
        )


# Kompatibilitás — régi kód ezt importálja
PROFILES_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "profiles")
os.makedirs(PROFILES_DIR, exist_ok=True)


# ─────────────────────────────────────────────
#  PROFIL ADATSTRUKTÚRA
# ─────────────────────────────────────────────

@dataclass
class BoostProfile:
    # Metaadatok
    name:        str   = "Névtelen Profil"
    description: str   = ""
    icon:        str   = "⚡"
    is_builtin:  bool  = False    # True = nem törölhető

    # Energiaséma
    power_plan:  str   = "high_performance"  # "high_performance" | "balanced" | "power_saver"

    # Windows szolgáltatások (lista a leállítandókból)
    stop_services: list = field(default_factory=list)

    # RAM kezelés
    ram_clean_on_boost:    bool  = True   # Boost aktiválásakor RAM tisztítás
    ram_clean_aggressive:  bool  = False  # Agresszív (több folyamat)

    # CPU/Process prioritás
    set_process_priority:  bool  = True   # Aktív folyamat HIGH prioritásra
    throttle_background:   bool  = True   # Háttér folyamatok lassítása

    # Registry tweakek
    registry_tweaks:       bool  = False  # Registry játék prioritás tweakek
    registry_hags:         bool  = True   # HAGS bekapcsolás (registry_tweaks-szal együtt)
    registry_gamebar:      bool  = True   # Xbox Game Bar letiltás
    registry_nagle:        bool  = True   # Nagle-algoritmus letiltás
    registry_game_mode:    bool  = True   # Windows Game Mode

    # Monitoring
    monitor_interval_sec:  float = 2.0

    # Auto-restore
    auto_restore_on_exit:  bool  = True   # App bezáráskor visszaállít

    # Megjelenítés
    color_accent:  str = "#00FF88"   # GUI szín


# ─────────────────────────────────────────────
#  BEÉPÍTETT PROFILOK
# ─────────────────────────────────────────────

BUILTIN_PROFILES: dict[str, BoostProfile] = {

    "gaming": BoostProfile(
        name        = "Gaming",
        description = "Maximum FPS — minden felesleges szolgáltatás le, High Performance energiaséma",
        icon        = "🎮",
        is_builtin  = True,
        power_plan  = "high_performance",
        stop_services = [
            "SysMain",      # Superfetch — RAM-ot eszik, gaming közben haszontalan
            "WSearch",      # Windows Search indexelő
            "DiagTrack",    # Telemetria
            "wuauserv",     # Windows Update
            "MapsBroker",   # Offline térkép
            "RetailDemo",   # Retail Demo
            "WbioSrvc",     # Biometrikus (ha nincs fingerprint reader)
        ],
        ram_clean_on_boost   = True,
        ram_clean_aggressive = True,
        set_process_priority = True,
        throttle_background  = True,
        registry_tweaks      = True,
        registry_hags        = True,
        registry_gamebar     = True,
        registry_nagle       = True,
        registry_game_mode   = True,
        monitor_interval_sec = 2.0,
        auto_restore_on_exit = True,
        color_accent         = "#FF2D55",
    ),

    "office": BoostProfile(
        name        = "Office / Tanulás",
        description = "Stabil munkakörnyezet — minimális beavatkozás, Balanced energiaséma",
        icon        = "💼",
        is_builtin  = True,
        power_plan  = "balanced",
        stop_services = [
            "DiagTrack",    # Telemetria — mindig ki lehet kapcsolni
            "RetailDemo",   # Retail Demo — sosem kell
        ],
        ram_clean_on_boost   = True,
        ram_clean_aggressive = False,
        set_process_priority = False,
        throttle_background  = False,
        monitor_interval_sec = 5.0,
        auto_restore_on_exit = False,
        color_accent         = "#00C8FF",
    ),

    "battery": BoostProfile(
        name        = "Akkumulátor kímélő",
        description = "Maximális üzemidő — Power Saver séma, háttér folyamatok minimalizálva",
        icon        = "🔋",
        is_builtin  = True,
        power_plan  = "power_saver",
        stop_services = [
            "SysMain",
            "WSearch",
            "DiagTrack",
            "wuauserv",
            "MapsBroker",
            "RetailDemo",
            "WbioSrvc",
        ],
        ram_clean_on_boost   = True,
        ram_clean_aggressive = False,
        set_process_priority = False,
        throttle_background  = True,
        monitor_interval_sec = 10.0,
        auto_restore_on_exit = True,
        color_accent         = "#FFC147",
    ),
}


# ─────────────────────────────────────────────
#  PROFIL KEZELŐ OSZTÁLY
# ─────────────────────────────────────────────

class ProfileManager:
    """
    Profilokat tölt, ment és kezel.
    Az egyéni profilokat JSON fájlban tárolja a profiles/ mappában.
    """

    def __init__(self):
        self._custom: dict[str, BoostProfile] = {}
        self._active_key: str = "gaming"
        self._load_custom()
        self._load_active()

    # ── Betöltés / mentés ──────────────────

    def _load_custom(self):
        """Egyéni profilok betöltése JSON-ból."""
        path = _get_profiles_file()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, val in data.items():
                try:
                    self._custom[key] = BoostProfile(**val)
                except TypeError as e:
                    logger.warning(f"Profil betöltési hiba ({key}): {e}")
        except Exception as e:
            logger.error(f"Profilok betöltési hiba: {e}")

    def _save_custom(self):
        """Egyéni profilok mentése JSON-ba."""
        try:
            path = _get_profiles_file()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = {k: asdict(v) for k, v in self._custom.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Profilok mentési hiba: {e}")

    def _load_active(self):
        """Utoljára aktív profil visszatöltése."""
        path = _get_active_file()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            key = data.get("active", "gaming")
            if key in self.all_profiles():
                self._active_key = key
        except Exception:
            pass

    def _save_active(self):
        """Aktív profil kulcs mentése."""
        try:
            path = _get_active_file()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"active": self._active_key}, f)
        except Exception:
            pass

    # ── Profil lekérdezés ──────────────────

    def all_profiles(self) -> dict[str, BoostProfile]:
        """Összes profil (beépített + egyéni), sorban."""
        result = {}
        result.update(BUILTIN_PROFILES)
        result.update(self._custom)
        return result

    def get(self, key: str) -> BoostProfile | None:
        return self.all_profiles().get(key)

    def get_active(self) -> tuple[str, BoostProfile]:
        """Visszaadja az aktív profil kulcsát és objektumát."""
        profiles = self.all_profiles()
        if self._active_key in profiles:
            return self._active_key, profiles[self._active_key]
        # Fallback: Gaming
        return "gaming", BUILTIN_PROFILES["gaming"]

    def set_active(self, key: str):
        if key in self.all_profiles():
            self._active_key = key
            self._save_active()

    # ── Egyéni profil műveletek ────────────

    def create_custom(self, name: str, based_on: str = "gaming") -> str:
        """
        Új egyéni profil létrehozása egy meglévő alapján.
        Visszaadja az új profil kulcsát.
        """
        base = self.get(based_on) or BUILTIN_PROFILES["gaming"]
        new  = copy.deepcopy(base)
        new.name       = name
        new.is_builtin = False
        new.icon       = "⚙"
        new.color_accent = "#9B59FF"

        # Egyedi kulcs generálása
        key = name.lower().replace(" ", "_")[:20]
        # Ha már létezik, szám hozzáadása
        if key in self.all_profiles():
            i = 2
            while f"{key}_{i}" in self.all_profiles():
                i += 1
            key = f"{key}_{i}"

        self._custom[key] = new
        self._save_custom()
        return key

    def update_custom(self, key: str, profile: BoostProfile) -> bool:
        """Egyéni profil frissítése. Beépítetteket nem lehet módosítani."""
        if key in BUILTIN_PROFILES:
            logger.warning(f"Beépített profil nem módosítható: {key}")
            return False
        if key not in self._custom:
            return False
        profile.is_builtin = False
        self._custom[key]  = profile
        self._save_custom()
        return True

    def delete_custom(self, key: str) -> bool:
        """Egyéni profil törlése. Beépítetteket nem lehet törölni."""
        if key in BUILTIN_PROFILES:
            return False
        if key not in self._custom:
            return False
        del self._custom[key]
        self._save_custom()
        if self._active_key == key:
            self._active_key = "gaming"
            self._save_active()
        return True

    def duplicate(self, key: str) -> str | None:
        """Profil másolása új egyéni profilként."""
        src = self.get(key)
        if not src:
            return None
        return self.create_custom(f"{src.name} (másolat)", based_on=key)


# Globális példány
profile_manager = ProfileManager()
