"""0.18.5 #57 and #58: the readability warning reads naturally, the preview shows the darkened colour while
it stands, a Fix aims at the hardest check, and Fix all fixes every problem."""

# ruff: noqa: F811  (pytest fixtures imported by name)

from __future__ import annotations

import re

import pytest

from desktop.native.custom_look import apply_fix, readability
from desktop.native.look import pack_stylesheet, resolved_palette
from desktop.native.look_editor import fix_all, problem_rows
from desktop.native.tokens import contrast, oklch_of
from desktop.tests.window_support import qapp, server, signed_out, window  # noqa: F401

LIME = {"name": "Lime", "base": "light", "accent": "#dfff00"}
GREY_AND_LIME = {**LIME, "colours": {"text": "#9aa0a6", "muted": "#c0c4c8"}}


def sentences(custom: dict) -> list[str]:
    return [row.words for row in problem_rows(readability(custom))]


def test_the_plan_buttons_warning_reads_in_plain_english() -> None:
    said = sentences(LIME)
    plan = next(words for words in said if "Plan" in words)
    assert re.fullmatch(r"The Plan button's words are \d\.\d:1", plan), plan
    # A singular subject keeps "is".
    assert any(re.fullmatch(r"Today's day name is \d\.\d:1", words) for words in said), said


def test_a_text_colour_warning_still_says_is() -> None:
    assert any(re.fullmatch(r"Text on the page is \d\.\d:1", words) for words in sentences(GREY_AND_LIME))


def test_every_warning_row_is_a_sentence_with_a_verb_and_a_ratio() -> None:
    for words in sentences(GREY_AND_LIME):
        assert re.search(r" (is|are) \d\.\d:1", words), words


@pytest.mark.parametrize("custom", [LIME, GREY_AND_LIME], ids=["lime", "grey text and lime"])
def test_one_rows_fix_leaves_no_row_of_the_same_colour_failing(custom: dict) -> None:
    for row in problem_rows(readability(custom)):
        fixed = custom
        for problem in row.fixes:
            fixed = apply_fix(fixed, problem)
        fields = {problem.field for problem in row.fixes}
        left = [problem for problem in readability(fixed) if problem.field in fields]
        assert not left, (row.words, [(problem.words, problem.ratio) for problem in left])


def test_fix_all_fixes_every_problem_not_only_the_first(monkeypatch) -> None:
    from desktop.native import look_editor

    custom = GREY_AND_LIME
    assert len({problem.field for problem in readability(custom)}) > 4
    # Two rounds are enough only if each round fixes every problem, not one of them.
    monkeypatch.setattr(look_editor, "FIX_ALL_ROUNDS", 2)
    assert readability(fix_all(custom, False)) == []


def test_fix_all_leaves_a_look_that_reads_in_the_dark_too() -> None:
    dark = {"name": "D", "base": "dark", "colours": {"text": "#3a3f47", "muted": "#2a2f36"}}
    assert len(readability(dark, True)) > 1
    assert readability(fix_all(dark, True), True) == []


PALE = ["#dfff00", "#f5d76e", "#ffd1dc", "#bff3ff", "#98ff98", "#00ffff", "#ffff99"]


@pytest.mark.parametrize("accent", PALE)
def test_a_fix_changes_lightness_only_and_keeps_the_hue(accent: str) -> None:
    custom = {"name": "P", "base": "light", "accent": accent}
    light, chroma, hue = oklch_of(accent)
    for problem in readability(custom):
        if problem.field != ("accent",):
            continue
        new_light, new_chroma, new_hue = oklch_of(problem.fixed)
        gap = abs(hue - new_hue)
        assert min(gap, 360 - gap) <= 12, (accent, problem.fixed)
        assert new_chroma >= min(chroma, 0.04) * 0.9, (accent, problem.fixed, "went grey")
        assert new_light < light, (accent, "a pale accent is darkened")


def link_colours(css: str) -> list[str]:
    names = ("planReviewDetails", "planReviewReplan", "updateSkip", "authSwitch", "authWhy")
    found = []
    for name in names:
        match = re.search(rf"QPushButton#{name}[^{{]*\{{[^}}]*?[; ]color: (#[0-9a-f]{{6}})", css)
        if match:
            found.append(match.group(1))
    return found


def test_words_in_a_pale_typed_accent_are_drawn_darkened_while_the_warning_stands() -> None:
    look = {"custom": LIME}
    palette = resolved_palette("system", False, look)
    assert palette["accent"] == "#dfff00", "a typed accent stays as typed"
    assert readability(LIME)
    colours = link_colours(pack_stylesheet("system", False, look, "default", palette))
    assert len(colours) >= 4, colours
    for colour in colours:
        for ground in ("window", "panel", "grid"):
            assert contrast(colour, palette[ground]) >= 4.5, (colour, ground)


def test_an_accent_that_already_reads_is_not_moved() -> None:
    palette = resolved_palette("system", False, None)
    colours = link_colours(pack_stylesheet("system", False, None, "default", palette))
    assert colours and set(colours) == {palette["accent"]}, colours


# #59: the editor in the window.


def _open(qapp, window):
    from desktop.native import motion
    from desktop.tests.test_look_editor import open_editor, pump
    from desktop.tests.window_support import wait_until

    page, editor = open_editor(qapp, window)
    wait_until(qapp, lambda: not motion.busy())
    pump(qapp, 20)
    return page, editor


def test_any_colour_ends_where_page_cards_text_and_lines_end(qapp, window) -> None:
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QWidget

    _page, editor = _open(qapp, window)

    def span(name: str) -> tuple[int, int]:
        field = editor.findChild(QWidget, f"lookColour-{name}")
        left = field.mapTo(editor, QPoint(0, 0)).x()
        return left, left + field.width()

    assert span("accent")[1] == span("page")[1] == span("card")[1] == span("text")[1] == span("line")[1]
    assert span("accent")[0] == span("page")[0], "the swatch starts where the others' do"


def test_reset_all_export_and_import_are_outlined_like_save_as_new(qapp, window) -> None:
    from PySide6.QtWidgets import QPushButton

    from desktop.native.look import outline_edge, resolved_palette

    _page, editor = _open(qapp, window)
    pack, dark, accent = window._look_inputs()
    palette = resolved_palette(pack, dark, window._look, accent)
    edge = outline_edge(palette)
    for name in ("lookResetAll", "lookExport", "lookImport"):
        button = editor.findChild(QPushButton, name)
        picture = button.grab().toImage()
        # The middle of the button's left side is its 1 px edge; two pixels in is the button's own fill.
        middle = picture.height() // 2
        pixel, inside = picture.pixelColor(0, middle), picture.pixelColor(3, middle)
        assert pixel != inside, (name, "no edge")
        if button.isEnabled():
            assert all(abs(a - b) <= 6 for a, b in zip(pixel.getRgb()[:3], _rgb(edge), strict=True)), (
                name,
                pixel.name(),
            )


def _rgb(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)
