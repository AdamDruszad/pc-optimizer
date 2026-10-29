"""Valódi rendszeren futó próba: eredeti érték rögzítése → alkalmazás → ellenőrzés → visszaállítás →
összevetés az eredetivel. Admin nélkül csak a felhasználói részt futtatja (HKCU, saját indítású
folyamatok). Az admin részt Windows Sandboxban vagy VM-ben futtasd, ne a napi gépeden.

    python scripts/system_test.py [kimeneti mappa] [--sandbox]

--sandbox: a valódi cache-mappákat is törli (eldobható gépen).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import winreg
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil

from gamebooster.core import legacy, restore_point, storage, winapi
from gamebooster.core.journal import Journal, registry_change
from gamebooster.optimizers import cleaner, game_mode, network, power, services, startup, tweaks

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SANDBOX = "--sandbox" in sys.argv
OUT = Path(ARGS[0]) if ARGS else Path(tempfile.mkdtemp(prefix="gb-systest-"))
OUT.mkdir(parents=True, exist_ok=True)
storage.set_data_dir(OUT / "data")
ADMIN = winapi.is_admin()
results: list[dict] = []
TESTS = []


def check(name: str, ok, detail="") -> None:
    results.append({"check": name, "ok": bool(ok), "detail": str(detail)})
    print(f"{'OK  ' if ok else 'HIBA'} {name}" + (f"  [{detail}]" if detail != "" else ""), flush=True)


def test(admin: bool = False):
    def register(fn):
        TESTS.append((fn, admin))
        return fn
    return register


def journal(name: str) -> Journal:
    return Journal(OUT / f"journal-{name}.json")


def raw(hive: str, path: str, name: str):
    return winapi.reg_read(hive, path, name)


def screenshot(app, path: Path) -> None:
    app.update()
    x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
    winapi.powershell(
        f"Add-Type -AssemblyName System.Drawing; $b = New-Object System.Drawing.Bitmap {w},{h}; "
        f"$g = [System.Drawing.Graphics]::FromImage($b); $g.CopyFromScreen({x},{y},0,0,$b.Size); "
        f"$b.Save('{path}'); $g.Dispose(); $b.Dispose()")


# ── Felhasználói rész (admin nélkül is) ─────────────────────

def _tweak_round_trip(t: tweaks.Tweak, j: Journal) -> None:
    before = {v.name: raw(v.hive, v.path, v.name) for v in t.values}
    was_on = tweaks.is_on(t)
    out = j.apply(tweaks.plan(t))
    check(f"tweak {t.key}: alkalmazás", not out.failed and tweaks.is_on(t),
          f"{len(out.ok)} változás, előtte {'be' if was_on else 'ki'} volt")
    j.revert()
    after = {v.name: raw(v.hive, v.path, v.name) for v in t.values}
    check(f"tweak {t.key}: visszaállítás az eredetire", after == before, after)


@test()
def hkcu_tweaks():
    for t in tweaks.TWEAKS:
        if all(v.hive == "HKCU" for v in t.values):
            _tweak_round_trip(t, journal(f"tweak-{t.key}"))


@test()
def repeated_apply_keeps_original():
    hive, path, name = "HKCU", tweaks._DX_PREFS, "DirectXUserGlobalSettings"
    before = raw(hive, path, name)
    j = journal("repeat")
    for value in ("SwapEffectUpgradeEnable=1;", "SwapEffectUpgradeEnable=1;VRROptimizeEnable=0;"):
        change = registry_change(hive, path, name, value, winreg.REG_SZ, "ismételt alkalmazás", "systest")
        j.apply([change] if change else [])
    entry = j.find(f"{hive}\\{path}\\{name}")
    check("ismételt alkalmazás: a napló az első eredeti értéket őrzi",
          entry is not None and entry.before == before[0], entry.before if entry else None)
    j.revert()
    check("ismételt alkalmazás: visszaállítás az eredetire", raw(hive, path, name) == before,
          raw(hive, path, name))


@test()
def startup_toggle():
    run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    approved = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
    name = "GameBoosterSystemTest"
    winapi.reg_write("HKCU", run_key, name, r"C:\Windows\System32\notepad.exe", winreg.REG_SZ)
    try:
        item = next(i for i in startup.items() if i.name == name)
        check("indítópult: a próbabejegyzés bekapcsoltként látszik", item.enabled)
        j = journal("startup")
        out = j.apply([startup.plan_toggle(item, False)])
        value = raw("HKCU", approved, name)[0]
        item = next(i for i in startup.items() if i.name == name)
        check("indítópult: kikapcsolás a Feladatkezelő formátumában",
              not out.failed and not item.enabled and value[:1] == b"\x03", value.hex() if value else None)
        j.revert()
        check("indítópult: visszaállítás", raw("HKCU", approved, name) == (None, None)
              and next(i for i in startup.items() if i.name == name).enabled)
    finally:
        winapi.reg_delete("HKCU", run_key, name)
        winapi.reg_delete("HKCU", approved, name)


@test()
def game_session():
    # „Játék”: PowerShell, háttérapp: ping; mindkettőt ez a teszt indítja és zárja be
    game = subprocess.Popen(["powershell", "-NoProfile", "-Command", "Start-Sleep 120"],
                            creationflags=subprocess.CREATE_NO_WINDOW)
    bg = subprocess.Popen(["ping", "-n", "120", "127.0.0.1"], stdout=subprocess.DEVNULL,
                          creationflags=subprocess.CREATE_NO_WINDOW)
    scheme = winapi.active_power_scheme()
    try:
        time.sleep(1.0)
        game_p, bg_p = psutil.Process(game.pid), psutil.Process(bg.pid)
        bg_before = bg_p.nice()
        settings = {**storage.SETTINGS_DEFAULTS, "game_power_plan": ADMIN, "game_priority": True,
                    "background_apps": ["PING.EXE"]}
        j = journal("game")
        watcher = game_mode.GameWatcher(j, lambda: settings, lambda *e: None)
        out = watcher.start_session(game_p)
        check("Játék mód: magas prioritás a játéknak, alacsonyabb a háttérappnak",
              not out.failed and game_p.nice() == psutil.HIGH_PRIORITY_CLASS
              and bg_p.nice() == psutil.BELOW_NORMAL_PRIORITY_CLASS,
              f"{len(out.ok)} változás: " + "; ".join(c.label for c in out.ok))
        game.kill()
        game.wait()
        watcher._tick()
        check("Játék mód: a játék bezárásakor minden visszaáll",
              not watcher.active and bg_p.nice() == bg_before and not j.entries()
              and winapi.active_power_scheme() == scheme, f"háttérapp: {bg_p.nice()}")
    finally:
        for p in (game, bg):
            p.kill()


@test()
def cleaner_safety():
    base = Path(tempfile.mkdtemp(prefix="gb-clean-"))
    root, outside = base / "cache", base / "outside"
    for f, age in ((root / "old.bin", 48), (root / "sub" / "old2.bin", 48), (root / "fresh.bin", 0),
                   (outside / "precious.txt", 48)):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * 100)
        t = time.time() - age * 3600
        os.utime(f, (t, t))
    links = (root / "link", base / "jroot")
    for link in links:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, check=True)
    try:
        os.environ["GB_SYSTEST_CACHE"], os.environ["GB_SYSTEST_JROOT"] = str(root), str(links[1])
        [scan] = cleaner.scan([cleaner.Target("t", "t", ("%GB_SYSTEST_CACHE%",), 24)])
        check("tisztító: csak a régi fájlok, junction nélkül",
              sorted(p.name for p in scan.files) == ["old.bin", "old2.bin"], [p.name for p in scan.files])
        res = cleaner.clean([scan])
        check("tisztító: törlés, a gyökér és a friss fájl marad",
              res.deleted == 2 and (root / "fresh.bin").exists() and root.exists(), vars(res))
        [jscan] = cleaner.scan([cleaner.Target("j", "j", ("%GB_SYSTEST_JROOT%",))])
        check("tisztító: junction gyökérmappát nem szkennel", jscan.files == [])
        check("tisztító: a junction mögötti fájl érintetlen", (outside / "precious.txt").exists())
    finally:
        for link in links:
            if os.path.lexists(link):
                os.rmdir(link)  # a junctiont rmdir bontja, a célt nem követi
        shutil.rmtree(base, ignore_errors=True)


@test()
def legacy_import():
    key = r"Software\GameBoosterSystemTest"
    winapi.reg_write("HKCU", key, "Value", 1, winreg.REG_DWORD)  # amit a „v2” létrehozott
    folder = Path(tempfile.mkdtemp(prefix="gb-v2-"))
    storage.write_json_atomic(folder / "registry_snapshot.json", {
        "test": {"Value": {"value": None, "type": None, "key": key, "hive": "HKCU"}}})
    try:
        j = journal("legacy")
        n = legacy.import_v2(j, folder)
        check("v2 import: a mentés a naplóba kerül",
              n == 1 and (folder / "registry_snapshot.json.imported").exists(), n)
        j.revert()
        check("v2 import: visszaállítás törli a v2 által létrehozott értéket",
              raw("HKCU", key, "Value") == (None, None))
    finally:
        winapi.reg_delete("HKCU", key, "Value")
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except OSError:
            pass
        shutil.rmtree(folder, ignore_errors=True)


# ── Admin rész ──────────────────────────────────────────────

@test(admin=True)
def hklm_tweaks():
    for t in tweaks.TWEAKS:
        if any(v.hive == "HKLM" for v in t.values):
            _tweak_round_trip(t, journal(f"tweak-{t.key}"))


@test(admin=True)
def services_round_trip():
    names = [s.name for s in services.SERVICES]
    before = {n: (winapi.service_start_type(n), winapi.service_running(n)) for n in names}
    j = journal("services")
    changes = services.plan(names)
    out = j.apply(changes)
    check("szolgáltatások: alkalmazás", not out.failed and changes, out.summary("alkalmazva"))
    wrong = {c.meta["name"]: winapi.service_start_type(c.meta["name"]) for c in changes
             if winapi.service_start_type(c.meta["name"]) != c.after}
    check("szolgáltatások: a célérték beállt", not wrong, wrong)
    check("szolgáltatások: ismételt terv üres", services.plan(names) == [])
    out = j.revert()
    diff = {}
    for _ in range(10):  # a szolgáltatások indulása aszinkron
        time.sleep(2)
        after = {n: (winapi.service_start_type(n), winapi.service_running(n)) for n in names}
        diff = {n: (before[n], after[n]) for n in names if before[n] != after[n]}
        if not diff:
            break
    check("szolgáltatások: visszaállítás (indítási típus és futás)", not out.failed and not diff,
          diff or {n: v for n, v in before.items()})


@test(admin=True)
def power_round_trip():
    before, overlay_before = winapi.active_power_scheme(), winapi.power_overlay()
    settings = dict(storage.SETTINGS_DEFAULTS)
    created = None
    try:
        try:
            created = power.add_ultimate(settings)
            check("energiaséma: Ultimate Performance létrehozva", created in winapi.power_schemes(), created)
        except OSError as e:
            check("energiaséma: Ultimate nem hozható létre, marad a tartalék", True, e)
        j = journal("power")
        changes = power.plan(settings, "systest")
        out = j.apply(changes)
        if changes and changes[0].kind == "power":
            check("energiaséma: átváltás", not out.failed and winapi.active_power_scheme() == changes[0].after,
                  changes[0].label)
        elif changes:
            check("energiamód: Legjobb teljesítmény", not out.failed and winapi.power_overlay() == changes[0].after)
        else:
            check("energiaséma: már a cél séma aktív", True, before)
        j.revert()
        check("energiaséma: visszaállítás",
              winapi.active_power_scheme() == before and winapi.power_overlay() == overlay_before,
              winapi.active_power_scheme())
    finally:
        if created and winapi.active_power_scheme() != created:
            winapi.run(["powercfg", "-delete", created])


@test(admin=True)
def dns_round_trip():
    adapters = network.adapters()
    if not adapters:
        check("DNS: nincs aktív fizikai adapter, kihagyva", True)
        return
    a = adapters[0]
    j = journal("dns")
    out = j.apply([network.plan_dns(a, ["1.1.1.1", "1.0.0.1"])])
    now = next(x for x in network.adapters() if x.guid == a.guid)
    check("DNS: Cloudflare beállítva", not out.failed and now.static_dns == ["1.1.1.1", "1.0.0.1"]
          and now.dns[:2] == ["1.1.1.1", "1.0.0.1"], now)
    j.revert()
    now = next(x for x in network.adapters() if x.guid == a.guid)
    check("DNS: visszaállítás", now.static_dns == a.static_dns and now.dns == a.dns, now)


@test(admin=True)
def restore_point_info():
    _, message = restore_point.create()
    check("visszaállítási pont (tájékoztató)", True, message)


@test(admin=True)
def real_cleaning():
    if not SANDBOX:
        check("valódi tisztítás: csak --sandbox módban fut", True)
        return
    scans = cleaner.scan(cleaner.TARGETS)
    total = sum(s.size for s in scans)
    res = cleaner.clean(scans)
    check("valódi tisztítás: lefut, a zárolt fájlokat kihagyja",
          res.deleted + res.skipped == sum(len(s.files) for s in scans),
          f"{total} bájt talált, {res.freed} törölve, {res.skipped} kihagyva")


@test(admin=True)
def ui_apply_and_revert():
    from gamebooster.ui import app as app_mod
    app_mod.confirm = lambda *a, **k: True  # a megerősítő ablakot automatikusan elfogadjuk
    app = app_mod.App()
    hags = next(t for t in tweaks.TWEAKS if t.key == "hags")
    path = hags.values[0]
    before = raw(path.hive, path.path, path.name)
    state = {}

    def finish():
        app.sampler.stop()
        app.watcher.stop()
        app.destroy()

    def reverted(out):
        state["reverted"] = out
        app.after(300, finish)

    def applied(out):
        state["applied"] = out
        app.show("history")
        app.after(1500, lambda: (screenshot(app, OUT / "ui-history.png"),
                                 app.revert(app.journal.entries(), done=reverted)))

    app.after(2000, lambda: app.apply(tweaks.plan(hags), "HAGS", done=applied))
    app.after(300_000, finish)  # biztonsági időkorlát
    app.mainloop()
    applied_out, reverted_out = state.get("applied"), state.get("reverted")
    check("UI: alkalmazás megerősítés után", applied_out and not applied_out.failed and applied_out.ok,
          applied_out.summary("alkalmazva") if applied_out else "nem futott le")
    check("UI: visszaállítás az eredetire", reverted_out and not reverted_out.failed
          and raw(path.hive, path.path, path.name) == before)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # a fájlba irányított kimenet ne a konzol kódlapján menjen
    print(f"GameBooster rendszerteszt; admin: {ADMIN}, sandbox: {SANDBOX}, kimenet: {OUT}", flush=True)
    for fn, admin in TESTS:
        if admin and not ADMIN:
            results.append({"check": fn.__name__, "ok": None, "detail": "kihagyva: admin kell"})
            print(f"KIHAGYVA {fn.__name__} (admin kell)", flush=True)
            continue
        try:
            fn()
        except Exception:
            check(f"{fn.__name__}: váratlan hiba", False, traceback.format_exc())
    (OUT / "results.json").write_text(json.dumps({"admin": ADMIN, "results": results},
                                                 ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [r for r in results if r["ok"] is False]
    print(f"\n{len(results)} ellenőrzés, {len(failed)} hiba", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
