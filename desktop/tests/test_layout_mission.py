"""Mission control's ops board: four figures, the lanes of hours on the shared hand, and a deadline
table whose rows of homework not placed yet are what the student drags onto a lane."""

from __future__ import annotations

import importlib.util
import itertools
import os
import re
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
    from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt
    from PySide6.QtGui import QColor, QHelpEvent, QMouseEvent, QPainter, QTextDocumentFragment
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QLabel,
        QPushButton,
        QScrollArea,
        QToolTip,
        QVBoxLayout,
        QWidget,
    )

    from desktop.native.hours import canvas as canvas_module
    from desktop.native.hours.chips import TrayChip
    from desktop.native.hours.geometry import Axis, Span
    from desktop.native.hours.hand import Hand, Move, Verdict
    from desktop.native.hours.zoom import HoursScroll
    from desktop.native.layouts.base import Scene
    from desktop.native.layouts.mission import WEEK_SCALE, Bar, MissionCanvas, MissionView
    from desktop.native.layouts.registry import LAYOUTS, options_for, tokens_for
    from desktop.native.look import ACCENTS, PACKS, category_paint, resolved_palette
    from desktop.native.weekmodel import build_week, minute_of
    from desktop.native.widgets import FittedLabel


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-mission-test"])


def shown(
    qapp: QApplication,
    *,
    surface: str = "week",
    blocks: list[dict] | None = None,
    homework: dict | None = None,
    iso_day: str = "",
    today: int | None = 3,
    minute: str = "13:40",
    size: tuple[int, int] = (1366, 760),
    scale: float = 1.0,
    hand: Hand | None = None,
    focus: str = "",
    **chosen: str,
) -> MissionView:
    """Mission on the test week, Thursday 13:40 unless told otherwise."""
    options = {**options_for(None, "mission"), **chosen}
    palette = resolved_palette("light-frost", False, None, "default")
    view = MissionView(hand=hand)
    view.resize(*size)
    week = build_week(WEEK, blocks or BLOCKS, homework or HOMEWORK, TRACE)
    view.show_week(
        Scene(
            week,
            today,
            minute_of(minute),
            options,
            tokens_for("mission", options["colour"], palette),
            scale=scale,
            surface=surface,
            iso_day=iso_day,
            focus=focus,
        )
    )
    view.show()
    qapp.processEvents()
    return view


def words(widget: QLabel) -> str:
    """What a label says, its markup and spacing aside."""
    return " ".join(QTextDocumentFragment.fromHtml(widget.text()).toPlainText().split())


def figure(view: MissionView, name: str) -> tuple[str, str]:
    """A figure's value and the line under it."""
    return words(view.findChild(QLabel, f"{name}Value")), words(view.findChild(QLabel, f"{name}Line"))


def table_rows(view: MissionView) -> list[tuple[str, str, str, str]]:
    """Each row of the deadline table: the homework, what it needs, the time left and where it is."""
    rows = []
    for row in view.findChild(QFrame, "missionDeadlines").findChildren(QFrame, "missionDeadline"):
        placed = row.findChild(QLabel, "missionPlaced")
        chips = " / ".join(chip.text() for chip in row.findChildren(TrayChip))
        where = words(placed) if placed is not None else chips
        rows.append(
            (
                row.findChild(FittedLabel, "missionDeadlineTitle").full_text(),
                row.findChild(QLabel, "missionFigure").text(),
                row.findChild(QLabel, "missionLeft").text(),
                where,
            )
        )
    return rows


def beside(view: MissionView, name: str) -> bool:
    """Whether the deadline table sits to the right of the hours called `name`, rather than under."""
    table = view.findChild(QFrame, "missionDeadlines")
    hours = view.findChild(HoursScroll, name)
    left = table.mapTo(view, QPoint(0, 0))
    lanes = hours.mapTo(view, QPoint(hours.width(), hours.height()))
    assert left.x() >= lanes.x() or left.y() >= lanes.y(), "the table lies over the lanes"
    return left.x() >= lanes.x()


def test_week_has_seven_live_horizontal_tracks_and_one_hand(qapp: QApplication) -> None:
    view = shown(qapp)
    hours = view.findChild(MissionCanvas, "missionHours")
    assert view.hours_surfaces() == [hours]
    assert [track.day for track in hours.tracks] == list(range(7))
    assert all(track.axis is Axis.ACROSS and track.first == 0 and track.last == 1440
               for track in hours.tracks)
    assert hours.hand is view.hand
    chip = view.findChild(TrayChip, "missionWaiting0")
    assert (chip.block_id, chip.text()) == ("poster-1", "Not placed yet")


def test_the_week_opens_at_the_mock_ups_scale(qapp: QApplication) -> None:
    """The mock-up draws 08:00 to 22:00 across the lanes at 1280 wide: 56 pixels an hour."""
    view = shown(qapp)
    assert view._scrolls["week"].px == WEEK_SCALE.default == 56


def test_day_is_one_lane_of_the_chosen_date_with_that_days_list(qapp: QApplication) -> None:
    view = shown(qapp, surface="day", iso_day="2026-09-18")
    hours = view.findChild(MissionCanvas, "missionHours")
    assert [(track.day, track.axis) for track in hours.tracks] == [(4, Axis.ACROSS)]
    assert view.findChild(QPushButton, "missionDay4").title.text() == "Fri"
    listed = view.findChild(QFrame, "missionDayList")
    assert listed.findChild(QLabel, "missionLabel").text() == "Friday"
    assert [name.full_text() for name in listed.findChildren(FittedLabel, "missionRowTitle")] == [
        "School",
        "Dinner",
    ]
    # What is still to come is today's alone.
    assert view.findChild(QFrame, "missionUpNext") is None
    assert view.findChild(QFrame, "missionFreeTime") is None


