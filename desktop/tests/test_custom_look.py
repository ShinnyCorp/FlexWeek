"""A look of the student's own (0.17's Customise): one of the ten looks with what they changed, drawn as
the built-in looks are, checked for readability, kept by name, and shared as a small file."""

from __future__ import annotations

import pytest

from desktop.native.calendar import CATEGORIES
from desktop.native.custom_look import (
    apply_fix,
    import_look,
    readability,
)
from desktop.native.look import (
    AA_TEXT,
    FILL,
    FONT_FAMILIES,
    LOOK_BASES,
    block_paint,
    category_paint,
    contrast,
    effective_look,
    look_measures,
    look_motion,
    pack_stylesheet,
    resolved_palette,
    sanitize_custom,
    sanitize_look,
)
from desktop.native.tokens import MARK, oklab, oklch, oklch_of


def worn(custom: dict) -> dict:
    return {"preset": "default", "knobs": {}, "custom": custom}


def test_a_custom_look_with_nothing_changed_draws_as_its_base() -> None:
    """Every one of the ten looks is a starting point: customised with nothing moved, it is that look."""
    for base, (pack, preset) in LOOK_BASES.items():
        for system_dark in (False, True):
            as_built = resolved_palette(pack, system_dark, {"preset": preset, "knobs": {}}, "sea")
            custom = resolved_palette("slate", system_dark, worn({"base": base, "accent": "sea"}))
            if preset == "high-contrast":
                # High contrast keeps its yellow unless the student picks an accent of their own.
                as_built = {**as_built, "accent": "#2dd4bf", "accent_ink": "#0b1224",
                            "accent_text": "#2dd4bf", "now": "#2dd4bf", "selection": "#2dd4bf"}
            assert custom == as_built, (base, system_dark)
            sheet = pack_stylesheet(pack, system_dark, {"preset": preset, "knobs": {}}, "sea")
            if preset != "high-contrast":
                assert pack_stylesheet("slate", system_dark, worn({"base": base, "accent": "sea"})) == sheet


def test_the_students_colours_replace_the_bases_and_the_rest_follows_from_them() -> None:
    """Page, card, text and line as set; muted text, the raised card and the strong line worked out
    from them, muted as quiet as it can be while it still reads."""
    colours = {"page": "#f4efe6", "card": "#fffaf0", "text": "#2b2118", "line": "#e2d6c2"}
    custom = {"base": "light", "colours": colours}
    palette = resolved_palette("system", False, worn(custom))
    assert (palette["window"], palette["panel"], palette["text"], palette["hairline"]) == (
        "#f4efe6",
        "#fffaf0",
        "#2b2118",
        "#e2d6c2",
    )
    assert palette["muted"] not in {palette["text"], palette["panel"]}
    assert contrast(palette["muted"], palette["panel"]) >= AA_TEXT
    assert contrast(palette["muted"], palette["window"]) >= AA_TEXT
    assert palette["card_2"] != palette["panel"] and palette["hairline_strong"] != palette["hairline"]
    # A dark page makes it a dark look: the dark accent, and fills sunk into the card.
    night = {"page": "#101418", "card": "#1b2026", "text": "#e6e9ee"}
    dark = resolved_palette("system", False, worn({"base": "light", "colours": night}))
    assert (dark["axis"], dark["family"], dark["accent"]) == ("dark", "dark", "#7fa8ff")
    assert category_paint("class", dark)[0] != CATEGORIES["class"]["color"]


def test_a_category_takes_a_hue_on_the_family_or_an_exact_colour() -> None:
    """A hue sits on the family's lightness and chroma, so it reads by construction; an exact colour
    is the block's fill in any look."""
    custom = {"base": "light", "categories": {"class": {"hue": 140}, "meals": {"colour": "#ffcc66"}}}
    palette = resolved_palette("system", False, worn(custom))
    fill, mark = category_paint("class", palette)
    assert (fill, mark) == (oklch(FILL[0], FILL[1], 140), oklch(*MARK["light"], 140))
    assert abs(oklab(fill)[0] - oklab(CATEGORIES["exercise"]["color"])[0]) <= 0.02
    assert category_paint("meals", palette)[0] == "#ffcc66"
    assert category_paint("study", palette) == (CATEGORIES["study"]["color"], CATEGORIES["study"]["mark"])
    night = resolved_palette("system", True, worn({**custom, "base": "dark"}))
    assert category_paint("meals", night)[0] == "#ffcc66"
    assert oklch_of(category_paint("class", night)[1])[0] == pytest.approx(MARK["dark"][0], abs=0.01)


