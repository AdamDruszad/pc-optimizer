import winreg

import pytest

from gamebooster.monitoring import pdh
from gamebooster.optimizers import power, services, tweaks


def test_set_flag_keeps_other_flags():
    f = tweaks.set_flag("SwapEffectUpgradeEnable", "1")
    assert f(None) == "SwapEffectUpgradeEnable=1;"
    assert f("VRROptimizeEnable=0;SwapEffectUpgradeEnable=0;") == \
        "VRROptimizeEnable=0;SwapEffectUpgradeEnable=1;"
    assert tweaks.set_flag("GpuPreference", None)("GpuPreference=2;") is None


@pytest.fixture
def registry(monkeypatch):
    reg = {}
    monkeypatch.setattr(tweaks.winapi, "reg_read",
                        lambda hive, path, name, wow=False: (reg[name], winreg.REG_DWORD)
                        if name in reg else (None, None))
    return reg


def test_missing_value_uses_windows_default(registry):
    game_mode = next(t for t in tweaks.TWEAKS if t.key == "game_mode")
    assert tweaks.is_on(game_mode) and tweaks.plan(game_mode) == []
    registry["AutoGameModeEnabled"] = 0
    assert not tweaks.is_on(game_mode)
    [change] = tweaks.plan(game_mode)
    assert (change.before, change.after) == (0, 1)


def test_services_plan_rejects_names_outside_allowlist():
    with pytest.raises(KeyError):
        services.plan(["mpssvc"])


def test_services_plan_skips_already_set_and_missing(monkeypatch):
    starts = {"DiagTrack": "disabled", "Fax": None, "SysMain": "auto"}
    monkeypatch.setattr(services.winapi, "service_start_type", starts.get)
    monkeypatch.setattr(services.winapi, "service_running", lambda n: True)
    [change] = services.plan(["DiagTrack", "Fax", "SysMain"])
    assert (change.target, change.before, change.after) == ("service:SysMain", "auto", "demand")
    assert change.meta == {"name": "SysMain", "stop": True, "was_running": True}


def test_power_plan_falls_back_to_overlay_on_modern_standby(monkeypatch):
    monkeypatch.setattr(power.winapi, "power_schemes", lambda: {"381b4222-f694-41f0-9685-ff5bb260df2e": "Balanced"})
    monkeypatch.setattr(power.winapi, "active_power_scheme", lambda: "381b4222-f694-41f0-9685-ff5bb260df2e")
    monkeypatch.setattr(power.winapi, "power_overlay", lambda: "00000000-0000-0000-0000-000000000000")
    [change] = power.plan({}, "game_mode")
    assert change.kind == "power_overlay" and change.after == power.BEST_PERFORMANCE_OVERLAY


def test_power_plan_has_no_side_effects(monkeypatch):
    monkeypatch.setattr(power.winapi, "power_schemes", lambda: {power.HIGH: "High"})
    monkeypatch.setattr(power.winapi, "active_power_scheme", lambda: power.HIGH)
    monkeypatch.setattr(power.winapi, "run", lambda *a, **k: pytest.fail("a terv nem futtathat parancsot"))
    assert power.plan({}, "game_mode") == []


def test_gpu_utilization_sums_processes_per_engine():
    engines = {
        "pid_1_luid_0x0_0xA_phys_0_eng_0_engtype_3D": 30.0,
        "pid_2_luid_0x0_0xA_phys_0_eng_0_engtype_3D": 25.0,
        "pid_3_luid_0x0_0xA_phys_0_eng_1_engtype_3D": 40.0,
    }
    assert pdh.gpu_utilization(engines) == 55.0
    assert pdh.gpu_utilization({}) is None