def test_two_blocks_at_one_time_take_separate_scope_rows(qapp: QApplication) -> None:
    view = shown(qapp, surface="day", blocks=[*BLOCKS, block("quiz", "locked", [3], "18:00", 60)])
    hours = view.findChild(MissionCanvas, "missionHours")
    track = hours.track_for(3)
    boxes = [rect for item, rect in hours.drawn(track) if item.block_id in {"dinner", "quiz"}]
    assert len(boxes) == 2
    assert boxes[0].bottom() < boxes[1].top() or boxes[1].bottom() < boxes[0].top()


CLUB = block("club", "locked", [0], "15:15", 45, title="Robotics club", category="extra")


def test_blocks_sharing_their_time_are_each_as_tall_as_a_block_alone(qapp: QApplication) -> None:
    """Monday's maths (15:45 to 16:30) shares a quarter hour with the club (15:15 to 16:00). They sit
    side by side in Monday's lane, and each has the room a block alone in its lane has, as the
    mock-up gives every block: the lane takes the room of two. Too short for their names, each has
    its name written after it, in its own row. Each day's name stays beside its lane."""
    view = shown(qapp, blocks=[*BLOCKS, CLUB], size=(1280, 744))
    hours = view.findChild(MissionCanvas, "missionHours")

    def rect(block_id: str, day: int):
        return next(rect for item, rect in hours.drawn(hours.track_for(day)) if item.block_id == block_id)

    maths, club, alone = rect("math-1", 0), rect("club", 0), rect("school", 1)
    assert maths.top() > club.bottom() or club.top() > maths.bottom(), "they are not side by side"
    assert min(maths.height(), club.height()) >= alone.height()
    image = hours.grab().toImage()
    for box in (maths, club):
        ink = sum(
            QColor(image.pixel(x, y)).lightness() < 110
            for x in range(round(box.right()) + 4, round(box.right()) + 60)
            for y in range(round(box.top()) + 6, round(box.top()) + 24)
        )
        assert ink > 20, "no name after it"
    for day in range(7):
        name = view.findChild(QPushButton, f"missionDay{day}")
        middle = hours.mapFromGlobal(name.mapToGlobal(name.rect().center())).y()
        lane = hours.painter.lane(hours.track_for(day))
        assert lane.top() < middle < lane.bottom(), f"day {day}'s name is not beside its lane"


