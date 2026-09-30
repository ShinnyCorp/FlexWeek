"""The approved 0.17.2 looks keep their category and accent differences readable."""

from __future__ import annotations

import pytest

from desktop.native.calendar import CATEGORIES
from desktop.native.custom_look import apply_fix, readability
from desktop.native.look import ACCENT_COLORS, look_measures, resolved_palette
from desktop.native.tokens import contrast, oklab, oklch_of
from desktop.tests.test_hours_painter import qapp as qapp


@pytest.mark.parametrize(("category", "hue"), [
    ("class", 250), ("assignments", 25), ("study", 320), ("exercise", 150),
    ("extra", 200), ("meals", 70), ("sleep", 280),
])
def test_the_categories_use_the_hues_in_the_approved_mockup(category: str, hue: int) -> None:
    assert CATEGORIES[category]["hue"] == hue


def test_sleep_is_darker_than_the_other_light_fills() -> None:
    sleep = oklab(CATEGORIES["sleep"]["color"])[0]
    assert all(oklab(info["color"])[0] - sleep >= 0.05
               for key, info in CATEGORIES.items() if key != "sleep")


def test_paper_is_a_cream_planner_with_serif_figures() -> None:
    palette = resolved_palette("light-frost", False, {"preset": "paper"})
    assert palette["accent"] == "#1f3a68"
    assert palette["panel"] == "#fbf6ea"
    assert look_measures({"preset": "paper"})["body"].startswith("Newsreader")


def test_pastel_has_tinted_cards_and_fuller_fills() -> None:
    pastel = resolved_palette("light-frost", False, {"preset": "pastel"})
    assert pastel["panel"] != "#ffffff"
    assert pastel.get("fill", (1.0, 0.0))[0] < 0.92


@pytest.mark.parametrize("axis", ["light", "dark"])
def test_sand_is_distinct_from_gold_and_reads_as_text(axis: str) -> None:
    gold, sand = ACCENT_COLORS["gold"][axis][0], ACCENT_COLORS["sand"][axis][0]
    a, b = oklab(gold), oklab(sand)
    assert sum((first - second) ** 2 for first, second in zip(a, b, strict=True)) ** 0.5 >= 0.05
    hue_a, hue_b = oklch_of(gold)[2], oklch_of(sand)[2]
    assert min(abs(hue_a - hue_b), 360 - abs(hue_a - hue_b)) >= 20
    palette = resolved_palette("dark-frost" if axis == "dark" else "light-frost", False, None, accent="sand")
    assert contrast(palette["accent"], palette["panel"]) >= 4.5


def test_readability_names_each_use_of_a_pale_accent_and_fixes_them() -> None:
    custom = {"name": "Lime", "base": "light", "accent": "#dfff00"}
    problems = readability(custom)
    named = {problem.words: problem for problem in problems}
    for words in ("Plan button words", "Today's day name", "Now line"):
        assert words in named
        fixed = apply_fix(custom, named[words])
        palette = resolved_palette("light-frost", False, {"custom": fixed})
        ratios = [contrast(palette["accent"], palette[under]) for under in ("window", "panel", "grid")]
        assert min(ratios) >= 4.5


def test_a_pale_custom_accent_stays_chosen_but_its_words_are_readable() -> None:
    from desktop.native.look import button_rules, mix

    palette = resolved_palette("light-frost", False, {"custom": {
        "name": "Lime", "base": "light", "accent": "#dfff00",
    }})
    assert palette["accent"] == "#dfff00"
    tint = mix(palette["accent"], palette["window"], 0.10)
    assert contrast(palette.get("accent_text", palette["accent"]), tint) >= 4.5
    assert contrast(palette.get("now", palette["accent"]), palette["grid"]) >= 4.5
    assert f'color: {palette["accent_text"]};' in button_rules(palette, 8, 6, "flat", "")


