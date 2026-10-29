"""A mentés és visszaállítás biztonsága: a rendszert nem érintik, a Windows-hívások hamisítva."""
import json
import os

import pytest

from modules import hw_optimizer, registry_tweaks
from modules.hardware_detector import HardwareProfile
from modules.profile_manager import BoostProfile
from utils import state_manager


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    path = tmp_path / "original_state.json"
    monkeypatch.setattr(state_manager, "_get_state_file", lambda: str(path))
    return path


class Calls(list):
    """Rögzített parancsok; a `fail` halmazban lévő szolgáltatás `sc config` hívása hibát ad."""
    fail: set


@pytest.fixture
def sc_calls(monkeypatch):
    calls = Calls()
    calls.fail = set()

    def fake_run(args, timeout=10):
        calls.append(args)
        return not (args[:2] == ["sc", "config"] and args[2] in calls.fail), ""

    monkeypatch.setattr(hw_optimizer, "_run", fake_run)
    monkeypatch.setattr(hw_optimizer, "is_admin", lambda: True)
    return calls


def test_start_type_name_keeps_delayed_start():
    assert state_manager.start_type_name(2, 1) == "DELAYED_AUTO_START"
    assert state_manager.start_type_name(2, 0) == "AUTO_START"
    assert state_manager.start_type_name(3, 0) == "DEMAND_START"
    assert state_manager.start_type_name(4, 0) == "DISABLED"
    assert state_manager.start_type_name(9, 0) == "UNKNOWN"


def test_second_boost_keeps_original_service_state(state_file, monkeypatch):
    current = {"WSearch": "DELAYED_AUTO_START", "Missing": "UNKNOWN"}
    monkeypatch.setattr(state_manager, "get_service_status", lambda s: current[s])
    monkeypatch.setattr(state_manager, "get_service_running_state", lambda s: "RUNNING")

    state_manager.save_original_state(["WSearch", "Missing"])
    current["WSearch"] = "DISABLED"  # az első Boost letiltotta
    state_manager.save_original_state(["WSearch"])

    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved == {"WSearch": {"start_type": "DELAYED_AUTO_START", "running": "RUNNING"}}


def test_restore_uses_delayed_auto_and_keeps_failed_entries(state_file, sc_calls):
    state_manager.write_state({
        "WSearch":   {"start_type": "DELAYED_AUTO_START", "running": "RUNNING"},
        "MapsBroker": {"start_type": "(DELAYED)", "running": "STOPPED"},  # v2.1 formátum
        "DiagTrack": {"start_type": "AUTO_START", "running": "RUNNING"},
    })
    sc_calls.fail.add("DiagTrack")

    hw_optimizer.restore_original()

    assert ["sc", "config", "WSearch", "start=", "delayed-auto"] in sc_calls
    assert ["sc", "config", "MapsBroker", "start=", "delayed-auto"] in sc_calls
    assert list(json.loads(state_file.read_text(encoding="utf-8"))) == ["DiagTrack"]


def test_restore_deletes_state_when_everything_succeeds(state_file, sc_calls):
    state_manager.write_state({"DiagTrack": {"start_type": "AUTO_START", "running": "RUNNING"}})
    hw_optimizer.restore_original()
    assert not state_file.exists()


def test_boost_aborts_when_backup_fails(sc_calls, monkeypatch):
    def broken_save(services):
        raise OSError("lemez megtelt")

    monkeypatch.setattr(hw_optimizer, "save_original_state", broken_save)
    profile = BoostProfile(stop_services=["DiagTrack"], throttle_background=False)

    hw_optimizer.apply_boost(HardwareProfile(), profile)

    assert sc_calls == []


def test_boost_saves_the_services_it_disables(sc_calls, monkeypatch):
    saved = []
    monkeypatch.setattr(hw_optimizer, "save_original_state", saved.extend)
    profile = BoostProfile(stop_services=["CustomSvc"], throttle_background=False)

    hw_optimizer.apply_boost(HardwareProfile(), profile)

    assert saved == ["CustomSvc"]
    assert ["sc", "config", "CustomSvc", "start=", "disabled"] in sc_calls


@pytest.fixture
def fake_registry(tmp_path, monkeypatch):
    reg = {}
    monkeypatch.setattr(registry_tweaks, "_get_snapshot_file", lambda: str(tmp_path / "snap.json"))
    monkeypatch.setattr(registry_tweaks, "_reg_read",
                        lambda hive, key, name: (reg[(key, name)], 4) if (key, name) in reg else (None, None))

    def write(hive, key, name, value, reg_type=4):
        reg[(key, name)] = value
        return True

    def delete(hive, key, name):
        reg.pop((key, name), None)
        return True

    monkeypatch.setattr(registry_tweaks, "_reg_write", write)
    monkeypatch.setattr(registry_tweaks, "_reg_delete_value", delete)
    return reg


def _only(**enabled):
    off = dict(game_scheduling=False, system_profile=False, win32_priority=False, hags=False,
               game_mode=False, disable_gamebar=False, nagle=False, mouse_latency=False)
    return registry_tweaks.RegistryTweakConfig(**{**off, **enabled})


def test_second_registry_apply_keeps_original_value(fake_registry):
    key = (registry_tweaks._PRIORITY_CONTROL_KEY, "Win32PrioritySeparation")
    fake_registry[key] = 2

    registry_tweaks.apply_registry_tweaks(_only(win32_priority=True))
    registry_tweaks.apply_registry_tweaks(_only(win32_priority=True))
    assert fake_registry[key] == 0x26

    registry_tweaks.restore_registry_tweaks()
    assert fake_registry[key] == 2
    assert not registry_tweaks.has_registry_snapshot()


def test_nagle_restore_targets_real_value_names(fake_registry, monkeypatch):
    guid = "{11111111-2222-3333-4444-555555555555}"
    iface = f"{registry_tweaks._TCPIP_INTERFACES_KEY}\\{guid}"
    monkeypatch.setattr(registry_tweaks, "_get_network_adapter_guids", lambda: [guid])
    fake_registry[(iface, "DhcpIPAddress")] = "192.168.1.10"

    registry_tweaks.apply_registry_tweaks(_only(nagle=True))
    assert fake_registry[(iface, "TCPNoDelay")] == 1

    registry_tweaks.restore_registry_tweaks()
    assert (iface, "TCPNoDelay") not in fake_registry
    assert (iface, "TcpAckFrequency") not in fake_registry


def test_registry_restore_keeps_failed_values(fake_registry, monkeypatch):
    key = (registry_tweaks._PRIORITY_CONTROL_KEY, "Win32PrioritySeparation")
    fake_registry[key] = 2
    registry_tweaks.apply_registry_tweaks(_only(win32_priority=True))

    monkeypatch.setattr(registry_tweaks, "_reg_write", lambda *a: False)
    registry_tweaks.restore_registry_tweaks()

    assert registry_tweaks.has_registry_snapshot()


def test_iter_processes_gives_each_caller_its_own_info():
    from utils.procs import iter_processes

    a = {p.pid: info for p, info in iter_processes(["name"])}
    b = {p.pid: info for p, info in iter_processes(["memory_info"])}
    me = os.getpid()
    assert a[me]["name"].lower().startswith("python")
    assert "name" not in b[me]  # a második bejárás nem írta felül az elsőt


def test_write_json_atomic_leaves_no_temp_file(tmp_path):
    path = tmp_path / "x.json"
    state_manager.write_json_atomic(str(path), {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert os.listdir(tmp_path) == ["x.json"]
