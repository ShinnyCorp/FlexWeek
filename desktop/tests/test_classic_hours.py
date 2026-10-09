"""Today's app's week scrolls a full day at a height where an hour still has edges."""

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
    from PySide6.QtCore import QPoint, QRect, QRectF, Qt
    from PySide6.QtGui import QFont, QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QPushButton,
        QScrollArea,
        QStyleOptionViewItem,
        QWidget,
    )

    from desktop.native.fonts import load_fonts
    from desktop.native.hours import canvas as canvas_module
    from desktop.native.hours.canvas import (
        EDGE_PX,
        TEXT_LEFT,
        TEXT_RIGHT,
        BlockPainter,
        Drawn,
        HoursCanvas,
        block_layout,
    )
    from desktop.native.hours.classic import (
        EMPTY_MIN_PX,
        WEEK_HOUR_PX,
        ClassicWeek,
        column_widths,
    )
    from desktop.native.hours.geometry import FIRST, LAST, LinearTrack, Span
    from desktop.native.hours.hand import Hand, Verdict
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import build_week
    from desktop.tests.test_hours_painter import Said


# The hosts of the hands these tests make. A hand is its host's Qt child and holds no reference of
# its own to it, so the host has to be kept for as long as the hand is used.
HOSTS: list = []


def a_hand() -> Hand:
    host = QWidget()
    HOSTS.append(host)
    return Hand(lambda block_id, from_day, span: Verdict(True, ""), host)


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-classic-hours-test"])


SCHOOL = {
    "id": "school", "title": "School", "kind": "locked", "category": "class",
    "days": [0, 1, 2, 3, 4], "start": "08:00", "duration_min": 405,
}
GYM = {
    "id": "gym", "title": "Gym", "kind": "locked", "category": "exercise",
    "days": [5], "start": "10:00", "duration_min": 90,
}


def week_view(qapp: QApplication, blocks: tuple[dict, ...] = ()) -> ClassicWeek:
    view = ClassicWeek(a_hand())
    view.set_look(None, resolved_palette("system", False, None))
    view.set_week(build_week("2026-09-21", list(blocks), {}, None), 3, 15 * 60 + 40)
    view.resize(980, 500)
    view.show()
    qapp.processEvents()
    view.hours.relayout()
    qapp.processEvents()
    return view


def test_an_hour_on_the_week_is_tall_enough_to_resize(qapp: QApplication) -> None:
    view = week_view(qapp)
    track = view.hours.track_for(3)
    assert track is not None
    hour = track.rect_for(19 * 60, 20 * 60).height()
    assert hour >= 2 * EDGE_PX + 6, f"a 60-minute block is {hour} px; the pointer would only move it"
    assert abs(track.per_minute() * 60 - WEEK_HOUR_PX) < 1


def test_midnight_and_the_end_of_the_day_can_be_scrolled_onto_the_week(qapp: QApplication) -> None:
    view = week_view(qapp)
    hours = view.hours
    assert hours.height() > view.scroll.viewport().height()

    hours.reveal(3, FIRST, FIRST + 60)
    qapp.processEvents()
    assert hours.in_view(3, FIRST), "00:00 is not in the hours viewport"
    assert not hours.in_view(3, LAST), "24:00 still counted as reached while it is clipped"

    hours.reveal(3, LAST - 60, LAST)
    qapp.processEvents()
    assert hours.in_view(3, LAST), "24:00 is not in the hours viewport"
    assert not hours.in_view(3, FIRST), "00:00 still counted as reached while it is clipped"


def test_reach_does_not_substitute_the_edge_of_a_partial_track(qapp: QApplication) -> None:
    scroll = QScrollArea()
    scroll.resize(230, 400)
    hours = HoursCanvas(
        a_hand(),
        BlockPainter(resolved_palette("system", False, None)),
        lambda area: [LinearTrack(3, QRectF(10, 10, 180, 1160), first=6 * 60, last=22 * 60)],
    )
    hours.setFixedSize(200, 1180)
    scroll.setWidget(hours)
    scroll.show()
    qapp.processEvents()
    hours.relayout()

    hours.reveal(3, 0, 60)
    qapp.processEvents()
    assert hours.in_view(3, 6 * 60)
    assert not hours.in_view(3, 0)

    hours.reveal(3, 23 * 60, 24 * 60)
    qapp.processEvents()
    assert hours.in_view(3, 22 * 60)
    assert not hours.in_view(3, 24 * 60)


