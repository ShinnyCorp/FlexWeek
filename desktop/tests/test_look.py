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
    HEADING_NAMES,
    KNOB_LABELS,
    KNOB_VALUE_LABELS,
    LOOK_DEFAULTS,
    LOOK_KNOBS,
    LOOK_PRESETS,
    PACKS,
    block_paint,
    block_time_colour,
    category_paint,
    contrast,
    effective_look,
    look_menu_items,
    look_menu_token,
    look_menu_value,
    look_motion,
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
from desktop.native.tokens import SINK, mix_oklab, oklch_of

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
    # A file edited by hand may hold anything; nothing in it can stop the look loading.
    odd = sanitize_look({"preset": ["poster"], "knobs": {"corners": ["round"], "depth": {"x": 1}}})
    assert odd == {"preset": "default", "knobs": {}}


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
    dark one. A student saw three accents before placing any homework. Where a tinted page needs it for
    the accent's words to read, as Slate's and Pastel's do, it is the blue's darker shade: the same hue,
    a little lower in lightness."""
    for pack, system_dark, preset in product(PACKS, (False, True), LOOK_PRESETS):
        palette = resolved_palette(pack, system_dark, look_of(preset))
        if preset == "high-contrast":
            assert (palette["accent"], palette["accent_ink"]) == ("#ffd400", "#000000")
            continue
        if preset == "paper":
            assert palette["accent"] == "#1f3a68"
            continue
        wanted = "#7fa8ff" if palette["axis"] == "dark" else "#3d6fc4"
        where = (pack, system_dark, preset)
        if palette["accent"] != wanted:
            light, _chroma, hue = oklch_of(palette["accent"])
            wanted_light, _wanted_chroma, wanted_hue = oklch_of(wanted)
            assert abs(hue - wanted_hue) < 1.5 and 0 < wanted_light - light < 0.02, where
            assert contrast(wanted, palette["window"]) < AA_TEXT, where
        assert contrast(palette["accent"], palette["window"]) >= AA_TEXT, where
    assert resolved_palette("light-frost", False, None)["accent"] == "#3d6fc4"
    assert resolved_palette("slate", False, None)["accent"] == "#3b6cc1"


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
    """Each look of 0.17's plan with the knobs it is drawn with. Blocks follow the default in all but
    High contrast, as the mock-up draws them."""
    blocks = LOOK_DEFAULTS["blocks"]
    common = {"density": "comfortable", "text": "normal", "blocks": blocks}
    expected = {
        "terminal": {**common, "surface": "layered", "corners": "sharp", "depth": "soft", "font": "mono"},
        "poster": {**common, "surface": "layered", "corners": "sharp", "depth": "bold", "font": "sans"},
        "ink": {**common, "surface": "layered", "corners": "soft", "depth": "soft", "font": "serif"},
        "paper": {**common, "surface": "layered", "corners": "soft", "depth": "none", "font": "serif"},
        "pastel": {**common, "surface": "layered", "corners": "rounded", "depth": "soft", "font": "sans"},
        "high-contrast": {
            "surface": "flat",
            "corners": "sharp",
            "depth": "bold",
            "font": "sans",
            "blocks": "outline",
            "density": "comfortable",
            "text": "large",
        },
    }
    assert preset_knobs("default") == LOOK_DEFAULTS
    for name, knobs in expected.items():
        assert preset_knobs(name) == knobs
        assert look_overrides(name, knobs) == {}
    assert look_overrides("terminal", {**preset_knobs("terminal"), "depth": "bold"}) == {"depth": "bold"}
    assert look_overrides("default", {**LOOK_DEFAULTS, "corners": "rounded"}) == {"corners": "rounded"}


def test_a_look_saved_by_016_opens_with_its_knobs_named_as_017_names_them() -> None:
    """0.17 renamed five knob values. A look file written by 0.16 keeps what it chose: frost is
    Layered, round Soft, pill Round, flat depth None, hard Bold, outlined Outline."""
    saved = {
        "preset": "terminal",
        "knobs": {"surface": "frost", "corners": "pill", "depth": "hard", "blocks": "outlined"},
    }
    assert sanitize_look(saved)["knobs"] == {
        "surface": "layered",
        "corners": "rounded",
        "depth": "bold",
        "blocks": "outline",
    }
    assert sanitize_look({"knobs": {"corners": "round", "depth": "flat"}})["knobs"] == {
        "corners": "soft",
        "depth": "none",
    }
    # Today's names pass through unchanged, Round among them.
    assert sanitize_look({"knobs": {"corners": "rounded"}})["knobs"] == {"corners": "rounded"}
    for knob, values in LOOK_KNOBS.items():
        assert all(value in KNOB_VALUE_LABELS for value in values), knob
    assert [KNOB_VALUE_LABELS[value] for value in LOOK_KNOBS["corners"]] == ["Soft", "Sharp", "Round"]
    assert set(KNOB_LABELS) == set(LOOK_KNOBS)


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


def faces(look: dict) -> tuple[str, str]:
    """The first face of the app-wide rule and of the headings' rule."""
    sheet = pack_stylesheet("slate", False, look)
    body = sheet.split("QWidget {")[1].split("font-family: ")[1].split(";")[0]
    headings = ", ".join(f"QLabel#{name}" for name in HEADING_NAMES) + " { font-family: "
    heading = sheet.split(headings)[1].split(";")[0]
    return body.split(", ")[0], heading.split(", ")[0]


