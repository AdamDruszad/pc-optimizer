import os
import socket
import subprocess
import threading
import time

import psutil
import pytest

from gamebooster.core.journal import Change, Journal
from gamebooster.optimizers import cleaner, game_mode, network, startup


def _touch(path, age_hours=0, size=10):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    t = time.time() - age_hours * 3600
    os.utime(path, (t, t))


@pytest.fixture
def cache(tmp_path, monkeypatch):
    root = tmp_path / "cache"
    _touch(root / "old.tmp", age_hours=48)
    _touch(root / "sub" / "old2.tmp", age_hours=48)
    _touch(root / "fresh.tmp")
    monkeypatch.setenv("GB_TEST_CACHE", str(root))
    return root


def test_scan_respects_age_and_clean_keeps_root(cache):
    target = cleaner.Target("t", "Teszt", ("%GB_TEST_CACHE%",), min_age_hours=24)
    [scan] = cleaner.scan([target])
    assert sorted(p.name for p in scan.files) == ["old.tmp", "old2.tmp"]

    result = cleaner.clean([scan])
    assert (result.deleted, result.freed) == (2, 20)
    assert (cache / "fresh.tmp").exists() and not (cache / "sub").exists() and cache.exists()


def test_scan_does_not_follow_junctions(cache, tmp_path):
    outside = tmp_path / "outside"
    _touch(outside / "precious.txt", age_hours=48)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(cache / "link"), str(outside)],
                   check=True, capture_output=True)
    target = cleaner.Target("t", "Teszt", ("%GB_TEST_CACHE%",))
    [scan] = cleaner.scan([target])
    cleaner.clean([scan])
    assert (outside / "precious.txt").exists()


def test_junction_root_is_skipped(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    _touch(outside / "precious.txt", age_hours=48)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(tmp_path / "cache"), str(outside)],
                   check=True, capture_output=True)
    monkeypatch.setenv("GB_TEST_CACHE", str(tmp_path / "cache"))
    [scan] = cleaner.scan([cleaner.Target("t", "Teszt", ("%GB_TEST_CACHE%",))])
    assert scan.files == []


def test_startup_approved_bytes_match_task_manager(monkeypatch):
    assert startup.approved_value(True) == bytes([2]) + bytes(11)
    disabled = startup.approved_value(False)
    assert disabled[:4] == bytes([3, 0, 0, 0]) and len(disabled) == 12
    values = {"On": bytes([2]) + bytes(11), "Off": disabled}
    monkeypatch.setattr(startup.winapi, "reg_read", lambda h, k, n, *a: (values.get(n), 3))
    assert startup._enabled("HKCU", "k", "On") and not startup._enabled("HKCU", "k", "Off")
    assert startup._enabled("HKCU", "k", "Missing")


def test_game_mode_never_touches_protected_processes(monkeypatch):
    settings = {"game_power_plan": False, "game_priority": False,
                "background_apps": ["svchost.exe", "audiodg.exe"]}
    assert game_mode.plan(settings, None) == []


def test_game_mode_raises_own_process_priority_plan():
    settings = {"game_power_plan": False, "game_priority": True, "background_apps": []}
    me = psutil.Process()
    [change] = game_mode.plan(settings, me)
    assert change.after == psutil.HIGH_PRIORITY_CLASS and change.meta["pid"] == me.pid


def test_manual_stop_is_not_restarted_by_auto_mode(tmp_path, monkeypatch):
    journal = Journal(tmp_path / "j.json")
    settings = {"auto_game_mode": True, "games": [{"exe": "game.exe"}],
                "game_power_plan": False, "game_priority": False, "background_apps": []}
    game = psutil.Process()  # a futó tesztfolyamat játssza a játékot
    monkeypatch.setattr(game_mode, "find_running", lambda names: game)
    events = []
    watcher = game_mode.GameWatcher(journal, lambda: settings, lambda *e: events.append(e[0]))

    watcher._tick()
    watcher.end_session()
    watcher._tick()
    assert events == ["start", "stop"]


def test_dns_plan_and_latency_to_local_server():
    adapter = network.Adapter("Ethernet", 7, "{G}", ["10.0.0.1"], [])
    change = network.plan_dns(adapter, ["1.1.1.1", "1.0.0.1"])
    assert (change.before, change.after, change.meta["index"]) == ([], ["1.1.1.1", "1.0.0.1"], 7)
    assert network.plan_dns(adapter, []) is None

    server = socket.create_server(("127.0.0.1", 0))
    threading.Thread(target=lambda: [server.accept()[0].close() for _ in range(3)],
                     daemon=True).start()
    result = network.tcp_latency("127.0.0.1", server.getsockname()[1], count=3)
    server.close()
    assert len(result.samples) == 3 and result.lost == 0 and "átlag" in result.summary
