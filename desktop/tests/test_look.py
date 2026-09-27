"""Look knobs, presets and palettes. Device-only knobs never become preference fields.

The palettes began as the retired web client's CSS custom properties, which had already passed its
readability and accent-distance audits. That client is gone, so there is nothing left to be in step
with: the colours live in look.py now, and what is checked here is the property the audit was for,
that every look a student can reach keeps its text readable. Expected behaviour comes from the
appearance contract.
"""

from __future__ import annotations

import math
from itertools import product

from desktop.native.calendar import CATEGORIES
from desktop.native.look import (
    AA_TEXT,
    ACCENTS,
    DARK_FILL,
    FONT_FAMILIES,
    LOOK_DEFAULTS,
    LOOK_KNOBS,
    LOOK_PRESETS,
    PACKS,
    block_paint,
    contrast,
    effective_look,
    look_menu_items,
    look_menu_token,
    look_menu_value,
    look_overrides,
    mix,
    pack_axis,
    pack_stylesheet,
    parse_look_menu_token,
    preset_knobs,
    readable_ink,
    resolved_pack_theme,
    resolved_palette,
    sanitize_look,
)

# Every look a student can reach: pack, the device's light or dark setting, preset, accent, surface.
EVERY_LOOK = list(product(PACKS, (False, True), LOOK_PRESETS, ACCENTS, LOOK_KNOBS["surface"]))


def look_of(preset: str, **knobs: str) -> dict:
    return {"preset": preset, "knobs": knobs}


def test_the_look_menu_offers_four_looks_then_the_experimental_ones() -> None:
    """Decision 3 of 0.16: System, Light, Dark and High contrast, and the other seven under
    Experimental styles. Every pack and preset is still offered once, so a saved look can be picked."""
    standard, experimental = look_menu_items()
    assert [label for _name, label, _kind in standard] == ["System", "Light", "Dark", "High contrast"]
    assert [label for _name, label, _kind in experimental] == [
        "Nocturne",
        "Slate",
        "Poster",
        "Terminal",
        "Paper",
        "Ink",
        "Pastel",
    ]
    offered = [(kind, name) for name, _label, kind in standard + experimental]
    assert sorted(offered) == sorted(
        [("pack", name) for name in PACKS] + [("preset", name) for name in LOOK_PRESETS if name != "default"]
    )
    assert look_menu_value("nocturne", {"preset": "default", "knobs": {}}) == look_menu_token(
        "pack", "nocturne"
    )
    assert look_menu_value("nocturne", {"preset": "terminal", "knobs": {}}) == look_menu_token(
        "preset", "terminal"
    )
    assert parse_look_menu_token("preset:default") is None
    assert parse_look_menu_token("preset:terminal") == ("preset", "terminal")


def test_unknown_knobs_and_packs_fall_back() -> None:
    clean = sanitize_look({"preset": "neon", "knobs": {"font": "comic", "text": "large"}})
    assert clean["preset"] == "default"
    assert clean["knobs"] == {"text": "large"}
    assert effective_look(clean)["font"] == "sans"
    assert effective_look(clean)["text"] == "large"


def test_terminal_preset_layers_before_knob_overrides() -> None:
    effective = effective_look(sanitize_look(look_of("terminal", text="large")))
    assert effective["font"] == "mono"
    assert effective["corners"] == "sharp"
    assert effective["text"] == "large"


def test_pack_axis_pairs_frost_with_slate_or_nocturne() -> None:
    assert pack_axis("light-frost") == "slate"
    assert pack_axis("dark-frost") == "nocturne"
    assert pack_axis("system") == "system"
    assert resolved_pack_theme("system", True) == "nocturne"
    assert resolved_pack_theme("system", False) == "slate"
    assert resolved_pack_theme("slate", True) == "slate"


