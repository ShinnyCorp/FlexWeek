"""Dragging in every design, not only Today's app: homework and blocks put down at a time, by one rule
and in the same words everywhere, through the window's one hand.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
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
    from PySide6.QtCore import QEvent, QPoint, QStandardPaths, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

    from desktop.native.calendar import sunday_due
    from desktop.native.hours.canvas import BlockPainter, HoursCanvas
    from desktop.native.hours.geometry import Span
    from desktop.native.hours.hand import Hand, Place
    from desktop.native.hours.zoom import HoursScroll, Scale
    from desktop.native.layouts.base import LayoutView, Scene, empty
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.layouts.views import VIEW_CLASSES
    from desktop.native.look import resolved_palette
    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer
    from desktop.tests.logic_support import past_setup

PASSWORD = "a-long-test-password"


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-drag-test"])


def wait_until(qapp: QApplication, predicate: Callable[[], bool], timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def settled(qapp: QApplication, window: NativeWindow) -> None:
    wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)
    for _ in range(5):
        qapp.processEvents()
    wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)


def look_file() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(root) / "flexweek-look.json"


@pytest.fixture()
def window(qapp: QApplication, tmp_path: Path) -> Iterator[NativeWindow]:
    """This week: School Monday to Friday 08:00-14:30, the History essay on Thursday 19:00-20:00, and
    a Math worksheet that still needs a time. The clock is held at Thursday 10:00."""
    look_file().unlink(missing_ok=True)
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    made = NativeWindow(server.origin)
    made.resize(1280, 860)
    made.show()
    try:
        made.username.setText("drag_student")
        made.password.setText(PASSWORD)
        made.findChild(QPushButton, "createAccount").click()
        wait_until(qapp, lambda: made._stack.currentWidget().objectName() == "recoveryPage")
        made.recovery_ack.setChecked(True)
        made.recovery_continue.click()
        past_setup(qapp, made)
        session = made.session
        thursday = datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=10)
        session.now_ms = lambda: int(thursday.timestamp() * 1000)
        session.add_block(
            {
                "id": "school",
                "title": "School",
                "kind": "locked",
                "category": "class",
                "start": "08:00",
                "duration_min": 390,
                "days": [0, 1, 2, 3, 4],
            }
        )
        due = sunday_due(session.week_start)
        for key, title in (("essay", "History essay"), ("math", "Math worksheet")):
            session.add_homework({"id": key, "title": title, "due": due, "estimate_min": 60, "revision": 0})
        session.save()
        settled(qapp, made)
        essay = session_of(made, "essay")
        session.add_block({**essay, "start": "19:00", "days": [3]})
        session.save()
        settled(qapp, made)
        yield made
    finally:
        with contextlib.suppress(RuntimeError):
            made.session.client.reset()
        made.hide()
        qapp.processEvents()
        server.stop()
        look_file().unlink(missing_ok=True)


def session_of(window: NativeWindow, assignment_id: str) -> dict:
    return next(block for block in window.session.blocks if block.get("assignment_id") == assignment_id)


def placed(window: NativeWindow, assignment_id: str) -> tuple[list[int], str | None, bool]:
    block = session_of(window, assignment_id)
    return list(block["days"]), block.get("start"), bool(block.get("pinned"))


def use(qapp: QApplication, window: NativeWindow, main: str, day: str = "one") -> LayoutView:
    window._layout = sanitize_layout({"main": main, "day": day})
    window._apply_appearance()
    window._on_week()
    for _ in range(10):
        qapp.processEvents()
    shown = window.planner.currentWidget()
    assert isinstance(shown, LayoutView)
    return shown


def shown_view(window: NativeWindow) -> LayoutView:
    view = window.planner.currentWidget()
    assert isinstance(view, LayoutView)
    return view


def named(view: QWidget, name: str) -> QWidget:
    found = view.findChild(QWidget, name)
    assert found is not None, name
    return found


def test_clay_week_day_name_opens_the_day_without_placing_homework(
    qapp: QApplication, window: NativeWindow
) -> None:
    view = use(qapp, window, "clay")
    pick = named(view, "clayDay5")
    QTest.mouseClick(pick, Qt.MouseButton.LeftButton)
    settled(qapp, window)
    assert window.session.planner_view == "day"
    assert (
        window.session.selected_day
        == (date.fromisoformat(window.session.week_start) + timedelta(days=5)).isoformat()
    )
    assert placed(window, "math")[1] is None


def test_a_drop_after_the_due_date_is_refused_and_changes_nothing(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Homework due on Friday, carried to Saturday: the hand is told why while it is held, and a
    placement that reaches the window anyway is refused in the same words and saves nothing."""
    window.session.add_homework(
        {
            "id": "poster",
            "title": "Science poster",
            "due": (date.fromisoformat(window.session.week_start) + timedelta(days=4)).isoformat() + "T23:59",
            "estimate_min": 60,
            "revision": 0,
        }
    )
    window.session.save()
    settled(qapp, window)
    poster_id = session_of(window, "poster")["id"]
    saturday = Span(5, 17 * 60, 18 * 60)
    said = window._hand_judge(poster_id, -1, saturday)
    assert (said.ok, said.words) == (False, "That ends after it is due, so it stayed where it was.")
    revision = window.session.revision
    window.hand.commit(Place(poster_id, saturday))
    settled(qapp, window)
    assert placed(window, "poster")[1] is None
    assert window.session.message == said.words
    assert window.session.revision == revision


