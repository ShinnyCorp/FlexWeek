"""After the week changes under the keyboard, it goes back to the week: not to the previous-week arrow,
where a stray Space or Enter turns the page."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from desktop.native.calendar import sunday_due
from desktop.native.widgets import BlockDialog
from desktop.native.window import LastInput, NativeWindow
from desktop.server import LocalServer
from desktop.tests.grid_support import (  # noqa: F401
    NONE,
    WEDNESDAY,
    add_piano,
    grid,
    hold_clock,
    key,
    tab_to_grid,
    window,
)
from desktop.tests.window_support import (  # noqa: F401
    free,
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
)
from desktop.tests.window_support import window as signed_in  # noqa: F401


def add_homework(qapp: QApplication, window: NativeWindow) -> None:
    session = window.session
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
    settled(qapp, window)
    hold_clock(window, WEDNESDAY, 14 * 60 + 7)


def plan(qapp: QApplication, window: NativeWindow, with_keys: bool) -> None:
    solve = window.findChild(QPushButton, "solveButton")
    if with_keys:
        solve.setFocus(Qt.FocusReason.TabFocusReason)
        key(window, Qt.Key.Key_Space)
    else:
        QTest.mouseClick(solve, Qt.MouseButton.LeftButton)
    wait_until(qapp, lambda: window.toast.isVisible() and window.toast.button.isVisible())
    settled(qapp, window)


def stray(window: NativeWindow) -> bool:
    """Whether the keyboard sits on a button that turns the page."""
    return window.focusWidget() in (window.prev_nav, window.next_nav)


def test_after_plan_by_keyboard_the_keyboard_is_on_the_block_it_placed_with_its_ring(
    qapp: QApplication, window: NativeWindow
) -> None:
    add_homework(qapp, window)
    hours = grid(window)
    tab_to_grid(window)
    for _ in range(2):
        key(window, Qt.Key.Key_Left)
    before = hours.focus_slot()
    plan(qapp, window, with_keys=True)
    placed = {item["id"] for item in window.session.trace["placed"]}
    assert placed, "the plan placed nothing, so the test says nothing"
    assert window.focusWidget() is hours
    block = hours.focus_block()
    assert block is not None and block[0] in placed, f"the keyboard stayed at {before}"
    assert hours.ring_shown


def test_after_plan_by_click_the_grid_has_the_keyboard_and_no_ring(
    qapp: QApplication, window: NativeWindow
) -> None:
    add_homework(qapp, window)
    plan(qapp, window, with_keys=False)
    assert window.focusWidget() is grid(window)
    assert not grid(window).ring_shown


def test_the_toasts_undo_leaves_the_keyboard_on_the_week_not_on_last_week(
    qapp: QApplication, window: NativeWindow
) -> None:
    add_homework(qapp, window)
    plan(qapp, window, with_keys=False)
    window.toast.button.setFocus(Qt.FocusReason.TabFocusReason)
    QTest.mouseClick(window.toast.button, Qt.MouseButton.LeftButton)
    settled(qapp, window)
    assert not stray(window)
    assert window.focusWidget() is grid(window)


def test_redo_leaves_the_keyboard_on_the_week(qapp: QApplication, window: NativeWindow) -> None:
    add_homework(qapp, window)
    plan(qapp, window, with_keys=False)
    key(window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    settled(qapp, window)
    redo = window.findChild(QPushButton, "redoButton")
    wait_until(qapp, redo.isEnabled)
    redo.setFocus(Qt.FocusReason.TabFocusReason)
    key(window, Qt.Key.Key_Space)
    settled(qapp, window)
    assert not stray(window)
    assert window.focusWidget() is grid(window)


def test_leaving_focus_with_escape_puts_the_keyboard_on_the_week(
    qapp: QApplication, window: NativeWindow
) -> None:
    window.prev_nav.setFocus(Qt.FocusReason.TabFocusReason)
    window._open_focus_screen()
    qapp.processEvents()
    key(window, Qt.Key.Key_Escape)
    assert window._stack.currentWidget() is window._week_page
    assert not stray(window)
    assert window.focusWidget() is grid(window)


def test_a_dropped_block_keeps_the_keyboard_on_the_week(qapp: QApplication, window: NativeWindow) -> None:
    add_piano(qapp, window)
    hours = grid(window)
    hours.reveal(WEDNESDAY, 14 * 60, 18 * 60)
    qapp.processEvents()
    start, end = hours.point_for(WEDNESDAY, 15 * 60 + 30), hours.point_for(WEDNESDAY, 17 * 60 + 30)

    def send(kind: QEvent.Type, at: QPoint, held: bool) -> None:
        buttons = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
        event = QMouseEvent(
            kind, QPointF(hours.mapFromGlobal(at)), QPointF(at), Qt.MouseButton.LeftButton, buttons, NONE
        )
        QApplication.sendEvent(hours, event)

    send(QEvent.Type.MouseButtonPress, start, True)
    for step in range(1, 9):
        send(QEvent.Type.MouseMove, start + (end - start) * step / 8, True)
    send(QEvent.Type.MouseButtonRelease, end, False)
    wait_until(qapp, lambda: not window.session.busy)
    settled(qapp, window)
    moved = next(block for block in window.session.blocks if block["id"] == "piano")
    assert moved["start"] != "15:00", "the block was not moved, so the test says nothing"
    assert not stray(window)
    assert window.focusWidget() is hours
    assert hours.focus_block() == ("piano", WEDNESDAY)
    assert not hours.ring_shown, "a drop is the pointer's; no ring"


def test_a_sheet_that_closes_leaves_the_keyboard_on_the_week_not_on_the_button_that_opened_it(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(BlockDialog, "exec", lambda dialog: QDialog.DialogCode.Rejected)
    add = window.findChild(QPushButton, "addButton")
    add.setFocus(Qt.FocusReason.TabFocusReason)
    key(window, Qt.Key.Key_Shift)
    window._add_fixed()
    assert window.focusWidget() is grid(window)
    assert grid(window).ring_shown


def test_every_window_reads_the_one_record_of_the_last_press(
    qapp: QApplication, window: NativeWindow, server: LocalServer
) -> None:
    """A filter for each window made every event wait on all of them, which slowed whole test runs and
    left animations unfinished when a test looked."""
    key(window, Qt.Key.Key_Shift)
    assert window._last_input.keyboard
    second = NativeWindow(server.origin)
    try:
        assert second._last_input is window._last_input is LastInput.shared()
        assert not second._last_input.keyboard, "a new window starts with the pointer as the last input"
    finally:
        free(second)
