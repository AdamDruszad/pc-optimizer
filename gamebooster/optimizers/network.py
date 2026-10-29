"""Hálózat: DNS-választó naplózott visszaállítással, DNS-gyorsítótár ürítése, késleltetésmérés."""
import json
import socket
import statistics
import time
from dataclasses import dataclass

from ..core import winapi
from ..core.journal import Change

DNS_PRESETS = {
    "Automatikus (DHCP)": [],
    "Cloudflare (1.1.1.1)": ["1.1.1.1", "1.0.0.1"],
    "Quad9 (9.9.9.9)": ["9.9.9.9", "149.112.112.112"],
    "Google (8.8.8.8)": ["8.8.8.8", "8.8.4.4"],
}
_IFACES = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"


@dataclass
class Adapter:
    name: str
    index: int
    guid: str
    dns: list[str]       # jelenleg használt (DHCP-ből vagy kézi)
    static_dns: list[str]  # kézzel beállított; üres = DHCP


def adapters() -> list[Adapter]:
    ok, out = winapi.powershell(
        "@(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object { "
        "[pscustomobject]@{ name = $_.Name; index = $_.ifIndex; guid = $_.InterfaceGuid; "
        "dns = @((Get-DnsClientServerAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4)"
        ".ServerAddresses) } }) | ConvertTo-Json -Compress")
    if not ok or not out:
        return []
    data = json.loads(out)
    result = []
    for a in data if isinstance(data, list) else [data]:
        static, _ = winapi.reg_read("HKLM", f"{_IFACES}\\{a['guid']}", "NameServer")
        servers = [s for s in (static or "").replace(",", " ").split() if s]
        result.append(Adapter(a["name"], int(a["index"]), a["guid"], a["dns"] or [], servers))
    return result


def plan_dns(adapter: Adapter, servers: list[str]) -> Change | None:
    if adapter.static_dns == servers:
        return None
    label = ", ".join(servers) if servers else "automatikus (DHCP)"
    return Change("dns", f"dns:{adapter.guid}", adapter.static_dns, servers,
                  f"{adapter.name} DNS: {label}", "network",
                  meta={"index": adapter.index, "alias": adapter.name})


def flush_dns() -> tuple[bool, str]:
    return winapi.run(["ipconfig", "/flushdns"])


@dataclass
class Latency:
    host: str
    samples: list[float]
    lost: int

    @property
    def summary(self) -> str:
        if not self.samples:
            return f"{self.host}: nem elérhető ({self.lost} sikertelen próba)"
        jitter = statistics.mean(abs(a - b) for a, b in zip(self.samples, self.samples[1:])) \
            if len(self.samples) > 1 else 0.0
        return (f"{self.host}: átlag {statistics.mean(self.samples):.1f} ms, "
                f"min {min(self.samples):.1f}, max {max(self.samples):.1f}, "
                f"jitter {jitter:.1f} ms, veszteség {self.lost}/{self.lost + len(self.samples)}")


def tcp_latency(host: str, port: int = 443, count: int = 10, timeout: float = 2.0) -> Latency:
    """TCP-kapcsolódási idő: a ping kimenete nyelvfüggő és ICMP-t sok hálózat tilt."""
    samples, lost = [], 0
    for _ in range(count):
        start = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                samples.append((time.perf_counter() - start) * 1000)
        except OSError:
            lost += 1
        time.sleep(0.1)
    return Latency(host, samples, lost)