def test_serif_is_newsreader_headings_over_inter_and_mono_is_jetbrains_mono_throughout() -> None:
    """The Font knob (0.17): Sans is Inter; Serif keeps Inter for the words and sets headings in
    Newsreader; Mono is JetBrains Mono for both. Paper uses serif words and figures;
    Ink keeps serif headings. Terminal uses mono."""
    assert {"weekTitle", "settingsTitle", "authHeading"} <= set(HEADING_NAMES)
    for look, wanted in (
        (look_of("default"), ("Inter", "Inter")),
        (look_of("default", font="serif"), ("Inter", "Newsreader")),
        (look_of("default", font="mono"), ("JetBrains Mono", "JetBrains Mono")),
        (look_of("paper"), ("Newsreader", "Newsreader")),
        (look_of("ink"), ("Inter", "Newsreader")),
        (look_of("terminal"), ("JetBrains Mono", "JetBrains Mono")),
    ):
        assert faces(look) == wanted, look


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


def test_soft_corners_are_6_on_controls_and_10_on_cards() -> None:
    """Decision 5 of 0.17: Soft is the system's shape, 6 on controls and 10 on cards; Sharp is 0 and
    2 and Round 10 and 16, as the plan's knobs name them."""
    for corners, control, card in (("soft", 6, 10), ("sharp", 0, 2), ("rounded", 10, 16)):
        sheet = pack_stylesheet("light-frost", False, look_of("default", corners=corners))
        frames = sheet.split("QFrame, QGroupBox, QTableWidget, QListWidget {")[1].split("}")[0]
        button = sheet.split("QPushButton {")[1].split("}")[0]
        field = sheet.split("QLineEdit, QComboBox, QSpinBox, QTimeEdit, QDateTimeEdit {")[1].split("}")[0]
        toast = sheet.split("QFrame#toast {")[1].split("}")[0]
        sheet_radius = 16 if card else 0
        assert f"border-radius: {card}px;" in frames, corners
        assert f"border-radius: {sheet_radius}px;" in toast, "the toast is a sheet, at 16 (decision 20)"
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


def test_ink_is_papers_night_on_any_pack() -> None:
    """0.16's Ink followed the pack between a light and a dark sheet. 0.17's is Paper's night
    counterpart (looks.css): charcoal and warm ivory whatever the pack, and Paper is its day."""
    for pack, system_dark in (("slate", False), ("nocturne", True), ("light-frost", False)):
        ink = resolved_palette(pack, system_dark, look_of("ink"))
        paper = resolved_palette(pack, system_dark, look_of("paper"))
        assert (ink["axis"], ink["window"], ink["text"]) == ("dark", "#1c1b19", "#f3eee3"), pack
        assert (paper["axis"], paper["window"], paper["text"]) == ("light", "#f7f0e1", "#1a1a1a"), pack


