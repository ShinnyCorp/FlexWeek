"""Clay deck is a row of cards, one day in front (0.17's Card carousel), all of them live hours on the
window's hand."""

from __future__ import annotations

import importlib.util
import os
import time
from collections.abc import Iterator

import pytest

from desktop.tests.test_weekmodel import BLOCKS, HOMEWORK, TRACE, WEEK

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QAbstractAnimation, QPoint, QPointF, Qt
    from PySide6.QtGui import QCursor, QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

    from desktop.native import motion
    from desktop.native.hours.canvas import HoursCanvas
    from desktop.native.hours.zoom import HoursScroll
    from desktop.native.layouts.base import Scene
    from desktop.native.layouts.clay import ClayChip, ClayDeckView, slots
    from desktop.native.layouts.registry import options_for, tokens_for
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import build_week, minute_of


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-clay-test"])
    yield application


@pytest.fixture(autouse=True)
def still() -> Iterator[None]:
    """The row where each move ends, unless a test asks for motion; the level is put back after."""
    was = motion.app_level()
    motion.apply_ui_effects("off")
    yield
    motion.apply_ui_effects(was)


def shown(qapp: QApplication, *, tab: str = "week", day: int = 3, **chosen: str) -> ClayDeckView:
    options = {**options_for(None, "clay"), **chosen}
    palette = resolved_palette("light-frost", False, None, "default")
    week = build_week(WEEK, BLOCKS, HOMEWORK, TRACE)
    view = ClayDeckView()
    view.resize(1280, 764)
    view.show_week(Scene(
        week, 3, minute_of("13:40"), options,
        tokens_for("clay", options["colour"], palette),
        surface=tab, iso_day=week.date_of(day).isoformat(),
    ))
    view.show()
    qapp.processEvents()
    return view


def again(qapp: QApplication, view: ClayDeckView, **changed: object) -> None:
    previous = view.scene
    fields = {
        "week": previous.week, "today": previous.today, "minute": previous.minute,
        "options": previous.options, "tokens": previous.tokens, "surface": previous.surface,
        "iso_day": previous.iso_day, **changed,
    }
    view.show_week(Scene(**fields))
    qapp.processEvents()


def front(view: ClayDeckView) -> HoursCanvas:
    surfaces = view.hours_surfaces()
    assert isinstance(surfaces[0], HoursCanvas)
    return surfaces[0]


def visible_scrolls(view: ClayDeckView) -> list[HoursScroll]:
    return [scroll for scroll in view.findChildren(HoursScroll) if scroll.isVisible()]


def pairs(view: ClayDeckView) -> list[tuple[str, str]]:
    summary = view.findChild(QWidget, "claySummary")
    names = [item.text() for item in summary.findChildren(QLabel, "claySumName")]
    values = [item.text() for item in summary.findChildren(QLabel, "claySumLength")]
    return list(zip(names, values, strict=True))


def wheel(target: QWidget, at: QPointF, notch: int) -> None:
    """One notch of the wheel over `at` in `target`, away from the student (1) or toward (-1)."""
    event = QWheelEvent(
        at, QPointF(target.mapToGlobal(at.toPoint())), QPoint(0, 0), QPoint(0, 120 * notch),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False,
    )
    QApplication.sendEvent(target, event)


def rest(qapp: QApplication, seconds: float) -> None:
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        qapp.processEvents()
        time.sleep(0.01)


def test_the_day_in_front_is_the_one_hours_that_scroll_and_zoom_and_its_neighbours_are_live(
    qapp: QApplication,
) -> None:
    view = shown(qapp)
    assert [scroll.objectName() for scroll in visible_scrolls(view)] == ["clayWeekScroll"]
    hours = front(view)
    assert hours.parentWidget() is visible_scrolls(view)[0].viewport()
    assert [(track.day, track.first, track.last) for track in hours.tracks] == [(3, 0, 1440)]
    assert hours.block_rect("essay-1", 3) is not None
    days = [track.day for surface in view.hours_surfaces() for track in surface.tracks]
    assert days == [3, 0, 1, 2, 4, 5, 6]
    assert all(surface.hand is view.hand for surface in view.hours_surfaces())