@pytest.mark.parametrize("accent", [None, "default", "sky", "gold", "sea", "sand"])
def test_stock_accents_have_no_readability_warning(accent: str | None) -> None:
    custom = {"name": "Stock", "base": "light"}
    if accent is not None:
        custom["accent"] = accent
    assert not [problem for problem in readability(custom) if problem.field == ("accent",)]


@pytest.mark.parametrize("large", [False, True])
def test_high_contrast_look_card_keeps_its_large_title_on_one_line(qapp, large: bool) -> None:
    from PySide6.QtWidgets import QLabel

    from desktop.native.look import pack_stylesheet
    from desktop.native.settings import LookPicker
    from desktop.native.tokens import TEXT_SCALE

    picker = LookPicker("testLook")
    knobs = {"text": "large"} if large else {"text": "normal"}
    picker.setStyleSheet(pack_stylesheet("high-contrast", False, {"knobs": knobs}))
    picker.set_text_scale(TEXT_SCALE[knobs["text"]])
    picker.resize(700, 800)
    picker.show()
    qapp.processEvents()
    card = next(card for card in picker.more.cards if card.accessibleName() == "High contrast")
    label = card.findChild(QLabel, "setupChoiceName")
    assert label.fontMetrics().horizontalAdvance(label.text()) <= label.contentsRect().width()
    assert label.heightForWidth(label.width()) <= label.fontMetrics().lineSpacing() + 2
    picker.close()


def _laid_out(qapp, title: str, room_for: str, lines: int):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont, QFontMetricsF

    from desktop.native.hours.canvas import Drawn, block_layout
    from desktop.native.hours.geometry import Span

    font = QFont(qapp.font())
    metrics = QFontMetricsF(font)
    room = QRectF(0, 0, metrics.horizontalAdvance(room_for) + 1, metrics.lineSpacing() * lines + 1)
    drawn = Drawn("block", title, "class", False, Span(0, 480, 540), 0, 1)
    return block_layout(drawn, font, font, room, book=True)


@pytest.mark.parametrize(("title", "room_for", "lines", "wanted"), [
    # One line with room for the name or for the icon and less of the name.
    ("School", "School", 1, ["School"]),
    ("Piano lesson", "Piano lesson", 1, ["Piano lesson"]),
    # Two lines: nothing follows "Swimming" on its line, so its own width is room enough.
    ("Swimming gala", "Swimming", 2, ["Swimming", "gala"]),
    # Shortened either way: at a word without the icon, inside one with it.
    ("Science poster", "Science…", 1, ["Science…"]),
])
def test_the_icon_gives_way_where_it_would_cost_the_name(
    qapp, title: str, room_for: str, lines: int, wanted: list[str],
) -> None:
    """Jonathan's decision: a small block keeps its name, and its icon is left out only when it must
    be. Beside the icon Piano lesson read "Piano…" in High contrast, and Soccer practice "Soc…" over
    "practice" in Mission control."""
    lay = _laid_out(qapp, title, room_for, lines)
    assert [line.text for line in lay if line.title] == wanted
    assert not any(line.book for line in lay)


@pytest.mark.parametrize(("title", "room_for", "wanted"), [
    ("School", "School and more", ["School"]),
    # Shortened at a word with the icon and without it: the icon costs the name nothing.
    ("Math worksheet", "Math works", ["Math…"]),
])
def test_the_icon_stays_where_it_costs_the_name_nothing(
    qapp, title: str, room_for: str, wanted: list[str],
) -> None:
    lay = _laid_out(qapp, title, room_for, 1)
    assert [line.text for line in lay if line.title] == wanted
    assert [line.book for line in lay if line.title] == [True]


LIGHT_AND_HIGH_CONTRAST = [None, {"preset": "high-contrast", "knobs": {}}]


