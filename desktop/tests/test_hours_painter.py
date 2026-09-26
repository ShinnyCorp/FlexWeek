"""A block's words are laid in whole lines: none is cut in half by the edge of the room it has. And
every block is written in the canvas's own font, whatever was drawn before it."""

from __future__ import annotations

import importlib.util
import math
import os
from collections.abc import Iterator

import pytest

from desktop.tests.test_weekmodel import BLOCKS, HOMEWORK, TRACE, WEEK

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter
    from PySide6.QtWidgets import QApplication, QWidget

    from desktop.native.fonts import TABULAR, load_fonts
    from desktop.native.hours import canvas as canvas_module
    from desktop.native.hours.canvas import BlockPainter, Drawn, HoursCanvas, fit_lines
    from desktop.native.hours.geometry import LinearTrack
    from desktop.native.hours.hand import Hand, Verdict
    from desktop.native.layouts.base import Scene
    from desktop.native.layouts.registry import options_for, tokens_for
    from desktop.native.layouts.timeline import TimelineView
    from desktop.native.look import mix, resolved_palette
    from desktop.native.weekmodel import build_week, minute_of

DETAIL = "16:00–17:30 · 1 h 30 min · Missed · Pinned"


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-painter-test"])


def fits(lines: list[str], font: QFont, width: float) -> bool:
    metrics = QFontMetricsF(font)
    return all(metrics.horizontalAdvance(line) <= width for line in lines)


def test_room_for_one_line_gives_one_shortened_line(qapp: QApplication) -> None:
    font = QFont()
    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance(DETAIL) / 2
    lines = fit_lines(DETAIL, font, width, metrics.height())
    assert len(lines) == 1
    assert lines[0].endswith("…")
    assert fits(lines, font, width)


def test_room_for_two_and_a_half_lines_gives_two(qapp: QApplication) -> None:
    font = QFont()
    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance("16:00–17:30 · 1 h") + 1
    lines = fit_lines(DETAIL, font, width, 2.5 * metrics.lineSpacing())
    assert lines[0] == "16:00–17:30 · 1 h"
    assert len(lines) == 2
    assert lines[1].endswith("…")
    assert fits(lines, font, width)


def test_ample_room_says_it_all(qapp: QApplication) -> None:
    font = QFont()
    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance("16:00–17:30 · 1 h") + 1
    lines = fit_lines(DETAIL, font, width, 20 * metrics.lineSpacing())
    assert " ".join(lines) == DETAIL
    assert len(lines) >= 3
    assert fits(lines, font, width)


def test_a_word_wider_than_the_room_is_shortened_and_the_rest_still_follows(qapp: QApplication) -> None:
    font = QFont()
    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance("16:00–1")
    lines = fit_lines("16:00–17:30 · 1 h", font, width, 20 * metrics.lineSpacing())
    assert lines[0].endswith("…") and lines[0] != "16:00–17:30"
    assert lines[1:] == ["· 1 h"]
    assert fits(lines, font, width)


def test_a_line_with_room_for_nothing_but_dots_is_left_out(qapp: QApplication) -> None:
    font = QFont()
    width = QFontMetricsF(font).horizontalAdvance("…") + 1
    assert fit_lines("18:00–18:30 · 30 min", font, width, 20 * QFontMetricsF(font).lineSpacing()) == []


def test_no_room_for_a_whole_line_gives_nothing(qapp: QApplication) -> None:
    font = QFont()
    assert fit_lines(DETAIL, font, 400, QFontMetricsF(font).height() - 1) == []