def test_a_students_accent_wins_over_the_presets_own() -> None:
    assert resolved_palette("slate", False, look_of("terminal"))["accent"] == "#7fa8ff"
    chosen = resolved_palette("slate", False, look_of("terminal"), "sky")
    # Terminal is a dark look whatever the pack underneath, so it takes the dark-axis sky and its ink.
    assert (chosen["accent"], chosen["accent_ink"]) == ("#38bdf8", "#0b1224")


def test_flat_surface_has_no_raised_panels_and_layered_does() -> None:
    frost = resolved_palette("nocturne", True, look_of("default"))
    flat = resolved_palette("nocturne", True, look_of("default", surface="flat"))
    assert frost["panel"] != frost["window"]
    assert flat["panel"] == flat["window"] == frost["window"]
    assert flat["field"] == flat["window"]


def test_depth_is_drawn_with_edges_because_qt_has_no_shadows() -> None:
    soft = pack_stylesheet("nocturne", True, look_of("default"))
    flat = pack_stylesheet("nocturne", True, look_of("default", depth="none"))
    hard = pack_stylesheet("nocturne", True, look_of("default", depth="bold"))
    assert "border: 1px solid" in soft and "border: none;" not in soft.split("QHeaderView")[0]
    # An outlined button is its hairline (button_rules), so it keeps that edge in a flat look too.
    flat_rest = "}".join(rule for rule in flat.split("}") if 'outline="true"' not in rule)
    assert "border: none;" in flat and "1px solid" not in flat_rest
    assert "border-bottom: 4px solid" in hard and "border-right: 4px solid" in hard


def test_a_block_shows_its_category_colour_in_the_place_the_knob_names() -> None:
    palette = resolved_palette("nocturne", True, None)
    blue = "#3b82f6"
    filled = block_paint(look_of("default", blocks="filled"), resolved_palette("slate", False, None), blue)
    assert (filled["fill"], filled["outline"], filled["edge"]) == (blue, None, None)
    outlined = block_paint(look_of("default", blocks="outline"), palette, blue)
    assert (outlined["fill"], outlined["outline"], outlined["edge"]) == (palette["grid"], blue, None)
    assert outlined["ink"] == palette["text"]
    # Edge, the default (decision 14 of 0.17): Filled, with the mark down its side.
    edge = block_paint(look_of("default"), palette, blue)
    assert (edge["mode"], edge["fill"], edge["outline"], edge["edge"]) == ("edge", blue, None, blue)
    # No category: a filled block uses the palette's own block colours, flexible work the warm pair.
    plain = block_paint(look_of("default"), palette, None, "flexible")
    assert (plain["fill"], plain["ink"]) == (palette["block_flex"], palette["block_flex_ink"])
    bare = block_paint(look_of("default", blocks="outline"), palette, None)
    assert bare["outline"] == palette["block_edge"]
    # A pale fill makes a vanishing outline on a light pack, so an outline or an edge uses the strong mark.
    pale, strong = "#bfdbfe", "#3b82f6"
    light = resolved_palette("slate", False, None)
    assert block_paint(look_of("default"), light, pale, "locked", strong)["fill"] == pale
    outlined_pale = block_paint(look_of("default", blocks="outline"), palette, pale, "locked", strong)
    assert outlined_pale["outline"] == strong
    assert block_paint(look_of("default", blocks="edge"), palette, pale, "locked", strong)["edge"] == strong


def test_a_filled_block_is_readable_on_every_category_colour() -> None:
    assert len(CATEGORIES) == 8
    for name, category in CATEGORIES.items():
        color = category["color"]
        ratio = contrast(readable_ink(color), color)
        assert ratio >= AA_TEXT, f"{name} {color}: best ink is only {ratio:.2f} to 1"


def test_a_blocks_times_read_in_every_look_and_block_style() -> None:
    """Times and length are drawn quieter than the title, but Terminal's read at 3.95 to 1: they give
    up quiet before they give up 4.5 to 1."""
    for pack, system_dark, preset, accent, surface in EVERY_LOOK:
        palette = resolved_palette(pack, system_dark, look_of(preset, surface=surface), accent)
        for blocks, (name, category) in product(LOOK_KNOBS["blocks"], CATEGORIES.items()):
            fill, mark = category_paint(name, palette)
            drawn = block_paint(look_of(preset, blocks=blocks), palette, fill, category["kind"], mark)
            paper = drawn["fill"] or palette["window"]
            ratio = contrast(block_time_colour(drawn["ink"], paper), paper)
            where = f"{pack}/{system_dark}/{preset}/{accent}/{surface}/{blocks} {name}"
            assert ratio >= AA_TEXT, f"{where}: {ratio:.2f}"


