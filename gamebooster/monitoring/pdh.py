"""Windows teljesítményszámlálók (PDH) folyamaton belül: nincs PowerShell-indítás mintánként.
Az angol számlálóneveket használja, így magyar Windowson is működik."""
import ctypes
from ctypes import wintypes

_pdh = ctypes.WinDLL("pdh")
_FMT_DOUBLE = 0x00000200 | 0x00008000  # PDH_FMT_DOUBLE | PDH_FMT_NOCAP100
_MORE_DATA = 0x800007D2
_VALID = (0, 1)  # PDH_CSTATUS_VALID_DATA, PDH_CSTATUS_NEW_DATA


class _Value(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class _Item(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _Value)]


_pdh.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wintypes.HANDLE)]
_pdh.PdhOpenQueryW.restype = wintypes.DWORD
_pdh.PdhAddEnglishCounterW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_size_t,
                                       ctypes.POINTER(wintypes.HANDLE)]
_pdh.PdhAddEnglishCounterW.restype = wintypes.DWORD
_pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
_pdh.PdhCollectQueryData.restype = wintypes.DWORD
_pdh.PdhGetFormattedCounterArrayW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                              ctypes.POINTER(wintypes.DWORD),
                                              ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_pdh.PdhGetFormattedCounterArrayW.restype = wintypes.DWORD
_pdh.PdhCloseQuery.argtypes = [wintypes.HANDLE]


class Query:
    """Helyettesítő karakteres (`*`) számlálók; a `collect()` példánynév → érték szótárakat ad."""

    def __init__(self, paths: dict[str, str]):
        self._query = wintypes.HANDLE()
        if _pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._query)) != 0:
            raise OSError("PdhOpenQuery sikertelen")
        self._counters = {}
        for key, path in paths.items():
            counter = wintypes.HANDLE()
            if _pdh.PdhAddEnglishCounterW(self._query, path, 0, ctypes.byref(counter)) == 0:
                self._counters[key] = counter  # a hiányzó számláló (pl. nincs GPU) kimarad
        _pdh.PdhCollectQueryData(self._query)

    def collect(self) -> dict[str, dict[str, float]]:
        _pdh.PdhCollectQueryData(self._query)
        return {key: self._read(counter) for key, counter in self._counters.items()}

    @staticmethod
    def _read(counter) -> dict[str, float]:
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        if _pdh.PdhGetFormattedCounterArrayW(counter, _FMT_DOUBLE, ctypes.byref(size),
                                             ctypes.byref(count), None) != _MORE_DATA:
            return {}
        buf = (ctypes.c_byte * size.value)()
        if _pdh.PdhGetFormattedCounterArrayW(counter, _FMT_DOUBLE, ctypes.byref(size),
                                             ctypes.byref(count), buf) != 0:
            return {}
        items = ctypes.cast(buf, ctypes.POINTER(_Item))
        return {items[i].szName: items[i].FmtValue.doubleValue
                for i in range(count.value) if items[i].FmtValue.CStatus in _VALID}

    def close(self) -> None:
        _pdh.PdhCloseQuery(self._query)


def gpu_utilization(engines: dict[str, float]) -> float | None:
    """A Feladatkezelővel azonos: motoronként összegzi a folyamatokat, a legterheltebb motor számít."""
    if not engines:
        return None
    per_engine: dict[str, float] = {}
    for name, value in engines.items():
        engine = name.split("_luid_", 1)[-1]  # "pid_123_luid_..._eng_0_engtype_3D" → motor
        per_engine[engine] = per_engine.get(engine, 0.0) + value
    return min(100.0, max(per_engine.values()))
