"""A paletta szövegpárjai WCAG AA kontrasztúak mindkét témában."""
import pytest

from gamebooster.ui.theme import DARK, LIGHT

# (előtér, háttér): minden pár, amit a felület szövegként kirajzol
TEXT_PAIRS = [
    ("text", "bg"), ("text", "surface"), ("muted", "bg"), ("muted", "surface"),
    ("subtle", "bg"), ("subtle", "surface"), ("accent", "bg"), ("accent", "surface"),
    ("hero_text", "hero"), ("hero_muted", "hero"), ("hero_link", "hero"),
    ("on_status", "success"), ("on_status", "warning"), ("on_status", "danger"), ("on_status", "accent"),
]


def _luminance(hex_color: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(int(hex_color[i:i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast_formula():
    assert contrast("#000000", "#FFFFFF") == pytest.approx(21)
    assert contrast("#777777", "#777777") == pytest.approx(1)


@pytest.mark.parametrize("palette", [DARK, LIGHT], ids=["dark", "light"])
@pytest.mark.parametrize(("fg", "bg"), TEXT_PAIRS)
def test_text_pairs_meet_aa(palette, fg, bg):
    assert contrast(palette[fg], palette[bg]) >= 4.5


@pytest.mark.parametrize(("palette", "line"), [(DARK, "accent_hi"), (LIGHT, "accent")], ids=["dark", "light"])
def test_chart_line_is_visible(palette, line):
    # Nem szöveges grafikai elem: AA szerint 3:1 kell (components.Sparkline vonala)
    assert contrast(palette[line], palette["surface"]) >= 3