def _dinner_on_the_week(monkeypatch: pytest.MonkeyPatch, look: dict | None, minutes: int, hour_px: int):
    """What a meals block of `minutes` at 18:30 writes and draws on a week of `hour_px` pixels an hour."""
    from PySide6.QtGui import QFont

    from desktop.native import icons
    from desktop.native.hours import canvas as canvas_module
    from desktop.native.hours.canvas import BlockPainter
    from desktop.tests.test_hours_painter import Said, three_days, words_on

    monkeypatch.setattr(canvas_module, "QPainter", Said)
    drew: list[str] = []
    real = icons.pixmap

    def pixmap(name: str, *rest: object):
        drew.append(name)
        return real(name, *rest)

    monkeypatch.setattr(icons, "pixmap", pixmap)
    palette = resolved_palette("system", False, look)
    dinner = {"id": "dinner", "title": "Dinner", "kind": "locked", "category": "meals", "days": [0],
              "start": "18:30", "duration_min": minutes}
    # 132 pixels, the width of a day on the week at 1280 pixels across.
    canvas = three_days(blocks=(dinner,), palette=palette, hour_px=hour_px, column=132)
    canvas.set_painter(BlockPainter(palette, look))
    # The app's own text size at 1280 pixels across: Inter at 13 points, and High contrast's Large.
    canvas.setFont(QFont("Inter", 15.5 if look else 13))
    Said.words = []
    canvas.grab()
    return words_on(canvas, "dinner", 0), drew


@pytest.mark.parametrize("look", LIGHT_AND_HIGH_CONTRAST, ids=["light", "high-contrast"])
def test_a_half_hour_writes_its_start_time_rather_than_its_icon(
    qapp, monkeypatch: pytest.MonkeyPatch, look: dict | None,
) -> None:
    """Jonathan's decision: the name, then the time, then the icon. A half-hour Dinner at the week's
    48 pixels an hour has room for "Dinner 18:30" or for the icon and "Dinner", and says the time."""
    words, icons_drawn = _dinner_on_the_week(monkeypatch, look, 30, 48)
    assert words == ["Dinner", "18:30"]
    assert icons_drawn == []


@pytest.mark.parametrize("look", LIGHT_AND_HIGH_CONTRAST, ids=["light", "high-contrast"])
def test_a_block_with_room_for_the_name_the_time_and_the_icon_has_all_three(
    qapp, monkeypatch: pytest.MonkeyPatch, look: dict | None,
) -> None:
    words, icons_drawn = _dinner_on_the_week(monkeypatch, look, 60, 96)
    assert words[0] == "Dinner" and "18:30–19:30" in words
    assert icons_drawn == ["clock"]


