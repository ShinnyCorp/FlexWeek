"""Opening hours and keeping the student's scroll across views and designs.

Today and returning to this week reopen at now; other returns keep the chosen position.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import time
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QAbstractAnimation, QPoint, QPointF, QStandardPaths
    from PySide6.QtWidgets import QApplication, QPushButton, QScrollBar

    from desktop.native import motion
    from desktop.native.calendar import monday_of, sunday_due
    from desktop.native.hours.geometry import Axis
    from desktop.native.hours.zoom import HoursScroll
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer
    from desktop.tests.logic_support import past_setup

PASSWORD = "a-long-test-password"
DESIGNS = ("classic", "timeline", "mission", "bento", "retro", "clay")
NOW = 15 * 60 + 40


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-hours-open-test"])


def wait_until(qapp: QApplication, predicate: Callable[[], bool], timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def look_file() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(root) / "flexweek-look.json"


@pytest.fixture()
def window(qapp: QApplication, tmp_path: Path) -> Iterator[NativeWindow]:
    """Signed in with the clock held at Thursday 15:40 from before the week is first shown: school
    on weekdays from 08:00, dinner every day at 18:00, and nothing next week."""
    # A look saved by an earlier test on this worker would choose another day screen (One thing has no
    # Running late), and the window reads it at start.
    look_file().unlink(missing_ok=True)
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    made = NativeWindow(server.origin)
    thursday = datetime.fromisoformat(monday_of(date.today().isoformat())) + timedelta(days=3)
    held = thursday + timedelta(minutes=NOW)
    made.session.now_ms = lambda: int(held.timestamp() * 1000)
    made.resize(1280, 860)
    made.show()
    try:
        made.username.setText("opening_student")
        made.password.setText(PASSWORD)
        made.findChild(QPushButton, "createAccount").click()
        wait_until(qapp, lambda: made._stack.currentWidget().objectName() == "recoveryPage")
        made.recovery_ack.setChecked(True)
        made.recovery_continue.click()
        past_setup(qapp, made)
        session = made.session
        session.add_block(
            {"id": "school", "title": "School", "kind": "locked", "category": "class",
             "start": "08:00", "duration_min": 390, "days": [0, 1, 2, 3, 4]}
        )
        session.add_block(
            {"id": "dinner", "title": "Dinner", "kind": "locked", "category": "meals",
             "start": "18:00", "duration_min": 30, "days": [0, 1, 2, 3, 4, 5, 6]}
        )
        session.save()
        wait_until(qapp, lambda: not session.busy and not session.dirty)
        yield made
    finally:
        with contextlib.suppress(RuntimeError):
            made.session.client.reset()
        made.hide()
        qapp.processEvents()
        server.stop()
        look_file().unlink(missing_ok=True)


def hours(window: NativeWindow) -> HoursScroll:
    shown = [scroll for scroll in window.planner.currentWidget().findChildren(HoursScroll)
             if scroll.isVisible()]
    assert len(shown) == 1, f"{len(shown)} hours on screen"
    return shown[0]


def span_shown(scroll: HoursScroll) -> tuple[float, float]:
    """The first and last minute on screen, along the way time runs."""
    canvas, port = scroll.canvas, scroll.viewport()
    track = next(track for track in canvas.tracks if not track.turn)
    start = QPointF(canvas.mapFrom(port, QPoint(0, 0)))
    end = QPointF(canvas.mapFrom(port, QPoint(port.width(), port.height())))
    if track.axis is Axis.DOWN:
        start.setX(track.area.center().x())
        end.setX(track.area.center().x())
    else:
        start.setY(track.area.center().y())
        end.setY(track.area.center().y())
    return track.minute_at(start), track.minute_at(end)


def opens_at(qapp: QApplication, window: NativeWindow, minute: int, where: str) -> None:
    """`minute` is on screen, with at most half of what shows before it, or the hours go no further:
    now opens in the middle (decision 12 of 0.17), a first block a little below the top. Clay deck
    slides its row to the day asked for, so the day is measured where it lands: part way, the card
    coming in from beside the open one can have hours with no width yet, and whether it was still
    sliding depended on how soon the server answered."""
    view = window.planner.currentWidget()
    running = QAbstractAnimation.State.Running
    # The app's own motion runs on `motion.Clock`, which is not a Qt animation.
    wait_until(
        qapp,
        lambda: (
            not motion.busy()
            and all(item.state() != running for item in view.findChildren(QAbstractAnimation))
        ),
    )
    for _ in range(4):
        qapp.processEvents()
    scroll = hours(window)
    first, last = span_shown(scroll)
    if scroll.axis is Axis.ACROSS:
        # Mission control's lanes: now always shows when it is in what is shown, and 22:00 does too
        # when both fit, else now sits 30 to 60 minutes from the left edge. Another week, or another
        # day, opens with the evening's end at the right edge.
        if minute == NOW:
            assert first <= minute <= last, f"{where}: now is not on screen"
            assert last >= 22 * 60 or 30 <= minute - first <= 60, f"{where}: now is not near the left edge"
        else:
            assert last >= 22 * 60, f"{where}: the lanes do not reach 22:00"
        return
    assert first <= minute <= last, f"{where}: {minute // 60:02d}:{minute % 60:02d} is not on screen"
    bar = scroll.verticalScrollBar() if scroll.axis is Axis.DOWN else scroll.horizontalScrollBar()
    at_end = bar.value() == bar.maximum()
    half = (last - first) / 2 + 1
    assert minute - first <= half or at_end, f"{where}: opens {minute - first:.0f} minutes above it"


def test_todays_app_opens_an_empty_next_week_at_eight_once_there_is_homework(
    qapp: QApplication, window: NativeWindow
) -> None:
    """With homework on the account an empty week keeps its hours, and they open at 08:00 even though
    they grow as the page lays out."""
    session = window.session
    session.add_homework(
        {"id": "essay", "title": "History essay", "due": sunday_due(session.week_start), "estimate_min": 60,
         "revision": 0}
    )
    session.save()
    wait_until(qapp, lambda: not session.busy and not session.dirty)
    window._layout = sanitize_layout({"main": "classic", "day": "one"})
    window._apply_appearance()
    window._on_week()
    for name in ("viewWeek", "nextWeek"):
        window.findChild(QPushButton, name).click()
        wait_until(qapp, lambda: not session.busy)
    assert window.planner.currentWidget() is not window.empty_week
    opens_at(qapp, window, 8 * 60, "classic next Week, empty")


def test_every_design_opens_at_now_or_the_first_block_and_again_on_another_day_or_week(
    qapp: QApplication, window: NativeWindow
) -> None:
    session = window.session
    thursday = (date.fromisoformat(session.week_start) + timedelta(days=3)).isoformat()

    def press(name: str) -> None:
        window.findChild(QPushButton, name).click()
        wait_until(qapp, lambda: not session.busy)

    for design in DESIGNS:
        window._layout = sanitize_layout({"main": design, "day": "one"})
        window._apply_appearance()
        window._on_week()
        press("viewWeek")
        opens_at(qapp, window, NOW, f"{design} Week")
        press("nextWeek")
        if design == "classic":
            # #16: a later empty week keeps its hours, with the offers on a card over them.
            assert window.planner.currentWidget() is window.week_table
            assert window.empty_week.parentWidget() is window.week_table and window.empty_week.isVisible()
        else:
            opens_at(qapp, window, 8 * 60, f"{design} next Week, empty")
        press("prevWeek")
        opens_at(qapp, window, NOW, f"{design} Week again")
        press("viewDay")
        # As a click on Thursday's name does: the day this computer calls today may be another.
        session.open_day(thursday)
        wait_until(qapp, lambda: not session.busy)
        opens_at(qapp, window, NOW, f"{design} Day, today")
        press("nextWeek")
        press("nextWeek")
        assert date.fromisoformat(session.selected_day).weekday() == 5
        opens_at(qapp, window, 18 * 60, f"{design} Saturday, first block")
        press("prevWeek")
        opens_at(qapp, window, 8 * 60, f"{design} Friday, first block")
        press("prevWeek")
        opens_at(qapp, window, NOW, f"{design} Thursday again")


def test_todays_app_keeps_its_scroll_after_a_page_or_look_change(
    qapp: QApplication, window: NativeWindow
) -> None:
    """The 0.17.2 scroll decision replaces reopening at now after a page or look change."""
    from desktop.native.look import sanitize_look

    session = window.session
    window._layout = sanitize_layout({"main": "classic", "day": "one"})
    window._apply_appearance()
    window._on_week()

    def press(name: str) -> None:
        window.findChild(QPushButton, name).click()
        wait_until(qapp, lambda: not session.busy)

    def away() -> None:
        hours(window).verticalScrollBar().setValue(0)
        qapp.processEvents()

    def new_look() -> None:
        window._look = sanitize_look({"preset": "high-contrast"})
        window._apply_appearance()
        window._on_week()

    def settings() -> None:
        window._open_settings()
        window._close_settings(save=False)

    press("viewWeek")
    opens_at(qapp, window, NOW, "Week")
    away()
    session.save()
    wait_until(qapp, lambda: not session.busy)
    window._on_week()
    assert hours(window).verticalScrollBar().value() == 0, "a refresh moved the week the student scrolled"
    for how, act in (
        ("after Month", lambda: (press("viewMonth"), press("viewWeek"))),
        ("in a new look", new_look),
        ("back from Settings", settings),
    ):
        away()
        act()
        assert hours(window).verticalScrollBar().value() == 0, how


def test_after_plan_the_week_scrolls_to_the_first_homework_it_placed(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Decision 34 of 0.17: the blocks a plan placed landed off screen while the week stayed where it
    was, so what it did went unseen."""
    session = window.session
    window._layout = sanitize_layout({"main": "classic", "day": "one"})
    window._apply_appearance()
    window._on_week()
    window.findChild(QPushButton, "viewWeek").click()
    wait_until(qapp, lambda: not session.busy)
    session.add_homework(
        {"id": "essay", "title": "History essay", "due": sunday_due(session.week_start), "estimate_min": 60,
         "revision": 0}
    )
    session.save()
    wait_until(qapp, lambda: not session.busy and not session.dirty)
    hours(window).verticalScrollBar().setValue(0)
    qapp.processEvents()
    session.solve()
    wait_until(qapp, lambda: session.plan_first is not None and not session.busy)
    for _ in range(4):
        qapp.processEvents()
    placed = next(block for block in session.blocks if block.get("assignment_id") == "essay")
    assert placed.get("start"), "the plan gave the essay a time"
    start = int(placed["start"][:2]) * 60 + int(placed["start"][3:])
    first, last = span_shown(hours(window))
    assert first <= start <= last, f"{placed['start']} is not on screen ({first:.0f} to {last:.0f})"


