"""Regression (item 3): Plan's Undo toast stays until it is used.

A second Plan with nothing new used to replace "Placed 1 homework block." and its Undo
with "All your homework already has a time." The toast also has to stay while the pointer
or the keyboard is on it, show how long is left, and leave the keyboard on the week.
"""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton, QWidget

from desktop.native.widgets import TOAST_MS
from desktop.tests.grid_support import (  # noqa: F401
    key,
    qapp,
    server,
    settled,
    signed_in,
    signed_out,
    wait_until,
    window,
)
from desktop.tests.test_focus_returns import add_homework

PLACED = "Placed 1 homework block."
# An action toast stays at least this long. Plain messages stay at TOAST_MS.
ACTION_MS = 10_000
# Leaving the toast starts its clock again with at least this much left.
RESUME_MS = 4_000


def planned(qapp, window) -> QPushButton:
    add_homework(qapp, window)
    solve = window.findChild(QPushButton, "solveButton")
    QTest.mouseClick(solve, Qt.MouseButton.LeftButton)
    wait_until(qapp, lambda: window.toast.isVisible() and window.toast.button.isVisible())
    settled(qapp, window)
    assert (window.toast.text(), window.toast.button.text()) == (PLACED, "Undo")
    return solve


def undo_still_offered(window) -> tuple[bool, str, bool, str]:
    toast = window.toast
    return toast.isVisible(), toast.text(), toast.button.isVisible(), toast.button.text()


def test_plan_offers_undo_in_its_toast(qapp, window) -> None:
    """Guard: the toast this finding is about."""
    planned(qapp, window)
    assert undo_still_offered(window) == (True, PLACED, True, "Undo")
    assert window.toast._timer.interval() >= ACTION_MS
    assert window.toast._timer.interval() > TOAST_MS


def test_a_second_plan_click_with_nothing_to_do_keeps_the_undo_toast(qapp, window) -> None:
    solve = planned(qapp, window)
    window.toast._timer.start(5_000)
    QTest.mouseClick(solve, Qt.MouseButton.LeftButton)
    settled(qapp, window)
    assert undo_still_offered(window) == (True, PLACED, True, "Undo")
    # The second Plan starts the Undo toast's time over, rather than leaving the short remainder.
    assert window.toast._timer.remainingTime() > 5_000


def test_space_on_plan_with_nothing_to_do_keeps_the_undo_toast(qapp, window) -> None:
    solve = planned(qapp, window)
    solve.setFocus(Qt.FocusReason.MouseFocusReason)
    key(window, Qt.Key.Key_Space)
    settled(qapp, window)
    assert undo_still_offered(window) == (True, PLACED, True, "Undo")


def test_a_plan_with_nothing_to_do_from_any_design_keeps_the_undo_toast(qapp, window) -> None:
    """The session's own Plan (what every design's Plan calls), not tied to one button."""
    planned(qapp, window)
    window.session.solve()
    settled(qapp, window)
    assert undo_still_offered(window) == (True, PLACED, True, "Undo")


def test_the_kept_undo_still_takes_the_plan_back(qapp, window) -> None:
    """Guard: Undo in the toast undoes the plan."""
    planned(qapp, window)
    session = window.session
    window.toast.button.click()
    settled(qapp, window)
    assert not any(b.get("start") for b in session.blocks if b.get("assignment_id"))


def test_the_undo_timer_pauses_while_its_button_has_the_keyboard(qapp, window) -> None:
    planned(qapp, window)
    toast = window.toast
    toast._timer.start(1_000)
    toast.button.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    assert toast._timer.isActive() is False
    window.solve_button.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    assert toast._timer.isActive() is True
    # `start` was given at least 4s. A little of that has already run by the time this reads it back.
    assert toast._timer.interval() >= RESUME_MS


def test_the_undo_timer_pauses_while_the_pointer_is_over_its_button(qapp, window) -> None:
    planned(qapp, window)
    toast = window.toast
    toast._timer.start(1_000)
    QTest.mouseMove(toast.button)
    qapp.processEvents()
    assert toast._timer.isActive() is False
    QTest.mouseMove(window.solve_button)
    qapp.processEvents()
    assert toast._timer.isActive() is True
    assert toast._timer.interval() >= RESUME_MS


def test_the_progress_line_uses_the_action_colour_and_hides_when_animations_are_quiet(
    qapp, window
) -> None:
    planned(qapp, window)
    bar = window.toast.findChild(QWidget, "toastProgress")
    assert bar is not None and bar.isVisible()
    assert bar.colour().alphaF() == pytest.approx(0.6)
    window.toast.motion = "off"
    window.toast.sync_progress()
    assert bar.isVisible() is False
    window.toast.motion = "reduce"
    window.toast.sync_progress()
    assert bar.isVisible() is False


def test_a_repeat_does_not_fade_the_card_when_animations_are_off(qapp, window) -> None:
    planned(qapp, window)
    window.toast.motion = "off"
    window.toast.bump()
    assert window.toast.graphicsEffect() is None
    window.toast.motion = "normal"
    window.toast.bump()
    assert window.toast.graphicsEffect() is not None


def _week_has_the_keyboard(window) -> None:
    focus = window.focusWidget()
    assert focus is not None
    assert getattr(focus, "takes_blocks", False), focus.objectName()
    assert not (focus.objectName() or "").startswith("clayDay")
    assert focus is not window.solve_button
    assert focus.objectName() != "moreButton"


def test_after_plan_clay_leaves_the_keyboard_on_the_week(qapp, window) -> None:
    """A day header used to take the keyboard, and Space there changed the day."""
    window._day_mode = False
    window._layout = {"main": "clay", "day": "dial", "options": {}}
    window._on_week()
    settled(qapp, window)
    planned(qapp, window)
    _week_has_the_keyboard(window)


def test_after_plan_dial_leaves_the_keyboard_on_the_week(qapp, window) -> None:
    """The keyboard used to stay on More."""
    window._day_mode = True
    window._layout = {"main": "classic", "day": "dial", "options": {}}
    window._on_week()
    settled(qapp, window)
    planned(qapp, window)
    _week_has_the_keyboard(window)