def _half_hour_layout(qapp, width: float):
    """A one-line half-hour Dinner with the icon offered, in a room `width` wide."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont, QFontMetricsF

    from desktop.native.hours.canvas import Drawn, block_layout
    from desktop.native.hours.geometry import Span

    font = QFont(qapp.font())
    metrics = QFontMetricsF(font)
    drawn = Drawn("dinner", "Dinner", "meals", False, Span(0, 18 * 60 + 30, 19 * 60), 0, 1)
    room = QRectF(0, 0, width, metrics.lineSpacing() + 1)
    return block_layout(drawn, font, font, room, book=True)


def _half_hour_widths(qapp) -> tuple[float, float, float]:
    """The room "Dinner 18:30" takes, "Dinner" alone, and the icon."""
    from PySide6.QtGui import QFont, QFontMetricsF

    from desktop.native.hours.canvas import INLINE_GAP, _book_room

    metrics = QFontMetricsF(QFont(qapp.font()))
    name = metrics.horizontalAdvance("Dinner")
    return name + INLINE_GAP + metrics.horizontalAdvance("18:30"), name, _book_room(metrics)


def test_a_line_with_room_for_the_name_and_its_time_but_not_the_icon_too_says_the_time(qapp) -> None:
    both, _name, _icon = _half_hour_widths(qapp)
    lay = _half_hour_layout(qapp, both + 1)
    assert [line.text for line in lay] == ["Dinner", "18:30"]
    assert not any(line.book for line in lay)


def test_a_line_with_room_for_the_name_and_the_icon_but_no_time_keeps_the_icon(qapp) -> None:
    _both, name, icon = _half_hour_widths(qapp)
    lay = _half_hour_layout(qapp, name + icon + 1)
    assert [line.text for line in lay] == ["Dinner"]
    assert [line.book for line in lay] == [True]


def test_a_line_with_room_for_the_name_alone_writes_the_name_alone(qapp) -> None:
    _both, name, _icon = _half_hour_widths(qapp)
    lay = _half_hour_layout(qapp, name + 1)
    assert [line.text for line in lay] == ["Dinner"]
    assert not any(line.book for line in lay)


def test_a_line_with_room_for_the_name_the_time_and_the_icon_has_all_three(qapp) -> None:
    both, _name, icon = _half_hour_widths(qapp)
    lay = _half_hour_layout(qapp, both + icon + 1)
    assert [line.text for line in lay] == ["Dinner", "18:30"]
    assert lay[0].book


@pytest.mark.parametrize(("category", "wanted"), [
    ("class", "house"), ("assignments", "book-open"), ("study", "pencil"),
    ("exercise", "target"), ("extra", "sparkles"), ("meals", "clock"), ("sleep", "moon"),
])
@pytest.mark.parametrize("design", ["classic", "mission", "clay"])
def test_each_category_paints_its_approved_icon_with_readable_ink(
    qapp, monkeypatch: pytest.MonkeyPatch, category: str, wanted: str, design: str,
) -> None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont, QImage, QPainter

    from desktop.native import icons
    from desktop.native.hours.canvas import BlockPainter, Drawn
    from desktop.native.hours.geometry import Span
    from desktop.native.layouts.clay import ClayPainter
    from desktop.native.layouts.mission import MissionPainter
    from desktop.native.layouts.registry import MATCH, tokens_for

    palette = resolved_palette("light-frost", False, None)
    painter = BlockPainter(palette) if design == "classic" else (
        MissionPainter(tokens_for("mission", MATCH, palette)) if design == "mission"
        else ClayPainter(tokens_for("clay", MATCH, palette), full=True)
    )
    drawn = Drawn("test", "School", category, False, Span(0, 480, 660), 0, 1)
    fill, ink, _outline, edge = painter.fills(drawn)
    used: list[tuple[str, str]] = []
    original = icons.pixmap

    def record(name, colour, *args):
        used.append((name, colour))
        return original(name, colour, *args)

    monkeypatch.setattr(icons, "pixmap", record)
    picture = QImage(500, 300, QImage.Format.Format_ARGB32)
    picture.fill(fill)
    paint = QPainter(picture)
    paint.setFont(QFont("Inter", 12))
    try:
        painter.words(paint, QRectF(0, 0, 480, 280), drawn, ink, QRectF(0, 0, 500, 300), fill, edge)
    finally:
        paint.end()
    assert any(name == wanted for name, _colour in used), used
    assert all(contrast(colour, fill.name()) >= 4.5 for name, colour in used if name == wanted)


@pytest.mark.parametrize("look_name", [
    "light", "dark", "high-contrast", "slate", "nocturne", "paper", "ink", "terminal", "poster", "pastel",
])
@pytest.mark.parametrize("style", ["edge", "filled", "outline", "none"])
def test_category_icons_read_on_each_block_style(qapp, look_name: str, style: str) -> None:
    from desktop.native.hours.canvas import BlockPainter, Drawn
    from desktop.native.hours.geometry import Span
    from desktop.native.look import LOOK_BASES, category_paint, sanitize_look

    pack, preset = LOOK_BASES[look_name]
    look = sanitize_look({"preset": preset, "knobs": {"blocks": style}})
    palette = resolved_palette(pack, False, look)
    painter = BlockPainter(palette, look)
    for category in CATEGORIES:
        drawn = Drawn("test", "School", category, False, Span(0, 480, 660), 0, 1)
        fill, ink, _outline, edge = painter.fills(drawn)
        colour = painter._book_colour(drawn, ink, fill, edge)
        assert colour is not None
        assert contrast(colour.name(), fill.name()) >= 4.5, (look_name, style, category)
        _fill, mark = category_paint(category, palette)
        if edge is not None and contrast(mark, fill.name()) >= 4.5:
            assert colour.name() == mark


def test_terminal_next_card_shows_its_whole_time_sentence(qapp) -> None:
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from desktop.native.hours.rail import RAIL_PX, NextCard
    from desktop.native.look import pack_stylesheet
    from desktop.native.weekmodel import build_week

    host = QWidget()
    host.setStyleSheet(pack_stylesheet("light-frost", False, {"preset": "terminal"}))
    card = NextCard(host)
    layout = QVBoxLayout(host)
    layout.addWidget(card)
    host.resize(RAIL_PX, 300)
    card.show_next(build_week("2026-09-28", [{
        "id": "school", "title": "School", "kind": "locked", "category": "class",
        "start": "08:00", "duration_min": 405, "days": [1],
    }], [], None), 1, 620)
    host.show()
    try:
        for _ in range(4):
            qapp.processEvents()
        assert card.when.wordWrap()
        assert card.when.height() >= card.when.heightForWidth(card.when.width())
        assert card.when.text().endswith("4 h 25 min left")
    finally:
        from shiboken6 import delete

        delete(host)


def test_dark_selected_segment_has_a_lighter_chip_and_a_one_pixel_ring(qapp, monkeypatch) -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QPainter, QPalette
    from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

    from desktop.native import widgets
    from desktop.native.look import pack_stylesheet

    host = QWidget()
    host.setStyleSheet(pack_stylesheet("dark-frost", False, None))
    track = widgets.SegmentTrack(host)
    track.setObjectName("segments")
    row = QHBoxLayout(track)
    chosen = QPushButton("Week")
    chosen.setObjectName("viewWeek")
    chosen.setCheckable(True)
    chosen.setChecked(True)
    row.addWidget(chosen)
    layout = QVBoxLayout(host)
    layout.addWidget(track)
    host.resize(300, 70)
    host.show()
    drew: list[tuple[QRectF, str, float, object]] = []

    class Rings(QPainter):
        def drawRoundedRect(self, box, *args):  # noqa: N802
            drew.append((QRectF(box), self.pen().color().name(), self.pen().widthF(), self.pen().style()))
            return super().drawRoundedRect(box, *args)

    monkeypatch.setattr(widgets, "QPainter", Rings)
    try:
        for _ in range(4):
            qapp.processEvents()
        colours = track.palette()
        assert oklab(colours.color(QPalette.ColorRole.Highlight).name())[0] - oklab(
            colours.color(QPalette.ColorRole.AlternateBase).name()
        )[0] >= 0.05
        track.grab()
        target = QRectF(chosen.geometry())
        assert any(box == target and colour == "#7fa8ff" and width == 1
                   and style == Qt.PenStyle.SolidLine for box, colour, width, style in drew), drew
    finally:
        from shiboken6 import delete

        delete(host)



def test_paper_has_no_shadows_and_pastel_has_rounder_corners() -> None:
    from desktop.native.look import effective_look

    assert effective_look({"preset": "paper"})["depth"] == "none"
    assert look_measures({"preset": "pastel"})["card_radius"] > look_measures(None)["card_radius"]


def test_chosen_blue_stays_exact_with_readable_now_and_selection() -> None:
    palette = resolved_palette("light-frost", False, None)
    assert palette["accent"] == "#3d6fc4"
    assert palette["now"] == palette["selection"]
    for category in CATEGORIES:
        from desktop.native.look import category_paint

        assert contrast(palette["now"], category_paint(category, palette)[0]) >= 3
