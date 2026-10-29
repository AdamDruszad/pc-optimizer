"""Windows-hívások egy helyen: parancsfuttatás, registry, szolgáltatások, energiaséma."""
import ctypes
import ipaddress
import logging
import re
import subprocess
import sys
import uuid
import winreg

import psutil

log = logging.getLogger(__name__)

HIVES = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}
GUID_RE = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """UAC-kéréssel újraindítja az appot. True, ha a kérés elindult."""
    if getattr(sys, "frozen", False):
        args = sys.argv[1:]
    else:
        args = sys.argv
    params = subprocess.list2cmdline(args)
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1) > 32


def run(args: list[str], timeout: float = 30, encoding: str = "oem") -> tuple[bool, str]:
    """Konzolos parancs; a kimenet a konzol kódlapján jön (magyar Windowson cp852)."""
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout, encoding=encoding,
                           errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, f"Időtúllépés ({timeout:.0f} s): {' '.join(args[:2])}"
    except OSError as e:
        return False, str(e)


def powershell(script: str, timeout: float = 60) -> tuple[bool, str]:
    prefix = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; $ErrorActionPreference = 'Stop'; "
    return run(["powershell", "-NoProfile", "-NonInteractive", "-Command", prefix + script],
               timeout=timeout, encoding="utf-8")


# ── Registry ────────────────────────────────────────────────

def _access(base: int, wow64_32: bool) -> int:
    return base | (winreg.KEY_WOW64_32KEY if wow64_32 else winreg.KEY_WOW64_64KEY)


def reg_read(hive: str, path: str, name: str, wow64_32: bool = False):
    """(érték, típus), vagy (None, None), ha az érték nem létezik."""
    try:
        with winreg.OpenKey(HIVES[hive], path, 0, _access(winreg.KEY_READ, wow64_32)) as k:
            return winreg.QueryValueEx(k, name)
    except FileNotFoundError:
        return None, None


def reg_write(hive: str, path: str, name: str, value, reg_type: int, wow64_32: bool = False) -> None:
    with winreg.CreateKeyEx(HIVES[hive], path, 0, _access(winreg.KEY_SET_VALUE, wow64_32)) as k:
        winreg.SetValueEx(k, name, 0, reg_type, value)


def reg_delete(hive: str, path: str, name: str, wow64_32: bool = False) -> None:
    try:
        with winreg.OpenKey(HIVES[hive], path, 0, _access(winreg.KEY_SET_VALUE, wow64_32)) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass


def reg_values(hive: str, path: str, wow64_32: bool = False) -> list[tuple[str, object, int]]:
    try:
        with winreg.OpenKey(HIVES[hive], path, 0, _access(winreg.KEY_READ, wow64_32)) as k:
            count = winreg.QueryInfoKey(k)[1]
            return [winreg.EnumValue(k, i) for i in range(count)]
    except FileNotFoundError:
        return []


def reg_subkeys(hive: str, path: str) -> list[str]:
    try:
        with winreg.OpenKey(HIVES[hive], path, 0, _access(winreg.KEY_READ, False)) as k:
            return [winreg.EnumKey(k, i) for i in range(winreg.QueryInfoKey(k)[0])]
    except OSError:
        return []


# ── Szolgáltatások ──────────────────────────────────────────

_START = {0: "boot", 1: "system", 2: "auto", 3: "demand", 4: "disabled"}


def start_type_name(start: int, delayed: int) -> str:
    if start == 2 and delayed:
        return "delayed-auto"
    return _START.get(start, "unknown")


def service_start_type(name: str) -> str | None:
    """Az `sc config start=` paraméterével azonos név, None ha nincs ilyen szolgáltatás."""
    path = rf"SYSTEM\CurrentControlSet\Services\{name}"
    start, _ = reg_read("HKLM", path, "Start")
    if start is None:
        return None
    delayed, _ = reg_read("HKLM", path, "DelayedAutostart")
    return start_type_name(start, delayed or 0)


def set_service_start(name: str, start: str) -> None:
    ok, out = run(["sc", "config", name, "start=", start])
    if not ok:
        raise OSError(out or f"sc config {name} sikertelen")


def service_delayed_flag(name: str) -> int | None:
    return reg_read("HKLM", rf"SYSTEM\CurrentControlSet\Services\{name}", "DelayedAutostart")[0]


def set_service_delayed_flag(name: str, value: int | None) -> None:
    """Az `sc config start=` nullázza a DelayedAutostart-ot; az eredetit közvetlenül írjuk vissza."""
    path = rf"SYSTEM\CurrentControlSet\Services\{name}"
    if value is None:
        reg_delete("HKLM", path, "DelayedAutostart")
    else:
        reg_write("HKLM", path, "DelayedAutostart", value, winreg.REG_DWORD)


def service_running(name: str) -> bool:
    try:
        return psutil.win_service_get(name).status() == "running"
    except Exception:
        return False


def stop_service(name: str) -> None:
    run(["sc", "stop", name])  # leállítás hiba esetén is folytatható: a letiltás a lényeg


def start_service(name: str) -> None:
    run(["sc", "start", name])


# ── Energiaséma ─────────────────────────────────────────────

def active_power_scheme() -> str | None:
    ok, out = run(["powercfg", "/getactivescheme"])
    m = GUID_RE.search(out) if ok else None
    return m.group().lower() if m else None


def power_schemes() -> dict[str, str]:
    """GUID → név (a név a rendszer nyelvén van)."""
    ok, out = run(["powercfg", "/list"])
    schemes = {}
    for line in out.splitlines() if ok else []:
        m = GUID_RE.search(line)
        if m:
            name = re.search(r"\((.+?)\)", line)
            schemes[m.group().lower()] = name.group(1) if name else m.group()
    return schemes


def set_power_scheme(guid: str) -> None:
    ok, out = run(["powercfg", "/setactive", guid])
    if not ok:
        raise OSError(out or "powercfg /setactive sikertelen")


class _GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort), ("d3", ctypes.c_ushort),
                ("d4", ctypes.c_ubyte * 8)]


def power_overlay() -> str | None:
    """Windows 11 energiamód (Modern Standby gépeken csak ez állítható)."""
    try:
        g = _GUID()
        if ctypes.windll.powrprof.PowerGetEffectiveOverlayScheme(ctypes.byref(g)) != 0:
            return None
        return str(uuid.UUID(bytes_le=bytes(g)))
    except (AttributeError, OSError):
        return None


def set_power_overlay(guid: str) -> None:
    g = _GUID.from_buffer_copy(uuid.UUID(guid).bytes_le)
    if ctypes.windll.powrprof.PowerSetActiveOverlayScheme(g) != 0:
        raise OSError("Az energiamód nem állítható")


# ── DNS ─────────────────────────────────────────────────────

def set_dns(interface_index: int, servers: list[str]) -> None:
    """Üres lista = DHCP. A címeket validáljuk, mert PowerShell-szkriptbe kerülnek."""
    index = int(interface_index)
    if servers:
        addrs = ",".join(f"'{ipaddress.ip_address(s)}'" for s in servers)
        script = f"Set-DnsClientServerAddress -InterfaceIndex {index} -ServerAddresses {addrs}"
    else:
        script = f"Set-DnsClientServerAddress -InterfaceIndex {index} -ResetServerAddresses"
    ok, out = powershell(script)
    if not ok:
        raise OSError(out or "A DNS nem állítható")