@pytest.mark.parametrize("today, month", [
    ("2026-09-29", "2026-09"), ("2026-10-01", "2026-10"), ("2026-10-04", "2026-10"),
])
def test_month_and_mini_month_use_today_at_a_week_boundary(
    qapp: QApplication, window: NativeWindow, today: str, month: str
) -> None:
    session = window.session
    held = datetime.fromisoformat(today + "T10:20")
    session.now_ms = lambda: int(held.timestamp() * 1000)
    session.load_week("2026-09-28")
    wait_until(qapp, lambda: not session.busy)
    window._on_week()
    assert window.rail.month.title.text() == ("September 2026" if month.endswith("09") else "October 2026")
    window.findChild(QPushButton, "viewMonth").click()
    wait_until(qapp, lambda: session.month_data is not None)
    assert session.selected_month == month
    assert [cell.iso for cell in window.month_grid.canvas.cells if cell.today] == [today]
    window.findChild(QPushButton, "viewDay").click()
    wait_until(qapp, lambda: not session.busy)
    assert session.selected_day == today
    window.findChild(QPushButton, "viewWeek").click()
    wait_until(qapp, lambda: not session.busy)
    window.findChild(QPushButton, "viewMyDay").click()
    qapp.processEvents()
    expected = {"2026-09-29": "Tuesday 29 September", "2026-10-01": "Thursday 1 October",
                "2026-10-04": "Sunday 4 October"}
    assert window.week_title.full_text() == expected[today]


