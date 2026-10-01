"""A block's words are laid in whole lines: none is cut in half by the edge of the room it has. And
every block is written in the canvas's own font, whatever was drawn before it."""

from __future__ import annotations

import importlib.util
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
    from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

    from desktop.native.fonts import TABULAR, load_fonts
    from desktop.native.hours import canvas as canvas_module
    from desktop.native.hours.canvas import BlockPainter, Drawn, HoursCanvas, fit_lines
    from desktop.native.hours.geometry import Axis, LinearTrack, Span
    from desktop.native.hours.hand import Hand, Verdict
    from desktop.native.hours.zoom import HoursScroll, Scale
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


def lane_week(qapp: QApplication) -> HoursCanvas:
    """Seven lanes whose time runs across at 64 pixels an hour, with the hour labels in a strip
    above them, as Mission control lays its week out."""

    def lanes(area: QRectF) -> list[LinearTrack]:
        tall = area.height() / 7
        return [
            LinearTrack(
                day,
                QRectF(area.left() + 24, area.top() + day * tall + 6, area.width() - 48, tall - 12),
                Axis.ACROSS,
            )
            for day in range(7)
        ]

    host = QWidget()
    HOSTS.append(host)
    canvas = HoursCanvas(
        Hand(lambda block_id, from_day, span: Verdict(True, ""), host),
        BlockPainter(resolved_palette("light-frost", False, None, "default")),
        lanes,
    )
    scroll = HoursScroll(
        canvas,
        Scale("lanes.week", (48, 64, 80, 96), 64),
        lambda px: 24 * px + 48,
        name="lanes",
        gutter=170,
        axis=Axis.ACROSS,
    )
    QVBoxLayout(host).addWidget(scroll)
    host.resize(1150, 700)
    canvas.set_week(build_week(WEEK, BLOCKS, HOMEWORK, TRACE).occurrences, 3, minute_of("17:00"))
    host.show()
    qapp.processEvents()
    return canvas


def words_on(canvas: HoursCanvas, block_id: str, day: int) -> list[str]:
    box = canvas.block_rect(block_id, day)
    inside = QRectF(QRect(canvas.mapFromGlobal(box.topLeft()), box.size()))
    return [text for text, where in Said.words if inside.contains(where.center())]


@pytest.mark.parametrize("points", [9, 13])
def test_a_block_with_no_room_for_three_letters_is_its_colour_alone(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, points: int
) -> None:
    """A week of lanes at 64 pixels an hour draws the 30-minute Dinner 30 pixels wide: no room for
    three letters of its name. Decision 14 of 0.17: below three letters, the colour alone, not "D"
    seven times down the week and not lines of "…". A block with room still says its name."""
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    usual = QFont(qapp.font())
    font = QFont(usual)
    font.setPointSize(points)
    qapp.setFont(font)
    try:
        canvas = lane_week(qapp)
        assert canvas.block_rect("dinner", 0).width() < 34
        Said.words = []
        canvas.repaint()
        school = words_on(canvas, "school", 0)
        # Dinner in view, or it says nothing because it is off screen, whatever the check for letters.
        scroll = canvas.parentWidget()
        while not isinstance(scroll, HoursScroll):
            scroll = scroll.parentWidget()
        scroll.scroll_to(minute_of("18:00"))
        qapp.processEvents()
        port = scroll.viewport()
        seen = QRect(port.mapToGlobal(QPoint(0, 0)), port.size())
        assert all(seen.contains(canvas.block_rect("dinner", day)) for day in range(7))
        Said.words = []
        canvas.repaint()
    finally:
        qapp.setFont(usual)
    for day in range(7):
        assert words_on(canvas, "dinner", day) == [], f"Dinner on day {day}"
    assert school[0].startswith("School")


