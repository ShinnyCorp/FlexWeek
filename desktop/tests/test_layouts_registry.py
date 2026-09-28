"""The registry is what the layout dialog is built from and what the file on disk is checked against,
so it is tested as data: the roles, the three levels, what survives a bad file, and the contrast of
every colourway including the one that follows the student's own look.
"""

from __future__ import annotations

import itertools

import pytest

from desktop.native.layouts.registry import (
    LAYOUTS,
    MATCH,
    contrast_failures,
    layouts_for,
    options_for,
    sanitize_layout,
    tokens_for,
)
from desktop.native.look import (
    AA_TEXT,
    ACCENT_COLORS,
    ACCENTS,
    LOOK_PRESETS,
    PACKS,
    contrast,
    palette_from_tokens,
    resolved_palette,
)
from desktop.native.tokens import oklch_of
from desktop.tests.test_look import TEXT_PAIRS, _lab

DESIGNS = [spec.id for spec in LAYOUTS.values() if spec.options]


def test_the_two_roles_hold_the_designs_the_owner_picked() -> None:
    assert [spec.id for spec in layouts_for("plan")] == [
        "classic",
        "timeline",
        "mission",
        "bento",
        "retro",
        "clay",
    ]
    assert [spec.id for spec in layouts_for("day")] == ["dial", "one"]


def test_two_main_views_and_one_day_screen_are_standard_and_the_rest_experimental() -> None:
    """Decision 3 of 0.16: one polished default and Timeline beside it; the rest stay, offered after."""
    assert [spec.id for spec in layouts_for("plan", experimental=False)] == ["classic", "timeline"]
    experimental = [spec.id for spec in layouts_for("plan", experimental=True)]
    assert experimental == ["mission", "bento", "retro", "clay"]
    assert [spec.id for spec in layouts_for("day", experimental=False)] == ["dial"]
    assert [spec.id for spec in layouts_for("day", experimental=True)] == ["one"]
    for spec in LAYOUTS.values():
        slot = "main" if spec.role == "plan" else "day"
        assert sanitize_layout({slot: spec.id})[slot] == spec.id, "a saved experimental choice still loads"


def test_every_design_offers_all_three_levels() -> None:
    for layout_id in DESIGNS:
        levels = {option.level for option in LAYOUTS[layout_id].options}
        assert levels == {"style", "detail"}, layout_id


def test_every_design_follows_the_students_look_until_one_of_its_own_colourways_is_picked() -> None:
    """Decision 3 of 0.17: a design's default is Match my look, and its signature colourways stay
    as choices. A colourway saved before then still loads as saved."""
    for layout_id in DESIGNS:
        spec = LAYOUTS[layout_id]
        colour = spec.options[0]
        assert colour.key == "colour" and colour.level == "style", layout_id
        assert colour.default == MATCH, layout_id
        assert colour.values == (MATCH, *[value for value, _, _ in spec.colourways]), layout_id
        signature = spec.colourways[0][0]
        saved = sanitize_layout({"options": {layout_id: {"colour": signature}}})
        assert options_for(saved, layout_id)["colour"] == signature, layout_id


def test_option_keys_and_choices_are_unambiguous() -> None:
    for spec in LAYOUTS.values():
        keys = [option.key for option in spec.options]
        assert len(keys) == len(set(keys)), spec.id
        for option in spec.options:
            assert len(option.values) == len(set(option.values)) >= 2, (spec.id, option.key)


def test_a_missing_or_broken_file_gives_the_shipped_choice() -> None:
    shipped = {"main": "classic", "day": "dial", "options": {}}
    for raw in (None, "bento", [], {"main": 7, "day": None, "options": "x"}):
        assert sanitize_layout(raw) == shipped


def test_a_day_screen_cannot_be_the_main_view_nor_the_other_way_round() -> None:
    assert sanitize_layout({"main": "one", "day": "bento"}) == {
        "main": "classic",
        "day": "dial",
        "options": {},
    }
    assert sanitize_layout({"main": "bento", "day": "dial"}) == {
        "main": "bento",
        "day": "dial",
        "options": {},
    }


def test_only_known_options_with_known_values_survive() -> None:
    raw = {
        "main": "bento",
        "options": {
            "bento": {"colour": "sunset", "corners": "triangular", "wallpaper": "cats"},
            "one": {"actions": "hide"},
            "heatmap": {"colour": "red"},
            "clay": "tilted",
        },
    }
    assert sanitize_layout(raw)["options"] == {"bento": {"colour": "sunset"}, "one": {"actions": "hide"}}


def test_options_are_the_students_choice_over_the_designs_defaults() -> None:
    choice = {"options": {"one": {"actions": "hide", "colour": "paper"}}}
    assert options_for(choice, "one") == {
        "colour": "paper",
        "lead": "now",
        "actions": "hide",
        "daybar": "show",
    }
    assert options_for(None, "dial") == {"colour": MATCH, "list": "show", "week": "show"}
    assert options_for(choice, "classic") == {}


