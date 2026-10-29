"""Egyetlen mintavevő szál. A UI csak a `latest`/`history` mezőket olvassa a saját szálán,
widgethez a háttérszál nem nyúl."""
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, fields

import psutil

from . import pdh

log = logging.getLogger(__name__)
_GB = 1024 ** 3
_MB = 1024 ** 2

_COUNTERS = {
    "gpu_3d": r"\GPU Engine(*engtype_3D)\Utilization Percentage",
    "gpu_ded": r"\GPU Adapter Memory(*)\Dedicated Usage",
    "gpu_shared": r"\GPU Adapter Memory(*)\Shared Usage",
    "thermal": r"\Thermal Zone Information(*)\Temperature",
}


@dataclass
class Sample:
    cpu: float = 0.0
    cpu_mhz: float = 0.0
    ram_pct: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    disk_read_mbs: float = 0.0
    disk_write_mbs: float = 0.0
    net_down_mbs: float = 0.0
    net_up_mbs: float = 0.0
    gpu: float | None = None
    gpu_mem_gb: float | None = None
    temp_c: float | None = None      # ACPI hőzóna: nem CPU-mag hőmérséklet
    gpu_temp_c: float | None = None  # csak NVIDIA, ha telepítve van az nvidia-ml-py


def _nvidia_temp():
    try:
        import pynvml  # opcionális: pip install nvidia-ml-py
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        return lambda: float(pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))
    except Exception:
        return None


class Sampler(threading.Thread):
    def __init__(self, interval: float = 1.0, history: int = 120):
        super().__init__(daemon=True, name="Sampler")
        self.interval = interval
        self.latest = Sample()
        self.history = {f.name: deque(maxlen=history) for f in fields(Sample)}
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            query = pdh.Query(_COUNTERS)
        except OSError as e:
            log.warning("PDH nem elérhető: %s", e)
            query = None
        gpu_temp = _nvidia_temp()
        psutil.cpu_percent(None)
        disk, net, last = psutil.disk_io_counters(), psutil.net_io_counters(), time.monotonic()
        while not self._stop_event.wait(self.interval):
            try:
                now = time.monotonic()
                dt = max(now - last, 1e-3)
                disk2, net2 = psutil.disk_io_counters(), psutil.net_io_counters()
                mem = psutil.virtual_memory()
                freq = psutil.cpu_freq()
                s = Sample(
                    cpu=psutil.cpu_percent(None),
                    cpu_mhz=freq.current if freq else 0.0,
                    ram_pct=mem.percent,
                    ram_used_gb=(mem.total - mem.available) / _GB,
                    ram_total_gb=mem.total / _GB,
                )
                if disk and disk2:
                    s.disk_read_mbs = (disk2.read_bytes - disk.read_bytes) / dt / _MB
                    s.disk_write_mbs = (disk2.write_bytes - disk.write_bytes) / dt / _MB
                if net and net2:
                    s.net_down_mbs = (net2.bytes_recv - net.bytes_recv) / dt / _MB
                    s.net_up_mbs = (net2.bytes_sent - net.bytes_sent) / dt / _MB
                disk, net, last = disk2, net2, now
                if query:
                    c = query.collect()
                    s.gpu = pdh.gpu_utilization(c.get("gpu_3d", {}))
                    dedicated = max(c.get("gpu_ded", {}).values(), default=0.0)
                    shared = max(c.get("gpu_shared", {}).values(), default=0.0)
                    if dedicated or shared:
                        # Integrált GPU-nak nincs saját VRAM-ja: ott a megosztott memória számít
                        s.gpu_mem_gb = (dedicated if dedicated > 64 * _MB else shared) / _GB
                    kelvins = [k for k in c.get("thermal", {}).values() if 250 < k < 400]
                    if kelvins:
                        s.temp_c = max(kelvins) - 273.15
                if gpu_temp:
                    s.gpu_temp_c = gpu_temp()
                self.latest = s
                for name, values in self.history.items():
                    values.append(getattr(s, name))
            except Exception as e:
                log.warning("Mintavételi hiba: %s", e)
        if query:
            query.close()