def test_every_knob_value_changes_what_is_drawn() -> None:
    """A control that stores a value nothing reads is a quiet click. Three of seven knobs once were."""
    palette = resolved_palette("nocturne", True, None)
    base_sheet = pack_stylesheet("nocturne", True, look_of("default"))
    base_block = block_paint(look_of("default"), palette, "#3b82f6")
    for knob, values in LOOK_KNOBS.items():
        for value in values:
            if value == LOOK_DEFAULTS[knob]:
                continue
            chosen = look_of("default", **{knob: value})
            if knob == "blocks":
                # Calendar blocks are painted per cell, not by the window stylesheet.
                drawn = block_paint(chosen, palette, "#3b82f6")
                assert drawn != base_block, f"blocks={value} draws nothing new"
            else:
                sheet = pack_stylesheet("nocturne", True, chosen)
                assert sheet != base_sheet, f"{knob}={value} draws nothing new"


def test_choosing_a_preset_means_every_one_of_its_knobs() -> None:
    expected = {
        "terminal": {
            "surface": "flat",
            "corners": "sharp",
            "depth": "flat",
            "font": "mono",
            "blocks": "outlined",
            "density": "compact",
            "text": "normal",
        },
        "poster": {
            "surface": "flat",
            "corners": "sharp",
            "depth": "hard",
            "font": "sans",
            "blocks": "filled",
            "density": "compact",
            "text": "large",
        },
        "ink": {
            "surface": "flat",
            "corners": "sharp",
            "depth": "flat",
            "font": "serif",
            "blocks": "edge",
            "density": "comfortable",
            "text": "normal",
        },
        "high-contrast": {
            "surface": "flat",
            "corners": "sharp",
            "depth": "hard",
            "font": "sans",
            "blocks": "outlined",
            "density": "comfortable",
            "text": "large",
        },
        "paper": {
            "surface": "flat",
            "corners": "round",
            "depth": "soft",
            "font": "serif",
            "blocks": "filled",
            "density": "comfortable",
            "text": "normal",
        },
        "pastel": {
            "surface": "frost",
            "corners": "pill",
            "depth": "soft",
            "font": "sans",
            "blocks": "filled",
            "density": "comfortable",
            "text": "normal",
        },
    }
    assert preset_knobs("default") == LOOK_DEFAULTS
    for name, knobs in expected.items():
        assert preset_knobs(name) == knobs
        assert look_overrides(name, knobs) == {}
    assert look_overrides("terminal", {**preset_knobs("terminal"), "depth": "hard"}) == {"depth": "hard"}
    assert look_overrides("default", {**LOOK_DEFAULTS, "corners": "pill"}) == {"corners": "pill"}


# Every pair of window colours the app puts text on.
TEXT_PAIRS = [
    ("text", "window"),
    ("text", "panel"),
    ("text", "field"),
    ("text", "grid"),
    ("muted", "window"),
    ("muted", "panel"),
    ("error", "panel"),
    ("accent_ink", "accent"),
    ("block_locked_ink", "block_locked"),
    ("block_flex_ink", "block_flex"),
]


def test_the_app_asks_for_its_own_inter_first_and_the_system_sans_after() -> None:
    assert FONT_FAMILIES["sans"].split(", ")[0] == "Inter"
    assert FONT_FAMILIES["sans"].endswith("sans-serif")
    assert "font-family: Inter, " in pack_stylesheet("slate", False, look_of("default"))
    # Terminal and Paper keep their own faces for the app's words. The focus screen's countdown is
    # drawn in the sans face whatever the look, so only the app-wide rule is read.
    for name in ("terminal", "paper"):
        app_wide = pack_stylesheet("slate", False, look_of(name)).split("QWidget {")[1].split("}")[0]
        assert "font-family: Inter" not in app_wide, name


