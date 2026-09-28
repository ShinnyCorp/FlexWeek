"""My day's two screens move blocks through the window's one hand, as every design does.

One thing's day bar is a track across the day and the thing itself can be carried onto it; Day
dial's face is a ring of the day's minutes. Each test presses, moves and lets go with Qt's own mouse
events, and reads back what the hand reported and what the week saved.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import re
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QPoint, QStandardPaths, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

    from desktop.native.calendar import sunday_due
    from desktop.native.hours.geometry import Span
    from desktop.native.hours.hand import Move, Place
    from desktop.native.layouts.base import LayoutView
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer
    from desktop.tests.logic_support import past_setup, wait_until

PASSWORD = "a-long-test-password"
LAYOUTS = Path(__file__).resolve().parents[1] / "native" / "layouts"
REFUSED = "That ends after it is due, so it stayed where it was."
THURSDAY = 3


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-my-day-test"])


def settled(qapp: QApplication, window: NativeWindow) -> None:
    wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)
    for _ in range(5):
        qapp.processEvents()
    wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)


@pytest.fixture()
def window(qapp: QApplication, tmp_path: Path) -> Iterator[NativeWindow]:
    """School Monday to Friday 08:00-14:30 and the History essay on Thursday 19:00-20:00, due on
    Sunday. The clock is held at Thursday 15:00, so the essay is what comes next. The window fits
    the offscreen screen, where the hand can find what lies under the pointer."""
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    made = NativeWindow(server.origin)
    made.resize(800, 780)
    made.move(0, 0)
    made.show()
    try:
        made.username.setText("my_day_student")
        made.password.setText(PASSWORD)
        made.findChild(QPushButton, "createAccount").click()
        wait_until(qapp, lambda: made._stack.currentWidget().objectName() == "recoveryPage")
        made.recovery_ack.setChecked(True)
        made.recovery_continue.click()
        past_setup(qapp, made)
        session = made.session
        thursday = datetime.fromisoformat(session.week_start) + timedelta(days=THURSDAY, hours=15)
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
        session.add_homework(
            {
                "id": "essay",
                "title": "History essay",
                "due": sunday_due(session.week_start),
                "estimate_min": 60,
                "revision": 0,
            }
        )
        session.save()
        settled(qapp, made)
        session.add_block({**essay_block(made), "start": "19:00", "days": [THURSDAY]})
        session.save()
        settled(qapp, made)
        yield made
    finally:
        with contextlib.suppress(RuntimeError):
            made.session.client.reset()
        made.hide()
        qapp.processEvents()
        server.stop()


def essay_block(window: NativeWindow) -> dict:
    return next(block for block in window.session.blocks if block.get("assignment_id") == "essay")


def essay_at(window: NativeWindow) -> tuple[list[int], str | None]:
    block = essay_block(window)
    return list(block["days"]), block.get("start")


def due_thursday_at_eight(qapp: QApplication, window: NativeWindow) -> None:
    session = window.session
    thursday = date.fromisoformat(session.week_start) + timedelta(days=THURSDAY)
    session.assignments["essay"] = {**session.assignments["essay"], "due": f"{thursday}T20:00"}
    session.dirty_assignments.add("essay")
    session.dirty = True
    session.save()
    settled(qapp, window)


def my_day(qapp: QApplication, window: NativeWindow, screen: str) -> tuple[LayoutView, QWidget]:
    """Open My day on `screen` from the top bar, and find the one surface it moves blocks on."""
    window._layout = sanitize_layout({"main": "classic", "day": screen})
    window.findChild(QPushButton, "viewMyDay").click()
    for _ in range(10):
        qapp.processEvents()
    view = window.planner.currentWidget()
    assert isinstance(view, LayoutView) and view.layout_id == screen
    surfaces = view.hours_surfaces()
    assert [surface.objectName() for surface in surfaces] == [
        {"one": "oneDayBar", "dial": "dialFace"}[screen]
    ]
    return view, surfaces[0]


def along(surface: QWidget, first: int, last: int) -> list[QPoint]:
    """Points on the surface's own track from one minute to another, a quarter hour apart: straight
    along a bar, round a dial."""
    step = 15 if last >= first else -15
    return [surface.point_for(THURSDAY, minute) for minute in [*range(first, last, step), last]]


def carry(qapp: QApplication, source: QWidget, path: list[QPoint], before_release=None) -> None:
    """Press at the first point, move through the rest, and let go at the last. Every event goes to
    the widget pressed, as Qt's implicit grab sends them."""
    QTest.mousePress(
        source, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, source.mapFromGlobal(path[0])
    )
    for point in path[1:]:
        QTest.mouseMove(source, source.mapFromGlobal(point))
    qapp.processEvents()
    if before_release is not None:
        before_release()
    QTest.mouseRelease(
        source, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, source.mapFromGlobal(path[-1])
    )
    qapp.processEvents()


