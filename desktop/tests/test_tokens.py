"""The shared system, checked by numbers (decision 10 of 0.17's plan) in Light, Dark and High contrast.

Colours are measured in OKLab, the space the category family is chosen in; a distance is OKLab's
times 100. Colour blindness is Machado, Oliveira and Fernandes (2009) at full severity, applied to
linear sRGB.
"""

from __future__ import annotations

import math
import re
from itertools import product

import pytest

from desktop.native.calendar import CATEGORIES
from desktop.native.layouts.registry import MATCH, tokens_for
from desktop.native.look import (
    ACCENTS,
    block_paint,
    category_paint,
    contrast,
    mix,
    pack_stylesheet,
    resolved_palette,
)
from desktop.native.tokens import family_colours, linear_rgb, oklab, oklab_from_linear

HIGH_CONTRAST = {"preset": "high-contrast", "knobs": {}}
# Each look as a student reaches it, on the device setting that goes with it.
LOOKS = {
    "Light": ("light-frost", False, None),
    "Dark": ("dark-frost", True, None),
    "High contrast": ("system", False, HIGH_CONTRAST),
}
CASES = [
    (name, surface, accent)
    for name, surface, accent in product(LOOKS, ("frost", "flat"), ACCENTS)
]
DEUTERANOPIA = (
    (0.367322, 0.860646, -0.227968),
    (0.280085, 0.672501, 0.047413),
    (-0.011820, 0.042940, 0.968881),
)


def look_for(name: str, surface: str = "frost") -> dict:
    look = LOOKS[name][2] or {"preset": "default", "knobs": {}}
    return {**look, "knobs": {**look["knobs"], "surface": surface}}


def palette_for(name: str, surface: str = "frost", accent: str = "default") -> dict:
    pack, dark, _look = LOOKS[name]
    return resolved_palette(pack, dark, look_for(name, surface), accent)


def floor_for(palette: dict) -> float:
    return 7.0 if palette["family"] == "contrast" else 4.5


def deuteranope_sees(colour: str) -> tuple[float, float, float]:
    red, green, blue = linear_rgb(colour)
    seen = (min(max(r * red + g * green + b * blue, 0.0), 1.0) for r, g, b in DEUTERANOPIA)
    return oklab_from_linear(*seen)


def test_the_category_colours_are_the_family_worked_out_from_their_hues() -> None:
    """The hex values in calendar.py are what the family's OKLCH gives, so none drifts by hand."""
    for key, info in CATEGORIES.items():
        worked = family_colours(info["hue"], grey=key == "free", homework=key == "assignments")
        held = {"light": (info["color"], info["mark"]), "dark": info["dark"], "contrast": info["contrast"]}
        assert held == worked, key


@pytest.mark.parametrize("name", LOOKS)
def test_every_category_fill_has_one_lightness(name: str) -> None:
    """No category shouts over another: every fill within 0.02 of the others in lightness."""
    for surface in ("frost", "flat"):
        palette = palette_for(name, surface)
        lightness = {key: oklab(category_paint(key, palette)[0])[0] for key in CATEGORIES}
        spread = max(lightness.values()) - min(lightness.values())
        assert spread <= 0.02, (name, surface, {key: round(value, 3) for key, value in lightness.items()})


@pytest.mark.parametrize(("name", "surface", "accent"), CASES)
def test_text_reads_on_every_fill_card_and_page(name: str, surface: str, accent: str) -> None:
    """4.5 to 1, and 7 to 1 in High contrast, for every block's words on every category and every
    word on the page, the cards and the fields."""
    palette = palette_for(name, surface, accent)
    floor = floor_for(palette)
    pairs = [
        (f"{ink} on {paper}", palette[ink], palette[paper])
        for ink, paper in (
            ("text", "window"),
            ("text", "panel"),
            ("text", "field"),
            ("text", "grid"),
            ("muted", "window"),
            ("muted", "panel"),
            ("error", "window"),
            ("error", "panel"),
            ("accent_ink", "accent"),
            ("block_locked_ink", "block_locked"),
            ("block_flex_ink", "block_flex"),
        )
    ]
    for key in CATEGORIES:
        fill, mark = category_paint(key, palette)
        filled = {"preset": "default", "knobs": {"blocks": "filled"}}
        drawn = block_paint(filled, palette, fill, "locked", mark)
        pairs.append((f"{key} block", drawn["ink"], drawn["fill"]))
    failed = [
        f"{where} {contrast(ink, paper):.2f}" for where, ink, paper in pairs if contrast(ink, paper) < floor
    ]
    assert failed == [], (name, surface, accent)


@pytest.mark.parametrize("name", LOOKS)
def test_homework_stands_apart_from_every_other_category_for_a_deuteranope(name: str) -> None:
    """Homework and sports lie side by side all week, and red and green are the pair a deuteranope
    loses. Homework's mark stays at least 20 from every other mark after the simulation."""
    palette = palette_for(name)
    marks = {key: category_paint(key, palette)[1] for key in CATEGORIES}
    homework = deuteranope_sees(marks.pop("assignments"))
    gaps = {key: 100 * math.dist(homework, deuteranope_sees(mark)) for key, mark in marks.items()}
    close = {key: round(gap, 1) for key, gap in gaps.items() if gap < 20}
    assert close == {}, name


def accent_mixes(palette: dict) -> set[str]:
    """Every colour the accent makes laid over one of the look's surfaces, short of the surface."""
    made = set()
    for base in {palette["window"], palette["panel"], palette["field"]}:
        made |= {mix(palette["accent"], base, step / 100) for step in range(1, 101)} - {base}
    return made


# The rules that paint a page, a card or a panel. A background named in one may be neutral or the
# look's own surfaces, never the accent or the accent laid over them.
LARGE = re.compile(
    r"(QMainWindow|QDialog|QFrame, QGroupBox|#(settingsPage|settingsRail|settingsCard|dialogCard|setupRail|"
    r"setupNav|setupChoice|setupGroup|authCard|weekSide|daySide|toast|commandBox))\b"
)


@pytest.mark.parametrize(("name", "surface", "accent"), CASES)
def test_the_accent_is_never_a_page_card_or_wash(name: str, surface: str, accent: str) -> None:
    """Decision 1: the accent marks controls and is never spread over anything larger. Gold once
    turned today's column khaki, and the setup cards were washed blue."""
    palette = palette_for(name, surface, accent)
    washed = accent_mixes(palette) | {palette["accent"]}
    for key in ("window", "panel", "field", "grid"):
        assert palette[key] not in washed, key
    pack, dark, _look = LOOKS[name]
    sheet = pack_stylesheet(pack, dark, look_for(name, surface), accent, palette)
    painted = [
        (selector.strip(), colour)
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", sheet)
        if LARGE.search(selector)
        for colour in re.findall(r"background: (#[0-9a-f]{6})", body)
    ]
    assert painted, "the pattern found no page or card to check"
    assert [(selector, colour) for selector, colour in painted if colour in washed] == []
    # A design in Match my look wears the look: its cards are not the accent either.
    match = tokens_for("clay", MATCH, palette)
    large = [key for key in match if key.startswith("card_") or key in {"bg", "surface"}]
    assert {key: match[key] for key in large if match[key] in washed} == {}