def test_month_keeps_a_picked_day_and_uses_thursday_for_a_week_without_today(
    qapp: QApplication, window: NativeWindow
) -> None:
    session = window.session
    held = datetime.fromisoformat("2026-09-29T10:20")
    session.now_ms = lambda: int(held.timestamp() * 1000)
    session.open_day("2026-09-30")
    wait_until(qapp, lambda: not session.busy)
    session.set_view("month")
    wait_until(qapp, lambda: session.month_data is not None)
    session.set_view("day")
    wait_until(qapp, lambda: not session.busy)
    assert session.selected_day == "2026-09-30"
    session.set_view("week")
    session.load_week("2026-10-26")
    wait_until(qapp, lambda: not session.busy)
    session.set_view("month")
    wait_until(qapp, lambda: session.month_data is not None)
    assert session.selected_month == "2026-10"


@pytest.mark.parametrize("design", DESIGNS)
def test_each_design_keeps_day_and_week_scroll_until_today_is_pressed(
    qapp: QApplication, window: NativeWindow, design: str
) -> None:
    session = window.session
    today = datetime.fromtimestamp(session.now_ms() / 1000).date().isoformat()
    window._layout = sanitize_layout({"main": design, "day": "one"})
    window._apply_appearance()
    window._on_week()

    def press(name: str) -> None:
        window.findChild(QPushButton, name).click()
        wait_until(qapp, lambda: not session.busy)
        for _ in range(4):
            qapp.processEvents()

    def away() -> None:
        scroll = hours(window)
        bar = scroll.verticalScrollBar() if scroll.axis is Axis.DOWN else scroll.horizontalScrollBar()
        bar.setValue(0)
        qapp.processEvents()

    def stays(where: str) -> None:
        scroll = hours(window)
        bar = scroll.verticalScrollBar() if scroll.axis is Axis.DOWN else scroll.horizontalScrollBar()
        assert bar.value() == 0, f"{design} {where} moved the hours away from midnight"

    press("viewWeek")
    away()
    session.open_day(today)
    wait_until(qapp, lambda: not session.busy)
    away()
    press("viewWeek")
    stays("Week after Day")
    press("viewDay")
    stays("Day after Week")
    session.open_day((date.fromisoformat(today) + timedelta(days=1)).isoformat())
    wait_until(qapp, lambda: not session.busy)
    session.open_day(today)
    wait_until(qapp, lambda: not session.busy)
    stays("Day after another day")
    press("viewWeek")
    press("viewMonth")
    press("viewWeek")
    stays("Week after Month")
    window._open_focus_screen()
    window._close_focus_screen()
    qapp.processEvents()
    stays("Week after Focus")
    press("todayWeek")
    opens_at(qapp, window, NOW, f"{design} Today")
    away()
    press("nextWeek")
    press("prevWeek")
    opens_at(qapp, window, NOW, f"{design} returning to this week")
    press("nextWeek")
    session.add_block({"id": "future-dinner", "title": "Dinner", "kind": "locked", "category": "meals",
                       "start": "18:00", "duration_min": 30, "days": [0]})
    wait_until(qapp, lambda: not session.busy)
    away()
    press("prevWeek")
    opens_at(qapp, window, NOW, f"{design} returning to this week after scrolling next week")
    press("nextWeek")
    stays("next week after Today reopened this week")