def test_a_drop_while_a_save_is_under_way_lands_once_it_is_done(
    qapp: QApplication, window: NativeWindow
) -> None:
    use(qapp, window, "clay")
    window.session.add_block(
        {
            "id": "band",
            "title": "Band",
            "kind": "locked",
            "category": "extra",
            "start": "16:00",
            "duration_min": 60,
            "days": [1],
        }
    )
    window.session.save()
    assert window.session.busy
    math_id = session_of(window, "math")["id"]
    window.hand.commit(Place(math_id, Span(4, 17 * 60, 18 * 60)))
    settled(qapp, window)
    wait_until(qapp, lambda: placed(window, "math")[1] is not None)
    settled(qapp, window)
    assert placed(window, "math") == ([4], "17:00", True)
    assert not window.session.conflict
    assert any(block["id"] == "band" for block in window.session.blocks)


def test_retro_keeps_the_hours_where_they_were_scrolled_through_a_drop(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Retro lays its windows out again after a drop, and for a moment the hours had a little less to
    scroll. The bar was pulled back to that shorter end and left there, so the hours jumped by a few
    pixels, or 22 at another size, under the student's pointer."""
    window.resize(1280, 800)
    view = use(qapp, window, "retro")
    scroll = view.findChild(HoursScroll, "retroWeekScroll")
    assert scroll is not None
    wait_until(qapp, lambda: scroll.verticalScrollBar().maximum() > 0)
    for _ in range(10):
        qapp.processEvents()
    bar = scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    qapp.processEvents()
    scrolled = bar.value()
    window.hand.commit(Place(session_of(window, "math")["id"], Span(4, 17 * 60, 18 * 60)))
    settled(qapp, window)
    wait_until(qapp, lambda: placed(window, "math")[1] == "17:00")
    for _ in range(20):
        qapp.processEvents()
    assert (bar.value(), bar.maximum()) == (scrolled, scrolled)


def test_how_close_the_hours_are_is_kept_for_this_device(qapp: QApplication, window: NativeWindow) -> None:
    """A zoom chosen on Week is in the look file, and the next window opens the Week at it."""
    window.findChild(QPushButton, "viewWeek").click()
    qapp.processEvents()
    QTest.mouseClick(window.findChild(QPushButton, "weekZoomIn"), Qt.MouseButton.LeftButton)
    assert window.week_table.scroll.px == 64
    assert json.loads(look_file().read_text())["zoom"] == {"classic.week": 64}
    again = NativeWindow(window.session.client.origin)
    try:
        assert again.week_table.scroll.px == 64
        assert again.day_view.scroll.px == 96, "the Day was not zoomed, so it opens at its own level"
    finally:
        # Closed and deleted here, so nothing of this second window runs during a later test.
        with contextlib.suppress(RuntimeError):
            again.session.client.reset()
        again.close()
        again.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class ZoomingDesign(LayoutView):
    """The least a design with hours of its own does: hours that scroll and zoom, made anew on every
    render, as a design that rebuilds its page does."""

    layout_id = "mission"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        self._box = QVBoxLayout(self)
        self.scroll: HoursScroll | None = None

    def render(self, scene: Scene, week_changed: bool) -> None:
        empty(self._box)
        hours = HoursCanvas(self.hand, BlockPainter(resolved_palette("system", False, None)))
        hours.set_week(scene.week.occurrences, scene.today, scene.minute)
        scale = Scale("test.hours", (32, 48, 64, 96), 48)
        self.scroll = self.keep_zoom(HoursScroll(hours, scale, lambda px: 24 * px, name="test", gutter=48))
        self._box.addWidget(self.scroll)


def zooming_design(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> ZoomingDesign:
    """The test design, where a real design goes: chosen as the main view, in Mission's place."""
    monkeypatch.setitem(VIEW_CLASSES, "mission", ZoomingDesign)
    view = use(qapp, window, "mission")
    assert isinstance(view, ZoomingDesign)
    return view


def zoom_in(view: ZoomingDesign) -> None:
    assert view.scroll is not None
    QTest.mouseClick(view.scroll.buttons.into, Qt.MouseButton.LeftButton)


def redrawn(qapp: QApplication, window: NativeWindow) -> None:
    """A real change, saved: the design draws a new scene, as it does after any edit."""
    window.session.add_block(
        {
            "id": "club",
            "title": "Club",
            "kind": "locked",
            "category": "extra",
            "start": "18:00",
            "duration_min": 60,
            "days": [5],
        }
    )
    window.session.save()
    settled(qapp, window)


def test_a_designs_zoom_is_kept_under_its_own_key(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = zooming_design(qapp, window, monkeypatch)
    zoom_in(view)
    assert view.scroll is not None and view.scroll.px == 64
    assert json.loads(look_file().read_text())["zoom"] == {"test.hours": 64}


def test_hours_a_design_makes_again_open_at_the_level_just_chosen(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hours made on the next render open where the student left the last ones, not where the
    design first opened."""
    view = zooming_design(qapp, window, monkeypatch)
    zoom_in(view)
    zoomed = view.scroll
    redrawn(qapp, window)
    assert view.scroll is not zoomed, "the save drew new hours"
    assert view.scroll is not None and view.scroll.px == 64


def test_a_new_window_opens_a_designs_hours_at_the_remembered_level(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = zooming_design(qapp, window, monkeypatch)
    zoom_in(view)
    again = NativeWindow(window.session.client.origin)
    try:
        again.username.setText("drag_student")
        again.password.setText(PASSWORD)
        again.findChild(QPushButton, "signIn").click()
        wait_until(qapp, lambda: again._stack.currentWidget().objectName() == "weekPage")
        shown = use(qapp, again, "mission")
        assert isinstance(shown, ZoomingDesign) and shown.scroll is not None
        assert shown.scroll.px == 64
    finally:
        with contextlib.suppress(RuntimeError):
            again.session.client.reset()
        again.close()
        again.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_a_design_that_never_zooms_leaves_the_kept_levels_alone(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.findChild(QPushButton, "viewWeek").click()
    qapp.processEvents()
    QTest.mouseClick(window.findChild(QPushButton, "weekZoomIn"), Qt.MouseButton.LeftButton)
    view = zooming_design(qapp, window, monkeypatch)
    redrawn(qapp, window)
    assert view.scroll is not None and view.scroll.px == 48
    assert json.loads(look_file().read_text())["zoom"] == {"classic.week": 64}


def test_a_design_holds_its_renders_from_the_press_and_has_the_windows_hand(
    qapp: QApplication, window: NativeWindow
) -> None:
    """A design is given the window's one hand, and a new scene waits from the moment anything is
    pressed, not from the moment it starts to move."""
    from desktop.native.hours.hand import Gesture, Held

    view = use(qapp, window, "timeline")
    assert view.hand is window.hand
    window.hand.press(window, Held(Gesture.PLACE, "Essay", 60, "essay"), QPoint(20, 20))
    assert view._dragging, "a press, before any movement, holds the design's renders"
    window.hand.cancel()
    assert not view._dragging


def test_month_stays_where_the_student_scrolled_it_through_a_refresh(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Month opens on the week the student is in, once. It used to scroll back there every time
    anything refreshed, such as a save, undoing the student's own scrolling."""
    window.resize(900, 560)
    window.findChild(QPushButton, "viewMonth").click()
    wait_until(qapp, lambda: window.session.month_data is not None and not window.session.busy)
    for _ in range(10):
        qapp.processEvents()
    bar = window.month_grid.scroll.verticalScrollBar()
    assert bar.maximum() > 0, "the month is taller than the window, so it scrolls"
    bar.setValue(0 if bar.value() else bar.maximum())
    chosen = bar.value()
    window._on_week()
    for _ in range(10):
        qapp.processEvents()
    assert bar.value() == chosen


def test_a_chip_let_go_after_a_save_failed_is_refused_not_kept_for_later(
    qapp: QApplication, window: NativeWindow
) -> None:
    """A drop after a save that did not go through used to be parked in silence, overwritten by the
    next drop, and made much later when some other save finished."""
    from desktop.native.hours.hand import MoveDate

    session = window.session
    settled(qapp, window)
    essay = session_of(window, "essay")
    thursday = date.fromisoformat(session.week_start) + timedelta(days=3)
    saturday = thursday + timedelta(days=2)
    session.pending_save = {"weeks": [], "assignments": [], "operation_id": "failed-before"}
    try:
        window._apply_change(MoveDate(essay["id"], thursday.isoformat(), saturday.isoformat()))
        assert window._date_waiting is None, "kept to be made later"
        assert "not saved yet" in session.message
    finally:
        session.pending_save = None
    settled(qapp, window)
    assert placed(window, "essay")[:2] == ([3], "19:00")


def test_a_designs_month_stays_where_the_student_scrolled_it_through_a_refresh(
    qapp: QApplication, window: NativeWindow
) -> None:
    window.resize(900, 560)
    view = use(qapp, window, "timeline")
    window.findChild(QPushButton, "viewMonth").click()
    wait_until(qapp, lambda: window.session.month_data is not None and not window.session.busy)
    for _ in range(10):
        qapp.processEvents()
    board = view.findChild(QWidget, "layoutMonthBoard")
    assert board is not None and board.isVisible()
    bar = board.scroll.verticalScrollBar()
    assert bar.maximum() > 0, "the month is taller than the window, so it scrolls"
    bar.setValue(0 if bar.value() else bar.maximum())
    chosen = bar.value()
    # A real change, saved: the design draws a new scene, as it does after any edit.
    window.session.add_block(
        {
            "id": "club",
            "title": "Club",
            "kind": "locked",
            "category": "extra",
            "start": "18:00",
            "duration_min": 60,
            "days": [5],
        }
    )
    window.session.save()
    settled(qapp, window)
    wait_until(qapp, lambda: window.session.month_data is not None and not window.session.busy)
    for _ in range(10):
        qapp.processEvents()
    assert board.canvas.index_of(window.session.selected_day) is not None
    assert bar.value() == chosen


def open_month_of(qapp: QApplication, window: NativeWindow, iso: str) -> None:
    window.session.open_month(iso[:7])
    wait_until(qapp, lambda: window.session.month_data is not None and not window.session.busy)
    for _ in range(10):
        qapp.processEvents()


@pytest.mark.parametrize("design", ["classic", "timeline"])
def test_month_draws_a_week_left_unsaved_as_the_student_has_it(
    qapp: QApplication, window: NativeWindow, design: str
) -> None:
    """The essay moved to 20:15 and its week left without saving. Month showed it at 19:00, where the
    server has it, and a chip there could be picked up and then refused."""
    session = window.session
    essay = session_of(window, "essay")
    first = date.fromisoformat(session.week_start)
    thursday = (first + timedelta(days=3)).isoformat()
    assert session.apply_times(essay["id"], 20 * 60 + 15, 21 * 60 + 15, 3) is True
    session.load_week((first + timedelta(days=7)).isoformat())
    wait_until(qapp, lambda: not session.busy and session.week_start != first.isoformat())
    assert not session.dirty, "the week now open has no changes; the one left behind has"
    if design == "classic":
        canvas = window.month_grid.canvas
    else:
        view = use(qapp, window, design)
    open_month_of(qapp, window, thursday)
    if design != "classic":
        board = view.findChild(QWidget, "layoutMonthBoard")
        assert board is not None and board.isVisible()
        canvas = board.canvas
    assert canvas.chip_words(essay["id"], thursday) == "8:15 PM History essay"
    window.session.preferences = {**(window.session.preferences or {}), "clock_24h": True}
    window._sync_chrome()
    for _ in range(5):
        qapp.processEvents()
    assert canvas.chip_words(essay["id"], thursday) == "20:15 History essay"


def test_a_chip_from_a_week_that_is_not_open_is_judged_by_its_own_time_and_homework(
    qapp: QApplication, window: NativeWindow
) -> None:
    """The essay is due on Sunday. With another week open, Month let its chip onto the Monday after,
    because the rule had no time or homework to judge it by."""
    session = window.session
    essay = session_of(window, "essay")
    first = date.fromisoformat(session.week_start)
    thursday = (first + timedelta(days=3)).isoformat()
    session.load_week((first + timedelta(days=7)).isoformat())
    wait_until(qapp, lambda: not session.busy and session.week_start != first.isoformat())
    open_month_of(qapp, window, thursday)
    late = window._date_judge(essay["id"], thursday, (first + timedelta(days=7)).isoformat())
    fine = window._date_judge(essay["id"], thursday, (first + timedelta(days=5)).isoformat())
    assert (late.ok, late.words) == (False, "That ends after it is due, so it stayed where it was.")
    assert (fine.ok, fine.words) == (True, "")
