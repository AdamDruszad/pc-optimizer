import pytest

from gamebooster.ui.app import window_geometry


@pytest.mark.parametrize("screen_w, screen_h, scale", [
    (1280, 960, 1.0), (1366, 768, 1.0), (1920, 1080, 1.25), (1920, 1080, 1.5), (2560, 1440, 1.0),
])
def test_window_stays_above_the_taskbar(screen_w, screen_h, scale):
    width, height, x, y = window_geometry(screen_w, screen_h, scale)
    title_bar, taskbar = round(30 * scale), round(48 * scale)
    assert x >= 0 and x + round(width * scale) <= screen_w
    assert y >= 0 and y + title_bar + round(height * scale) <= screen_h - taskbar


def test_large_screen_keeps_design_size():
    assert window_geometry(2560, 1440, 1.0)[:2] == (1240, 800)