@pytest.mark.parametrize("design", DESIGNS)
def test_today_opens_this_week_at_now_and_leaves_the_week_it_was_pressed_from_where_it_was(
    qapp: QApplication, window: NativeWindow, design: str
) -> None:
    """Today opens this week at now. Next week, scrolled before Today was pressed, is where the student
    left it when they go forward to it again."""
    session = window.session
    window._layout = sanitize_layout({"main": design, "day": "one"})
    window._apply_appearance()
    window._on_week()

    def press(name: str) -> None:
        window.findChild(QPushButton, name).click()
        wait_until(qapp, lambda: not session.busy)
        for _ in range(4):
            qapp.processEvents()

    def bar() -> QScrollBar:
        scroll = hours(window)
        return scroll.verticalScrollBar() if scroll.axis is Axis.DOWN else scroll.horizontalScrollBar()

    press("viewWeek")
    press("nextWeek")
    # Today's app shows an empty week as one button, not hours.
    session.add_block({"id": "future-dinner", "title": "Dinner", "kind": "locked", "category": "meals",
                       "start": "18:00", "duration_min": 30, "days": [0]})
    session.save()
    wait_until(qapp, lambda: not session.busy and not session.dirty)
    for _ in range(4):
        qapp.processEvents()
    opened = bar().value()
    bar().setValue(opened + 40 if opened + 40 <= bar().maximum() else opened - 40)
    left = bar().value()
    assert abs(left - opened) == 40, f"{design}: next week's hours have no room to scroll"
    press("todayWeek")
    assert session.week_start == monday_of(date.today().isoformat())
    opens_at(qapp, window, NOW, f"{design} Today from next week")
    press("nextWeek")
    assert bar().value() == left, f"{design}: Today lost where next week was scrolled to"