def test_neighbours_show_the_stretch_the_day_in_front_shows_on_the_drags_step(qapp: QApplication) -> None:
    view = shown(qapp)
    scroll = visible_scrolls(view)[0]
    track = front(view).tracks[0]
    x = track.area.center().x()
    top = scroll.verticalScrollBar().value()
    first = track.minute_at(QPointF(x, top))
    last = track.minute_at(QPointF(x, top + scroll.viewport().height()))
    step = view.hand.step
    for surface in view.hours_surfaces()[1:]:
        (peek,) = surface.tracks
        assert peek.first % step == 0 and peek.last % step == 0
        assert peek.first <= first < peek.first + step
        assert peek.last - step < last <= peek.last
    scroll.verticalScrollBar().setValue(top - 120)
    qapp.processEvents()
    moved = view.hours_surfaces()[1].tracks[0]
    assert moved.first == pytest.approx(first - 120 / track.per_minute(), abs=step)


def test_neighbours_are_the_card_in_front_at_70_percent_with_the_room_between_kept() -> None:
    """The mock-up's row at 1280 pixels: the card in front 452 wide at 414, a neighbour 316 wide, 32
    between cards."""
    rects = slots(1280, 632, 3, 1.0, wide=False)
    assert (rects[3].left(), rects[3].width(), rects[3].height()) == (414, 452, 600)
    for day in (2, 4):
        assert rects[day].width() == pytest.approx(0.7 * 452)
        assert rects[day].height() == pytest.approx(0.7 * 600)
        assert rects[day].center().y() == pytest.approx(rects[3].center().y())
    assert rects[2].right() == pytest.approx(414 - 32)
    assert rects[4].left() == pytest.approx(414 + 452 + 32)
    assert rects[5].left() == pytest.approx(rects[4].right() + 32)
    assert rects[2].left() == pytest.approx(66, abs=1)
    assert slots(1280, 632, 3, 1.0, wide=True)[3].width() == 800


def test_a_narrower_row_narrows_the_card_in_front_so_both_neighbours_stay_whole() -> None:
    rects = slots(1150, 632, 3, 1.2, wide=False)
    assert rects[3].width() < 452 * 1.2
    assert rects[2].left() >= 0 and rects[4].right() <= 1150


def test_the_arrows_slide_the_row_a_day_and_stop_at_the_weeks_ends(qapp: QApplication) -> None:
    view = shown(qapp)
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    ahead = view.findChild(QPushButton, "clayAhead")
    back = view.findChild(QPushButton, "clayBack")
    ahead.click()
    assert view.row.front == 4
    assert [track.day for track in front(view).tracks] == [4]
    assert view.findChild(QPushButton, "clayWeekFront").day == 4
    for _ in range(4):
        back.click()
    assert view.row.front == 0
    assert not back.isEnabled() and ahead.isEnabled()
    for _ in range(6):
        ahead.click()
    assert view.row.front == 6
    assert back.isEnabled() and not ahead.isEnabled()
    assert opened == []


def test_the_front_names_its_day_and_how_much_it_holds(qapp: QApplication) -> None:
    view = shown(qapp)
    note = view.findChild(QPushButton, "clayWeekFront").findChild(QLabel, "clayNote")
    assert note.text() == "Today · 4 things"
    view.findChild(QPushButton, "clayAhead").click()
    assert note.text() == "2 things"
    view.findChild(QPushButton, "clayAhead").click()
    assert note.text() == "1 thing"


def test_the_wheel_slides_the_row_over_a_neighbour_and_scrolls_the_hours_over_the_front(
    qapp: QApplication,
) -> None:
    view = shown(qapp)
    friday = view.findChild(HoursCanvas, "clayPeek4")
    wheel(friday, QPointF(friday.rect().center()), -1)
    assert view.row.front == 4
    # At the top of the hours, where the wheel has nothing left to scroll and passes on to the row.
    visible_scrolls(view)[0].verticalScrollBar().setValue(0)
    wheel(front(view), QPointF(front(view).rect().center()), 1)
    assert view.row.front == 4


