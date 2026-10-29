"""Hardver- és rendszerinformáció registryből és psutil-lal (WMI és PowerShell nélkül)."""
import platform
from dataclasses import dataclass, field

import psutil

from ..core import winapi

_DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
# Virtuális/távoli kijelzőadapterek, nem valódi GPU-k (a név bármely részén)
_SKIP_GPUS = ("Basic Display", "Basic Render", "Remote Display", "Virtual", "Parsec", "Indirect Display")


@dataclass
class Gpu:
    name: str
    vram_gb: float | None
    driver: str


@dataclass
class HardwareInfo:
    cpu: str = "Ismeretlen CPU"
    cores: int = 0
    threads: int = 0
    ram_gb: float = 0.0
    gpus: list[Gpu] = field(default_factory=list)
    windows: str = ""
    battery: str | None = None   # None: asztali gép


def _int(value) -> int | None:
    if isinstance(value, bytes):
        return int.from_bytes(value[:8], "little")
    return value if isinstance(value, int) else None


def gpus() -> list[Gpu]:
    result = []
    for sub in winapi.reg_subkeys("HKLM", _DISPLAY_CLASS):
        path = f"{_DISPLAY_CLASS}\\{sub}"
        try:
            name, _ = winapi.reg_read("HKLM", path, "DriverDesc")
        except OSError:
            continue  # pl. a Properties alkulcs nem olvasható
        if not name or any(skip in name for skip in _SKIP_GPUS):
            continue
        # A 64 bites qwMemorySize helyes 4 GB fölött is (a WMI AdapterRAM 32 bites)
        mem = _int(winapi.reg_read("HKLM", path, "HardwareInformation.qwMemorySize")[0]) \
            or _int(winapi.reg_read("HKLM", path, "HardwareInformation.MemorySize")[0])
        driver, _ = winapi.reg_read("HKLM", path, "DriverVersion")
        result.append(Gpu(name, mem / 1024 ** 3 if mem else None, driver or ""))
    return result


def windows_version() -> str:
    nt = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    build = winapi.reg_read("HKLM", nt, "CurrentBuild")[0] or platform.version()
    display = winapi.reg_read("HKLM", nt, "DisplayVersion")[0] or ""
    edition = winapi.reg_read("HKLM", nt, "EditionID")[0] or ""
    # A ProductName Windows 11-en is „Windows 10”-et ír, ezért a buildszám dönt
    name = "Windows 11" if str(build).isdigit() and int(build) >= 22000 else "Windows 10"
    return " ".join(p for p in (name, edition, display, f"(build {build})") if p)


def detect() -> HardwareInfo:
    cpu, _ = winapi.reg_read("HKLM", r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
                             "ProcessorNameString")
    battery = psutil.sensors_battery()
    return HardwareInfo(
        cpu=(cpu or platform.processor()).strip(),
        cores=psutil.cpu_count(logical=False) or 0,
        threads=psutil.cpu_count() or 0,
        ram_gb=psutil.virtual_memory().total / 1024 ** 3,
        gpus=gpus(),
        windows=windows_version(),
        battery=None if battery is None else
        f"{battery.percent:.0f}% ({'töltőn' if battery.power_plugged else 'akkumulátorról'})",
    )