@pytest.mark.parametrize("axis", [Axis.DOWN, Axis.ACROSS])
def test_a_block_partly_out_of_view_says_nothing_the_edge_of_view_cuts(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, axis: Axis
) -> None:
    """A block scrolled partly out of view has its words laid out in the part that shows: each word
    that is written lies whole inside `visible`, whichever edge cuts the block and however far in,
    and when nothing fits, the colour alone is left. Laid out for the whole block and clipped, a
    word was cut in half at the edge."""
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    load_fonts()
    blocks = BlockPainter(resolved_palette("system", False, None))
    rect = QRectF(100, 100, 170, 90)
    drawn = Drawn("lab", "Photosynthesis lab", "class", False, Span(1, 9 * 60, 10 * 60), 0, 1, axis=axis)
    image = QImage(400, 300, QImage.Format.Format_ARGB32)
    page = QRectF(0, 0, 400, 300)
    # Each edge of what shows, moved a pixel at a time across the block.
    cuts = [
        ("left", lambda at: page.adjusted(at, 0, 0, 0), range(100, 271)),
        ("right", lambda at: page.adjusted(0, 0, at - 400, 0), range(100, 271)),
        ("top", lambda at: page.adjusted(0, at, 0, 0), range(100, 191)),
        ("bottom", lambda at: page.adjusted(0, 0, 0, at - 300), range(100, 191)),
    ]
    for edge, shown, steps in cuts:
        for at in steps:
            visible = shown(at)
            paint = Said(image)
            Said.inks = []
            blocks.block(paint, rect, drawn, visible)
            paint.end()
            for text, ink in Said.inks:
                cut = visible.intersects(ink) and not visible.adjusted(-0.5, -0.5, 0.5, 0.5).contains(ink)
                assert not cut, f"{text!r} is cut by the {edge} edge at {at}: {ink} in {visible}"