def test_cards_are_padded_16_or_8_and_controls_keep_their_size() -> None:
    """Cards and dialogs padded 8 px read as cramped. The padding grew; a button, a field or a list
    kept its own, so none of them grew with it."""
    for density, card, control in (("comfortable", 16, 8), ("compact", 8, 4)):
        sheet = pack_stylesheet("slate", False, look_of("default", density=density))
        frames = sheet.split("QFrame, QGroupBox, QTableWidget, QListWidget {")[1].split("}")[0]
        assert f"padding: {card}px;" in frames, density
        assert f"QAbstractScrollArea {{ padding: {control}px; }}" in sheet, density
        button = sheet.split("QPushButton {")[1].split("}")[0]
        assert f"padding: {control}px {control * 2}px;" in button, density
        field = sheet.split("QLineEdit, QComboBox, QSpinBox, QTimeEdit, QDateTimeEdit {")[1].split("}")[0]
        assert f"padding: {control}px;" in field, density


def test_every_look_keeps_its_text_readable() -> None:
    assert len(EVERY_LOOK) == 5 * 2 * 7 * 5 * 2
    for pack, system_dark, preset, accent, surface in EVERY_LOOK:
        palette = resolved_palette(pack, system_dark, look_of(preset, surface=surface), accent)
        for ink, fill in TEXT_PAIRS:
            ratio = contrast(palette[ink], palette[fill])
            where = f"{pack}/{'dark' if system_dark else 'light'}/{preset}/{accent}/{surface}"
            assert ratio >= AA_TEXT, f"{where}: {ink} on {fill} is {ratio:.2f} to 1"


def test_button_text_comes_from_the_palette_not_a_fixed_white() -> None:
    # White on Terminal's amber was 1.8 to 1. The ink has to be the one paired with the accent.
    sheet = pack_stylesheet("slate", False, look_of("terminal"))
    assert "QPushButton { background: #ffb000; color: #000000;" in sheet
    assert "#ffffff" not in sheet
    dark = pack_stylesheet("nocturne", True, look_of("default"), "gold")
    assert "QPushButton { background: #eab308; color: #0b1224;" in dark


def test_an_accent_always_changes_the_accent() -> None:
    """Sky once equalled the Light frost default, so choosing it did nothing."""
    for pack, system_dark, preset in product(PACKS, (False, True), LOOK_PRESETS):
        plain = resolved_palette(pack, system_dark, look_of(preset))["accent"]
        seen = {plain}
        for accent in ACCENTS:
            if accent == "default":
                continue
            chosen = resolved_palette(pack, system_dark, look_of(preset), accent)["accent"]
            assert chosen not in seen, f"{accent} on {pack}/{preset} repeats {chosen}"
            seen.add(chosen)


def test_ink_follows_the_pack_axis() -> None:
    light = resolved_palette("slate", False, look_of("ink"))
    dark = resolved_palette("nocturne", True, look_of("ink"))
    frost_light = resolved_palette("light-frost", False, look_of("ink"))
    assert light["text"] == frost_light["text"] == "#1a1a1a"
    assert dark["text"] == "#eaeaea"
    assert light["axis"] == "light"
    assert dark["axis"] == "dark"


def test_a_students_accent_wins_over_the_presets_own() -> None:
    assert resolved_palette("slate", False, look_of("terminal"))["accent"] == "#ffb000"
    chosen = resolved_palette("slate", False, look_of("terminal"), "sky")
    # Terminal is a dark look whatever the pack underneath, so it takes the dark-axis sky and its ink.
    assert (chosen["accent"], chosen["accent_ink"]) == ("#38bdf8", "#0b1224")


def test_flat_surface_has_no_raised_panels_and_frost_does() -> None:
    frost = resolved_palette("nocturne", True, look_of("default"))
    flat = resolved_palette("nocturne", True, look_of("default", surface="flat"))
    assert frost["panel"] != frost["window"]
    assert flat["panel"] == flat["window"] == frost["window"]
    assert flat["field"] == flat["window"]