def test_a_day_name_on_the_week_stays_visible_and_opens_that_day(qapp: QApplication) -> None:
    view = week_view(qapp)
    opened: list[int] = []
    view.day_opened.connect(opened.append)
    view.hours.reveal(3, LAST - 60, LAST)
    qapp.processEvents()
    name = view.findChild(QLabel, "weekDayName4")
    assert name is not None and name.isVisible()
    QTest.mouseClick(name, Qt.MouseButton.LeftButton)
    assert opened == [4]


def test_a_rail_chip_shortens_its_title_to_the_rail_and_keeps_its_length(qapp: QApplication) -> None:
    """The rail is narrower than a long title. A chip there shortens the title, never the length,
    never widens the rail, and says the whole title to a screen reader and in its tooltip; given
    room again it says it all."""
    from desktop.native.hours.rail import RAIL_PX, Rail

    title = "Science poster on the water cycle for Ms Alvarez"
    poster = {
        "id": "poster-1",
        "title": title,
        "kind": "flexible",
        "category": "homework",
        "assignment_id": "poster",
        "duration_min": 90,
        "days": [0, 1, 2, 3, 4],
    }
    rail = Rail(a_hand())
    rail.set_look(None, resolved_palette("system", False, None))
    rail.resize(RAIL_PX, 700)
    week = build_week("2026-09-21", [poster], {"poster": {"id": "poster", "due": "2026-09-25"}})
    rail.set_week(week, 3, 900, {})
    rail.show()
    qapp.processEvents()
    chip = rail.chips()[0]
    assert rail.width() == RAIL_PX, "a long title widened the rail"
    assert chip.mapTo(rail, chip.rect().topRight()).x() <= rail.width(), "the chip ran past the rail"
    lines = chip.title_lines()
    assert len(lines) <= 2 and chip.shown_title() != title
    assert lines[-1].endswith("…"), lines
    assert chip.length == "1 h 30 min"
    assert chip.accessibleName() == f"{title} · 1 h 30 min"
    assert title in chip.toolTip()
    chip.setFixedWidth(900)
    qapp.processEvents()
    assert chip.shown_title() == title, "given room again, it says it all"


def test_a_tray_chip_shortens_its_title_and_keeps_its_length_whole(qapp: QApplication) -> None:
    """The length is the number the chip is for, so the title gives way first: "Science pos… ·
    1 h 30 min", not "Science poster · 1 h …". With no room for a letter of the title beside the
    length, the words shorten from their end as before."""
    from PySide6.QtWidgets import QHBoxLayout

    from desktop.native.hours.chips import TrayChip
    from desktop.native.weekmodel import Waiting

    row = QWidget()
    line = QHBoxLayout(row)
    line.setContentsMargins(0, 0, 0, 0)
    chip = TrayChip(a_hand(), Waiting("poster", "Science poster", "homework", 90, "poster", "2026-09-25", ""))
    line.addWidget(chip)
    line.addStretch(1)
    row.show()
    qapp.processEvents()
    assert chip.text() == "Science poster · 1 h 30 min"
    fonts = chip.fontMetrics()
    # A plain button's own width beside its words: the chip's padding and frame.
    chrome = QPushButton.sizeHint(chip).width() - fonts.horizontalAdvance(chip.text())
    chip.setFixedWidth(chrome + fonts.horizontalAdvance("Science pos… · 1 h 30 min") + 1)
    qapp.processEvents()
    assert chip.text() == "Science pos… · 1 h 30 min"
    chip.setFixedWidth(chrome + fonts.horizontalAdvance(" · 1 h 30 min"))
    qapp.processEvents()
    assert chip.text().startswith("S") and chip.text().endswith("…") and "1 h 30 min" not in chip.text()


def test_a_tray_chip_in_a_row_says_it_all_again_once_the_row_has_room(qapp: QApplication) -> None:
    """The Week's tray is a row. A chip shortened while the window was narrow asks for its whole words
    again, so a wider window shows them."""
    from PySide6.QtWidgets import QHBoxLayout

    from desktop.native.hours.chips import TrayChip
    from desktop.native.weekmodel import Waiting

    title = "Science poster on the water cycle"
    whole = f"{title} · 1 h 30 min"
    row = QWidget()
    line = QHBoxLayout(row)
    chip = TrayChip(
        a_hand(),
        Waiting("poster", title, "homework", 90, "poster", "2026-09-25", ""),
    )
    line.addWidget(chip)
    line.addStretch(1)
    row.setFixedWidth(160)
    row.show()
    qapp.processEvents()
    assert chip.text().endswith("… · 1 h 30 min"), chip.text()
    row.setFixedWidth(700)
    qapp.processEvents()
    assert chip.text() == whole


