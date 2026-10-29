"""Szolgáltatások: csak egy ismert, kockázattal jelölt engedélylistáról.

Egyéni szolgáltatásnevet nem fogadunk el (emelt jogon futunk). A legtöbb szolgáltatás
„Kézi” indításra kerül, nem letiltásra, így ha egy program igényli, a Windows elindítja.
"""
from dataclasses import dataclass

from ..core import winapi
from ..core.journal import Change

START_LABELS = {
    "auto": "Automatikus", "delayed-auto": "Automatikus (késleltetett)", "demand": "Kézi",
    "disabled": "Letiltva", "boot": "Rendszerindítás", "system": "Rendszer", None: "Nincs telepítve",
}


@dataclass(frozen=True)
class ServiceInfo:
    name: str
    label: str
    risk: str      # alacsony | közepes
    target: str    # demand | disabled
    note: str


SERVICES = [
    ServiceInfo("DiagTrack", "Telemetria (Connected User Experiences)", "alacsony", "disabled",
                "Diagnosztikai adatküldés a Microsoftnak."),
    ServiceInfo("dmwappushservice", "WAP push üzenetek (telemetria)", "alacsony", "disabled",
                "Telemetria-útvonal, otthoni gépen nincs más szerepe."),
    ServiceInfo("RetailDemo", "Bolti bemutató mód", "alacsony", "disabled",
                "Csak bolti bemutató gépeken használt."),
    ServiceInfo("MapsBroker", "Letöltött térképek kezelője", "alacsony", "demand",
                "Az offline térképek nem frissülnek automatikusan."),
    ServiceInfo("WerSvc", "Windows hibajelentés", "alacsony", "demand",
                "Összeomláskor nem küld jelentést automatikusan."),
    ServiceInfo("Fax", "Fax", "alacsony", "demand", "Faxolás nem működik, amíg el nem indul."),
    ServiceInfo("XblGameSave", "Xbox Live játékmentés", "közepes", "demand",
                "Xbox / Game Pass játékok felhőmentése ritkábban szinkronizál."),
    ServiceInfo("SysMain", "SysMain (Superfetch)", "közepes", "demand",
                "SSD-n nincs mérhető hatása; HDD-n az appok lassabban indulnak."),
    ServiceInfo("WSearch", "Windows keresés indexelő", "közepes", "demand",
                "A Start menü és az Intéző keresése lassabb lesz."),
    ServiceInfo("Spooler", "Nyomtatási sor", "közepes", "demand",
                "Csak akkor, ha nem nyomtatsz erről a gépről."),
]
BY_NAME = {s.name: s for s in SERVICES}


def status() -> list[tuple[ServiceInfo, str | None, bool]]:
    return [(s, winapi.service_start_type(s.name), winapi.service_running(s.name)) for s in SERVICES]


def plan(names: list[str]) -> list[Change]:
    changes = []
    for name in names:
        info = BY_NAME[name]  # KeyError: engedélylistán kívüli név
        current = winapi.service_start_type(name)
        if current is None or current == info.target:
            continue
        changes.append(Change(
            "service", f"service:{name}", current, info.target,
            f"{info.label}: {START_LABELS[current]} → {START_LABELS[info.target]}", "services",
            meta={"name": name, "stop": True, "was_running": winapi.service_running(name)}))
    return changes