def test_the_row_slides_in_240_ms_and_jumps_with_motion_off(qapp: QApplication) -> None:
    view = shown(qapp)
    motion.apply_ui_effects("normal")
    friday = view.row.findChild(QWidget, "clayPeek4").parentWidget()
    before = friday.geometry()
    view.findChild(QPushButton, "clayAhead").click()
    qapp.processEvents()
    assert view.row._slide.state() == QAbstractAnimation.State.Running
    assert front(view).tracks[0].day == 4
    rest(qapp, 0.4)
    assert view.row._slide.state() == QAbstractAnimation.State.Stopped
    thursday = view.row.findChild(QWidget, "clayPeek3").parentWidget()
    assert thursday.isVisible() and thursday.geometry().right() < before.left()
    motion.apply_ui_effects("off")
    view.findChild(QPushButton, "clayAhead").click()
    assert view.row._slide.state() == QAbstractAnimation.State.Stopped
    assert view.row.front == 5


def test_under_reduce_the_row_changes_where_it_is_under_a_fading_picture(qapp: QApplication) -> None:
    """Decision 35 of 0.17: Clay's own motion keeps to the levels. Reduce fades and moves nothing;
    More slides longer than Normal."""
    view = shown(qapp)
    motion.apply_ui_effects("reduce")
    view.findChild(QPushButton, "clayAhead").click()
    assert view.row._slide.state() == QAbstractAnimation.State.Stopped, "nothing slides"
    assert view.row.front == 4 and front(view).tracks[0].day == 4, "Friday is in front at once"
    fading = [label for label in view.row.findChildren(QLabel, motion.FADE_NAME) if label.isVisible()]
    assert len(fading) == 1, "the row as it was fades away over it"
    rest(qapp, 0.4)
    assert [label for label in view.row.findChildren(QLabel, motion.FADE_NAME) if label.isVisible()] == []
    motion.apply_ui_effects("extra")
    view.findChild(QPushButton, "clayAhead").click()
    assert view.row._slide.duration() == motion.duration(240, "extra") > 240


def test_a_block_held_on_an_arrow_slides_the_row_to_the_next_day(qapp: QApplication) -> None:
    """How a block reaches a day that is not beside the one in front: rest it on an arrow."""
    view = shown(qapp)
    ahead = view.findChild(QPushButton, "clayAhead")
    QCursor.setPos(ahead.mapToGlobal(ahead.rect().center()))
    view.hand.active_changed.emit(True)
    rest(qapp, 0.8)
    assert view.row.front == 4
    view.hand.active_changed.emit(False)
    rest(qapp, 0.8)
    assert view.row.front == 4


def test_day_names_open_their_day_and_every_day_has_one(qapp: QApplication) -> None:
    view = shown(qapp)
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    names = {item.property("day_target") for item in view.findChildren(QPushButton)} - {None}
    assert names == set(range(7))
    QTest.mouseClick(view.findChild(QPushButton, "clayDay4"), Qt.MouseButton.LeftButton)
    QTest.mouseClick(view.findChild(QPushButton, "clayWeekFront"), Qt.MouseButton.LeftButton)
    week = view.scene.week
    assert opened == [week.date_of(4).isoformat(), week.date_of(3).isoformat()]


def test_a_name_past_the_rows_edge_is_brought_to_the_front_before_it_is_found(qapp: QApplication) -> None:
    view = shown(qapp)
    hours = front(view)
    friday = view.findChild(QPushButton, "clayDay4")
    assert friday.rect().contains(friday.mapFromGlobal(hours.day_name(4)))
    assert view.row.front == 3
    point = hours.day_name(6)
    assert view.row.front == 6
    head = view.findChild(QPushButton, "clayWeekFront")
    assert head.rect().contains(head.mapFromGlobal(point))
    assert view.row.rect().contains(view.row.mapFromGlobal(point))


def test_reveal_brings_a_day_to_the_front_and_its_time_into_view(qapp: QApplication) -> None:
    view = shown(qapp)
    view.hours_surfaces()[-1].reveal(5, 9 * 60, 10 * 60)
    qapp.processEvents()
    assert view.row.front == 5
    hours = front(view)
    assert hours.track_for(5, 9 * 60) is not None
    assert hours.in_view(5, 9 * 60) and hours.in_view(5, 10 * 60)


def test_with_the_days_either_side_hidden_only_the_front_is_hours(qapp: QApplication) -> None:
    view = shown(qapp, peek="hide")
    assert [track.day for surface in view.hours_surfaces() for track in surface.tracks] == [3]
    view.findChild(QPushButton, "clayAhead").click()
    assert [track.day for surface in view.hours_surfaces() for track in surface.tracks] == [4]