def test_a_short_ghost_shows_only_whole_lines(qapp: QApplication) -> None:
    """A new block too short for its times on two lines says one line, shortened, rather than two
    with the second cut in half by its bottom edge."""
    font = QFont()
    bold = QFont(font)
    bold.setBold(True)
    metrics = QFontMetricsF(bold)
    words = "Thu 16:00–17:30 · 1 h 30 min"
    # The ghost writes 8 px in from its left, 6 from its right and 3 from its top and bottom.
    rect = QRectF(10, 10, metrics.horizontalAdvance("Thu 16:00–17:30") + 16, 1.5 * metrics.lineSpacing() + 6)
    room = rect.adjusted(8, 3, -6, -3)

    def ghost(text: str) -> QImage:
        image = QImage(240, 120, QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setFont(font)
        BlockPainter(resolved_palette("system", False, None)).ghost(painter, rect, text, True)
        painter.end()
        return image

    written, blank = ghost(words), ghost("")
    inked = [
        y
        for y in range(int(room.top()), int(room.bottom()) + 1)
        for x in range(int(room.left()), int(room.right()) + 1)
        if written.pixel(x, y) != blank.pixel(x, y)
    ]
    assert inked, "the ghost says nothing"
    second = room.top() + metrics.lineSpacing()
    assert max(inked) < second, f"a line starting at y {second:.0f} is cut at the ghost's bottom edge"


HOSTS: list = []
ESSAY = {
    "id": "essay",
    "title": "Essay",
    "kind": "locked",
    "days": [0, 1, 2],
    "start": "16:00",
    "duration_min": 90,
}
MATHS = {"id": "maths", "title": "Maths", "kind": "locked", "days": [1], "start": "09:00", "duration_min": 60}


def test_every_block_is_written_in_the_canvas_font_whatever_was_drawn_before_it(qapp: QApplication) -> None:
    """The same Essay on three days, drawn in one paint. On the first day it follows the hour labels,
    on the second it follows Maths, drawn by a painter that, like Mission's, sets a font of its own
    after the default block; on the third it follows nothing. All three are drawn alike."""

    class Marked(BlockPainter):
        def block(self, painter: QPainter, rect: QRectF, drawn: Drawn, visible: QRectF) -> None:
            super().block(painter, rect, drawn, visible)
            painter.setFont(QFont("DejaVu Sans Mono", 8))

    def columns(area: QRectF) -> list[LinearTrack]:
        # Whole pixels apart, so the same block on each day covers the same pixels.
        return [
            LinearTrack(day, QRectF(60 + 150 * day, 10, 140, 600), first=8 * 60, last=20 * 60)
            for day in range(3)
        ]

    host = QWidget()
    HOSTS.append(host)
    canvas = HoursCanvas(
        Hand(lambda block_id, from_day, span: Verdict(True, ""), host),
        Marked(resolved_palette("system", False, None)),
        columns,
        gutter=56,
    )
    canvas.resize(520, 620)
    occurrences = build_week("2026-09-21", [ESSAY, MATHS], {}, None).occurrences
    # Maths first, so on its day the Essay is drawn after it.
    canvas.set_week(sorted(occurrences, key=lambda item: item.block_id != "maths"))
    canvas.relayout()
    image = canvas.grab().toImage()
    boxes = [canvas.block_rect("essay", day) for day in range(3)]
    essays = [image.copy(QRect(canvas.mapFromGlobal(box.topLeft()), box.size())) for box in boxes]
    assert essays[2] == essays[0], "the Essay after the hour labels is drawn unlike the one after nothing"
    assert essays[2] == essays[1], "the Essay after Maths is drawn unlike the one after nothing"


if importlib.util.find_spec("PySide6") is not None:

    class Said(QPainter):
        """A painter that keeps every word it writes, where, and the ink it covers, in the widget's
        coordinates. Put in place of the canvas module's QPainter, it is the one a real paint event
        draws with."""

        words: list[tuple[str, QRectF]] = []
        inks: list[tuple[str, QRectF]] = []
        fonts: list[tuple[str, QFont]] = []

        def drawText(self, *args: object) -> None:  # noqa: N802
            text = next(arg for arg in reversed(args) if isinstance(arg, str))
            where = next(arg for arg in args if isinstance(arg, (QRectF, QRect, QPointF)))
            box = QRectF(where, where) if isinstance(where, QPointF) else QRectF(where)
            flags = next((arg for arg in args if isinstance(arg, (int, Qt.AlignmentFlag))), 0)
            ink = QFontMetricsF(self.font()).boundingRect(box, int(flags), text)
            Said.words.append((text, self.worldTransform().mapRect(box)))
            Said.inks.append((text, self.worldTransform().mapRect(ink)))
            Said.fonts.append((text, QFont(self.font())))
            super().drawText(*args)


def timeline_week(qapp: QApplication) -> TimelineView:
    options = options_for(None, "timeline")
    palette = resolved_palette("light-frost", False, None, "default")
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    tokens = tokens_for("timeline", options["colour"], palette)
    view = TimelineView()
    HOSTS.append(view)
    view.resize(1150, 700)
    view.show_week(Scene(week, 3, minute_of("17:00"), options, tokens))
    view.show()
    qapp.processEvents()
    return view


def words_on(canvas: HoursCanvas, block_id: str, day: int) -> list[str]:
    box = canvas.block_rect(block_id, day)
    inside = QRectF(QRect(canvas.mapFromGlobal(box.topLeft()), box.size()))
    return [text for text, where in Said.words if inside.contains(where.center())]


@pytest.mark.parametrize("points", [9, 13])
def test_a_short_block_on_sideways_hours_is_its_first_letter_not_dots(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, points: int
) -> None:
    """Timeline's Week at 64 pixels an hour draws the 30-minute Dinner 30 pixels wide: no room for
    any of its name, in three lines of small text or one of large. It says "D", its first letter,
    and nothing else; not lines of "…". A block with room still says its name."""
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    usual = QFont(qapp.font())
    font = QFont(usual)
    font.setPointSize(points)
    qapp.setFont(font)
    try:
        canvas = timeline_week(qapp).hours_surfaces()[0]
        assert canvas.block_rect("dinner", 0).width() < 34
        Said.words = []
        canvas.repaint()
    finally:
        qapp.setFont(usual)
    for day in range(7):
        assert words_on(canvas, "dinner", day) == ["D"], f"Dinner on day {day}"
    assert words_on(canvas, "school", 0)[0].startswith("School")


def test_an_hour_label_at_the_edge_of_what_shows_is_moved_inside_it(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Timeline's Week scrolled so 08:00 sits on the left edge of what shows, then so 20:00 sits on
    its right edge: each label is written whole inside what shows, not cut to ")8:00" or "20:0"."""
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    canvas = timeline_week(qapp).hours_surfaces()[0]
    scroll = canvas._scroll_area()
    port, bar = scroll.viewport(), scroll.horizontalScrollBar()
    track = canvas.tracks[0]
    for label, x in (
        ("08:00", track.area.left() + track.offset(8 * 60)),
        ("20:00", track.area.left() + track.offset(20 * 60) - port.width()),
    ):
        bar.setValue(round(x))
        Said.inks = []
        canvas.repaint()
        shown = QRectF(QRect(canvas.mapFrom(port, QPoint(0, 0)), port.size()))
        ink = [where for text, where in Said.inks if text == label]
        assert len(ink) == 1, f"{label} written {len(ink)} times"
        assert shown.left() <= ink[0].left() and ink[0].right() <= shown.right(), (
            f"{label} runs from {ink[0].left():.0f} to {ink[0].right():.0f}, "
            f"outside {shown.left():.0f} to {shown.right():.0f}"
        )


def test_a_length_is_never_broken_between_its_number_and_unit(qapp) -> None:
    font = QFont()
    metrics = QFontMetricsF(font)
    # Room for "08:00–14:30 · 6" but not for "08:00–14:30 · 6 h".
    width = metrics.horizontalAdvance("08:00–14:30 · 6") + 2
    lines = fit_lines("08:00–14:30 · 6 h 30 min", font, width, metrics.lineSpacing() * 4)
    assert lines == ["08:00–14:30 ·", "6 h 30 min"], lines


HOUR_PX = 48


def three_days(
    now_min: int | None = None, blocks: tuple[dict, ...] = (ESSAY,), hour_px: int = HOUR_PX
) -> HoursCanvas:
    """Three days from 08:00 to 20:00, at Today's app's default 48 pixels an hour unless told, in
    Inter at the normal text size, with today on the first when there is a now."""
    load_fonts()

    def columns(area: QRectF) -> list[LinearTrack]:
        return [
            LinearTrack(day, QRectF(60 + 150 * day, 10, 140, 12 * hour_px), first=8 * 60, last=20 * 60)
            for day in range(3)
        ]

    host = QWidget()
    HOSTS.append(host)
    canvas = HoursCanvas(
        Hand(lambda block_id, from_day, span: Verdict(True, ""), host),
        BlockPainter(resolved_palette("system", False, None)),
        columns,
        gutter=56,
    )
    canvas.setFont(QFont("Inter", 12))
    canvas.resize(520, 12 * hour_px + 20)
    occurrences = build_week("2026-09-21", list(blocks), {}, None).occurrences
    canvas.set_week(occurrences, 0 if now_min is not None else None, now_min)
    canvas.relayout()
    return canvas


def test_every_time_on_the_hours_is_written_in_figures_of_one_width(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inter's figures are proportional: without tabular ones, 11:00 is narrower than 20:00 and a
    column of hours or a block's times wobble."""
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    canvas = three_days(now_min=15 * 60 + 40)
    Said.fonts = []
    canvas.grab()
    timed = [(text, font) for text, font in Said.fonts if any(letter.isdigit() for letter in text)]
    assert {"08:00", "20:00"} <= {text for text, _font in timed}
    assert any("16:00–17:30" in text for text, _font in timed)
    for text, font in timed:
        assert font.featureValue(QFont.Tag(TABULAR)) == 1, text


CLUB = {"id": "club", "title": "Club", "kind": "locked", "days": [1], "start": "19:00", "duration_min": 60}


def test_a_one_hour_block_says_its_name_and_its_times_on_two_lines(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Club at 19:00 for an hour was one shortened line, "Club · 19:00–20:00 · …", when it had room
    for its name in bold and its times in the smaller font below: the test asked for two bold lines.
    Here it has just that room, which is less than two bold lines, and at the default 48 pixels an
    hour it has more."""
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    font = QFont("Inter", 12)
    bold = QFont(font)
    bold.setBold(True)
    bold_line = QFontMetricsF(bold).height()
    just = math.ceil(bold_line + 1 + QFontMetricsF(canvas_module._small(font)).height())
    assert just < 2 * bold_line
    # A block's words have its height less 7 pixels: 2 between blocks, 3 above and 2 below.
    for hour_px in (just + 7, HOUR_PX):
        canvas = three_days(blocks=(CLUB,), hour_px=hour_px)
        Said.words = []
        canvas.grab()
        assert words_on(canvas, "club", 1) == ["Club", "19:00–20:00 · 1 h"], hour_px


def rows(palette: dict, today: bool) -> QImage:
    """One track from 08:00 to 10:00 at 48 pixels an hour, painted on the window colour."""
    track = LinearTrack(0, QRectF(10, 10, 100, 2 * HOUR_PX), first=8 * 60, last=10 * 60)
    image = QImage(120, 2 * HOUR_PX + 20, QImage.Format.Format_ARGB32)
    image.fill(QColor(palette["window"]))
    painter = QPainter(image)
    BlockPainter(palette).track(painter, track, today)
    painter.end()
    return image


def test_the_hours_have_a_rule_at_each_hour_and_none_at_the_half(qapp: QApplication) -> None:
    """The dashed half-hour rules crowded the grid. On a dark look the hour rules take the stronger
    hairline, since the plain one all but vanished on the page."""
    for pack, dark, rule in (("slate", False, "hairline"), ("nocturne", True, "hairline_strong")):
        palette = resolved_palette(pack, dark, None)
        image = rows(palette, today=False)
        at = {minute: 10 + (minute - 8 * 60) * HOUR_PX // 60 for minute in (8 * 60 + 30, 9 * 60)}
        assert QColor(image.pixel(60, at[9 * 60])).name() == palette[rule], pack
        assert QColor(image.pixel(60, at[8 * 60 + 30])).name() == palette["window"], pack


def test_today_is_washed_in_a_tenth_of_the_accent(qapp: QApplication) -> None:
    palette = resolved_palette("slate", False, None)
    washed = QColor(rows(palette, today=True).pixel(60, 10 + HOUR_PX // 2))
    wanted = QColor(mix(palette["accent"], palette["window"], 0.10))
    for got, want in zip(washed.getRgb()[:3], wanted.getRgb()[:3], strict=True):
        assert abs(got - want) <= 1, (washed.name(), wanted.name())


def test_the_now_line_carries_the_time_on_a_pill_at_its_start(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The line said where now is but not what time it is. At 15:40 it starts from a pill in the
    error colour reading "15:40", level with the line."""
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    canvas = three_days(now_min=15 * 60 + 40)
    Said.inks = []
    image = canvas.grab().toImage()
    track = canvas.tracks[0]
    line_y = track.area.top() + track.offset(15 * 60 + 40)
    written = [where for text, where in Said.inks if text == "15:40"]
    assert len(written) == 1
    assert abs(written[0].center().y() - line_y) <= 2
    assert track.area.left() <= written[0].left() < track.area.left() + 12
    error = resolved_palette("system", False, None)["error"]
    assert QColor(image.pixel(int(track.area.left()) + 3, round(line_y))).name() == error