def test_depth_is_drawn_with_edges_because_qt_has_no_shadows() -> None:
    soft = pack_stylesheet("nocturne", True, look_of("default"))
    flat = pack_stylesheet("nocturne", True, look_of("default", depth="flat"))
    hard = pack_stylesheet("nocturne", True, look_of("default", depth="hard"))
    assert "border: 1px solid" in soft and "border: none;" not in soft.split("QHeaderView")[0]
    assert "border: none;" in flat and "1px solid" not in flat
    assert "border-bottom: 4px solid" in hard and "border-right: 4px solid" in hard


def test_a_block_shows_its_category_colour_in_the_place_the_knob_names() -> None:
    palette = resolved_palette("nocturne", True, None)
    blue = "#3b82f6"
    filled = block_paint(look_of("default"), resolved_palette("slate", False, None), blue)
    assert (filled["fill"], filled["outline"], filled["edge"]) == (blue, None, None)
    outlined = block_paint(look_of("default", blocks="outlined"), palette, blue)
    assert (outlined["fill"], outlined["outline"], outlined["edge"]) == (palette["grid"], blue, None)
    assert outlined["ink"] == palette["text"]
    edge = block_paint(look_of("default", blocks="edge"), palette, blue)
    assert (edge["fill"], edge["edge"]) == (palette["panel"], blue)
    # No category: a filled block uses the palette's own block colours, flexible work the warm pair.
    plain = block_paint(look_of("default"), palette, None, "flexible")
    assert (plain["fill"], plain["ink"]) == (palette["block_flex"], palette["block_flex_ink"])
    bare = block_paint(look_of("default", blocks="outlined"), palette, None)
    assert bare["outline"] == palette["block_edge"]
    # A pale fill makes a vanishing outline on a light pack, so an outline or an edge uses the strong mark.
    pale, strong = "#bfdbfe", "#3b82f6"
    light = resolved_palette("slate", False, None)
    assert block_paint(look_of("default"), light, pale, "locked", strong)["fill"] == pale
    outlined_pale = block_paint(look_of("default", blocks="outlined"), palette, pale, "locked", strong)
    assert outlined_pale["outline"] == strong
    assert block_paint(look_of("default", blocks="edge"), palette, pale, "locked", strong)["edge"] == strong


def test_a_filled_block_is_readable_on_every_category_colour() -> None:
    assert len(CATEGORIES) == 8
    for name, category in CATEGORIES.items():
        color = category["color"]
        ratio = contrast(readable_ink(color), color)
        assert ratio >= AA_TEXT, f"{name} {color}: best ink is only {ratio:.2f} to 1"


def test_a_filled_block_on_a_dark_look_is_its_colour_sunk_into_the_panel_with_light_ink() -> None:
    """A pale fill on near-black glared off the page. Every dark look, packs and presets, fills a
    block with the category's strong colour mixed into the panel, and writes on it in white."""
    seen = 0
    for pack, system_dark, preset, accent, surface in EVERY_LOOK:
        palette = resolved_palette(pack, system_dark, look_of(preset, surface=surface), accent)
        if palette["axis"] != "dark":
            continue
        seen += 1
        filled = look_of(preset, blocks="filled")
        for name, category in CATEGORIES.items():
            drawn = block_paint(filled, palette, category["color"], "locked", category["mark"])
            where = f"{pack}/{preset}/{surface} {name}"
            assert drawn["fill"] == mix(category["mark"], palette["panel"], DARK_FILL), where
            assert drawn["ink"] == "#ffffff", where
            assert contrast(drawn["ink"], drawn["fill"]) >= AA_TEXT, where
    assert seen


def test_homework_stands_apart_from_every_other_category() -> None:
    """Activity was pink beside Homework's coral, 14 apart; a student could not tell a club from an
    essay. Homework's pale fill is now at least 20 from every other category's, Activity teal."""
    homework = _lab(CATEGORIES["assignments"]["color"])
    for name, category in CATEGORIES.items():
        if name != "assignments":
            gap = math.dist(homework, _lab(category["color"]))
            assert gap >= 20, f"{name} {category['color']} is {gap:.1f} from Homework"
    assert (CATEGORIES["extra"]["color"], CATEGORIES["extra"]["mark"]) == ("#a5f3fc", "#06b6d4")