def test_every_measure_and_choice_reaches_what_is_drawn() -> None:
    """Corners, spacing, shadows, faces, text size, blocks, the grid and motion, each as set."""
    custom = {
        "base": "light",
        "corners": 14,
        "spacing": "compact",
        "shadows": "bold",
        "body_font": "serif",
        "heading_font": "mono",
        "text_scale": 1.2,
        "blocks": "outline",
        "edge_width": 5,
        "show_times": False,
        "show_lengths": True,
        "today_highlight": False,
        "hour_lines": "none",
        "now_line": "text",
        "motion": "off",
    }
    look = worn(custom)
    measures = look_measures(look)
    # The body size at 1.2 times the type scale's 13 points, to the half point.
    assert (measures["card_radius"], measures["radius"], measures["size"]) == (14, 8, 15.5)
    assert (measures["body"], measures["heading"]) == (FONT_FAMILIES["serif"], FONT_FAMILIES["mono"])
    assert (measures["edge_width"], measures["show_times"], measures["today_highlight"]) == (5, False, False)
    knobs = effective_look(look)
    drawn = (knobs["density"], knobs["depth"], knobs["blocks"], knobs["text"])
    assert drawn == ("compact", "bold", "outline", "large")
    sheet = pack_stylesheet("system", False, look)
    assert "font-family: Newsreader" in sheet.split("QWidget {")[1].split("}")[0]
    assert "font-size: 15.5pt" in sheet and "border-radius: 14px" in sheet
    assert "border-bottom: 4px solid" in sheet
    palette = resolved_palette("system", False, look)
    assert palette["rule"] == palette["window"] and palette["now"] == palette["text"]
    assert block_paint(look, palette, "#dddddd")["outline"] == "#dddddd"
    assert look_motion(look) == "off"
    assert look_motion(worn({"base": "paper"})) == "reduce"


def test_a_colour_of_the_students_own_as_the_accent() -> None:
    palette = resolved_palette("system", False, worn({"base": "light", "accent": "#9a3412"}))
    assert palette["accent"] == "#9a3412"
    assert contrast(palette["accent_ink"], palette["accent"]) >= AA_TEXT
    # One so pale its words would not read stays as typed, and the check offers the darker shade.
    pale = {"base": "light", "accent": "#9fd3ff"}
    assert resolved_palette("system", False, worn(pale))["accent"] == "#9fd3ff"
    problem = next(p for p in readability(pale) if p.words == "Accent text on cards")
    mended = resolved_palette("system", False, worn(apply_fix(pale, problem)))
    assert mended["accent"] == problem.fixed
    for ground in ("window", "panel"):
        assert contrast(mended["accent"], mended[ground]) >= AA_TEXT, ground
    assert contrast(mended["accent_ink"], mended["accent"]) >= AA_TEXT
    assert abs(oklch_of(mended["accent"])[2] - oklch_of("#9fd3ff")[2]) < 3
    # A swatch on a tinted page is its own darker shade already, as in the built-in looks.
    swatch = resolved_palette("system", False, worn({"base": "slate", "accent": "default"}))
    assert swatch["accent"] == "#3b6cc1"


def test_unknown_settings_and_bad_values_are_dropped_and_said_never_a_crash() -> None:
    raw = {
        "base": "paper",
        "wallpaper": "cats",
        "accent": "chartreuse",
        "colours": {"page": "#fffff", "text": "#123456", "glow": "#ffffff"},
        "categories": {"class": {"hue": "blue"}, "robots": {"hue": 10}, "study": {"hue": 300}},
        "corners": 40,
        "text_scale": "big",
        "spacing": "roomy",
        "show_times": "yes",
        "name": "  Late   night  ",
    }
    clean, problems = sanitize_custom(raw)
    assert clean == {
        "base": "paper",
        "name": "Late night",
        "colours": {"text": "#123456"},
        "categories": {"study": {"hue": 300.0}},
    }
    assert len(problems) == 10, problems
    assert any("wallpaper" in problem for problem in problems)
    for broken in (
        None,
        [],
        "paper",
        {"base": "neon"},
        {"base": ["light"]},
        {"base": "light", "colours": 3},
        {"base": "light", "categories": "all"},
        {"base": "light", "corners": float("nan")},
    ):
        try:
            sanitize_custom(broken)
            kept = sanitize_look({"preset": "default", "custom": broken}).get("custom")
            resolved_palette("system", False, sanitize_look({"custom": broken}))
        except Exception as error:
            raise AssertionError(f"{broken!r} crashed with {error!r}") from None
        assert kept in (None, {"base": "light"})


def fixed_until_it_reads(custom: dict) -> dict:
    for _round in range(5):
        problems = readability(custom)
        if not problems:
            return custom
        custom = apply_fix(custom, problems[0])
    return custom