def test_a_block_sharing_its_time_is_picked_up_and_dropped_on_another_lane(qapp: QApplication) -> None:
    host = QWidget()
    hand = Hand(lambda block_id, from_day, span: Verdict(True, ""), host)
    said: list[object] = []
    hand.committed.connect(said.append)
    view = shown(qapp, blocks=[*BLOCKS, CLUB], size=(1280, 744), hand=hand)
    hours = view.findChild(MissionCanvas, "missionHours")
    start = hours.block_rect("math-1", 0).center()
    # 70 pixels at 56 an hour is an hour and a quarter later, in Tuesday's lane.
    end = QPoint(start.x() + 70, hours.point_for(1, 12 * 60).y())

    def send(kind: QEvent.Type, at: QPoint, held: bool) -> None:
        buttons = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
        event = QMouseEvent(kind, QPointF(hours.mapFromGlobal(at)), QPointF(at), Qt.MouseButton.LeftButton,
                            buttons, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(hours, event)

    send(QEvent.Type.MouseButtonPress, start, True)
    for step in range(1, 9):
        send(QEvent.Type.MouseMove, start + (end - start) * step / 8, True)
    send(QEvent.Type.MouseButtonRelease, end, False)
    assert said == [Move("math-1", 0, Span(1, 17 * 60, 17 * 60 + 45))]


def test_week_name_opens_a_real_day_and_todays_date_is_a_chip(qapp: QApplication) -> None:
    view = shown(qapp)
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    view.findChild(QPushButton, "missionDay4").click()
    assert opened == [view.scene.week.date_of(4).isoformat()]
    today, friday = view.findChild(QPushButton, "missionDay3"), view.findChild(QPushButton, "missionDay4")
    assert (today.chip.isVisible(), today.date.isVisible(), today.chip.text()) == (True, False, "17")
    assert (friday.chip.isVisible(), friday.date.isVisible(), friday.date.text()) == (False, True, "18")


def test_a_bar_opens_and_gives_its_name_and_times_on_hover(qapp: QApplication) -> None:
    """How a tick too small for its name is named, and a bar's name that did not fit whole."""
    view = shown(qapp)
    hours = view.findChild(MissionCanvas, "missionHours")
    box = hours.block_rect("chem-1", 3)
    local = hours.mapFromGlobal(box.center())
    opened: list[str] = []
    hours.hand.opened.connect(opened.append)
    QTest.mouseDClick(hours, Qt.MouseButton.LeftButton, pos=local)
    QTest.mouseRelease(hours, Qt.MouseButton.LeftButton, pos=local)
    assert opened == ["chem-1"]
    QApplication.sendEvent(hours, QHelpEvent(QEvent.Type.ToolTip, local, box.center()))
    assert QToolTip.text() == "Chem-1\n20:00–21:30 · 1 h 30 min"


def test_full_day_reaches_early_block_and_quarter_hour(qapp: QApplication) -> None:
    blocks = [*BLOCKS, block("paper-round", "locked", [3], "05:00", 45),
              block("quiz", "locked", [4], "10:00", 15)]
    view = shown(qapp, blocks=blocks)
    hours = view.findChild(MissionCanvas, "missionHours")
    assert hours.block_rect("paper-round", 3) is not None
    assert hours.block_rect("quiz", 4).width() >= 10
    assert hours.block_rect("quiz", 4).height() >= 14


def test_the_four_figures_say_what_is_planned_due_free_and_focused(qapp: QApplication) -> None:
    """Thursday 13:40. Planned today is the day's homework: the essay at 18:45, the chem report at
    20:00 and the finished maths at 21:30, which is still on the day. Due this week is homework still
    to do: the maths was finished. Free time runs to 22:00 around School, Dinner and both homework
    still to do, and counts the finished maths as free: 500 minutes, less School's 50 to 14:30,
    Dinner's 30, the essay's 60 and the chem report's 90. No focus has been timed."""
    finished = block(
        "math-2", "flexible", [3], "21:30", 30, assignment_id="math", completed=True, completed_day=3
    )
    view = shown(qapp, blocks=[*BLOCKS, finished])
    assert figure(view, "missionPlanned") == ("3 h", "Essay-1 at 18:45")
    assert figure(view, "missionDue") == ("3", "2 placed, 1 not placed yet")
    assert figure(view, "missionFree") == ("4 h 30 min", "Until 22:00")
    assert figure(view, "missionFocus") == ("0 min", "None yet this week")
    cards = view.findChild(QFrame, "missionStrip").cards
    labels = [card.findChild(QLabel, "missionLabel").text() for card in cards]
    assert labels == ["Planned today", "Due this week", "Free time left today", "Focus minutes"]


def test_focus_minutes_are_what_the_timer_credited_to_this_weeks_homework(qapp: QApplication) -> None:
    homework = {**HOMEWORK, "chem": {**HOMEWORK["chem"], "focus_minutes": 35}}
    view = shown(qapp, homework=homework)
    assert figure(view, "missionFocus") == ("35 min", "On this week's homework")


def test_the_focus_figure_says_a_timer_is_running_instead_of_none_yet(qapp: QApplication) -> None:
    """Audit X5: a session was running and the figure said "None yet this week". The minutes stay
    those already credited; the line says what the timer is doing."""
    assert figure(shown(qapp, focus="focusing"), "missionFocus") == ("0 min", "Focusing now")
    assert figure(shown(qapp, focus="paused"), "missionFocus") == ("0 min", "Focus paused")
    assert figure(shown(qapp, focus="break"), "missionFocus") == ("0 min", "On a break")
    homework = {**HOMEWORK, "chem": {**HOMEWORK["chem"], "focus_minutes": 35}}
    credited = shown(qapp, homework=homework, focus="focusing")
    assert figure(credited, "missionFocus") == ("35 min", "Focusing now")


def test_another_week_has_no_today_to_count_from(qapp: QApplication) -> None:
    view = shown(qapp, today=None)
    for name in ("missionPlanned", "missionFree"):
        assert figure(view, name) == ("–", "Today is in another week.")
    assert figure(view, "missionDue") == ("3", "2 placed, 1 not placed yet")
    table = view.findChild(QFrame, "missionDeadlines")
    columns = [label.text() for label in table.findChildren(QLabel, "missionColumn")]
    assert columns == ["Homework", "Needs", "Due"]
    assert [row[2] for row in table_rows(view)] == ["Thu 17 Sep", "Fri 18 Sep", "Sun 20 Sep"]


def test_the_deadline_table_lists_homework_still_to_do_by_time_left(qapp: QApplication) -> None:
    """Chem is due at the end of today, the essay at 21:00 tomorrow and the poster on Sunday at
    20:00; the finished maths is not listed. The bar is how much of each is placed."""
    view = shown(qapp)
    assert table_rows(view) == [
        ("Chem-1", "1:30", "10 h", "Placed Thu 20:00"),
        ("Essay-1", "1:00", "1 d 7 h", "Placed Thu 18:45"),
        ("Poster-1", "2:00", "3 d 6 h", "Not placed yet"),
    ]
    table = view.findChild(QFrame, "missionDeadlines")
    assert [bar.share for bar in table.findChildren(Bar)] == [1.0, 1.0, 0.0]
    foot = table.findChild(QLabel, "missionFoot").text()
    assert foot == "The bar is how much of each is placed in the week."


def test_homework_due_on_one_day_says_so_under_the_table(qapp: QApplication) -> None:
    homework = {key: {**item, "due": "2026-09-20T23:59"} for key, item in HOMEWORK.items()}
    view = shown(qapp, homework=homework)
    foot = view.findChild(QFrame, "missionDeadlines").findChild(QLabel, "missionFoot").text()
    assert foot == "All 3 are due Sunday 20 September. The bar is how much of each is placed in the week."


def test_part_placed_homework_offers_the_session_still_waiting(qapp: QApplication) -> None:
    """The essay has an hour placed and 45 minutes waiting: its bar is part full, its waiting session
    is the handle to drag, and it counts as not placed yet."""
    second = block("second-wait", "flexible", [], None, 45, assignment_id="essay", title="Second wait")
    blocks = [*BLOCKS, second]
    view = shown(qapp, blocks=blocks)
    essay = table_rows(view)[1]
    assert essay == ("Essay-1", "1:45", "1 d 7 h", "45 min not placed yet")
    share = view.findChild(QFrame, "missionDeadlines").findChildren(Bar)[1].share
    assert share == pytest.approx(60 / 105)
    chips = {chip.block_id for chip in view.findChildren(TrayChip)}
    assert chips == {"poster-1", "second-wait"}
    assert figure(view, "missionDue")[1] == "1 placed, 2 not placed yet"


def test_homework_past_due_says_so_in_the_danger_colour(qapp: QApplication) -> None:
    homework = {**HOMEWORK, "essay": {**HOMEWORK["essay"], "due": "2026-09-17T10:00"}}
    view = shown(qapp, homework=homework)
    first = view.findChild(QFrame, "missionDeadlines").findChildren(QLabel, "missionLeft")[0]
    assert (first.text(), first.property("gone")) == ("Past due", True)
    assert table_rows(view)[0][0] == "Essay-1"


def test_a_block_keeps_its_bar_until_it_would_be_narrower_than_eight_pixels(qapp: QApplication) -> None:
    """Dinner's half hour is still a filled bar at the week's zoom; only a block too narrow for 8 px
    is a tick."""
    view = shown(qapp, blocks=[*BLOCKS, block("quiz", "locked", [4], "10:00", 45)])
    hours = view.findChild(MissionCanvas, "missionHours")
    image = hours.grab().toImage()
    surface = view.scene.tokens["surface"]
    meals_fill, meals_mark = category_paint("meals", {"family": "light", "panel": surface})
    class_fill, _ = category_paint("class", {"family": "light", "panel": surface})
    dinner = next(rect for item, rect in hours.drawn(hours.track_for(3)) if item.block_id == "dinner")
    assert dinner.width() >= 8
    middle = dinner.center().toPoint()
    assert image.pixelColor(QPoint(round(dinner.left()) + 6, round(dinner.bottom()) - 4)).name() == meals_fill
    assert image.pixelColor(middle).name() != meals_mark
    quiz = next(rect for item, rect in hours.drawn(hours.track_for(4)) if item.block_id == "quiz")
    assert image.pixelColor(QPoint(round(quiz.left()) + 6, round(quiz.bottom()) - 4)).name() == class_fill


def test_a_block_narrower_than_eight_pixels_is_a_tick(qapp: QApplication) -> None:
    """A five-minute block zoomed out until its bar would be under 8 px is a tick, not a sliver bar."""
    tiny = block("bell", "locked", [3], "12:00", 5, title="Bell", category="extra")
    view = shown(qapp, blocks=[*BLOCKS, tiny])
    hours = view.findChild(MissionCanvas, "missionHours")
    scroll = view.findChild(HoursScroll, "missionWeekScroll")
    while scroll.px > 40:
        scroll.zoom_by(-1)
    rect = next(r for item, r in hours.drawn(hours.track_for(3)) if item.block_id == "bell")
    assert rect.width() < 8
    surface = view.scene.tokens["surface"]
    _, mark = category_paint("extra", {"family": "light", "panel": surface})
    middle = rect.center().toPoint()
    assert hours.grab().toImage().pixelColor(middle).name() == mark


def test_the_line_for_now_crosses_a_block_it_lies_on(qapp: QApplication) -> None:
    """At 18:15 now is the middle of Dinner's half hour. The line goes over the block's colour:
    under it, now had a gap at Dinner."""
    view = shown(qapp, minute="18:15")
    hours = view.findChild(MissionCanvas, "missionHours")
    image = hours.grab().toImage()
    dinner = next(rect for item, rect in hours.drawn(hours.track_for(3)) if item.block_id == "dinner")
    middle = dinner.center().toPoint()
    across = {image.pixelColor(x, middle.y()).name() for x in range(middle.x() - 2, middle.x() + 3)}
    assert view.scene.tokens["now"] in across


def minutes_shown(view: MissionView, name: str) -> tuple[float, float]:
    """The minutes at the left and right edges of the lanes as they are scrolled."""
    scroll = view.findChild(HoursScroll, name)
    track = view.findChild(MissionCanvas, "missionHours").tracks[0]
    along = scroll.horizontalScrollBar().value()
    return tuple(track.first + (edge - track.area.left()) / track.per_minute()
                 for edge in (along, along + scroll.viewport().width()))


def last_minute_shown(view: MissionView, name: str) -> float:
    return minutes_shown(view, name)[1]


SURFACES = [("week", "missionWeekScroll", {}), ("day", "missionDayScroll", {"iso_day": "2026-09-17"})]


@pytest.mark.parametrize("size", [(1366, 760), (1280, 800), (810, 800)])
def test_the_lanes_of_another_week_open_through_the_evening(
    qapp: QApplication, size: tuple[int, int]
) -> None:
    """With now not in what shows, the lanes open showing the end of the day that has something in it:
    22:00 at the least, plus half an hour, so a name written at the evening's end is not cut off at the
    edge of the lanes, and for a day with a late block, that block's end. The view of the hours is not
    shrunk to get there: it scrolls."""
    week = shown(qapp, size=size, today=None)
    assert last_minute_shown(week, "missionWeekScroll") == pytest.approx(22 * 60 + 30, abs=2)
    late = block("late", "locked", [4], "22:00", 75, title="Late", category="extra")
    week = shown(qapp, size=size, blocks=[*BLOCKS, late], today=None)
    assert last_minute_shown(week, "missionWeekScroll") == pytest.approx(23 * 60 + 45, abs=2)
    assert week._scrolls["week"].px == WEEK_SCALE.default
    day = shown(qapp, size=size, surface="day", iso_day="2026-09-16")
    assert last_minute_shown(day, "missionDayScroll") == pytest.approx(22 * 60 + 30, abs=2)


@pytest.mark.parametrize("size", [(1280, 800), (810, 800)])
@pytest.mark.parametrize(("surface", "name", "chosen"), SURFACES)
def test_now_is_on_screen_when_the_evening_does_not_fit_with_it(
    qapp: QApplication, size: tuple[int, int], surface: str, name: str, chosen: dict
) -> None:
    """At 08:00 the lanes cannot show both now and 22:30, so now stays near the left edge, with 30 to
    60 minutes of the morning before it, and the evening is a scroll."""
    view = shown(qapp, size=size, surface=surface, minute="08:00", **chosen)
    first, last = minutes_shown(view, name)
    assert last < 22 * 60 + 30, "the case is one where the evening does not fit"
    assert 8 * 60 - 60 <= first <= 8 * 60 - 30, f"{surface}: the lanes start at {first:.0f}"


@pytest.mark.parametrize("size", [(1280, 800), (810, 800)])
@pytest.mark.parametrize(("surface", "name", "chosen"), SURFACES)
def test_now_and_the_evening_both_show_when_they_fit(
    qapp: QApplication, size: tuple[int, int], surface: str, name: str, chosen: dict
) -> None:
    view = shown(qapp, size=size, surface=surface, minute="15:40", **chosen)
    first, last = minutes_shown(view, name)
    assert first <= 15 * 60 + 40 <= last
    assert last == pytest.approx(22 * 60 + 30, abs=2), f"{surface}: the lanes end at {last:.0f}"


@pytest.mark.parametrize("minute", ["22:48", "23:50"])
@pytest.mark.parametrize("size", [(1280, 800), (810, 800)])
@pytest.mark.parametrize(("surface", "name", "chosen"), SURFACES)
def test_now_is_on_screen_when_it_is_later_than_the_evening(
    qapp: QApplication, size: tuple[int, int], surface: str, name: str, chosen: dict, minute: str
) -> None:
    """Audit #12: opened at 22:48 the lanes showed about 09:00 to 21:00 or ended at 22:30, with now off
    the right edge. The lanes open with now in view at any time of day."""
    view = shown(qapp, size=size, surface=surface, minute=minute, **chosen)
    first, last = minutes_shown(view, name)
    now = int(minute[:2]) * 60 + int(minute[3:])
    assert first <= now <= last, f"{surface}: now {now} is outside {first:.0f} to {last:.0f}"


def test_the_day_after_today_opens_through_the_evening_whatever_the_time_now(qapp: QApplication) -> None:
    """Now is not in the day shown when it is another day's, so the evening rule holds for it."""
    view = shown(qapp, size=(1280, 800), surface="day", iso_day="2026-09-18", minute="08:00")
    assert last_minute_shown(view, "missionDayScroll") == pytest.approx(22 * 60 + 30, abs=2)


@pytest.mark.parametrize(("minute", "today"), [("13:40", None), ("08:00", 3)])
def test_the_lanes_keep_their_opening_while_the_window_settles(
    qapp: QApplication, minute: str, today: int | None
) -> None:
    """A window is laid out in steps, and the lanes are narrower or wider than they started. They
    open where the rule puts them and stay there until the student scrolls: the evening's end at the
    right edge, or now near the left edge when the evening does not fit with it. A wider window may
    fit both, and then the evening wins."""
    view = shown(qapp, size=(1280, 800), minute=minute, today=today)
    for width in (1000, 1200):
        view.resize(width, 800)
        qapp.processEvents()
        first, last = minutes_shown(view, "missionWeekScroll")
        if today is None:
            assert 22 * 60 <= last <= 22 * 60 + 60, width
        else:
            assert 8 * 60 - 60 <= first <= 8 * 60 - 30, width


def test_a_name_written_beside_a_block_stays_inside_what_shows(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A short block that ends at 22:00 has lane after it, but its name would run off the lanes' edge when
    that is where they are scrolled to; it goes before the tick, where it shows whole."""
    seen: list[QRectF] = []

    class Said(QPainter):
        def drawText(self, *args) -> None:  # noqa: N802
            if len(args) == 3 and isinstance(args[0], QRectF) and args[2] == "Chemistry":
                seen.append(QRectF(args[0]))
            super().drawText(*args)

    monkeypatch.setattr(canvas_module, "QPainter", Said)
    tick = block("tick", "locked", [4], "21:15", 45, title="Chemistry", category="extra")
    view = shown(qapp, blocks=[*BLOCKS, tick])
    scroll = view.findChild(HoursScroll, "missionWeekScroll")
    track = view.findChild(MissionCanvas, "missionHours").tracks[0]
    edge = round(track.area.left() + (22 * 60 + 5) * track.per_minute())
    scroll.horizontalScrollBar().setValue(edge - scroll.viewport().width())
    seen.clear()
    view.findChild(MissionCanvas, "missionHours").repaint()
    assert len(seen) == 1, "the name is written once, beside its tick"
    assert seen[0].right() <= edge, "and not past the right edge of the lanes"


def test_the_now_pill_covers_no_hour_label_at_any_zoom(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pill that gives the time now sits in the row of hours. An hour label it would overlap is
    left out, however far apart the zoom puts the hours: at the smallest, a pill at 10:45 lay over
    the 10:00 label, which the old rule of leaving out labels within 40 minutes of now let through."""
    seen: list[tuple[QRectF, str]] = []

    class Said(QPainter):
        def drawText(self, *args) -> None:  # noqa: N802
            if len(args) == 3 and isinstance(args[0], QRectF):
                seen.append((QRectF(args[0]), args[2]))
            super().drawText(*args)

    monkeypatch.setattr(canvas_module, "QPainter", Said)
    for clock, px in itertools.product(("10:20", "10:45", "10:50", "11:10", "11:15"), (40, 56)):
        view = shown(qapp, minute=clock)
        scroll = view.findChild(HoursScroll, "missionWeekScroll")
        while scroll.px != px:
            scroll.zoom_by(1 if scroll.px < px else -1)
        hours = view.findChild(MissionCanvas, "missionHours")
        seen.clear()
        hours.repaint()
        row = hours.tracks[0].area.top()
        times = [(box, text) for box, text in seen if re.fullmatch(r"\d\d:\d\d", text) and box.top() < row]
        (pill,) = [box for box, text in times if text == clock]
        covered = [text for box, text in times if text != clock and box.intersects(pill)]
        assert covered == [], f"{clock} at {px} px an hour"
        assert len(times) > 2, "the other hours are still written"
        view.deleteLater()


def test_the_line_for_now_stops_short_of_a_ticks_icon(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tick carries its icon above the mark. At 18:02 the line for now crosses the tick and stops
    short of the icon, as it stops short of a block's words, and resumes on the mark."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainter

    from desktop.native.hours import canvas as canvas_module

    drawn: list[QRectF] = []
    bell = block("bell", "locked", [3], "18:00", 5, title="Bell", category="extra")

    class Pictures(QPainter):
        def drawPixmap(self, *args):  # noqa: N802
            if isinstance(args[0], QPointF):
                drawn.append(self.transform().mapRect(QRectF(args[0], args[1].deviceIndependentSize())))
            return super().drawPixmap(*args)

    monkeypatch.setattr(canvas_module, "QPainter", Pictures)
    images = []
    for minute in ("12:00", "18:02"):
        view = shown(qapp, blocks=[*BLOCKS, bell], minute=minute)
        scroll = view.findChild(HoursScroll, "missionWeekScroll")
        while scroll.px > 40:
            scroll.zoom_by(-1)
        hours = view.findChild(MissionCanvas, "missionHours")
        drawn.clear()
        images.append(hours.grab().toImage())
    tick = next(rect for item, rect in hours.drawn(hours.track_for(3)) if item.block_id == "bell")
    assert tick.width() < 8
    (icon,) = [box for box in drawn if tick.contains(box.center())]
    near = icon.adjusted(-2, -2, 2, 2).toAlignedRect()
    bare, lit = images
    changed = [
        (x, y) for x in range(near.left(), near.right() + 1) for y in range(near.top(), near.bottom() + 1)
        if bare.pixel(x, y) != lit.pixel(x, y)
    ]
    assert changed == [], "the line for now is drawn on the tick's icon"
    middle = tick.center().toPoint()
    across = {lit.pixelColor(x, middle.y()).name() for x in range(middle.x() - 2, middle.x() + 3)}
    assert hours.painter.c("now").name() in across


def test_a_name_that_cannot_fit_is_written_beside_its_block_where_the_lane_is_free(
    qapp: QApplication,
) -> None:
    """The piano lesson's 45 minutes cannot hold its name, and Dinner is too close after it, so the
    name goes before it, over free lane. School's name fits inside, so nothing is written before it."""
    piano = block("piano", "locked", [2], "17:00", 45, title="Piano lesson", category="extra")
    view = shown(qapp, blocks=[*BLOCKS, piano])
    hours = view.findChild(MissionCanvas, "missionHours")
    image = hours.grab().toImage()

    def ink_before(block_id: str) -> int:
        rect = next(rect for item, rect in hours.drawn(hours.track_for(2)) if item.block_id == block_id)
        return sum(
            QColor(image.pixel(x, y)).lightness() < 110
            for x in range(max(round(rect.left()) - 110, 0), round(rect.left()) - 4)
            for y in range(round(rect.top()) + 6, round(rect.top()) + 24)
        )

    assert ink_before("piano") > 20
    assert ink_before("school") == 0


def test_day_says_what_is_still_to_come_today_and_the_free_time_left(qapp: QApplication) -> None:
    view = shown(qapp, surface="day", iso_day="2026-09-17")
    coming = view.findChild(QFrame, "missionUpNext")
    assert words(coming.findChild(QLabel, "missionMuted")) == "3 more today"
    assert [
        (when.text(), name.full_text(), wait.text())
        for when, name, wait in zip(
            coming.findChildren(QLabel, "missionWhen"),
            coming.findChildren(FittedLabel, "missionRowTitle"),
            coming.findChildren(QLabel, "missionIn"),
            strict=True,
        )
    ] == [
        ("18:00", "Dinner", "in 4 h 20 min"),
        ("18:45", "Essay-1", "in 5 h 5 min"),
        ("20:00", "Chem-1", "in 6 h 20 min"),
    ]
    assert words(coming.findChild(QLabel, "missionFoot")) == "Then Friday: School at 08:00."
    free = view.findChild(QFrame, "missionFreeTime")
    assert words(free.findChild(QLabel, "missionMuted")) == "4:30 until 22:00"
    assert [
        (when.text(), length.text())
        for when, length in zip(
            free.findChildren(QLabel, "missionWhen"), free.findChildren(QLabel, "missionFigure"), strict=True
        )
    ] == [("14:30–18:00", "3:30"), ("18:30–18:45", "0:15"), ("19:45–20:00", "0:15"), ("21:30–22:00", "0:30")]
    assert words(free.findChild(QLabel, "missionFoot")) == "Room for Poster-1, 2:00, before 22:00."


def test_up_next_shows_whole_rows_and_leaves_out_what_does_not_fit(qapp: QApplication) -> None:
    """At 15:40 four things are still to come on Thursday, and at 1280 by 744 the card has room for
    fewer. It shows the first ones whole, never the next cut at its foot, and its head still counts
    all four."""
    soccer = block("soccer", "locked", [1, 3], "16:00", 90, title="Soccer practice", category="exercise")
    view = shown(qapp, surface="day", iso_day="2026-09-17", minute="15:40", size=(1280, 744),
                 blocks=[*BLOCKS, soccer])
    coming = view.findChild(QFrame, "missionUpNext")
    assert words(coming.findChild(QLabel, "missionMuted")) == "4 more today"

    def showing(row: QWidget) -> QRect:
        """The part of a row on screen: inside every widget it is in, up to the card."""
        if not row.isVisibleTo(coming):
            return QRect()
        seen = QRect(row.mapTo(coming, QPoint(0, 0)), row.size())
        inside = row.parentWidget()
        while inside is not coming:
            seen &= QRect(inside.mapTo(coming, QPoint(0, 0)), inside.size())
            inside = inside.parentWidget()
        return seen

    rows = coming.findChildren(QFrame, "missionListRow")
    shows = [row for row in rows if not showing(row).isEmpty()]
    assert 0 < len(shows) < len(rows)
    assert [showing(row).size() for row in shows] == [row.size() for row in shows], "a row is cut"
    titles = [row.findChild(FittedLabel, "missionRowTitle").full_text() for row in shows]
    assert titles == ["Soccer practice", "Dinner", "Essay-1", "Chem-1"][: len(shows)]


def busy_thursday(qapp: QApplication, height: int) -> MissionView:
    """Thursday at 15:40 with six things still to come and five stretches of free time left."""
    extra = [
        block("soccer", "locked", [1, 3], "16:00", 90, title="Soccer practice", category="exercise"),
        block("piano", "locked", [3], "19:00", 30, title="Piano", category="extra"),
        block("walk", "locked", [3], "21:00", 30, title="Walk", category="exercise"),
    ]
    return shown(qapp, surface="day", iso_day="2026-09-17", minute="15:40", size=(1280, height),
                 blocks=[*BLOCKS, *extra])


def test_a_card_that_leaves_rows_out_ends_with_and_n_more_in_the_room_of_a_row(qapp: QApplication) -> None:
    """At 1280 by 800 Up next has room for three of its six rows and Free time left for three of its
    five. Each shows whole rows, then an "and N more" where the next row would be, N counting
    the row it replaces, so what shows and what is left out add up to the head's count."""
    view = busy_thursday(qapp, 800)
    for card_name, total in (("missionUpNext", 6), ("missionFreeTime", 5)):
        card = view.findChild(QFrame, card_name)
        rows = [row for row in card.findChildren(QFrame, "missionListRow") if row.isVisibleTo(card)]
        more = card.findChild(QLabel, "missionMore")
        assert more.isVisibleTo(card), f"{card_name} does not say what it leaves out"
        left = int(re.fullmatch(r"and (\d+) more", more.text()).group(1))
        assert len(rows) == 3
        assert len(rows) + left == total
        assert more.geometry().bottom() <= card.findChild(QWidget, f"{card_name}Rows").height()
        assert more.height() == rows[-1].height()
        assert more.geometry().top() == rows[-1].geometry().bottom() + 1, "not straight after the last row"
        assert all(row.property("last") is False for row in rows)


def test_a_card_whose_rows_all_fit_has_no_more_row(qapp: QApplication) -> None:
    view = busy_thursday(qapp, 1100)
    for card_name, total in (("missionUpNext", 6), ("missionFreeTime", 5)):
        card = view.findChild(QFrame, card_name)
        rows = [row for row in card.findChildren(QFrame, "missionListRow") if row.isVisibleTo(card)]
        assert len(rows) == total
        assert not card.findChild(QLabel, "missionMore").isVisibleTo(card)
        assert [row.property("last") for row in rows] == [False] * (total - 1) + [True]


def test_late_in_the_day_the_free_time_says_when_what_waits_will_not_fit(qapp: QApplication) -> None:
    view = shown(qapp, surface="day", iso_day="2026-09-17", minute="20:30")
    free = view.findChild(QFrame, "missionFreeTime")
    assert [when.text() for when in free.findChildren(QLabel, "missionWhen")] == ["21:30–22:00"]
    said = words(free.findChild(QLabel, "missionFoot"))
    assert said == "Poster-1 needs 2:00, more than is free before 22:00."
    coming = view.findChild(QFrame, "missionUpNext")
    assert coming.findChildren(QLabel, "missionWhen") == []
    assert coming.findChild(QLabel, "missionHint").text() == "Nothing else scheduled today."


@pytest.mark.parametrize(
    ("size", "scale", "side"),
    [((1280, 760), 1.0, True), ((1150, 700), 1.2, True), ((900, 700), 1.0, False)],
)
def test_the_table_stays_beside_the_lanes_until_they_would_show_too_little(
    qapp: QApplication, size: tuple[int, int], scale: float, side: bool
) -> None:
    """It holds the only handle on homework not placed yet, so at 1150 wide with large text, where the
    rig checks the handles are on screen, it is still beside them; under 924 pixels it goes under."""
    view = shown(qapp, size=size, scale=scale)
    assert beside(view, "missionWeekScroll") is side


def test_the_figures_fold_two_over_two_in_a_narrow_window(qapp: QApplication) -> None:
    wide = shown(qapp)
    tops = [wide.findChild(QFrame, name).y() for name in ("missionPlanned", "missionDue", "missionFree")]
    assert len(set(tops)) == 1
    narrow = shown(qapp, size=(800, 700))
    names = ("missionPlanned", "missionDue", "missionFree")
    planned, due, free = (narrow.findChild(QFrame, name) for name in names)
    assert planned.y() == due.y() < free.y()
    page = narrow.findChild(QScrollArea, "missionScroll")
    assert page.horizontalScrollBar().maximum() == 0, "the page scrolls sideways"


def test_in_a_short_window_the_lanes_and_not_the_tables_rows_set_the_pages_height(
    qapp: QApplication,
) -> None:
    """Six homework make a table taller than a laptop's short window. Its rows scroll inside it, and
    every lane is on screen with the page still."""
    extra = {
        f"hw{at}": {"id": f"hw{at}", "title": f"Reading {at}", "due": "2026-09-20T23:59", "completed": False}
        for at in range(4)
    }
    sessions = [block(f"hw{at}-1", "flexible", [], None, 30, assignment_id=f"hw{at}") for at in range(4)]
    blocks = [*BLOCKS, *sessions]
    view = shown(qapp, blocks=blocks, homework={**HOMEWORK, **extra}, size=(1366, 490))
    assert view.findChild(QScrollArea, "missionScroll").verticalScrollBar().maximum() == 0
    assert view.findChild(QScrollArea, "missionDeadlineRowsScroll").verticalScrollBar().maximum() > 0


def test_the_figures_can_be_hidden(qapp: QApplication) -> None:
    assert shown(qapp, figures="hide").findChild(QFrame, "missionStrip") is None
    assert shown(qapp).findChild(QFrame, "missionStrip") is not None


def test_a_narrow_week_keeps_its_hours_and_their_zoom(qapp: QApplication) -> None:
    view = shown(qapp)
    original = view._scrolls["week"]
    original.zoom_by(1)
    view.resize(800, 640)
    view.show_week(replace(view.scene, minute=view.scene.minute + 1))
    # The board is laid out in one pass, and its scroll area grows the page to hold it in the next.
    for _ in range(2):
        qapp.processEvents()
    assert beside(view, "missionWeekScroll") is False
    assert view.findChild(TrayChip, "missionWaiting0") is not None
    assert view._scrolls["week"] is original
    assert original.px == 72
    view.show_week(replace(view.scene, surface="day"))
    view.show_week(replace(view.scene, surface="week"))
    assert view._scrolls["week"] is original and original.px == 72


def test_parked_day_scroll_dies_with_its_host(qapp: QApplication) -> None:
    options = options_for(None, "mission")
    palette = resolved_palette("light-frost", False, None, "default")
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    scene = Scene(week, 3, minute_of("13:40"), options,
                  tokens_for("mission", options["colour"], palette))
    host = QWidget()
    view = MissionView(host)
    QVBoxLayout(host).addWidget(view)
    view.show_week(scene)
    host.show()
    qapp.processEvents()
    view.show_week(replace(scene, surface="day", iso_day="2026-09-18"))
    parked = view._scrolls["day"]
    view.show_week(scene)
    assert shiboken6.isValid(parked)

    host.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(parked)


def test_colour_option_repaints_the_console(qapp: QApplication) -> None:
    colours = [shown(qapp, colour=name).grab().toImage().pixelColor(3, 3).name()
               for name in ("deck", "cyan", "amber", "green")]
    assert colours == ["#0b0f14", "#070b12", "#0d0a04", "#040b06"]


def test_flight_deck_is_the_mock_ups_signature_in_flexweeks_blue_whatever_the_look() -> None:
    """A design's own colourway stays the same whichever look and accent the student wears."""
    assert LAYOUTS["mission"].colourways[0][:2] == ("deck", "Flight deck")
    for pack, dark, accent in itertools.product(PACKS, (False, True), ACCENTS):
        tokens = tokens_for("mission", "deck", resolved_palette(pack, dark, None, accent))
        assert (tokens["bg"], tokens["surface"], tokens["accent"]) == ("#0b0f14", "#121821", "#7fa8ff")


def test_a_long_title_in_the_table_is_shortened_with_its_whole_name_to_hand(qapp: QApplication) -> None:
    title = "History essay outline and annotated bibliography"
    blocks = [{**item, "title": title} if item["id"] == "essay-1" else item for item in BLOCKS]
    view = shown(qapp, blocks=blocks)
    name = view.findChild(QFrame, "missionDeadlines").findChildren(FittedLabel, "missionDeadlineTitle")[1]
    assert name.text().endswith("…")
    assert (name.full_text(), name.toolTip()) == (title, title)


def test_a_waiting_row_click_opens_homework(qapp: QApplication) -> None:
    view = shown(qapp, surface="day")
    opened: list[str] = []
    view.block_activated.connect(opened.append)
    chip = view.findChild(TrayChip, "missionWaiting0")
    QTest.mouseClick(chip, Qt.MouseButton.LeftButton)
    assert opened == [chip.block_id] == ["poster-1"]
