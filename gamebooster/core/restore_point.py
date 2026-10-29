"""Windows rendszer-visszaállítási pont, a napló mellé független védőhálónak."""
from . import winapi

_SCRIPT = (
    "Checkpoint-Computer -Description 'GameBooster' -RestorePointType MODIFY_SETTINGS "
    "-WarningVariable w -WarningAction SilentlyContinue; if ($w) { 'WARN ' + $w } else { 'OK' }"
)


def create() -> tuple[bool, str]:
    """(létrejött-e, üzenet). Kikapcsolt rendszervédelem és a 24 órás limit nem hiba, csak jelzés."""
    ok, out = winapi.powershell(_SCRIPT, timeout=180)
    if ok and out.endswith("OK"):
        return True, "Visszaállítási pont létrehozva."
    if ok and "WARN" in out:
        return False, "Az elmúlt 24 órában már készült visszaállítási pont, a Windows most nem hoz létre újat."
    return False, ("Nem jött létre visszaállítási pont (a rendszervédelem valószínűleg ki van "
                   "kapcsolva a C: meghajtón). A változásnapló ettől függetlenül működik.")
