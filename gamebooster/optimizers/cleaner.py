"""Tisztítás előnézettel: csak rögzített cache- és ideiglenes mappák, a felhasználói adatokhoz nem nyúl.

A szkennelés nem követ szimbolikus linket és junctiont (azon át a mappán kívülre is törölhetne),
a zárolt fájlokat kihagyja, a gyökérmappát nem törli.
"""
import os
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..core import winapi


@dataclass(frozen=True)
class Target:
    key: str
    label: str
    paths: tuple[str, ...]
    min_age_hours: int = 0
    note: str = ""


_SHADER_NOTE = "A törlés után az első játékindításkor újrafordulnak a shaderek (rövid akadás)."
TARGETS = [
    Target("user_temp", "Ideiglenes fájlok (felhasználó)", ("%TEMP%",), 24,
           "Csak a 24 óránál régebbi fájlok."),
    Target("win_temp", "Ideiglenes fájlok (Windows)", (r"%WINDIR%\Temp",), 24,
           "Csak a 24 óránál régebbi fájlok."),
    Target("dx_shader", "DirectX shader cache", (r"%LOCALAPPDATA%\D3DSCache",), note=_SHADER_NOTE),
    Target("nvidia_shader", "NVIDIA shader cache",
           (r"%LOCALAPPDATA%\NVIDIA\DXCache", r"%LOCALAPPDATA%\NVIDIA\GLCache"), note=_SHADER_NOTE),
    Target("amd_shader", "AMD shader cache",
           (r"%LOCALAPPDATA%\AMD\DxCache", r"%LOCALAPPDATA%\AMD\DxcCache",
            r"%LOCALAPPDATA%\AMD\VkCache", r"%LOCALAPPDATA%\AMD\GLCache"), note=_SHADER_NOTE),
    Target("crash_dumps", "Összeomlási dumpok",
           (r"%LOCALAPPDATA%\CrashDumps", r"%WINDIR%\Minidump")),
    Target("wer", "Windows hibajelentések",
           (r"%PROGRAMDATA%\Microsoft\Windows\WER\ReportArchive",
            r"%PROGRAMDATA%\Microsoft\Windows\WER\ReportQueue")),
]


@dataclass
class Scan:
    target: Target
    files: list[Path] = field(default_factory=list)
    size: int = 0


def _is_link(entry: os.DirEntry) -> bool:
    return entry.is_symlink() or getattr(entry, "is_junction", lambda: False)()


def _has_reparse_point(path: Path) -> bool:
    """Emelt jogon törlünk: ha egy szülőmappa junction vagy link, egy nem-admin folyamat
    átirányíthatná a törlést (pl. a System32-re)."""
    for p in (path, *path.parents):
        try:
            if os.lstat(p).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                return True
        except OSError:
            return True
    return False


def _walk(root: Path, cutoff: float, cancel: threading.Event, scan: Scan) -> None:
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    for entry in entries:
        if cancel.is_set():
            return
        try:
            if _is_link(entry):
                continue
            if entry.is_dir(follow_symlinks=False):
                _walk(Path(entry.path), cutoff, cancel, scan)
            elif entry.is_file(follow_symlinks=False):
                st = entry.stat(follow_symlinks=False)
                if st.st_mtime <= cutoff:
                    scan.files.append(Path(entry.path))
                    scan.size += st.st_size
        except OSError:
            continue


def scan(targets: list[Target], cancel: threading.Event | None = None) -> list[Scan]:
    cancel = cancel or threading.Event()
    results = []
    for target in targets:
        result = Scan(target)
        cutoff = time.time() - target.min_age_hours * 3600
        for raw in target.paths:
            root = Path(os.path.expandvars(raw))
            if "%" not in str(root) and root.is_dir() and not _has_reparse_point(root):
                _walk(root, cutoff, cancel, result)
        results.append(result)
    return results


@dataclass
class CleanResult:
    deleted: int = 0
    freed: int = 0
    skipped: int = 0


def clean(scans: list[Scan], cancel: threading.Event | None = None, progress=None) -> CleanResult:
    cancel = cancel or threading.Event()
    result = CleanResult()
    files = [f for s in scans for f in s.files]
    dirs = set()
    unsafe: dict[Path, bool] = {}
    for i, path in enumerate(files):
        if cancel.is_set():
            break
        # shortcut: a szkennelés óta cserélt junction ellen ez csak szűkíti az ablakot; teljes
        # védelemhez FILE_FLAG_OPEN_REPARSE_POINT-tal nyitott handle-lel kellene törölni
        if unsafe.setdefault(path.parent, _has_reparse_point(path.parent)):
            result.skipped += 1
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            result.deleted += 1
            result.freed += size
            dirs.add(path.parent)
        except OSError:
            result.skipped += 1  # zárolt vagy közben eltűnt fájl
        if progress and i % 50 == 0:
            progress(i / max(len(files), 1))
    roots = {Path(os.path.expandvars(p)) for s in scans for p in s.target.paths}
    for d in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        # Kiürült almappák törlése, a gyökér marad
        while d not in roots and any(r in d.parents for r in roots):
            try:
                d.rmdir()
            except OSError:
                break
            d = d.parent
    return result


def delivery_optimization_cleanup() -> tuple[bool, str]:
    return winapi.powershell("Delete-DeliveryOptimizationCache -Force", timeout=300)


def component_cleanup() -> tuple[bool, str]:
    """Windows Update komponenstár takarítása (DISM). Lassú: akár 10-20 perc."""
    return winapi.run(["dism", "/Online", "/Cleanup-Image", "/StartComponentCleanup"], timeout=3600)