def reported(window: NativeWindow) -> list[object]:
    said: list[object] = []
    window.hand.committed.connect(said.append)
    return said


@pytest.mark.parametrize("screen", ["one", "dial"])
def test_a_block_moved_along_my_days_track_lands_at_the_snapped_time(
    qapp: QApplication, window: NativeWindow, screen: str
) -> None:
    """Held by its middle at 19:30 and let go at 21:00, the hour-long essay starts at 20:30."""
    _view, surface = my_day(qapp, window, screen)
    said = reported(window)
    essay = essay_block(window)["id"]
    carry(qapp, surface, along(surface, 19 * 60 + 30, 21 * 60))
    assert said == [Move(essay, THURSDAY, Span(THURSDAY, 20 * 60 + 30, 21 * 60 + 30))]
    settled(qapp, window)
    assert essay_at(window) == ([THURSDAY], "20:30")
    assert essay_block(window).get("pinned") is True


@pytest.mark.parametrize("screen", ["one", "dial"])
def test_a_move_past_the_due_time_is_refused_in_the_shared_words_and_moves_nothing(
    qapp: QApplication, window: NativeWindow, screen: str
) -> None:
    due_thursday_at_eight(qapp, window)
    _view, surface = my_day(qapp, window, screen)
    said = reported(window)
    revision = window.session.revision
    words: list[str] = []
    carry(qapp, surface, along(surface, 19 * 60 + 30, 21 * 60), lambda: words.append(surface.held_words()))
    assert words == [REFUSED], "said while it is held, on the screen"
    assert said == []
    assert window.session.message == REFUSED
    settled(qapp, window)
    assert essay_at(window) == ([THURSDAY], "19:00")
    assert window.session.revision == revision


