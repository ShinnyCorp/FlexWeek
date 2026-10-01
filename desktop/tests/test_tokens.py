"""The shared system, checked by numbers (decision 10 of 0.17's plan) in all ten looks.

Colours are measured in OKLab, the space the category family is chosen in; a distance is OKLab's
times 100. Colour blindness is Machado, Oliveira and Fernandes (2009) at full severity, applied to
linear sRGB.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from itertools import product
from pathlib import Path

import pytest

from desktop.native.calendar import CATEGORIES
from desktop.native.layouts.registry import MATCH, tokens_for
from desktop.native.look import (
    ACCENTS,
    LOOK_KNOBS,
    block_paint,
    category_paint,
    contrast,
    mix,
    pack_stylesheet,
    resolved_palette,
)
from desktop.native.tokens import (
    TEXT_SCALE,
    TYPE_PT,
    WEIGHT_NUMBER,
    WEIGHT_REGULAR,
    WEIGHT_STRONG,
    family_colours,
    linear_rgb,
    oklab,
    oklab_from_linear,
    type_pt,
)


def preset(name: str) -> dict:
    return {"preset": name, "knobs": {}}


# Each look as a student reaches it, on the device setting that goes with it. A preset is the same
# look on any pack, so each is reached from the device's opposite setting too.
LOOKS = {
    "Light": ("light-frost", False, None),
    "Dark": ("dark-frost", True, None),
    "High contrast": ("system", False, preset("high-contrast")),
    "Slate": ("slate", False, None),
    "Nocturne": ("nocturne", True, None),
    "Paper": ("system", True, preset("paper")),
    "Ink": ("system", False, preset("ink")),
    "Terminal": ("slate", False, preset("terminal")),
    "Poster": ("nocturne", True, preset("poster")),
    "Pastel": ("system", True, preset("pastel")),
}
CASES = [
    (name, surface, accent)
    for name, surface, accent in product(LOOKS, LOOK_KNOBS["surface"], ACCENTS)
]
DEUTERANOPIA = (
    (0.367322, 0.860646, -0.227968),
    (0.280085, 0.672501, 0.047413),
    (-0.011820, 0.042940, 0.968881),
)


def look_for(name: str, surface: str = "layered") -> dict:
    look = LOOKS[name][2] or {"preset": "default", "knobs": {}}
    return {**look, "knobs": {**look["knobs"], "surface": surface}}


def palette_for(name: str, surface: str = "layered", accent: str = "default") -> dict:
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
        worked = family_colours(
            info["hue"], grey=key == "free", homework=key == "assignments", sleep=key == "sleep",
        )
        held = {"light": (info["color"], info["mark"]), "dark": info["dark"], "contrast": info["contrast"]}
        assert held == worked, key


@pytest.mark.parametrize("name", LOOKS)
def test_every_category_fill_has_one_lightness(name: str) -> None:
    """No category shouts over another: every fill within 0.02 of the others in lightness."""
    for surface in LOOK_KNOBS["surface"]:
        palette = palette_for(name, surface)
        lightness = {key: oklab(category_paint(key, palette)[0])[0]
                     for key in CATEGORIES if key != "sleep"}
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
            # The accent's own words: today's name, the side panel's headings, links.
            ("accent", "window"),
            ("accent", "panel"),
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
    r"(QMainWindow|QDialog|QFrame, QGroupBox|#(settingsPage|settingsRail|settingsCard|dialogCard|sheetCard|"
    r"setupRail|setupNav|setupChoice|setupGroup|authCard|weekTable|dayView|planReview|toast|commandBox))\b"
)


@pytest.mark.parametrize(("name", "surface", "accent"), CASES)
def test_the_accent_is_never_a_page_card_or_wash(name: str, surface: str, accent: str) -> None:
    """Decision 1: the accent marks controls and is never spread over anything larger. Gold once
    turned today's column khaki, and the setup cards were washed blue."""
    palette = palette_for(name, surface, accent)
    reference = palette_for(name, surface, "default")
    for key in ("window", "panel", "field", "grid"):
        assert palette[key] == reference[key], key
    pack, dark, _look = LOOKS[name]
    sheet = pack_stylesheet(pack, dark, look_for(name, surface), accent, palette)
    painted = [
        (selector.strip(), colour)
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", sheet)
        if LARGE.search(selector)
        for colour in re.findall(r"background: (#[0-9a-f]{6})", body)
    ]
    assert painted, "the pattern found no page or card to check"
    probe = {**palette, "accent": "#ff00ff"}
    reference_sheet = pack_stylesheet(pack, dark, look_for(name, surface), accent, probe)
    reference_painted = [
        (selector.strip(), colour)
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", reference_sheet)
        if LARGE.search(selector)
        for colour in re.findall(r"background: (#[0-9a-f]{6})", body)
    ]
    assert painted == reference_painted
    # A design in Match my look wears the look: its cards are not the accent either.
    match = tokens_for("clay", MATCH, palette)
    large = [key for key in match if key.startswith("card_") or key in {"bg", "surface"}]
    reference_match = tokens_for("clay", MATCH, probe)
    assert {key: match[key] for key in large} == {key: reference_match[key] for key in large}