def test_day_opens_the_card_wider_with_its_hours_by_kind_and_what_is_left_today(qapp: QApplication) -> None:
    """Thursday at 13:40: School 08:00-14:30, Dinner 18:00-18:30, the essay 18:45-19:45 and chemistry
    20:00-21:30. Until 22:00: 50 minutes of School, and all the rest, are still ahead."""
    view = shown(qapp, tab="day")
    assert [scroll.objectName() for scroll in visible_scrolls(view)] == ["clayDayScroll"]
    assert [(track.day, track.first, track.last) for track in front(view).tracks] == [(3, 0, 1440)]
    summary = view.findChild(QWidget, "claySummary")
    assert summary.findChild(QLabel, "claySumTitle").text() == "Thursday, 08:00 to 22:00"
    assert pairs(view) == [
        ("School", "6 h 30 min"),
        ("Homework", "2 h 30 min"),
        ("Meals", "30 min"),
        ("Free", "4 h 30 min"),
        ("Planned", "3 h 50 min"),
        ("Free until 22:00", "4 h 30 min"),
        ("Next at 18:00", "in 4 h 20 min"),
    ]
    assert summary.geometry().left() > visible_scrolls(view)[0].geometry().right()


def test_another_day_has_no_left_today(qapp: QApplication) -> None:
    view = shown(qapp, tab="day", day=4)
    assert view.row.front == 4
    assert pairs(view) == [("School", "6 h 30 min"), ("Meals", "30 min"), ("Free", "7 h")]
    assert view.findChild(QLabel, "clayLeftTitle") is None


def test_days_arrows_ask_the_window_for_the_day_either_side_across_the_weeks_edge(
    qapp: QApplication,
) -> None:
    view = shown(qapp, tab="day", day=0)
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    view.findChild(QPushButton, "clayAhead").click()
    view.findChild(QPushButton, "clayBack").click()
    assert opened == ["2026-09-15", "2026-09-13"]
    assert view.row.front == 0


def test_a_block_carried_to_another_day_on_day_takes_the_window_there_when_it_is_let_go(
    qapp: QApplication,
) -> None:
    view = shown(qapp, tab="day")
    opened: list[str] = []
    view.day_activated.connect(opened.append)
    ahead = view.findChild(QPushButton, "clayAhead")
    QCursor.setPos(ahead.mapToGlobal(ahead.rect().center()))
    view.hand.active_changed.emit(True)
    rest(qapp, 0.8)
    assert opened == []
    view.hand.active_changed.emit(False)
    assert opened == [view.scene.week.date_of(4).isoformat()]


def test_the_dish_holds_what_is_not_placed_yet_with_when_it_is_due(qapp: QApplication) -> None:
    view = shown(qapp)
    assert view.findChild(QLabel, "clayTrayLabel").text() == "Not placed yet"
    assert view.findChild(QLabel, "clayDue").text() == "Due Sun 20"
    assert view.findChild(QLabel, "clayHint").text() == "Drag a chip onto a day."
    chips = view.findChildren(ClayChip)
    assert [chip.block_id for chip in chips] == ["poster-1"]
    assert all(chip.hand is view.hand for chip in chips)


def test_scroll_and_zoom_survive_a_scene_refresh(qapp: QApplication) -> None:
    view = shown(qapp)
    scroll = view.findChild(HoursScroll, "clayWeekScroll")
    scroll.zoom_by(1)
    scroll.verticalScrollBar().setValue(240)
    before = (scroll.px, scroll.verticalScrollBar().value())
    again(qapp, view, minute=view.scene.minute + 15)
    assert view.findChild(HoursScroll, "clayWeekScroll") is scroll
    assert (scroll.px, scroll.verticalScrollBar().value()) == before
    assert front(view).now_min == view.scene.minute


def test_day_and_week_keep_separate_scrolls(qapp: QApplication) -> None:
    view = shown(qapp)
    week_scroll = view.findChild(HoursScroll, "clayWeekScroll")
    week_scene = view.scene
    again(qapp, view, surface="day")
    day_scroll = view.findChild(HoursScroll, "clayDayScroll")
    assert day_scroll is not week_scroll
    assert visible_scrolls(view) == [day_scroll]
    view.show_week(week_scene)
    qapp.processEvents()
    assert visible_scrolls(view) == [week_scroll]
