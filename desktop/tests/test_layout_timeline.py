"""Timeline on the shared hours: Day is one ruled column with a margin, Week seven lines down a page."""

from __future__ import annotations

import importlib.util
import os
import time
from collections.abc import Iterator
from dataclasses import replace

import pytest

from desktop.tests.test_weekmodel import BLOCKS, HOMEWORK, TRACE, WEEK, block

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    import shiboken6
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QColor, QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

    from desktop.native.hours.chips import TrayChip
    from desktop.native.hours.geometry import Axis
    from desktop.native.hours.zoom import HoursScroll
    from desktop.native.layouts.base import Scene
    from desktop.native.layouts.registry import options_for, tokens_for
    from desktop.native.layouts.timeline import TimelineCanvas, TimelineView
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import build_week, minute_of


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-timeline-test"])
    yield application


def scene_of(
    tab: str = "week", clock: str = "13:40", blocks: list[dict] | None = None, **chosen: str
) -> Scene:
    options = {**options_for(None, "timeline"), **chosen}
    palette = resolved_palette("light-frost", False, None, "default")
    week = build_week(WEEK, BLOCKS if blocks is None else blocks, HOMEWORK, TRACE)
    return Scene(
        week,
        3,
        minute_of(clock),
        options,
        tokens_for("timeline", options["colour"], palette),
        surface=tab,
        iso_day=week.date_of(3).isoformat(),
    )


def shown(
    qapp: QApplication, tab: str = "week", size: tuple[int, int] = (1150, 768), **given
) -> TimelineView:
    view = TimelineView()
    view.resize(*size)
    view.show_week(scene_of(tab, **given))
    view.show()
    qapp.processEvents()
    return view


def canvas(view: TimelineView) -> TimelineCanvas:
    found = view.hours_surfaces()
    assert len(found) == 1 and isinstance(found[0], TimelineCanvas)
    return found[0]


def scroll_of(view: TimelineView) -> HoursScroll:
    area = canvas(view)._scroll_area()
    assert isinstance(area, HoursScroll)
    return area


def page_of(view: TimelineView) -> QScrollArea:
    return view.findChild(QScrollArea, "timelineScroll")


def near(colour: QColor, hex_colour: str, within: int = 8) -> bool:
    other = QColor(hex_colour)
    return (
        max(
            abs(colour.red() - other.red()),
            abs(colour.green() - other.green()),
            abs(colour.blue() - other.blue()),
        )
        <= within
    )


# Day: Column rule


def test_day_keeps_the_big_heading_and_says_what_is_planned(qapp: QApplication) -> None:
    view = shown(qapp, "day")
    assert view.findChild(QLabel, "timelineDay").text() == "Thursday"
    assert view.findChild(QLabel, "timelineSub").text() == "September 17 · 2 h 30 min planned · 0 done"


def test_day_is_one_column_of_the_whole_day_on_the_windows_hand(qapp: QApplication) -> None:
    view = shown(qapp, "day")
    hours = canvas(view)
    assert [(track.day, track.axis, track.first, track.last) for track in hours.tracks] == [
        (3, Axis.DOWN, 0, 1440)
    ]
    assert scroll_of(view).axis is Axis.DOWN
    assert [
        key for key in ("school", "dinner", "essay-1", "chem-1") if hours.block_rect(key, 3) is None
    ] == []
    assert hours.hand is view.hand


def test_two_cards_at_one_time_go_half_width(qapp: QApplication) -> None:
    view = shown(qapp, "day", blocks=[*BLOCKS, block("quiz", "locked", [3], "18:00", 30)])
    hours = canvas(view)
    track = hours.tracks[0]
    boxes = {item.block_id: rect for item, rect in hours.drawn(track) if item.block_id in {"dinner", "quiz"}}
    dinner, quiz = boxes["dinner"], boxes["quiz"]
    assert abs(dinner.width() - quiz.width()) < 1
    assert dinner.width() < track.area.width() / 2
    assert dinner.right() <= quiz.left() or quiz.right() <= dinner.left()


def test_homework_is_an_ink_card_and_everything_else_is_paper(qapp: QApplication) -> None:
    view = shown(qapp, "day", colour="paper")
    hours = canvas(view)
    image = hours.grab().toImage()

    def corner(block_id: str) -> QColor:
        box = hours.block_rect(block_id, 3)
        inside = hours.mapFromGlobal(box.bottomRight()) - QPoint(10, 8)
        return image.pixelColor(inside)

    assert (corner("essay-1").name(), corner("school").name()) == ("#1d1b16", "#f6f4ef")