def test_each_unreadable_pair_is_named_with_a_fix_that_ends_at_four_and_a_half_to_one() -> None:
    custom = {
        "base": "light",
        "colours": {"page": "#f2f2f2", "card": "#ffffff", "text": "#9a9a9a"},
        "categories": {"class": {"colour": "#5a5a5a"}},
    }
    problems = readability(custom)
    said = {problem.words for problem in problems}
    assert {"Text on the page", "Text on cards", "Muted text on the page", "Muted text on cards"} <= said
    for problem in problems:
        assert problem.ratio < AA_TEXT
        mended = apply_fix(custom, problem)
        palette = resolved_palette("system", False, worn(mended))
        if problem.field[0] == "colours":
            # Moved to read on the page, the cards and the calendar at once.
            key = problem.field[1]
            for ground in ("window", "panel", "grid"):
                assert contrast(palette[key], palette[ground]) >= AA_TEXT, problem
        if problem.field == ("colours", "text"):
            # Its lightness moved; its hue and chroma, what makes it the student's colour, stayed.
            assert oklch_of(palette["text"])[0] < oklch_of("#9a9a9a")[0]
    # Muted text can be set too, and its fix moves it and not the text.
    quiet = {"base": "light", "colours": {"muted": "#c0c0c0"}}
    problem = next((p for p in readability(quiet) if p.words == "Muted text on cards"), None)
    assert problem is not None, "a muted colour set on its own is not checked for reading"
    assert problem.field == ("colours", "muted")
    assert resolved_palette("system", False, worn(apply_fix(quiet, problem)))["text"] == "#111827"
    ended = fixed_until_it_reads(custom)
    assert readability(ended) == []


def test_a_block_colour_that_does_not_read_is_moved_until_its_words_do() -> None:
    """A look of the student's own writes its text on every block, as the mock-up does, so a colour
    the text does not read on is drawn as it is and named with a Fix, not hidden under black or white
    ink. The Fix moves the colour the student chose until the words read."""
    custom = {"base": "dark", "colours": {"text": "#d0d4da"}, "categories": {"study": {"colour": "#8a6fd0"}}}
    palette = resolved_palette("system", True, worn(custom))
    fill, mark = category_paint("study", palette)
    assert block_paint(worn(custom), palette, fill, CATEGORIES["study"]["kind"], mark)["ink"] == "#d0d4da"
    problem = next(p for p in readability(custom, True) if p.field == ("categories", "study"))
    assert problem.ratio < AA_TEXT and problem.words == "Text on Study blocks"
    assert (problem.ink, problem.ground) == ("#d0d4da", "#8a6fd0")
    mended = apply_fix(custom, problem)
    assert mended["categories"]["study"] == {"colour": problem.fixed}
    palette = resolved_palette("system", True, worn(mended))
    assert contrast(palette["text"], category_paint("study", palette)[0]) >= AA_TEXT
    assert abs(oklch_of(problem.fixed)[2] - oklch_of("#8a6fd0")[2]) < 3
    for hue in range(0, 360, 15):
        # A hue on the family reads by construction, in every look.
        for base in LOOK_BASES:
            problems = readability({"base": base, "categories": {"class": {"hue": hue}}})
            assert [p for p in problems if p.field[0] == "categories"] == [], (base, hue)


def test_grey_text_names_every_block_colour_and_its_fix_reads_on_the_blocks_too() -> None:
    """The mock-up's bad colours: grey text on Light fails 4.5 to 1 on every category colour. The Text
    Fix moves the text until it reads on the page, the cards, the calendar and those blocks at once, so
    the categories keep their colours; moved against the surfaces alone, it left every block to fix."""
    grey = {"base": "light", "colours": {"text": "#999999"}}
    blocks = [p for p in readability(grey) if p.field[0] == "categories"]
    assert [p.field[1] for p in blocks] == list(CATEGORIES)
    assert {p.ink for p in blocks} == {"#999999"}
    assert all(p.ratio < AA_TEXT for p in blocks)
    text = next(p for p in readability(grey) if p.field == ("colours", "text"))
    mended = apply_fix(grey, text)
    remaining = readability(mended)
    assert all(problem.field == ("accent",) for problem in remaining)
    assert "categories" not in mended
    # A block on the other side of mid-grey from the page cannot share one text with it: that block
    # keeps its own Fix, and the text still reads on the page and the cards.
    dark_study = {**grey, "categories": {"study": {"colour": "#2a1f5c"}}}
    text = next(p for p in readability(dark_study) if p.field == ("colours", "text"))
    left = readability(apply_fix(dark_study, text))
    assert [p.field for p in left if p.field != ("accent",)] == [("categories", "study")]


def test_an_import_with_a_not_a_number_value_leaves_it_out_and_says_so() -> None:
    """Python's JSON reader accepts NaN, which no file format and no engine value allows. The wrapper
    rewrites it before the engine sees it, so the look keeps what it can and names the bad field."""
    got = import_look('{"kind": "FlexWeek look", "version": 1, "base": "poster", "corners": NaN}')
    assert got.look == {"base": "poster", "name": "My look"}
    assert len(got.problems) == 1 and "Corners" in got.problems[0]
