"""Times and words on blocks: a short block keeps its start with its name."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from desktop.native.hours.canvas import (
        TEXT_LEFT,
        TEXT_RIGHT,
        TEXT_TOP,
        BlockPainter,
        Drawn,
        Started,
        block_layout,
    )
    from desktop.native.hours.geometry import Span
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import clock_label, range_label, set_clock_24h, short_clock


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-week-words-test"])


def _fonts(look: dict | None = None) -> tuple[QFont, QFont]:
    painter = BlockPainter(resolved_palette("system", False, look), look)
    return painter.fonts(QFont("Inter", 12))


def _math(
    *, short: bool = False, started: bool = False, large: bool = False
) -> tuple[Drawn, QFont, QFont, QRectF, QRectF]:
    look = {"preset": "default", "knobs": {"text": "large"}} if large else None
    title, small = _fonts(look)
    # A column of the week beside the rail at 1280, 45 minutes at 48 pixels an hour.
    rect = QRectF(0, 0, 128, 45 * 48 / 60 - 3)
    room = rect.adjusted(TEXT_LEFT, TEXT_TOP, -TEXT_RIGHT, -1)
    tight = QRectF(room.left(), 1, room.width(), rect.height() - 1)
    span = Span(1, 17 * 60, 17 * 60 + 45)
    kind = Started if started else Drawn
    drawn = kind(
        "math",
        "Math worksheet",
        "assignments",
        True,
        span,
        0,
        1,
        short=short,
    )
    return drawn, title, small, room, tight


def said(drawn: Drawn, title: QFont, small: QFont, room: QRectF, tight: QRectF) -> list[str]:
    return [line.text for line in block_layout(drawn, title, small, room, tight=tight, book=drawn.work)]


def test_a_short_block_says_its_name_then_its_start(qapp: QApplication) -> None:
    """A 45-minute Math worksheet at 17:00. Today's app, Paper and Timeline wrote the name only;
    Clay and Retro already wrote the start. Every design writes the name, then the start."""
    start = clock_label(17 * 60)
    for short, started, large in (
        (False, False, False),
        (False, False, True),
        (True, False, False),
        (False, True, False),
        (True, True, False),
    ):
        drawn, title, small, room, tight = _math(short=short, started=started, large=large)
        words = said(drawn, title, small, room, tight)
        assert any("Math" in line for line in words), (short, started, large, words)
        assert start in words, (short, started, large, words)


def test_a_blocks_range_stays_on_one_line_and_the_two_times_are_never_stacked(
    qapp: QApplication,
) -> None:
    """At 810 px, and on the 12-hour clock, stacking 08:30 over 14:15 with no dash reads as two
    events. The range stays on one line; the duration is dropped first; then the start alone."""
    from PySide6.QtGui import QFontMetricsF

    title, small = _fonts()
    tm, sm = QFontMetricsF(title), QFontMetricsF(small)
    span = Span(4, 8 * 60 + 30, 14 * 60 + 15)
    drawn = Drawn("school", "School", "class", False, span, 0, 1)
    range_words = range_label(span.start, span.end)
    start, end = clock_label(span.start), clock_label(span.end)
    # Narrower than the range as one extra, wide enough for each time on its own line.
    width = sm.horizontalAdvance(start) + 8
    assert sm.horizontalAdvance(range_words) > width
    room = QRectF(0, 0, width, tm.lineSpacing() * 4 + sm.lineSpacing() * 3)
    extras = [line.text for line in block_layout(drawn, title, small, room) if not line.title]
    assert extras != [start, end], extras
    assert range_words in extras or start in extras or short_clock(span.start) in extras, extras

    set_clock_24h(False)
    try:
        drawn12 = Drawn("school", "School", "class", False, span, 0, 1)
        range12 = range_label(span.start, span.end)
        assert "–" in range12
        start12 = clock_label(span.start)
        width12 = sm.horizontalAdvance(start12) + 8
        room12 = QRectF(0, 0, width12, tm.lineSpacing() * 4 + sm.lineSpacing() * 3)
        extras12 = [line.text for line in block_layout(drawn12, title, small, room12) if not line.title]
        assert extras12 != [clock_label(span.start), clock_label(span.end)], extras12
        assert range12 in extras12 or short_clock(span.start) in extras12, extras12
    finally:
        set_clock_24h(True)


def test_overlapping_blocks_cut_the_title_first_and_keep_the_time_whole(qapp: QApplication) -> None:
    """Two blocks that share a time are half a column. Wrapping leftover words of the title beside
    the neighbour reads as a second event, such as "Soccer | Pract... extra"."""
    from PySide6.QtGui import QFontMetricsF

    title, small = _fonts()
    tm = QFontMetricsF(title)
    span = Span(1, 16 * 60, 17 * 60)
    practice = Drawn("practice", "Practice extra", "extra", False, span, 1, 2)
    width = tm.horizontalAdvance("Pract") + 12
    room = QRectF(0, 0, width, tm.lineSpacing() * 4)
    words = [line.text for line in block_layout(practice, title, small, room)]
    extras = [line.text for line in block_layout(practice, title, small, room) if not line.title]
    assert extras != [clock_label(span.start), clock_label(span.end)], words
    assert "extra" not in words, words


def test_the_rail_timer_list_keeps_the_time_whole(qapp: QApplication) -> None:
    """The focus list clipped "Mon 06:0(". The time stays whole; the title is what shortens."""
    from PySide6.QtCore import QRect, QRectF
    from PySide6.QtGui import QFont, QFontMetricsF, QImage
    from PySide6.QtWidgets import QStyleOptionViewItem, QWidget

    from desktop.native.fonts import load_fonts
    from desktop.native.hours.hand import Hand, Verdict
    from desktop.native.hours.rail import Rail, focus_when
    from desktop.native.look import resolved_palette
    from desktop.tests.test_hours_painter import Said

    load_fonts()
    when = focus_when({"day": 0, "start": "06:00"}, today=3)
    assert when == "Mon 06:00"
    host = QWidget()
    rail = Rail(Hand(lambda *_a, **_k: Verdict(True, ""), host))
    rail.setFont(QFont("Inter", 11))
    rail.set_look(None, resolved_palette("system", False, None))
    rail.set_tasks(
        [{"id": "essay", "title": "History essay that is quite long", "day": 0, "start": "06:00"}],
        3,
    )
    index = rail.tasks.indexFromItem(rail.tasks.item(0))
    delegate = rail.tasks.itemDelegate()
    image = QImage(90, 40, QImage.Format.Format_ARGB32)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 90, 30)
    Said.words = []
    Said.inks = []
    paint = Said(image)
    delegate.paint(paint, option, index)
    paint.end()
    said = {text: box for text, box in Said.words}
    assert when in said, Said.words
    _, small = rail.fonts()
    need = QFontMetricsF(small).horizontalAdvance(when)
    box = said[when]
    assert box.width() >= need, (when, box, need)
    ink = next(where for text, where in Said.inks if text == when)
    row = QRectF(option.rect)
    assert row.left() - 0.5 <= ink.left() and ink.right() <= row.right() + 0.5, (when, ink, row)


def test_a_short_homework_length_is_hours_and_minutes_not_a_time_of_day() -> None:
    """Friday's header at 810 px and Bento's day cards said "2 h 15", which reads like a time of day.
    The short form is "2h 15m" at every width."""
    from desktop.native.layouts.base import short_length

    assert short_length(135) == "2h 15m"
    assert short_length(90) == "1h 30m"
    assert short_length(60) == "1h"
    assert short_length(45) == "45 min"


def test_fridays_header_says_2h_15m_when_the_column_is_narrow(qapp: QApplication) -> None:
    """The day's homework length under Friday must not look like 2:15."""
    from desktop.native.hours.classic import DayName

    name = DayName(4)
    name.show_day("Fri", "18", 135, False)
    name.resize(48, 80)
    words = name.homework_words()
    assert words in ("2 h 15 min", "2h 15m"), words
    assert ":" not in words
    assert words != "2 h 15"