def test_every_category_has_a_mark_of_its_own() -> None:
    """These began as the retired web client's category colours. What has to hold now that they live
    only here is that there are eight and no two are the same, or two kinds of block look alike."""
    marks = {name: category["mark"] for name, category in CATEGORIES.items()}
    assert len(marks) == 8
    assert len(set(marks.values())) == 8, marks


def test_paper_and_pastel_are_light_looks_on_any_pack_and_close_the_menu() -> None:
    standard, experimental = look_menu_items()
    assert [name for name, _label, _kind in experimental][-3:] == ["paper", "ink", "pastel"]
    for preset, accent in (("paper", "#8a4b2a"), ("pastel", "#7a3e9d")):
        for pack, system_dark in (("nocturne", True), ("dark-frost", True), ("slate", False)):
            palette = resolved_palette(pack, system_dark, look_of(preset))
            assert (palette["axis"], palette["accent"]) == ("light", accent), f"{preset} on {pack}"
        # A chosen accent therefore takes its light-axis colour, even over a dark pack.
        chosen = resolved_palette("nocturne", True, look_of(preset), "sea")
        assert (chosen["accent"], chosen["accent_ink"]) == ("#0f766e", "#ffffff")


def test_paper_and_pastel_are_the_soft_looks_and_are_not_ink() -> None:
    """Every earlier preset is flat and sharp. These two keep rounded corners and drawn depth."""
    for preset in ("paper", "pastel"):
        sheet = pack_stylesheet("slate", False, look_of(preset))
        assert "border-radius: 0px" not in sheet
        assert "border: 1px solid" in sheet, "soft depth is a hairline edge"
    assert "border-radius: 16px" in pack_stylesheet("slate", False, look_of("pastel"))
    assert "Noto Serif" in pack_stylesheet("slate", False, look_of("paper"))
    # Pastel is the one preset with raised panels; Paper's pages sit flat in the cream.
    pastel = resolved_palette("slate", False, look_of("pastel"))
    paper = resolved_palette("slate", False, look_of("paper"))
    assert pastel["panel"] != pastel["window"]
    assert paper["panel"] == paper["window"] == "#f7ecd2"
    ink = resolved_palette("slate", False, look_of("ink"))
    assert (paper["text"], paper["window"]) != (ink["text"], ink["window"])
    assert preset_knobs("paper")["blocks"] == "filled" and preset_knobs("ink")["blocks"] == "edge"


def _lab(colour: str) -> tuple[float, float, float]:
    """sRGB to CIE Lab, as the retired web client's theme-tokens test computed it."""

    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    raw = colour.lstrip("#")
    red, green, blue = (channel(int(raw[index : index + 2], 16) / 255) for index in (0, 2, 4))
    x = (red * 0.4124 + green * 0.3576 + blue * 0.1805) / 0.95047
    y = red * 0.2126 + green * 0.7152 + blue * 0.0722
    z = (red * 0.0193 + green * 0.1192 + blue * 0.9505) / 1.08883
    fx, fy, fz = (t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in (x, y, z))
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def test_every_accent_stays_clearly_apart_from_every_category_colour() -> None:
    """An accent close to a category colour makes a selected button look like a block of that
    category. The web client's theme-tokens test enforced this and was deleted with the client;
    nothing native replaced it until a documentation sweep noticed the rule's only guard was gone.
    School blue against the default light accent is the near miss, at about 18."""
    reached = {}
    for pack, system_dark, preset, accent, surface in EVERY_LOOK:
        colour = resolved_palette(pack, system_dark, look_of(preset, surface=surface), accent)["accent"]
        reached.setdefault(colour, (pack, system_dark, preset, accent))
    for colour, where in reached.items():
        for name, category in CATEGORIES.items():
            gap = math.dist(_lab(colour), _lab(category["mark"]))
            assert gap >= 15, f"{where} accent {colour} is {gap:.1f} from the {name} category"