@pytest.mark.parametrize("layout_id", DESIGNS)
def test_every_shipped_colourway_is_readable(layout_id: str) -> None:
    palette = resolved_palette("light-frost", False, None, "default")
    for value, _, _ in LAYOUTS[layout_id].colourways:
        assert contrast_failures(tokens_for(layout_id, value, palette)) == [], (layout_id, value)


def test_every_design_dresses_its_page_in_colours_its_text_reads_on() -> None:
    """A design in its own colours dresses its whole page: its panels, buttons, fields and scroll
    bars (the chrome keeps the look). Retro's dark desktops put their white page text on its grey
    windows and fields, 1.82 to 1. A design's colours are fixed, and the look lends them only its
    block colours, so a light and a dark look are enough."""
    light, dark = resolved_palette("light-frost", False, None), resolved_palette("nocturne", True, None)
    dressed = [
        (f"{layout_id} {value}", palette_from_tokens(tokens_for(layout_id, value, base), base))
        for layout_id in DESIGNS
        for value, _, _ in LAYOUTS[layout_id].colourways
        for base in (light, dark)
    ]
    failures = {
        (name, ink, paper, round(contrast(page[ink], page[paper]), 2))
        for name, page in dressed
        for ink, paper in TEXT_PAIRS
        if contrast(page[ink], page[paper]) < AA_TEXT
    }
    assert sorted(failures) == []


def test_match_my_look_is_readable_in_every_look_the_app_has() -> None:
    failures = []
    combos = list(itertools.product(PACKS, (False, True), LOOK_PRESETS, ACCENT_COLORS, ("layered", "flat")))
    for pack, dark, preset, accent, surface in combos:
        look = {"preset": preset, "knobs": {"surface": surface}}
        tokens = tokens_for("bento", MATCH, resolved_palette(pack, dark, look, accent))
        failures += [(pack, dark, preset, accent, surface, item) for item in contrast_failures(tokens)]
    assert len(combos) == 5 * 2 * 7 * len(ACCENT_COLORS) * 2
    assert failures == []


def test_a_design_can_ask_for_a_colour_its_colourway_does_not_name() -> None:
    palette = resolved_palette("light-frost", False, None, "default")
    tokens = tokens_for("one", "black", palette)
    # Poster names no accent, so it wears the student's own in place of 0.16's orange: the same hue,
    # lightened until it reads on the black page.
    assert tokens["bg"] == "#000000" and tokens["cta"] == tokens["accent"]
    assert oklch_of(tokens["accent"])[2] == pytest.approx(oklch_of(palette["accent"])[2], abs=2)
    assert oklch_of(tokens["accent"])[0] > oklch_of(palette["accent"])[0]
    assert contrast(tokens["cta_ink"], tokens["cta"]) >= 4.5
    # Derived from the colourway itself. Borrowed from the student's light look it was white on pale.
    for key in ("card_a", "card_b", "card_c", "card_d"):
        assert contrast(tokens["text"], tokens[key]) >= 4.5
        assert contrast(tokens["muted"], tokens[key]) >= 4.5
        assert contrast(tokens[key], tokens["bg"]) >= 1.01


def test_an_unknown_colourway_falls_back_to_the_students_look() -> None:
    palette = resolved_palette("nocturne", True, None, "default")
    assert tokens_for("clay", "no-such-colours", palette) == tokens_for("clay", MATCH, palette)
    assert tokens_for("clay", MATCH, palette)["bg"] == palette["window"]


def test_the_audit_names_each_unreadable_pair() -> None:
    palette = resolved_palette("light-frost", False, None, "default")
    good = tokens_for("bento", "indigo", palette)
    assert contrast_failures(good) == []
    assert contrast_failures({**good, "muted": good["surface"]})[0] == "muted 1.00"
    assert contrast_failures({**good, "cta_ink": good["cta"]}) == ["cta_ink 1.00"]
    assert contrast_failures({**good, "bg_muted": good["bg"]}) == ["bg_muted 1.00"]
    assert contrast_failures({**good, "card_b": good["text"]}) == [
        "text on card_b 1.00",
        "muted on card_b 1.93",
    ]
    assert contrast_failures({**good, "card_c": good["bg"]}) == ["card_c on bg 1.00"]


def test_a_bar_that_carries_no_text_is_free_to_be_seen() -> None:
    """Bento's load bars used a card tint, which is held down by the text that sits on a card.
    Measured across every look that left them at 1.27 to 1 against their tile in the median and
    1.01 at worst, so Terminal's came out dark brown on black. A bar has no text on it."""
    worst = 99.0
    for pack, dark, preset, accent, surface in itertools.product(
        PACKS, (False, True), LOOK_PRESETS, ACCENT_COLORS, ("layered", "flat")
    ):
        look = {"preset": preset, "knobs": {"surface": surface}}
        tokens = tokens_for("bento", MATCH, resolved_palette(pack, dark, look, accent))
        worst = min(worst, contrast(tokens["fill"], tokens["surface"]))
    assert worst >= 1.8, f"a load bar sank to {worst:.2f} against its tile"


