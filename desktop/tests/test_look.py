"""Look knobs, presets and palettes. Device-only knobs never become preference fields.

The palettes began as the retired web client's CSS custom properties, which had already passed its
readability and accent-distance audits. That client is gone, so there is nothing left to be in step
with: the colours live in look.py now, and what is checked here is the property the audit was for,
that every look a student can reach keeps its text readable. Expected behaviour comes from the
appearance contract.
"""

from __future__ import annotations

from itertools import product

from desktop.native.calendar import CATEGORIES
from desktop.native.look import (
    AA_TEXT,
    ACCENTS,
    FONT_FAMILIES,
    LOOK_DEFAULTS,
    LOOK_KNOBS,
    LOOK_PRESETS,
    PACKS,
    block_paint,
    category_paint,
    contrast,
    effective_look,
    look_menu_items,
    look_menu_token,
    look_menu_value,
    look_overrides,
    pack_axis,
    pack_stylesheet,
    parse_look_menu_token,
    preset_knobs,
    readable_ink,
    resolved_pack_theme,
    resolved_palette,
    sanitize_look,
)
from desktop.native.tokens import SINK, mix_oklab

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


def test_system_follows_the_device_between_light_and_dark() -> None:
    """Decision 2 of 0.17: System is Light or Dark as the device is. The server still hears the
    frost looks as slate and nocturne, the axis a saved preference has always had."""
    assert pack_axis("light-frost") == "slate"
    assert pack_axis("dark-frost") == "nocturne"
    assert pack_axis("system") == "system"
    assert resolved_pack_theme("system", True) == "dark-frost"
    assert resolved_pack_theme("system", False) == "light-frost"
    assert resolved_pack_theme("slate", True) == "slate"


def test_light_and_dark_are_the_neutral_surfaces_of_decision_2() -> None:
    light = resolved_palette("light-frost", False, None)
    dark = resolved_palette("dark-frost", True, None)
    assert (light["window"], light["panel"], light["hairline"]) == ("#f7f8fa", "#ffffff", "#e4e7ec")
    assert (light["text"], light["muted"]) == ("#111827", "#5b6474")
    assert (dark["window"], dark["panel"], dark["hairline"]) == ("#111315", "#1a1d21", "#2a2e34")
    assert (dark["text"], dark["muted"]) == ("#e8eaed", "#9aa1ab")


def test_every_look_but_high_contrast_wears_flexweeks_blue_by_default() -> None:
    """Decision 1 of 0.17: one accent, the icon's blue, #3d6fc4 on a light look and #7fa8ff on a
    dark one. A student saw three accents before placing any homework."""
    for pack, system_dark, preset in product(PACKS, (False, True), LOOK_PRESETS):
        palette = resolved_palette(pack, system_dark, look_of(preset))
        if preset == "high-contrast":
            assert (palette["accent"], palette["accent_ink"]) == ("#ffd400", "#000000")
            continue
        wanted = "#7fa8ff" if palette["axis"] == "dark" else "#3d6fc4"
        assert palette["accent"] == wanted, (pack, system_dark, preset)


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


def test_round_corners_are_6_on_controls_and_10_on_cards() -> None:
    """Decision 5 of 0.17: one shape for controls and one for cards. The other Corners keep theirs."""
    for corners, control, card in (("round", 6, 10), ("sharp", 0, 0), ("pill", 16, 16)):
        sheet = pack_stylesheet("light-frost", False, look_of("default", corners=corners))
        frames = sheet.split("QFrame, QGroupBox, QTableWidget, QListWidget {")[1].split("}")[0]
        button = sheet.split("QPushButton {")[1].split("}")[0]
        field = sheet.split("QLineEdit, QComboBox, QSpinBox, QTimeEdit, QDateTimeEdit {")[1].split("}")[0]
        toast = sheet.split("QFrame#toast {")[1].split("}")[0]
        assert f"border-radius: {card}px;" in frames and f"border-radius: {card}px;" in toast, corners
        assert f"border-radius: {control}px;" in button and f"border-radius: {control}px;" in field, corners


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
    assert "QPushButton { background: #7fa8ff; color: #0b1224;" in sheet
    assert "#ffffff" not in sheet
    dark = pack_stylesheet("nocturne", True, look_of("default"), "gold")
    assert "QPushButton { background: #eab308; color: #0b1224;" in dark


