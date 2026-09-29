"""Where every design's Day and Week open: at now on today and this week, otherwise at the first block
of the day or the week, otherwise at 08:00. On first show, and again each time the student goes to
another day or week; the same day or week keeps wherever the student scrolled it."""

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
    from PySide6.QtCore import QPoint, QPointF, QStandardPaths
    from PySide6.QtWidgets import QApplication, QPushButton

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


@pytest.fixture()
def window(qapp: QApplication, tmp_path: Path) -> Iterator[NativeWindow]:
    """Signed in with the clock held at Thursday 15:40 from before the week is first shown: school
    on weekdays from 08:00, dinner every day at 18:00, and nothing next week."""
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
    now opens in the middle (decision 12 of 0.17), a first block a little below the top."""
    for _ in range(4):
        qapp.processEvents()
    scroll = hours(window)
    first, last = span_shown(scroll)
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
            # With no homework yet, Today's app shows an empty week one button, not hours.
            assert window.planner.currentWidget() is window.empty_week
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


def test_todays_app_opens_at_now_every_time_it_is_shown_and_not_on_a_save(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Decision 12 of 0.17. Scrolled away, Week opened on the night again after Month, a new look or
    Settings. Each of those opens it at now; a save while it shows leaves it where it is."""
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
        opens_at(qapp, window, NOW, f"Week {how}")


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