@pytest.mark.parametrize("design", DESIGNS)
def test_each_design_keeps_the_week_where_it_was_through_a_new_text_size(
    qapp: QApplication, window: NativeWindow, design: str
) -> None:
    """Timeline and Bento make their hours again for a new text size. Those are where the student left
    the week, not at now, like every other look change."""
    from desktop.native.look import sanitize_look

    session = window.session
    window._layout = sanitize_layout({"main": design, "day": "one"})
    window._apply_appearance()
    window._on_week()
    window.findChild(QPushButton, "viewWeek").click()
    wait_until(qapp, lambda: not session.busy)
    for _ in range(4):
        qapp.processEvents()
    scroll = hours(window)
    bar = scroll.verticalScrollBar() if scroll.axis is Axis.DOWN else scroll.horizontalScrollBar()
    opened = bar.value()
    bar.setValue(opened + 40 if opened + 40 <= bar.maximum() else opened - 40)
    assert bar.value() != opened
    left = span_shown(scroll)[0]
    window._look = sanitize_look({"knobs": {"text": "large"}})
    window._apply_appearance()
    window._on_week()
    for _ in range(4):
        qapp.processEvents()
    top = span_shown(hours(window))[0]
    assert abs(top - left) <= 2, f"{design}: a new text size moved the week from {left:.0f} to {top:.0f}"


def test_my_day_title_names_the_day_chosen_on_its_strip(
    qapp: QApplication, window: NativeWindow
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from desktop.native.layouts.dial import DialFace

    window._layout = sanitize_layout({"main": "classic", "day": "dial"})
    window._enter_day()
    for _ in range(4):
        qapp.processEvents()
    face = next(face for face in window.planner.currentWidget().findChildren(DialFace)
                if face.mini and face.day == 4)
    QTest.mouseClick(face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, face.rect().center())
    qapp.processEvents()
    chosen = date.fromisoformat(window.session.week_start) + timedelta(days=4)
    assert window.week_title.full_text() == f"Friday {chosen.day} {chosen.strftime('%B')}"