@pytest.mark.parametrize("screen", ["one", "dial"])
def test_a_tap_on_a_block_opens_it(
    qapp: QApplication, window: NativeWindow, screen: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(window, "_edit_homework", opened.append)
    _view, surface = my_day(qapp, window, screen)
    said = reported(window)
    at = surface.point_for(THURSDAY, 19 * 60 + 30)
    QTest.mouseClick(
        surface, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, surface.mapFromGlobal(at)
    )
    qapp.processEvents()
    assert opened == ["essay"]
    assert said == []


@pytest.mark.parametrize("screen", ["one", "dial"])
def test_escape_puts_a_held_block_back(qapp: QApplication, window: NativeWindow, screen: str) -> None:
    _view, surface = my_day(qapp, window, screen)
    said = reported(window)
    revision = window.session.revision
    held: list[bool] = []

    def escape() -> None:
        held.append(window.hand.preview is not None)
        QTest.keyClick(surface, Qt.Key.Key_Escape)
        held.append(window.hand.busy)

    carry(qapp, surface, along(surface, 19 * 60 + 30, 21 * 60), escape)
    assert held == [True, False], "held over the track, then let go by Escape"
    assert said == []
    settled(qapp, window)
    assert essay_at(window) == ([THURSDAY], "19:00")
    assert window.session.revision == revision


def test_the_thing_itself_carried_onto_the_day_bar_goes_at_that_time(
    qapp: QApplication, window: NativeWindow
) -> None:
    """At 15:00 the thing is the essay, up next. Its big title is picked up like a tray chip and let
    go on the bar at 20:30, which is where it starts."""
    view, bar = my_day(qapp, window, "one")
    said = reported(window)
    title = view.findChild(QLabel, "oneTitle")
    assert title.text() == "History essay"
    start = title.mapToGlobal(title.rect().center())
    end = bar.point_for(THURSDAY, 20 * 60 + 30)
    carry(qapp, title, [start + (end - start) * step / 8 for step in range(9)])
    essay = essay_block(window)["id"]
    assert said == [Move(essay, THURSDAY, Span(THURSDAY, 20 * 60 + 30, 21 * 60 + 30))]
    settled(qapp, window)
    assert essay_at(window) == ([THURSDAY], "20:30")


def test_homework_due_today_with_no_time_is_given_one_by_carrying_its_title_onto_the_bar(
    qapp: QApplication, window: NativeWindow
) -> None:
    """At 20:30 nothing else is planned today, so the thing is the Math worksheet, due today and
    still without a time. Let go on the bar at 21:00, it is placed there."""
    session = window.session
    thursday = datetime.fromisoformat(session.week_start) + timedelta(days=THURSDAY, hours=20, minutes=30)
    session.now_ms = lambda: int(thursday.timestamp() * 1000)
    due = f"{thursday.date().isoformat()}T23:59"
    session.add_homework(
        {"id": "math", "title": "Math worksheet", "due": due, "estimate_min": 60, "revision": 0}
    )
    session.save()
    settled(qapp, window)
    view, bar = my_day(qapp, window, "one")
    said = reported(window)
    title = view.findChild(QLabel, "oneTitle")
    assert title.text() == "Math worksheet"
    start = title.mapToGlobal(title.rect().center())
    end = bar.point_for(THURSDAY, 21 * 60)
    carry(qapp, title, [start + (end - start) * step / 8 for step in range(9)])
    math = next(block for block in session.blocks if block.get("assignment_id") == "math")
    assert said == [Place(math["id"], Span(THURSDAY, 21 * 60, 22 * 60))]
    settled(qapp, window)
    math = next(block for block in session.blocks if block.get("assignment_id") == "math")
    assert (math["days"], math.get("start")) == ([THURSDAY], "21:00")


def test_the_dial_picks_nothing_up_in_its_gap_outside_its_ring_or_in_its_middle(
    qapp: QApplication, window: NativeWindow
) -> None:
    _view, face = my_day(qapp, window, "dial")
    said = reported(window)
    track = face.track_for(THURSDAY)
    centre = face.mapToGlobal(track.centre.toPoint())
    middle = round((track.inner + track.outer) / 2)
    gap, beyond = centre + QPoint(0, middle), centre + QPoint(0, -round(track.outer) - 12)
    essay_middle = face.point_for(THURSDAY, 19 * 60 + 30)
    for pressed in (gap, beyond, centre):
        assert face.track_at(face.mapFromGlobal(pressed)) is None
        QTest.mousePress(
            face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, face.mapFromGlobal(pressed)
        )
        assert not window.hand.busy, "nothing held"
        QTest.mouseMove(face, face.mapFromGlobal(essay_middle))
        QTest.mouseRelease(
            face, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, face.mapFromGlobal(essay_middle)
        )
        qapp.processEvents()
    assert said == []
    assert essay_at(window) == ([THURSDAY], "19:00")


def test_my_day_has_no_drag_rules_of_its_own() -> None:
    """Both screens move blocks only through the hand: no system drag and drop, no threshold or
    snap of their own."""
    for name in ("one_thing.py", "dial.py"):
        text = (LAYOUTS / name).read_text()
        assert not re.search(r"\bQDrag\b|\bQMimeData\b|startDragDistance|\bsnap\(", text), (
            name
        )