def test_now_is_written_in_red_beside_the_line(qapp: QApplication) -> None:
    view = shown(qapp, "day", colour="paper")
    hours = canvas(view)
    track = hours.tracks[0]
    at = round(track.area.top() + track.offset(minute_of("13:40")))
    image = hours.grab().toImage()
    red = [
        (x, y)
        for y in range(at - 6, at + 7)
        for x in range(2, round(track.area.left()) - 8)
        if near(image.pixelColor(x, y), "#b3202a", 12)
    ]
    assert len(red) > 20, "no NOW in the gutter"


def test_the_margin_holds_what_has_no_time_and_a_click_opens_it(qapp: QApplication) -> None:
    view = shown(qapp, "day")
    margin = view.findChild(QFrame, "timelineMargin")
    assert margin.findChild(QLabel, "timelineTrayLabel").text() == "Not placed yet · in the margin"
    chips = margin.findChildren(TrayChip)
    assert [(chip.held.title, chip.hand is view.hand) for chip in chips] == [("Poster-1", True)]
    opened: list[str] = []
    view.block_activated.connect(opened.append)
    QTest.mouseClick(chips[0], Qt.MouseButton.LeftButton)
    assert opened == ["poster-1"]


def test_the_strip_opens_another_day_on_the_same_hours(qapp: QApplication) -> None:
    view = shown(qapp, "day")
    kept = scroll_of(view)
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    view.findChild(QPushButton, "timelineDay0").click()
    assert opened == ["2026-09-14"]
    view.show_week(replace(view.scene, iso_day="2026-09-14"))
    qapp.processEvents()
    assert view.findChild(QLabel, "timelineDay").text() == "Monday"
    assert [track.day for track in canvas(view).tracks] == [0]
    assert scroll_of(view) is kept


# Week: Continuous scroll


def test_week_is_seven_lines_across_one_canvas_in_reading_order(qapp: QApplication) -> None:
    view = shown(qapp)
    hours = canvas(view)
    assert [(track.day, track.axis) for track in hours.tracks] == [(day, Axis.ACROSS) for day in range(7)]
    tops = [track.area.top() for track in hours.tracks]
    assert tops == sorted(tops)
    assert all((track.first, track.last) == (0, 1440) for track in hours.tracks)
    assert scroll_of(view).axis is Axis.ACROSS


def test_each_days_heading_sits_beside_its_line_and_opens_it(qapp: QApplication) -> None:
    view = shown(qapp)
    hours = canvas(view)
    for track in hours.tracks:
        heading = view.findChild(QPushButton, f"timelineWeekDay{track.day}")
        middle = hours.mapToGlobal(track.area.center().toPoint()).y()
        assert abs(heading.mapToGlobal(heading.rect().center()).y() - middle) <= 8, track.day
        assert hours.day_name(track.day) == heading.mapToGlobal(heading.rect().center())
    assert view.findChild(QPushButton, "timelineWeekDay4").findChild(
        QLabel, "timelineHeadingDate"
    ).text() == ("18 September")
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    QTest.mouseClick(view.findChild(QPushButton, "timelineWeekDay4"), Qt.MouseButton.LeftButton)
    assert opened == ["2026-09-18"]


def test_week_says_its_dates_and_load_and_keeps_a_margin(qapp: QApplication) -> None:
    view = shown(qapp)
    assert view.findChild(QLabel, "timelineWeekTitle").text() == "This week"
    assert view.findChild(QLabel, "timelineSub").text() == (
        "14 September – 20 September · 3 h 15 min planned · 45 min done"
    )
    assert view.findChild(QLabel, "timelineTrayLabel").text().startswith("Not placed yet")
    assert [chip.held.title for chip in view.findChildren(TrayChip)] == ["Poster-1"]


def test_a_week_taller_than_the_window_scrolls_and_every_day_can_be_reached(qapp: QApplication) -> None:
    view = shown(qapp, size=(1150, 240))
    page, hours = page_of(view), canvas(view)
    assert page.verticalScrollBar().maximum() > 0, "the seven lines are taller than the window"
    page.verticalScrollBar().setValue(0)
    qapp.processEvents()
    assert not hours.in_view(6, 17 * 60), "Sunday is below the fold"
    hours.reveal(6, 17 * 60, 18 * 60)
    qapp.processEvents()
    assert hours.in_view(6, 17 * 60) and hours.in_view(6, 18 * 60)
    name = page.viewport().mapFromGlobal(hours.day_name(6))
    assert page.viewport().rect().contains(name), "Sunday's name is on screen beside it"
    hours.reveal(0, 8 * 60, 9 * 60)
    qapp.processEvents()
    assert hours.in_view(0, 8 * 60) and not hours.in_view(6, 17 * 60)


