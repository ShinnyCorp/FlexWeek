"""Regression for fix-specs.md item 6: the keyboard stays on Monday's School after a sheet closes.

The week keeps a keyboard spot (`HoursCanvas._cursor`) that a mouse press does not move, so after the
keyboard was on Monday's School, a click on Thursday 19:00 (the Add sheet opens) and Esc leave the spot on
School, and Shift+F10 opens School's menu. Every click and key goes through the window system's path
(QTest on `window.windowHandle()`), as in item 0's tests; sheets are real and modal and are answered by
keys sent to their own window from a timer, so Dialog.showEvent/hideEvent and _give_focus_back run as
in the app. Today's app only; test_regress_item6_other_designs.py repeats it in Timeline, Mission, Bento
and Retro.
"""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

from collections.abc import Callable

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from desktop.native.hours.canvas import HoursCanvas
from desktop.native.weekmodel import clock_text
from desktop.native.widgets import BlockDialog
from desktop.tests.grid_support import (  # noqa: F401
    NONE,
    grid,
    key,
    menus,
    qapp,
    server,
    settled,
    signed_in,
    signed_out,
    tab_to_grid,
    window,
)

MONDAY, TUESDAY, THURSDAY = 0, 1, 3
SCHOOL = {"id": "school", "title": "School", "kind": "locked", "category": "class", "start": "08:00",
          "duration_min": 390, "days": [0, 1, 2, 3, 4]}


def on_monday_school(qapp, window) -> HoursCanvas:
    """Tab to the week and put the keyboard on Monday's School, as arrows would."""
    window.session.add_block(dict(SCHOOL))
    window.session.save()
    settled(qapp, window)
    hours = grid(window)
    tab_to_grid(window)
    hours.take_focus(True, ("school", MONDAY, 8 * 60))
    qapp.processEvents()
    assert hours.focus_block() == ("school", MONDAY) and hours.ring_shown
    return hours


def click_with_sheet(qapp, window, hours: HoursCanvas, day: int, minute: int,
                     answer: Callable[[QDialog], None]) -> list[str]:
    """Click the grid at (day, minute); `answer` is given the sheet that opens. Returns its objectName."""
    hours.reveal(day, minute, minute + 60)
    qapp.processEvents()
    seen: list[str] = []

    def reply() -> None:
        sheet = QApplication.activeModalWidget()
        if sheet is None:
            return
        seen.append(sheet.objectName())
        answer(sheet)

    QTimer.singleShot(300, reply)
    at = window.mapFromGlobal(hours.point_for(day, minute + 7))
    QTest.mouseClick(window.windowHandle(), Qt.MouseButton.LeftButton, NONE, at)
    for _ in range(12):
        QTest.qWait(50)
    return seen


def escape(sheet: QDialog) -> None:
    QTest.keyClick(sheet.windowHandle(), Qt.Key.Key_Escape)


def name_and_save(sheet: QDialog) -> None:
    title = sheet.findChild(BlockDialog) or sheet
    title.title.setFocus()
    for char in "Club":
        QTest.keyClick(sheet.windowHandle(), char)
    QTest.keyClick(sheet.windowHandle(), Qt.Key.Key_Return)


def test_6_1_after_a_click_and_esc_shift_f10_asks_about_the_clicked_slot(qapp, window, menus) -> None:
    hours = on_monday_school(qapp, window)
    assert click_with_sheet(qapp, window, hours, THURSDAY, 19 * 60, escape) == ["blockDialog"]
    assert window.focusWidget() is hours, "the keyboard did not come back to the week"
    key(window, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
    asked = [(shown["name"], shown["rows"][0]) for shown in menus]
    expected = [("spotMenu", f"Add fixed time at {clock_text(19 * 60)}")]
    assert asked == expected, f"spot {hours.focus_slot()}, menus {asked}"


def test_6_mouse_press_moves_the_spot_and_hides_the_ring(qapp, window) -> None:
    hours = on_monday_school(qapp, window)
    click_with_sheet(qapp, window, hours, THURSDAY, 19 * 60, escape)
    assert hours.focus_slot() == (THURSDAY, 19 * 60) and not hours.ring_shown


def test_6_2_a_saved_new_block_gets_the_keyboard_and_enter_opens_it(qapp, window, monkeypatch) -> None:
    hours = on_monday_school(qapp, window)
    assert click_with_sheet(qapp, window, hours, THURSDAY, 19 * 60, name_and_save) == ["blockDialog"]
    settled(qapp, window)
    club = next((b for b in window.session.blocks if b["title"] == "Club"), None)
    assert club is not None, "the new block was not saved"
    assert window.focusWidget() is hours, "the keyboard did not come back to the week"
    assert hours.focus_block() == (club["id"], THURSDAY), hours.focus_block()
    opened: list[str] = []

    def look(dialog: BlockDialog) -> int:
        opened.append(dialog.block()["id"])
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(BlockDialog, "exec", look)
    key(window, Qt.Key.Key_Return)
    assert opened == [club["id"]]


def test_6_3_after_clicking_school_and_closing_right_moves_from_school(qapp, window) -> None:
    window.session.add_block(dict(SCHOOL))
    window.session.save()
    settled(qapp, window)
    hours = grid(window)
    tab_to_grid(window)  # the spot starts on Wednesday 14:15
    assert hours.focus_slot()[0] != MONDAY
    click_with_sheet(qapp, window, hours, MONDAY, 10 * 60, escape)
    key(window, Qt.Key.Key_Right)
    assert hours.focus_slot() is not None and hours.focus_slot()[0] == TUESDAY, hours.focus_slot()
    assert hours.focus_block() == ("school", TUESDAY)


def test_6_4_only_one_thing_looks_focused(qapp, window) -> None:
    hours = on_monday_school(qapp, window)
    click_with_sheet(qapp, window, hours, THURSDAY, 19 * 60, escape)
    spot = hours.focus_block()
    selected = window.session.selected_block_id
    said = f"selected {selected!r}, keyboard on {spot or hours.focus_slot()}"
    assert selected in (None, spot and spot[0]), said
    assert selected != "school"


def test_6_keyboard_only_round_trip_still_returns_to_the_block(qapp, window, menus) -> None:
    """Guard: with no mouse at all, Shift+F10 on Monday's School still opens School's menu."""
    hours = on_monday_school(qapp, window)
    key(window, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
    assert [(shown["name"], shown["rows"][0]) for shown in menus] == [("blockMenu", "Open\tEnter")]
    assert window.focusWidget() is hours


def test_6_2_a_block_saved_from_the_add_button_gets_the_keyboard_not_the_button(qapp, window) -> None:
    """The sheet hands the keyboard back to what had it (the button) a moment after it closes; the new
    block still ends up with it."""
    hours = grid(window)
    window.findChild(QPushButton, "addButton").setFocus(Qt.FocusReason.MouseFocusReason)
    qapp.processEvents()
    QTimer.singleShot(300, lambda: name_and_save(QApplication.activeModalWidget()))
    window._add_fixed()
    for _ in range(12):
        QTest.qWait(50)
    settled(qapp, window)
    club = next((b for b in window.session.blocks if b["title"] == "Club"), None)
    assert club is not None, "the new block was not saved"
    assert window.focusWidget() is hours, type(window.focusWidget()).__name__
    assert hours.focus_block() is not None and hours.focus_block()[0] == club["id"], hours.focus_block()