def test_a_blocks_times_stay_quieter_than_its_title_where_they_can() -> None:
    palette = resolved_palette("system", False, look_of("default"), "default")
    fill, mark = category_paint("study", palette)
    drawn = block_paint(look_of("default"), palette, fill, CATEGORIES["study"]["kind"], mark)
    times = block_time_colour(drawn["ink"], drawn["fill"])
    assert contrast(times, drawn["fill"]) < contrast(drawn["ink"], drawn["fill"])

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
            assert palette["axis"] == "light", f"{preset} on {pack}"
            assert palette["accent"] == resolved_palette("slate", False, look_of(preset))["accent"]
        # A chosen accent therefore takes its light-axis colour, even over a dark pack.
        chosen = resolved_palette("nocturne", True, look_of(preset), "sea")
        assert (chosen["accent"], chosen["accent_ink"]) == ("#0f766e", "#ffffff")


def test_the_seven_looks_wear_looks_css_colours() -> None:
    """Each look's page, card, raised card, text, muted text and hairlines as the mock-up draws them
    (look-017, with the approved polish-0172 Paper and Pastel changes)."""
    drawn = {
        ("slate", "default"): ("#eef1f5", "#ffffff", "#e7ebf1", "#0f172a", "#475569", "#dbe1ea", "#c3ccd9"),
        ("nocturne", "default"): ("#0a0e27", "#121633", "#1a1f42", "#e0e4f0", "#9aa3c0", "#262b4d",
                                  "#343a63"),
        ("system", "paper"): ("#f7f0e1", "#fbf6ea", "#f6f1e8", "#1a1a1a", "#5c5750", "#e6e0d6", "#cfc7b9"),
        ("system", "ink"): ("#1c1b19", "#242320", "#2c2a26", "#f3eee3", "#b3ab9c", "#3a3833", "#4a4740"),
        ("system", "terminal"): ("#0d1117", "#161b22", "#1c2129", "#c9d1d9", "#8b949e", "#30363d", "#484f58"),
        ("system", "poster"): ("#fff8e7", "#ffffff", "#fff1cc", "#111111", "#3d3d3d", "#111111", "#111111"),
        ("system", "pastel"): ("#f3ecff", "#fbf8ff", "#ece7ff", "#1e1b2e", "#4b4763", "#e4ddfb", "#cfc5f5"),
    }
    keys = ("window", "panel", "card_2", "text", "muted", "hairline", "hairline_strong")
    for (pack, preset), colours in drawn.items():
        palette = resolved_palette(pack, False, look_of(preset))
        assert tuple(palette[key] for key in keys) == colours, (pack, preset)


def test_paper_draws_the_family_quieter_and_poster_bolder() -> None:
    """looks.css: Paper's fills at chroma 0.035, Poster's at lightness 0.88 and chroma 0.09. The
    marks stay the family's, so an edge or outline is the same colour in every light look."""
    light = resolved_palette("light-frost", False, None)
    paper = resolved_palette("system", False, look_of("paper"))
    poster = resolved_palette("system", False, look_of("poster"))
    for key in CATEGORIES:
        plain, mark = category_paint(key, light)
        quiet, quiet_mark = category_paint(key, paper)
        bold, bold_mark = category_paint(key, poster)
        assert mark == quiet_mark == bold_mark, key
        if key == "free":
            continue
        assert oklch_of(quiet)[1] < oklch_of(plain)[1] < oklch_of(bold)[1], key
        assert oklch_of(bold)[0] < oklch_of(plain)[0], key


def test_paper_starts_at_reduce_motion() -> None:
    """E-Ink's "distinct page turns, sharp transitions": Paper's level when the student never chose
    one. Every other look starts at Normal, whatever the pack."""
    assert look_motion(look_of("paper")) == "reduce"
    for preset in ("default", "ink"):
        assert look_motion(look_of(preset)) == "normal", preset


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