def test_a_block_rested_at_the_edge_of_a_tall_week_scrolls_the_lines_sideways(qapp: QApplication) -> None:
    """Inside the offscreen screen (800 by 800), where the hand can find what is under the pointer."""
    view = TimelineView()
    view.move(0, 0)
    view.resize(780, 420)
    view.show_week(scene_of())
    view.show()
    qapp.processEvents()
    hours, scroll = canvas(view), scroll_of(view)
    assert page_of(view).verticalScrollBar().maximum() > 0
    hours.reveal(3, 19 * 60, 20 * 60)
    qapp.processEvents()
    bar = scroll.horizontalScrollBar()
    before = bar.value()
    assert before > 0
    grab = hours.block_rect("essay-1", 3).center()
    edge = QPoint(scroll.viewport().mapToGlobal(QPoint(10, 0)).x(), grab.y())

    def send(kind: QEvent.Type, at: QPoint, held: bool) -> None:
        buttons = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
        local = QPointF(hours.mapFromGlobal(at))
        QApplication.sendEvent(
            hours,
            QMouseEvent(
                kind, local, QPointF(at), Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier
            ),
        )

    send(QEvent.Type.MouseButtonPress, grab, True)
    for step in range(1, 9):
        send(QEvent.Type.MouseMove, grab + (edge - grab) * step / 8, True)
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline and bar.value() >= before:
        qapp.processEvents()
    assert bar.value() < before, "rested at the start of the lines: they scroll back"
    view.hand.cancel()


def test_the_hours_are_kept_through_renders_and_tabs(qapp: QApplication) -> None:
    view = shown(qapp)
    week = scroll_of(view)
    week.zoom_by(1)
    view.show_week(replace(view.scene, minute=view.scene.minute + 1))
    view.show_week(replace(view.scene, surface="day"))
    day = scroll_of(view)
    view.show_week(replace(view.scene, surface="week"))
    qapp.processEvents()
    assert scroll_of(view) is week and week.px == 80
    assert day is not week and shiboken6.isValid(day) and not day.isVisible()


def test_parked_hours_die_with_the_window(qapp: QApplication) -> None:
    host = QWidget()
    view = TimelineView(host)
    QVBoxLayout(host).addWidget(view)
    view.show_week(scene_of("day"))
    host.show()
    qapp.processEvents()
    parked = scroll_of(view)
    view.show_week(scene_of("week"))
    assert shiboken6.isValid(parked) and not parked.isVisible()
    host.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(parked)


def test_a_new_text_size_makes_the_week_again_at_the_zoom_the_window_remembers(qapp: QApplication) -> None:
    view = shown(qapp)
    first = scroll_of(view)
    view.remembered_zoom = {"timeline.week": 80}
    view.show_week(replace(view.scene, scale=1.25))
    qapp.processEvents()
    again = scroll_of(view)
    assert again is not first and again.px == 80
    name = canvas(view).headings[2].title
    assert name.width() >= name.sizeHint().width(), "Wednesday fits beside its line in large text"


# Options


def test_option_finished_hidden_drops_what_is_over(qapp: QApplication) -> None:
    def drawn(view: TimelineView) -> list[str]:
        return sorted(
            {item.block_id for track in canvas(view).tracks for item, _ in canvas(view).drawn(track)}
        )

    assert drawn(shown(qapp, clock="19:00")) == ["chem-1", "dinner", "essay-1", "math-1", "school"]
    assert drawn(shown(qapp, clock="19:00", finished="hide")) == ["chem-1", "dinner", "essay-1", "school"]
    day = shown(qapp, "day", clock="19:00", finished="hide")
    assert drawn(day) == ["chem-1", "essay-1"]


def test_option_strip_with_and_without_load_bars(qapp: QApplication) -> None:
    def bars(view: TimelineView) -> int:
        return len([item for item in view.findChildren(QFrame) if item.property("role") == "load"])

    assert (bars(shown(qapp, "day")), bars(shown(qapp, "day", strip="names"))) == (7, 0)
    assert shown(qapp, "day", strip="names").findChild(QPushButton, "timelineDay6") is not None


def test_option_compact_tightens_the_page(qapp: QApplication) -> None:
    def heights(view: TimelineView) -> tuple[int, int]:
        return view.findChild(QLabel, "timelineWeekTitle").height(), scroll_of(view).minimumHeight()

    tight, roomy = heights(shown(qapp, density="compact")), heights(shown(qapp))
    assert tight[0] < roomy[0] and tight[1] < roomy[1]


def test_option_colours_repaint_the_page(qapp: QApplication) -> None:
    def corner(view: TimelineView) -> str:
        return view.grab().toImage().pixelColor(5, 5).name()

    assert corner(shown(qapp, colour="paper")) == "#f6f4ef"
    assert corner(shown(qapp, colour="night")) == "#14161c"
