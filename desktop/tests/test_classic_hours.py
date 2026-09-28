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
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea, QWidget

    from desktop.native.hours.canvas import EDGE_PX, BlockPainter, HoursCanvas
    from desktop.native.hours.classic import WEEK_HOUR_PX, ClassicWeek
    from desktop.native.hours.geometry import FIRST, LAST, LinearTrack
    from desktop.native.hours.hand import Hand, Verdict
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import build_week


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


def week_view(qapp: QApplication) -> ClassicWeek:
    view = ClassicWeek(a_hand())
    view.set_look(None, resolved_palette("system", False, None))
    view.set_week(build_week("2026-09-21", [], {}, None), 3, 15 * 60 + 40)
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
    assert chip.shown_title() != title and chip.shown_title().endswith("…"), chip.shown_title()
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


def test_day_is_its_agenda_in_order_with_now_between_what_has_been_and_what_is_next(
    qapp: QApplication,
) -> None:
    """Decision 16 of 0.17: Day drops its Next band; beside the rail it lists the day, times and
    lengths, with the time now as a line, and a summary with a dot for each kind of thing. A click on
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
    assert agenda.heading.text() == "Thursday"
    assert agenda.sub.text() == "3 things · 8 h 45 min"
    rows = [row.item.title if row.item is not None else "now" for row in agenda.list.rows]
    assert rows == ["School", "now", "Soccer practice", "Dinner"]
    assert view.summary.text() == "School: 6 h 45 min\nActivity: 1 h 30 min\nMeals: 30 min"
    soccer = agenda.list.rows[2].box.center().toPoint()
    QTest.mouseClick(agenda.list, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, soccer)
    assert opened == ["soccer"]
    view.set_day(build_week("2026-09-21", blocks, {}, None), 3, None, None)
    assert [row.item is None for row in agenda.list.rows] == [False] * 3, "no now on a day that is not today"
