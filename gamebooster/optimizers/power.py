"""Teljesítmény energiaséma: Ultimate Performance, ennek hiányában High Performance,
Modern Standby gépen (ahol csak a Balanced séma létezik) a Windows 11 energiamód."""
from ..core import winapi
from ..core.journal import Change

ULTIMATE = "e9a42b02-d5df-448d-aa00-03f14749eb61"
HIGH = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
BEST_PERFORMANCE_OVERLAY = "ded574b5-45a0-4f42-8737-46345c09c238"


def performance_scheme(settings: dict, schemes: dict[str, str]) -> str | None:
    saved = settings.get("performance_scheme")
    if saved in schemes:
        return saved
    if ULTIMATE in schemes:
        return ULTIMATE
    return HIGH if HIGH in schemes else None


def add_ultimate(settings: dict) -> str:
    """Az Ultimate Performance séma sok kiadáson rejtett; ez egyszer lemásolja (kifejezett kérésre)."""
    ok, out = winapi.run(["powercfg", "-duplicatescheme", ULTIMATE])
    match = winapi.GUID_RE.search(out) if ok else None
    if not match:
        raise OSError(out or "Az Ultimate Performance séma nem hozható létre ezen a gépen")
    settings["performance_scheme"] = match.group().lower()
    return settings["performance_scheme"]


def plan(settings: dict, source: str) -> list[Change]:
    schemes = winapi.power_schemes()
    current = winapi.active_power_scheme()
    target = performance_scheme(settings, schemes)
    if target and current:
        if current == target:
            return []
        return [Change("power", "power:scheme", current, target,
                       f"Energiaséma: {schemes.get(current, current)} → {schemes.get(target, target)}",
                       source)]
    overlay = winapi.power_overlay()
    if overlay and overlay != BEST_PERFORMANCE_OVERLAY:
        return [Change("power_overlay", "power:overlay", overlay, BEST_PERFORMANCE_OVERLAY,
                       "Energiamód: Legjobb teljesítmény", source)]
    return []
