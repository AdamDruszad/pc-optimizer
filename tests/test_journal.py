"""Változásnapló: a rendszerhez nem nyúl, a 'fake' típus egy dict-be ír."""
import json
import winreg

import pytest

from gamebooster.core import journal as jmod
from gamebooster.core import legacy, storage
from gamebooster.core.journal import Change, Journal


class FakeSystem(dict):
    """A 'fake' változások ide írnak; a `fail` halmazban lévő célpont hibát dob."""
    fail: set


@pytest.fixture
def system(monkeypatch):
    state = FakeSystem(x="orig")
    state.fail = set()

    def setter(field):
        def apply(c):
            if c.target in state.fail:
                raise OSError("hozzáférés megtagadva")
            state[c.target] = getattr(c, field)
        return apply

    monkeypatch.setitem(jmod.HANDLERS, "fake", (setter("after"), setter("before")))
    return state


def change(target="x", before="orig", after="new"):
    return Change("fake", target, before, after, f"{target} → {after}", "test")


def test_apply_then_revert_restores_original(tmp_path, system):
    j = Journal(tmp_path / "j.json")
    assert not j.apply([change()]).failed
    assert system["x"] == "new"

    assert not j.revert().failed
    assert system["x"] == "orig"
    assert j.entries() == []


def test_second_apply_keeps_first_original(tmp_path, system):
    j = Journal(tmp_path / "j.json")
    j.apply([change(after="new")])
    j.apply([change(before="new", after="newer")])  # a második terv már a módosított értéket látja

    assert [c.before for c in j.entries()] == ["orig"]
    j.revert()
    assert system["x"] == "orig"


def test_journal_is_written_before_the_change(tmp_path, monkeypatch, system):
    path = tmp_path / "j.json"
    seen = []
    monkeypatch.setitem(jmod.HANDLERS, "fake",
                        (lambda c: seen.append(json.loads(path.read_text(encoding="utf-8"))),
                         lambda c: None))
    Journal(path).apply([change()])
    assert seen[0][0]["before"] == "orig"


def test_failed_apply_leaves_no_entry(tmp_path, system):
    system.fail.add("x")
    j = Journal(tmp_path / "j.json")
    out = j.apply([change()])
    assert out.failed and j.entries() == []


def test_failed_revert_keeps_entry_and_survives_restart(tmp_path, system):
    path = tmp_path / "j.json"
    j = Journal(path)
    j.apply([change("x"), change("y", before=None)])
    system.fail.add("x")

    out = j.revert()
    assert [c.target for c, _ in out.failed] == ["x"]
    assert [c.target for c in Journal(path).entries()] == ["x"]


def test_corrupt_journal_is_set_aside(tmp_path):
    path = tmp_path / "j.json"
    path.write_text("{nem json", encoding="utf-8")
    assert Journal(path).entries() == []
    assert any(p.name.startswith("j.json.corrupt-") for p in tmp_path.iterdir())


def test_registry_binary_values_round_trip_as_hex(monkeypatch):
    written = {}
    monkeypatch.setattr(jmod.winapi, "reg_read", lambda *a: (b"\x03\x00", winreg.REG_BINARY))
    monkeypatch.setattr(jmod.winapi, "reg_write",
                        lambda hive, path, name, value, t, wow: written.update(v=value))
    c = jmod.registry_change("HKCU", r"Software\X", "App", b"\x02\x00", winreg.REG_BINARY, "x", "t")
    assert (c.before, c.after) == ("0300", "0200")

    jmod.HANDLERS["registry"][1](c)
    assert written["v"] == b"\x03\x00"


def test_registry_change_is_none_when_already_set(monkeypatch):
    monkeypatch.setattr(jmod.winapi, "reg_read", lambda *a: (1, winreg.REG_DWORD))
    assert jmod.registry_change("HKCU", "K", "N", 1, winreg.REG_DWORD, "x", "t") is None


def test_v2_files_are_imported_and_renamed(tmp_path, monkeypatch):
    monkeypatch.setattr(legacy.winapi, "service_start_type", lambda n: "disabled")
    monkeypatch.setattr(legacy.winapi, "reg_read", lambda *a: (1, winreg.REG_DWORD))
    storage.write_json_atomic(tmp_path / "original_state.json", {
        "WSearch": {"start_type": "(DELAYED)", "running": "RUNNING"},
        "Gone": {"start_type": "UNKNOWN", "running": "UNKNOWN"},
    })
    storage.write_json_atomic(tmp_path / "registry_snapshot.json", {
        "nagle": {"{GUID}_TCPNoDelay": {"value": None, "type": None,
                                        "key": r"SYSTEM\Tcpip\{GUID}", "hive": "HKLM"}},
    })
    j = Journal(tmp_path / "j.json")

    assert legacy.import_v2(j, tmp_path) == 2
    by_target = {c.target: c for c in j.entries()}
    assert by_target["service:WSearch"].before == "delayed-auto"
    assert by_target["service:WSearch"].meta["was_running"] is True
    assert by_target[r"HKLM\SYSTEM\Tcpip\{GUID}\TCPNoDelay"].before is None
    assert (tmp_path / "original_state.json.imported").exists()