def test_day_lists_its_agenda_in_order_and_keeps_now_on_the_grid(
    qapp: QApplication,
) -> None:
    """Decision 16 of 0.17: Day drops its Next band; beside the rail it lists the day, times and
    lengths, and a summary with a dot for each kind of thing. A click on
    a line opens it."""
    from desktop.native.hours.classic import ClassicDay

    blocks = [
        {"id": "school", "title": "School", "kind": "locked", "category": "class", "start": "08:00",
         "duration_min": 405, "days": [3]},
        {"id": "soccer", "title": "Soccer practice", "kind": "locked", "category": "extra", "start": "16:00",
         "duration_min": 90, "days": [3]},
        {"id": "dinner", "title": "Dinner", "kind": "locked", "category": "meals", "start": "18:30",
         "duration_min": 30, "days": [3]},
    ]
    hand = a_hand()
    opened: list[str] = []
    hand.opened.connect(opened.append)
    view = ClassicDay(hand)
    view.set_look(None, resolved_palette("system", False, None))
    view.resize(1000, 700)
    view.set_day(build_week("2026-09-21", blocks, {}, None), 3, 3, 15 * 60 + 40)
    view.show()
    qapp.processEvents()
    agenda = view.agenda
    assert agenda.heading.text() == "Agenda"
    assert agenda.sub.text() == "3 things · 8 h 45 min"
    rows = [row.item.title if row.item is not None else "now" for row in agenda.list.rows]
    assert rows == ["School", "Soccer practice", "Dinner"]
    assert view.summary.text() == "School: 6 h 45 min\nActivity: 1 h 30 min\nMeals: 30 min"
    soccer = agenda.list.rows[1].box.center().toPoint()
    QTest.mouseClick(agenda.list, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, soccer)
    assert opened == ["soccer"]
    view.set_day(build_week("2026-09-21", blocks, {}, None), 3, None, None)
    assert [row.item is None for row in agenda.list.rows] == [False] * 3, "no now on a day that is not today"


def day_widths(view: ClassicWeek) -> list[float]:
    return [view.hours.track_for(day).area.width() for day in range(7)]


def test_an_empty_weekend_is_narrower_than_the_days_with_something_in_them(qapp: QApplication) -> None:
    """Saturday and Sunday with nothing on them take less of the week, though never less than
    EMPTY_MIN_PX, so a block dropped there can still be read; the five days with something in them
    stay equal; and each day's name stays over its own column."""
    view = week_view(qapp, (SCHOOL,))
    widths = day_widths(view)
    assert max(widths[:5]) - min(widths[:5]) < 0.01, f"days with something are unequal: {widths}"
    for day in (5, 6):
        assert EMPTY_MIN_PX <= widths[day] < widths[0] - 1, f"day {day} is {widths[day]:.0f} px: {widths}"
    tracks = view.hours.tracks
    assert abs(sum(widths) - (tracks[-1].area.right() - tracks[0].area.left())) < 0.01
    assert all(abs(a.area.right() - b.area.left()) < 0.01 for a, b in zip(tracks, tracks[1:], strict=False))
    for day in range(7):
        track = view.hours.track_for(day)
        name = view.findChild(QLabel, f"weekDayName{day}")
        left = view.hours.mapTo(view, QPoint(round(track.area.left()), 0)).x()
        assert abs(name.mapTo(view, QPoint(0, 0)).x() - left) <= 1, f"day {day}'s name is off its column"
        assert abs(name.width() - track.area.width()) <= 1, f"day {day}'s name is {name.width()} wide"


def test_a_weekend_day_with_something_on_it_is_as_wide_as_a_weekday(qapp: QApplication) -> None:
    view = week_view(qapp, (SCHOOL, GYM))
    widths = day_widths(view)
    assert max(widths[:6]) - min(widths[:6]) < 0.01, f"Saturday has Gym and should be a full day: {widths}"
    assert EMPTY_MIN_PX <= widths[6] < widths[0] - 1, f"Sunday is empty and should be narrower: {widths}"


def test_a_weekend_that_fills_up_widens_and_a_week_that_empties_narrows(qapp: QApplication) -> None:
    view = week_view(qapp, (SCHOOL,))
    narrow = day_widths(view)[5]
    view.set_week(build_week("2026-09-21", [SCHOOL, GYM], {}, None), 3, 15 * 60 + 40)
    qapp.processEvents()
    assert day_widths(view)[5] > narrow + 1, "Saturday did not widen once it had Gym"
    view.set_week(build_week("2026-09-21", [SCHOOL], {}, None), 3, 15 * 60 + 40)
    qapp.processEvents()
    assert abs(day_widths(view)[5] - narrow) < 0.01, "Saturday did not narrow when Gym went"