def test_an_accent_always_changes_the_accent() -> None:
    """Sky once equalled the Light frost default, so choosing it did nothing. High contrast is the
    one look whose accent no swatch replaces: its yellow is part of its contrast."""
    for pack, system_dark, preset in product(PACKS, (False, True), LOOK_PRESETS):
        plain = resolved_palette(pack, system_dark, look_of(preset))["accent"]
        if preset == "high-contrast":
            for accent in ACCENTS:
                chosen = resolved_palette(pack, system_dark, look_of(preset), accent)
                assert (chosen["accent"], chosen["accent_ink"]) == ("#ffd400", "#000000"), accent
            continue
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
    assert resolved_palette("slate", False, look_of("terminal"))["accent"] == "#7fa8ff"
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
    filled = block_paint(look_of("default", blocks="filled"), resolved_palette("slate", False, None), blue)
    assert (filled["fill"], filled["outline"], filled["edge"]) == (blue, None, None)
    outlined = block_paint(look_of("default", blocks="outlined"), palette, blue)
    assert (outlined["fill"], outlined["outline"], outlined["edge"]) == (palette["grid"], blue, None)
    assert outlined["ink"] == palette["text"]
    # Edge, the default (decision 14 of 0.17): Filled, with the mark down its side.
    edge = block_paint(look_of("default"), palette, blue)
    assert (edge["mode"], edge["fill"], edge["outline"], edge["edge"]) == ("edge", blue, None, blue)
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
    block with the category's tone mixed into its panel, and writes on it in its own light text."""
    seen = 0
    for pack, system_dark, preset, accent, surface in EVERY_LOOK:
        palette = resolved_palette(pack, system_dark, look_of(preset, surface=surface), accent)
        if palette["axis"] != "dark":
            continue
        seen += 1
        filled = look_of(preset, blocks="filled")
        for name, category in CATEGORIES.items():
            fill, mark = category_paint(name, palette)
            drawn = block_paint(filled, palette, fill, "locked", mark)
            where = f"{pack}/{preset}/{surface} {name}"
            tone = category[palette["family"]][0]
            assert drawn["fill"] == mix_oklab(tone, palette["panel"], SINK), where
            assert drawn["ink"] == palette["text"], where
            assert contrast(drawn["ink"], drawn["fill"]) >= AA_TEXT, where
    assert seen


def test_every_category_has_a_mark_of_its_own() -> None:
    """These began as the retired web client's category colours. What has to hold now that they live
    only here is that there are eight and no two are the same, or two kinds of block look alike."""
    marks = {name: category["mark"] for name, category in CATEGORIES.items()}
    assert len(marks) == 8
    assert len(set(marks.values())) == 8, marks


def test_paper_and_pastel_are_light_looks_on_any_pack_and_close_the_menu() -> None:
    standard, experimental = look_menu_items()
    assert [name for name, _label, _kind in experimental][-3:] == ["paper", "ink", "pastel"]
    for preset in ("paper", "pastel"):
        for pack, system_dark in (("nocturne", True), ("dark-frost", True), ("slate", False)):
            palette = resolved_palette(pack, system_dark, look_of(preset))
            assert (palette["axis"], palette["accent"]) == ("light", "#3d6fc4"), f"{preset} on {pack}"
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


def test_a_tray_chip_is_edged_in_homeworks_colour_not_in_red() -> None:
    """Not placed yet is not a problem, so a tray chip's edge is homework's own mark in the look, not
    the red that said something was wrong (decision 8 of 0.17)."""
    homework = CATEGORIES["assignments"]
    high_contrast = {"preset": "high-contrast", "knobs": {}}
    for pack, dark, look, mark in (
        ("light-frost", False, None, homework["mark"]),
        ("dark-frost", True, None, homework["dark"][1]),
        ("system", False, high_contrast, homework["contrast"][1]),
    ):
        palette = resolved_palette(pack, dark, look)
        tray = pack_stylesheet(pack, dark, look).split('QPushButton[tray="true"] {')[1].split("}")[0]
        assert f"border-left: 4px solid {mark};" in tray, pack
        assert palette["error"] not in tray and "#ef4444" not in tray, pack