def test_the_audit_holds_a_fill_to_its_own_floor() -> None:
    palette = resolved_palette("light-frost", False, None, "default")
    good = tokens_for("bento", "indigo", palette)
    assert contrast_failures(good) == []
    assert contrast_failures({**good, "fill": good["surface"]}) == ["fill on surface 1.00"]


def relative_luminance(colour: str) -> float:
    raw = colour.lstrip("#")
    red, green, blue = (int(raw[index : index + 2], 16) for index in (0, 2, 4))
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255


def test_every_design_offers_a_dark_colourway() -> None:
    """A student who works at night should not have to give up the design they picked. Bento and
    Clay shipped with three colourways each and every one of them light."""
    for layout_id, spec in LAYOUTS.items():
        if not spec.colourways:
            continue  # Today's app wears the pack, which has dark packs of its own.
        darks = [
            label for _value, label, tokens in spec.colourways if relative_luminance(tokens["bg"]) < 0.35
        ]
        assert darks, f"{layout_id} has no dark colourway"


def test_every_design_offers_a_light_colourway_too() -> None:
    """The same argument the other way: Mission control is three shades of dark."""
    missing = [
        layout_id
        for layout_id, spec in LAYOUTS.items()
        if spec.colourways
        and not [
            label for _value, label, tokens in spec.colourways if relative_luminance(tokens["bg"]) >= 0.35
        ]
    ]
    assert missing == ["mission"], (
        "Mission control is the known exception and reaches light through Match my look; "
        f"these now have no light colourway either: {missing}"
    )


def test_a_dark_colourway_is_readable_like_any_other() -> None:
    palette = resolved_palette("light-frost", False, None)
    for layout_id, spec in LAYOUTS.items():
        for value, _label, tokens in spec.colourways:
            if relative_luminance(tokens["bg"]) < 0.35:
                assert contrast_failures(tokens_for(layout_id, value, palette)) == [], (layout_id, value)


@pytest.mark.parametrize(("layout_id", "colour"), [("one", "black"), ("dial", "midnight")])
def test_a_colourway_in_the_students_accent_reads_in_every_one(layout_id: str, colour: str) -> None:
    """One thing's Poster and Day dial's Night take the student's accent onto their dark pages, so
    each is held to the rules in every accent of every pack, light and dark, not only in the one the
    other tests use, and a refusal never wears it."""
    import math

    named = next(tokens for value, _, tokens in LAYOUTS[layout_id].colourways if value == colour)
    assert "accent" not in named
    failures, close = [], {}
    for pack, dark, accent in itertools.product(PACKS, (False, True), ACCENTS):
        tokens = tokens_for(layout_id, colour, resolved_palette(pack, dark, None, accent))
        failures += [(pack, dark, accent, item) for item in contrast_failures(tokens)]
        for ground in ("bg", "surface"):
            if (ratio := contrast(tokens["accent"], tokens[ground])) < AA_TEXT:
                failures.append((pack, dark, accent, f"accent on {ground} {ratio:.2f}"))
        if (gap := math.dist(_lab(tokens["accent"]), _lab(tokens["danger"]))) < 25:
            close[(pack, dark, accent)] = round(gap, 1)
    assert failures == []
    assert close == {}


def test_a_dark_looks_accent_already_reads_on_night_and_is_worn_as_it_is() -> None:
    palette = resolved_palette("nocturne", True, None, "default")
    tokens = tokens_for("dial", "midnight", palette)
    assert (tokens["accent"], tokens["accent_ink"]) == (palette["accent"], palette["accent_ink"])


def test_a_refusal_never_wears_the_accent() -> None:
    """A held block is outlined and labelled in the accent where it can go and in the danger colour
    where it cannot. One thing's black scheme had both at #fb923c, so a refusal looked allowed and
    only its words differed. The gap is in CIE Lab, as the accent and category audit in test_look
    measures it; two dark reds on Poster sat 15 apart and read as one."""
    import math

    reached = {
        f"{layout_id}/{value}": tokens_for(layout_id, value, resolved_palette("light-frost", False, None))
        for layout_id, spec in LAYOUTS.items()
        for value, _, _ in spec.colourways
    }
    for pack, dark, preset, accent, surface in itertools.product(
        PACKS, (False, True), LOOK_PRESETS, ACCENTS, ("layered", "flat")
    ):
        look = {"preset": preset, "knobs": {"surface": surface}}
        where = f"match {pack}/{'dark' if dark else 'light'}/{preset}/{accent}"
        reached[where] = tokens_for("bento", MATCH, resolved_palette(pack, dark, look, accent))
    close = {
        where: round(gap, 1)
        for where, tokens in reached.items()
        if (gap := math.dist(_lab(tokens["accent"]), _lab(tokens["danger"]))) < 25
    }
    assert close == {}