@pytest.mark.parametrize(("name", "surface", "accent"), CASES)
def test_the_now_line_and_the_selection_show_over_every_block(name: str, surface: str, accent: str) -> None:
    """The drawn Now and selection shades contrast with blocks without changing the chosen accent."""
    palette = palette_for(name, surface, accent)
    faint = []
    for key, mode, shade in product(CATEGORIES, LOOK_KNOBS["blocks"], ("now", "selection")):
        fill, mark = category_paint(key, palette)
        drawn = block_paint({"preset": "default", "knobs": {"blocks": mode}}, palette, fill, "locked", mark)
        if contrast(palette[shade], drawn["fill"]) < 3.0:
            faint.append(f"{key} {mode} {shade} {contrast(palette[shade], drawn['fill']):.2f}")
    assert faint == [], (name, surface, accent)



SIZE = re.compile(r"font-size: ([^;}]+)")
WEIGHT = re.compile(r"font-weight: ([^;}]+)")
# control_rules only writes the images' paths into the sheet.
ART = defaultdict(lambda: "art.png")


@pytest.mark.parametrize(("name", "text"), list(product(LOOKS, TEXT_SCALE)))
def test_every_font_size_and_weight_in_the_stylesheet_is_on_the_scale(name: str, text: str) -> None:
    """Decision 4: caption, body, heading, title and display, which the Text knob scales together, and
    two weights, with 700 only for display numbers. The focus screen's countdown is the one size
    drawn beyond the scale, and it is a number."""
    pack, dark, _look = LOOKS[name]
    look = look_for(name)
    look = {**look, "knobs": {**look["knobs"], "text": text}}
    palette = resolved_palette(pack, dark, look)
    sheet = pack_stylesheet(pack, dark, look, "default", palette, ART)
    scale = {type_pt(role, text) for role in TYPE_PT}
    display = type_pt("display", text)
    off = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", sheet):
        where = selector.strip()
        # "11pt" and "11.0pt" are one size.
        sizes = [float(size.strip().removesuffix("pt")) for size in SIZE.findall(body)]
        off += [f"{where}: {size:g}pt" for size in sizes if size not in scale]
        for weight in (weight.strip() for weight in WEIGHT.findall(body)):
            number = weight == str(WEIGHT_NUMBER) and sizes == [display]
            if weight not in {str(WEIGHT_REGULAR), str(WEIGHT_STRONG)} and not number:
                off.append(f"{where}: weight {weight}")
    assert SIZE.search(sheet) and WEIGHT.search(sheet), "the patterns found nothing to check"
    assert off == [], (name, text)


def test_the_text_knob_scales_all_five_sizes() -> None:
    """Small and Large move every size together, so a heading stays a heading at any text size."""
    for role in TYPE_PT:
        assert type_pt(role, "small") < type_pt(role, "normal") < type_pt(role, "large"), role
    assert [type_pt(role, "normal") for role in TYPE_PT] == [11, 13, 15, 20, 28]


# The only modules that may set a font's size or weight: the stylesheet and the scale's own helpers.
# ring.py fits the focus screen's countdown numeral to its ring, beyond the scale on purpose, as
# 0.16's countdown was; its other words are the scale's.
SCALE_KEEPERS = {"look.py", "fonts.py", "ring.py"}
OWN_FONT = re.compile(r"\.set(Bold|Weight|PointSize|PointSizeF|PixelSize)\(|font-size|font-weight")


def test_no_widget_outside_the_designs_sets_a_size_or_weight_of_its_own() -> None:
    """A widget that sets its own size or weight is off the scale however the scale changes. The
    designs under layouts/ keep their own sizes until their lanes redraw them."""
    native = Path(__file__).resolve().parents[1] / "native"
    found = [
        f"{path.relative_to(native)}:{number}: {line.strip()}"
        for path in sorted(native.rglob("*.py"))
        if path.name not in SCALE_KEEPERS and "layouts" not in path.parts
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if OWN_FONT.search(line) and not line.strip().startswith("#")
    ]
    assert found == []


@pytest.mark.parametrize("name", LOOKS)
def test_every_stylesheet_is_whole_rules_that_qt_can_parse(name: str) -> None:
    """Qt drops a whole stylesheet it cannot parse, with only a line on the console. A stray
    declaration left by a merge once did that to the window in every look, and every test still
    passed: the window was drawn in Qt's own grey."""
    for text in ("small", "normal", "large"):
        pack, dark, look = LOOKS[name]
        look = {**(look or {"preset": "default", "knobs": {}}), "knobs": {"text": text}}
        sheet = pack_stylesheet(pack, dark, look, "default", resolved_palette(pack, dark, look))
        leftover = re.sub(r"[^{}]+\{[^{}]*\}", "", sheet)
        assert leftover.strip() == "", (name, text, leftover[:200])
