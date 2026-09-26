"""The focus timer as the whole window: opened by Start focus, Quick focus or F, closed by Esc."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from desktop.native.calendar import sunday_due
from desktop.native.focus import format_countdown, phase_duration_ms, remaining_ms
from desktop.native.focus_screen import READY
from desktop.native.window import NativeWindow
from desktop.server import LocalServer
from desktop.tests.logic_support import past_setup

PASSWORD = "a-long-test-password"
LEFT = Qt.MouseButton.LeftButton


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-focus-screen-test"])


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


def settled(qapp: QApplication, window: NativeWindow) -> None:
    session = window.session
    wait_until(
        qapp, lambda: not session.busy and not session.dirty and not any(session.client._replies.values())
    )


@pytest.fixture()
def window(qapp: QApplication, tmp_path: Path) -> Iterator[NativeWindow]:
    """Today's app's Week with the History essay on Thursday 19:00 and the clock held at Thursday
    19:10, so the essay is on now."""
    look_file().unlink(missing_ok=True)
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    made = NativeWindow(server.origin)
    made.resize(1280, 860)
    made.show()
    try:
        made.username.setText("focus_screen_student")
        made.password.setText(PASSWORD)
        made.findChild(QPushButton, "createAccount").click()
        wait_until(qapp, lambda: made._stack.currentWidget().objectName() == "recoveryPage")
        made.recovery_ack.setChecked(True)
        made.recovery_continue.click()
        past_setup(qapp, made)
        session = made.session
        thursday = datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=19, minutes=10)
        session.now_ms = lambda: int(thursday.timestamp() * 1000)
        session.add_homework({"id": "essay", "title": "History essay", "due": sunday_due(session.week_start),
                              "estimate_min": 60, "revision": 0})
        session.save()
        settled(qapp, made)
        essay = next(block for block in session.blocks if block.get("assignment_id") == "essay")
        session.add_block({**essay, "start": "19:00", "days": [3], "pinned": True})
        session.save()
        settled(qapp, made)
        made.findChild(QPushButton, "viewWeek").click()
        settled(qapp, made)
        yield made
    finally:
        with contextlib.suppress(RuntimeError):
            made.session.client.reset()
        made.hide()
        qapp.processEvents()
        server.stop()
        look_file().unlink(missing_ok=True)


def on_screen(window: NativeWindow) -> str:
    return window._stack.currentWidget().objectName()


def visible_buttons(widget) -> list[str]:
    return [button.text() for button in widget.findChildren(QPushButton) if button.isVisible()]


def test_quick_focus_fills_the_window_and_esc_comes_back(qapp: QApplication, window: NativeWindow) -> None:
    window.findChild(QPushButton, "quickFocusAction").click()
    assert window.session.focus is not None
    assert on_screen(window) == "focusPage"
    screen = window.focus_screen
    assert screen.isVisible() and window.findChild(QPushButton, "solveButton").isVisible() is False
    state = window.session.focus
    assert screen.time.text() == format_countdown(remaining_ms(state, window.session.now_ms()))
    assert screen.phase.text() == "Focus"
    assert screen.task.text() == "Quick focus"
    screen.time.ensurePolished()
    assert screen.time.font().pointSize() == 96 and screen.time.font().bold()
    assert visible_buttons(screen) == ["Back", "Pause", "Skip", "Finish"]

    QTest.keyClick(screen, Qt.Key.Key_Escape)
    assert on_screen(window) == "weekPage"
    assert window.session.focus is not None, "going back leaves the timer running"
    panel = window.focus_panel
    assert panel.time.isVisible() and panel.task.text() == "Quick focus"
    assert visible_buttons(panel) == ["Focus screen"], "the strip keeps its line and one way back"
    QTest.mouseClick(panel.screen, LEFT)
    assert on_screen(window) == "focusPage"
    QTest.mouseClick(screen.back, LEFT)
    assert on_screen(window) == "weekPage"


def test_pause_skip_and_finish_act_on_the_one_timer(qapp: QApplication, window: NativeWindow) -> None:
    window.findChild(QPushButton, "quickFocusAction").click()
    screen = window.focus_screen
    QTest.mouseClick(screen.pause, LEFT)
    assert window.session.focus["running"] is False
    assert screen.pause.text() == "Resume"
    assert screen.phase.text() == "Focus · Paused"
    assert window.focus_panel.phase.text() == "Focus session", "the strip shows the same timer"
    QTest.mouseClick(screen.pause, LEFT)
    assert window.session.focus["running"] is True
    QTest.mouseClick(screen.skip, LEFT)
    assert window.session.focus["phase"] == "break"
    assert screen.phase.text() == "Break"
    assert screen.time.text() == format_countdown(phase_duration_ms("break", window.session.preferences))
    QTest.mouseClick(screen.stop, LEFT)
    assert window.session.focus is None
    assert on_screen(window) == "weekPage"


def test_start_focus_from_the_strip_opens_it_on_that_homework(
    qapp: QApplication, window: NativeWindow
) -> None:
    tasks = window.week_table.side.tasks
    assert tasks.count() == 1
    tasks.setCurrentRow(0)
    QTest.keyClick(tasks, Qt.Key.Key_Return)
    wait_until(qapp, lambda: window.session.focus is not None)
    assert on_screen(window) == "focusPage"
    assert window.focus_screen.task.text() == "History essay"


def test_start_focus_on_my_day_opens_it(qapp: QApplication, window: NativeWindow) -> None:
    window.findChild(QPushButton, "viewMyDay").click()
    window.findChild(QPushButton, "oneFocus").click()
    wait_until(qapp, lambda: window.session.focus is not None)
    assert on_screen(window) == "focusPage"
    assert window.focus_screen.task.text() == "History essay"
    QTest.keyClick(window.focus_screen, Qt.Key.Key_Escape)
    assert on_screen(window) == "weekPage"
    assert window._day_mode is True, "Esc leaves the focus screen, not My day"


def test_f_opens_it_ready_to_start_unless_typing(qapp: QApplication, window: NativeWindow) -> None:
    field = QLineEdit(window.findChild(QPushButton, "solveButton").parentWidget())
    field.show()
    field.setFocus()
    QTest.keyClick(field, Qt.Key.Key_F)
    assert on_screen(window) == "weekPage", "an F typed into a box is a letter"
    field.deleteLater()
    window.week_table.hours.setFocus()

    QTest.keyClick(window.week_table.hours, Qt.Key.Key_F)
    assert on_screen(window) == "focusPage"
    screen = window.focus_screen
    assert window.session.focus is None, "F shows the timer; it does not start one"
    assert screen.phase.text() == READY
    assert screen.time.text() == format_countdown(phase_duration_ms("work", window.session.preferences))
    assert visible_buttons(screen) == ["Back", "Start"]
    QTest.mouseClick(screen.start, LEFT)
    assert window.session.focus is not None and window.session.focus["title"] == "Quick focus"
    assert visible_buttons(screen) == ["Back", "Pause", "Skip", "Finish"]


def test_a_week_change_does_not_take_the_screen_away(qapp: QApplication, window: NativeWindow) -> None:
    window.findChild(QPushButton, "quickFocusAction").click()
    window.session.week_changed.emit()
    assert on_screen(window) == "focusPage"


def test_a_finished_session_offers_finished_and_a_break(qapp: QApplication, window: NativeWindow) -> None:
    session = window.session
    essay = next(block for block in session.blocks if block.get("assignment_id") == "essay")
    window._start_focus(essay["id"], 3)
    assert on_screen(window) == "focusPage"
    later = session.now_ms() + phase_duration_ms("work", session.preferences) + 1000
    session.now_ms = lambda: later
    session.tick_focus()
    settled(qapp, window)
    screen = window.focus_screen
    assert session.focus["phase"] == "ended"
    assert screen.phase.text() == "Session finished"
    assert visible_buttons(screen) == ["Back", "Finished", "Take a break"]
    QTest.mouseClick(screen.finished, LEFT)
    settled(qapp, window)
    assert session.assignments["essay"]["completed"] is True
    essay = next(block for block in session.blocks if block.get("assignment_id") == "essay")
    assert (essay["completed"], essay["completed_day"], essay["start"]) == (True, 3, "19:00")
    assert session.focus is None
    assert on_screen(window) == "weekPage"