def test_an_hour_label_at_the_edge_of_what_shows_is_moved_inside_it(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A week of lanes scrolled so 08:00 sits on the left edge of what shows, then so 20:00 sits on
    its right edge: each label is written whole inside what shows, not cut to ")8:00" or "20:0"."""
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    canvas = lane_week(qapp)
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
    now_min: int | None = None,
    blocks: tuple[dict, ...] = (ESSAY,),
    hour_px: int = HOUR_PX,
    palette: dict | None = None,
    days: int = 3,
    column: int = 140,
) -> HoursCanvas:
    """Three days from 08:00 to 20:00, at Today's app's default 48 pixels an hour unless told, in
    Inter at the normal text size, with today on the first when there is a now."""
    load_fonts()

    def columns(area: QRectF) -> list[LinearTrack]:
        return [
            LinearTrack(day, QRectF(60 + 150 * day, 10, column, 12 * hour_px), first=8 * 60, last=20 * 60)
            for day in range(days)
        ]

    host = QWidget()
    HOSTS.append(host)
    canvas = HoursCanvas(
        Hand(lambda block_id, from_day, span: Verdict(True, ""), host),
        BlockPainter(palette or resolved_palette("system", False, None)),
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
    assert {"09:00", "19:00"} <= {text for text, _font in timed}
    assert any("16:00–17:30" in text for text, _font in timed)
    for text, font in timed:
        assert font.featureValue(QFont.Tag(TABULAR)) == 1, text


CLUB = {"id": "club", "title": "Club", "kind": "locked", "days": [1], "start": "19:00", "duration_min": 60}


DINNER = {"id": "dinner", "title": "Dinner", "kind": "locked", "days": [1], "start": "18:30",
          "duration_min": 30}


def test_a_block_says_the_most_it_can_without_cutting_a_word_or_ending_a_line_in_a_dot(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 14 of 0.17. Club at 19:00 for an hour says its name and its times at the week's 48
    pixels an hour, and its length on a line of its own once there is room; a half-hour Dinner says
    "Dinner 18:30" on one line. No line ends in "·", which 0.16 left dangling after every time."""
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    for hour_px, club in ((HOUR_PX, ["Club", "19:00–20:00"]), (96, ["Club", "19:00–20:00", "1 h"])):
        canvas = three_days(blocks=(CLUB, DINNER), hour_px=hour_px)
        Said.words = []
        canvas.grab()
        assert words_on(canvas, "club", 1) == club, hour_px
        assert not any(text.rstrip().endswith("·") for text, _where in Said.words)
    canvas = three_days(blocks=(DINNER,))
    Said.words = []
    canvas.grab()
    assert words_on(canvas, "dinner", 1) == ["Dinner", "18:30"]
    dinner = [where for text, where in Said.words if text in ("Dinner", "18:30")]
    assert abs(dinner[0].center().y() - dinner[1].center().y()) < 3, "Dinner and its time on one line"


def test_a_word_too_wide_for_its_block_is_shortened_only_when_nothing_else_fits(qapp: QApplication) -> None:
    """A word is never cut while a smaller arrangement would say it whole; with none, the title gives
    way with "…", and with no room for three letters there are no words at all."""
    from desktop.native.hours.canvas import block_layout
    from desktop.native.hours.geometry import Span

    title, small = BlockPainter(resolved_palette("system", False, None)).fonts(QFont("Inter", 12))
    tall = QFontMetricsF(title).lineSpacing() * 4
    drawn = Drawn("long", "Photosynthesis", "class", False, Span(1, 9 * 60, 10 * 60), 0, 1)
    whole = QFontMetricsF(title).horizontalAdvance("Photosynthesis")
    said = [line.text for line in block_layout(drawn, title, small, QRectF(0, 0, whole + 2, tall))]
    assert said[0] == "Photosynthesis"
    narrow = [line.text for line in block_layout(drawn, title, small, QRectF(0, 0, whole / 2, tall))]
    assert narrow[0].endswith("…") and narrow[0] != "…"
    three = QFontMetricsF(title).horizontalAdvance("Pho")
    assert block_layout(drawn, title, small, QRectF(0, 0, three - 1, tall)) == []


def painted(drawn: Drawn, rect: QRectF) -> QImage:
    image = QImage(200, 140, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    BlockPainter(resolved_palette("system", False, None)).body(painter, rect, drawn)
    painter.end()
    return image


def test_a_block_that_shares_its_time_is_drawn_like_one_that_does_not(qapp: QApplication) -> None:
    """Two blocks side by side show they share their time by sitting side by side. The dot that 0.14
    drew at the corner of each said nothing a student could read, and covered the end of the name."""
    rect = QRectF(20, 20, 60, 90)
    alone = Drawn("soccer", "Soccer practice", "extra", False, Span(1, 16 * 60, 17 * 60 + 30), 0, 1)
    shared = Drawn("soccer", "Soccer practice", "extra", False, Span(1, 16 * 60, 17 * 60 + 30), 0, 2)
    assert painted(shared, rect) == painted(alone, rect), "a block that shares its time has a mark on it"


def test_a_half_of_a_column_names_its_block_to_the_last_word_it_has_room_for(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Homework dropped on Soccer leaves each of them half a column. A half that has room for
    "Math…" says that, not "M…"."""
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    load_fonts()
    blocks = BlockPainter(resolved_palette("system", False, None))
    title, _small = blocks.fonts(QFont("Inter", 11))
    need = QFontMetricsF(title).horizontalAdvance("Math…")
    # A block alone keeps 8 pixels before its words and 5 after; a half keeps 4 pixels fewer in all.
    wide = need + 9 + 0.5
    image = QImage(300, 200, QImage.Format.Format_ARGB32)
    page = QRectF(0, 0, 300, 200)
    drawn = Drawn("math", "Math worksheet", "homework", True, Span(1, 16 * 60 + 15, 17 * 60), 1, 2)
    paint = Said(image)
    paint.setFont(QFont("Inter", 11))
    Said.words = []
    blocks.block(paint, QRectF(20, 20, wide, 33), drawn, page)
    paint.end()
    assert [text for text, _where in Said.words] == ["Math…"]


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
    hairline, since the plain one all but vanished on the page; High contrast's are 40 % white, since
    full white turned the grid into graph paper. Nocturne, Ink and Terminal draw looks.css's 8 % of
    their text."""
    high_contrast = {"preset": "high-contrast", "knobs": {}}
    for pack, dark, look, rule in (
        ("slate", False, None, resolved_palette("slate", False, None)["hairline"]),
        ("dark-frost", True, None, resolved_palette("dark-frost", True, None)["hairline_strong"]),
        ("nocturne", True, None, mix("#e0e4f0", "#0a0e27", 0.08)),
        ("light-frost", False, high_contrast, "#666666"),
    ):
        palette = resolved_palette(pack, dark, look)
        image = rows(palette, today=False)
        at = {minute: 10 + (minute - 8 * 60) * HOUR_PX // 60 for minute in (8 * 60 + 30, 9 * 60)}
        assert QColor(image.pixel(60, at[9 * 60])).name() == rule, pack
        assert QColor(image.pixel(60, at[8 * 60 + 30])).name() == palette["window"], pack


def _near(got: QColor, want: str) -> bool:
    return all(abs(a - b) <= 1 for a, b in zip(got.getRgb()[:3], QColor(want).getRgb()[:3], strict=True))


def test_today_is_washed_in_a_little_of_the_text_colour_on_a_week_and_not_at_all_on_a_day(
    qapp: QApplication,
) -> None:
    """Decision 13 of 0.17: 3 % of the text colour at most, never the accent, which picked as Gold
    turned today's column khaki; and none on Day, where washing the one day marks nothing."""
    for pack, dark, accent in (("light-frost", False, "gold"), ("dark-frost", True, "default")):
        palette = resolved_palette(pack, dark, None, accent)
        y = 10 + HOUR_PX // 2
        week = three_days(now_min=15 * 60 + 40, palette=palette).grab().toImage()
        assert _near(week.pixelColor(130, y), mix(palette["text"], palette["window"], 0.03)), pack
        assert _near(week.pixelColor(280, y), palette["window"]), pack
        day = three_days(now_min=15 * 60 + 40, palette=palette, days=1).grab().toImage()
        assert _near(day.pixelColor(130, y), palette["window"]), pack


def test_the_now_line_carries_the_time_on_a_pill_at_its_start(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The line said where now is but not what time it is. At 15:40 it starts from a pill reading
    "15:40", level with the line, in the accent: red is for what cannot be, and now is not that."""
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
    shade = resolved_palette("system", False, None)["now"]
    assert QColor(image.pixel(int(track.area.left()) + 3, round(line_y))).name() == shade


def test_a_now_pill_that_reaches_into_a_block_is_whole_over_its_colour(qapp: QApplication) -> None:
    """At 15:55 the line is four pixels above an Essay that starts at 16:00, and the pill on it
    reaches a few pixels into the Essay. That part is drawn over the Essay's colour, as the line is
    where it crosses a block: under the colour, the pill lost its foot. The Essay is a quarter of an
    hour, too short to say its name: on a block's words the pill is left out, as the line is."""
    canvas = three_days(now_min=15 * 60 + 55, blocks=({**ESSAY, "duration_min": 15},))
    image = canvas.grab().toImage()
    track = canvas.tracks[0]
    line_y = round(track.area.top() + track.offset(15 * 60 + 55))
    essay = canvas.mapFromGlobal(canvas.block_rect("essay", 0).topLeft())
    assert line_y < essay.y() <= line_y + 5
    shade = resolved_palette("system", False, None)["now"]
    assert QColor(image.pixel(int(track.area.left()) + 20, line_y + 6)).name() == shade


def custom_hours(custom: dict) -> tuple[HoursCanvas, dict]:
    """Three days at 15:40 in a custom look on Light, with its painter."""
    look = {"preset": "default", "knobs": {}, "custom": {"base": "light", **custom}}
    palette = resolved_palette("system", False, look)
    canvas = three_days(now_min=15 * 60 + 40, palette=palette)
    canvas.set_painter(BlockPainter(palette, look))
    return canvas, palette


def test_a_custom_look_sets_todays_wash_the_now_line_and_the_edge(qapp: QApplication) -> None:
    """Customise's grid and block settings: today's highlight off, the now line in the text colour,
    and a 6-pixel category edge, where the look's own are a 3 % wash, the accent and 3 pixels."""
    y = 10 + HOUR_PX // 2
    plain, plain_palette = custom_hours({"blocks": "edge"})
    changed, palette = custom_hours(
        {"blocks": "edge", "today_highlight": False, "now_line": "text", "edge_width": 6}
    )
    before, after = plain.grab().toImage(), changed.grab().toImage()
    assert _near(before.pixelColor(130, y), mix(plain_palette["text"], plain_palette["window"], 0.03))
    assert _near(after.pixelColor(130, y), palette["window"])
    track = changed.tracks[0]
    line_y = round(track.area.top() + track.offset(15 * 60 + 40))
    x = int(track.area.right()) - 3
    assert before.pixelColor(x, line_y).name() == plain_palette["now"]
    assert after.pixelColor(x, line_y).name() == palette["text"]
    block = changed.block_rect("essay", 1)
    middle = block.center().y()
    # Five pixels in is past the look's own 3-pixel edge and inside the custom look's 6.
    assert not _near(before.pixelColor(block.left() + 5, middle), plain_palette["block_edge"])
    assert _near(after.pixelColor(block.left() + 5, middle), palette["block_edge"])


def test_a_custom_look_can_leave_out_a_blocks_times_or_its_length(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    for shown, missing, custom in (
        ("16:00–17:30", "1 h 30 min", {"show_lengths": False}),
        ("1 h 30 min", "16:00–17:30", {"show_times": False}),
    ):
        canvas, _palette = custom_hours(custom)
        Said.words = []
        canvas.grab()
        written = " ".join(text for text, _where in Said.words)
        assert shown in written and missing not in written, custom


def test_a_short_block_at_large_text_keeps_its_title_first_and_whole_words(qapp: QApplication) -> None:
    """At Large text a 45-minute block on the week has room for one line. "Piano lesson" is said
    whole; "Math worksheet", which cannot be, gives way at a space, "Math…", and its name comes before
    its time: not "Mat… 19:00", nor "Math works…"."""
    from desktop.native.hours.canvas import TEXT_LEFT, TEXT_RIGHT, TEXT_TOP, block_layout
    from desktop.native.hours.geometry import Span

    large = {"preset": "default", "knobs": {"text": "large"}}
    title, small = BlockPainter(resolved_palette("system", False, None), large).fonts(QFont("Inter", 15))
    # A column of the week beside the rail at 1280, 45 minutes at 48 pixels an hour.
    rect = QRectF(0, 0, 128, 45 * 48 / 60 - 3)
    room = rect.adjusted(TEXT_LEFT, TEXT_TOP, -TEXT_RIGHT, -1)
    tight = QRectF(room.left(), 1, room.width(), rect.height() - 1)

    def said(name: str, homework: bool) -> list[str]:
        span = Span(1, 19 * 60, 19 * 60 + 45)
        drawn = Drawn(name, name, "assignments" if homework else "extra", homework, span, 0, 1)
        return [line.text for line in block_layout(drawn, title, small, room, tight=tight, book=homework)]

    assert said("Piano lesson", False)[0] == "Piano lesson"
    assert said("Math worksheet", True) == ["Math…"]


def test_a_half_hour_in_high_contrast_says_its_name_on_the_week(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """High contrast's text is Large, where a half-hour on the week is one caption line exactly. Kept a
    pixel clear of its top, Dinner said nothing, and High contrast draws blocks as outlines, so there
    was no colour to say it either: an empty box."""
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    look = {"preset": "high-contrast", "knobs": {}}
    palette = resolved_palette("system", False, look)
    dinner = {
        "id": "dinner",
        "title": "Dinner",
        "kind": "locked",
        "category": "meals",
        "days": [0],
        "start": "18:30",
        "duration_min": 30,
    }
    canvas = three_days(blocks=(dinner,), palette=palette)
    canvas.set_painter(BlockPainter(palette, look))
    Said.words = []
    canvas.grab()
    assert "Dinner" in [text for text, _where in Said.words]


def test_a_paint_that_raises_still_ends_its_painter(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A design's painter that raises leaves the hours' painter to the traceback. Still active, it
    outlived the picture a grab painted on, and the collector crashed the worker when it ended the
    painter later, in some other test."""
    seen: list[QPainter] = []

    def raises(painter: QPainter, *_rest: object, **_named: object) -> None:
        seen.append(painter)
        raise RuntimeError("no words")

    monkeypatch.setattr(canvas_module, "_paint_layout", raises)
    canvas = three_days()
    # The test's own picture, so a painter left active can still be ended safely below.
    picture = QImage(canvas.size(), QImage.Format.Format_ARGB32)
    try:
        with pytest.raises(RuntimeError, match="no words"):
            canvas.render(picture)
        assert seen and not seen[0].isActive()
    finally:
        for painter in seen:
            if painter.isActive():
                painter.end()