def test_the_weekend_never_gets_narrower_than_a_block_can_be_read_in() -> None:
    """Where the week itself is narrow, an equal share is already less than the minimum, and the
    weekend keeps it rather than growing past the weekdays; where there is room, it takes 60 %."""
    both = frozenset({5, 6})
    for total in (420.0, 700.0, 900.0, 1400.0, 2100.0):
        widths = column_widths(total, both)
        assert abs(sum(widths) - total) < 0.01, total
        share = total / 7
        assert widths[5] == widths[6] <= share + 0.01, total
        assert widths[5] >= min(EMPTY_MIN_PX, share) - 0.01, total
        assert widths[0] >= share - 0.01, total
    assert column_widths(420.0, both) == [60.0] * 7
    assert column_widths(2100.0, both)[5] == pytest.approx(180.0)
    assert column_widths(1400.0, frozenset({6}))[5] == column_widths(1400.0, frozenset({6}))[0]
    assert column_widths(1400.0, frozenset({2, 3})) == [200.0] * 7, "only a weekend day gets narrower"


def test_a_block_on_the_narrowest_weekend_day_keeps_the_start_of_its_name_and_its_times(
    qapp: QApplication,
) -> None:
    """A block dropped on an empty Saturday shows its first word whole and its times. The room is
    what `words` gives a block alone in its column: its width less the text's margins."""
    load_fonts()
    view = week_view(qapp, (SCHOOL,))
    track = view.hours.track_for(5)
    rect = track.rect_for(16 * 60, 17 * 60 + 30)
    title, small = view.hours.painter.fonts(QFont("Inter", 11))
    drawn = Drawn("soccer", "Soccer practice", "extra", False, Span(5, 16 * 60, 17 * 60 + 30), 0, 1)
    room = QRectF(0, 0, rect.width() - TEXT_LEFT - TEXT_RIGHT, rect.height() - 4)
    said = [line.text for line in block_layout(drawn, title, small, room, book=True)]
    assert said[0] == "Soccer", said
    assert any(text.startswith("16:00") for text in said), said


def test_the_hours_end_with_their_end_label_and_keep_the_room_below_it(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Today's app's Week or Day labels the end of the day as every design does: "24:00", or "12:00 AM"
    on the 12-hour clock. The room below the last rule is kept so the label is never cut."""
    monkeypatch.setattr(canvas_module, "QPainter", Said)
    view = week_view(qapp, (SCHOOL,))
    view.hours.reveal(3, LAST - 60, LAST)
    qapp.processEvents()
    Said.words = []
    view.hours.repaint()
    labels = [text for text, _where in Said.words if text.endswith(":00") and len(text) == 5]
    assert "23:00" in labels and "24:00" in labels, labels
    track = view.hours.track_for(3)
    assert track.last == LAST and view.hours.height() - track.area.bottom() >= 12, "the room below was lost"


def test_a_focus_row_cuts_a_homework_title_only_when_the_row_has_no_room_for_it(qapp: QApplication) -> None:
    """The rail is 280 pixels wide, and "Math worksheet" beside today's "Today 16:15" has room in it,
    so it is said whole; a narrower row still cuts it, and says the day and time whole."""
    from desktop.native.hours.rail import RAIL_PX, Rail

    load_fonts()
    rail = Rail(a_hand())
    rail.setFont(QFont("Inter", 11))
    rail.set_look(None, resolved_palette("system", False, None))
    rail.resize(RAIL_PX, 700)
    rail.set_tasks([{"id": "math", "title": "Math worksheet", "day": 3, "start": "16:15"}], 3)
    rail.show()
    qapp.processEvents()
    index = rail.tasks.indexFromItem(rail.tasks.item(0))
    delegate = rail.tasks.itemDelegate()

    def said(width: int) -> list[str]:
        image = QImage(width, 40, QImage.Format.Format_ARGB32)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, width, 30)
        Said.words = []
        paint = Said(image)
        delegate.paint(paint, option, index)
        paint.end()
        return [text for text, _where in Said.words]

    wide = said(rail.tasks.viewport().width())
    assert wide[0] == "Today 16:15" and "Math worksheet" in " ".join(wide[1:])
    narrow = said(200)
    assert narrow[0] == "Today 16:15" and narrow[-1].endswith("…"), narrow
