"""Registry-tweakek: csak dokumentált, ellenőrizhető hatású beállítások.

A v2 MMCSS-értékei (GPU Priority, SFIO Priority, SystemResponsiveness=0), a Win32PrioritySeparation,
a Nagle- és az egér-puffer tweak kikerült: a Windows ezeket figyelmen kívül hagyja vagy felülírja,
illetve mérhető hatásuk nincs.
"""
import winreg
from dataclasses import dataclass
from typing import Callable

from ..core import winapi
from ..core.journal import Change, registry_change

DWORD, SZ = winreg.REG_DWORD, winreg.REG_SZ
_DX_PREFS = r"Software\Microsoft\DirectX\UserGpuPreferences"


def set_flag(flag: str, value: str | None) -> Callable[[str | None], str | None]:
    """`Kulcs=érték;` listában egy kulcs beállítása (None: törlése), a többi megtartásával."""
    def transform(current: str | None) -> str | None:
        parts = [p for p in (current or "").split(";") if p and not p.startswith(flag + "=")]
        if value is not None:
            parts.append(f"{flag}={value}")
        return ";".join(parts) + ";" if parts else None
    return transform


@dataclass(frozen=True)
class RegValue:
    hive: str
    path: str
    name: str
    value: object          # konkrét érték, vagy függvény a jelenlegi értékből
    type: int
    default: object = None  # amit a Windows hiányzó érték esetén érvényesnek vesz

    def current(self):
        value, _ = winapi.reg_read(self.hive, self.path, self.name)
        return self.default if value is None else value

    def desired(self, current):
        return self.value(current) if callable(self.value) else self.value


@dataclass(frozen=True)
class Tweak:
    key: str
    label: str
    description: str
    impact: str            # mérhető | helyzetfüggő
    restart: bool
    values: tuple[RegValue, ...]


TWEAKS = [
    Tweak("game_dvr_off", "Háttérfelvétel kikapcsolva",
          "Bekapcsolt háttérfelvételnél („Rögzítés a háttérben”) a Windows folyamatosan videót "
          "kódol a játékról. Kikapcsolva ez a terhelés megszűnik; a Game Bar overlay megmarad.",
          "mérhető", False,
          (RegValue("HKCU", r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
                    "AppCaptureEnabled", 0, DWORD, default=0),)),
    Tweak("windowed_opt", "Ablakos játékok optimalizálása",
          "DirectX 10/11 játékok ablakos és keret nélküli módban is flip modellel futnak: "
          "kisebb késleltetés, VRR támogatás (Windows 11).",
          "mérhető", False,
          (RegValue("HKCU", _DX_PREFS, "DirectXUserGlobalSettings",
                    set_flag("SwapEffectUpgradeEnable", "1"), SZ),)),
    Tweak("hags", "Hardveresen gyorsított GPU-ütemezés (HAGS)",
          "A GPU memóriáját a saját ütemezője kezeli. Az NVIDIA DLSS Frame Generation igényli; "
          "más esetben a hatás GPU-tól és drivertől függ.",
          "helyzetfüggő", True,
          (RegValue("HKLM", r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
                    "HwSchMode", 2, DWORD),)),
    Tweak("game_mode", "Windows Játék mód",
          "A Windows a futó játéknak ad elsőbbséget, és játék közben nem telepít frissítést. "
          "A Windows 10 1703 óta alapból be van kapcsolva.",
          "helyzetfüggő", False,
          (RegValue("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1, DWORD,
                    default=1),)),
]


def is_on(tweak: Tweak) -> bool:
    return all(v.current() == v.desired(v.current()) for v in tweak.values)


def plan(tweak: Tweak) -> list[Change]:
    changes = []
    for v in tweak.values:
        current = v.current()
        if current == v.desired(current):
            continue
        change = registry_change(v.hive, v.path, v.name, v.desired(current), v.type,
                                 f"{tweak.label}: {v.name}", "tweaks")
        if change:
            changes.append(change)
    return changes


def targets(tweak: Tweak) -> set[str]:
    return {f"{v.hive}\\{v.path}\\{v.name}" for v in tweak.values}


def gpu_preference_change(exe_path: str, high: bool) -> Change | None:
    """Alkalmazásonkénti GPU-választás hibrid (iGPU + dGPU) gépen; a Windows Grafika beállításával azonos."""
    current, _ = winapi.reg_read("HKCU", _DX_PREFS, exe_path)
    after = set_flag("GpuPreference", "2" if high else None)(current)
    return registry_change("HKCU", _DX_PREFS, exe_path, after, SZ,
                           f"Nagy teljesítményű GPU: {exe_path}", "gpu_pref")


def security_status() -> dict[str, bool | None]:
    """Csak megjelenítés: a Memóriaintegritás (HVCI) egyes játékokban mérhetően lassít,
    de biztonsági funkció, ezért nem kapcsoljuk automatikusan."""
    hvci, _ = winapi.reg_read(
        "HKLM", r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity",
        "Enabled")
    return {"memory_integrity": None if hvci is None else bool(hvci)}
