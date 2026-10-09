"""The week grid is one Tab stop a student works with the arrow keys, with a ring that shows where they
are; Shift+F10 and the Menu key ask for the menu at that slot."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from desktop.native.hours.canvas import HoursCanvas
from desktop.native.widgets import BlockDialog
from desktop.native.window import NativeWindow
from desktop.tests.grid_support import (  # noqa: F401
    NONE,
    PIANO,
    WEDNESDAY,
    add_piano,
    grid,
    hold_clock,
    key,
    menus,
    tab_to_grid,
    window,
)
from desktop.tests.window_support import (  # noqa: F401
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
)
from desktop.tests.window_support import window as signed_in  # noqa: F401


@pytest.mark.parametrize(
    ("which", "mods"),
    [(Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier), (Qt.Key.Key_Menu, NONE)],
)
def test_the_menu_keys_ask_at_the_next_free_quarter_hour_after_now_without_scrolling(
    qapp: QApplication, window: NativeWindow, menus: list[dict], which: Qt.Key, mods: Qt.KeyboardModifier
) -> None:
    hold_clock(window, WEDNESDAY, 20 * 60 + 7)
    hours = grid(window)
    bar = window.week_table.scroll.verticalScrollBar()
    hours.setFocus(Qt.FocusReason.MouseFocusReason)
    bar.setValue(0)
    qapp.processEvents()
    assert not hours.in_view(WEDNESDAY, 20 * 60 + 15), "the slot has to start off screen"
    key(window, which, mods)
    assert [shown["rows"][0] for shown in menus] == ["Add fixed time at 8:15 PM"]
    assert bar.value() == 0, "the menu key scrolled the grid"
    assert hours.focus_slot() == (WEDNESDAY, 20 * 60 + 15)


def test_the_menu_key_skips_slots_that_are_taken(
    qapp: QApplication, window: NativeWindow, menus: list[dict]
) -> None:
    window.session.add_block({**PIANO, "id": "now", "start": "14:00", "duration_min": 45})
    window.session.save()
    settled(qapp, window)
    hold_clock(window, WEDNESDAY, 14 * 60 + 7)
    grid(window).setFocus(Qt.FocusReason.MouseFocusReason)
    key(window, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
    assert [shown["rows"][0] for shown in menus] == ["Add fixed time at 2:45 PM"]


def test_the_grid_is_one_tab_stop_and_shows_where_the_student_is(
    qapp: QApplication, window: NativeWindow
) -> None:
    hours = grid(window)
    tab_to_grid(window)
    assert hours.ring_shown and hours.focus_slot() == (WEDNESDAY, 14 * 60 + 15)
    key(window, Qt.Key.Key_Tab)
    assert not window.week_table.isAncestorOf(window.focusWidget()), "Tab stayed inside the grid"
    key(window, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert window.focusWidget() is hours, "Shift+Tab did not come straight back to the grid"


def test_a_click_gives_the_grid_focus_without_a_ring(qapp: QApplication, window: NativeWindow) -> None:
    hours = grid(window)
    window.prev_nav.setFocus(Qt.FocusReason.TabFocusReason)
    hours.setFocus(Qt.FocusReason.MouseFocusReason)
    qapp.processEvents()
    assert window.focusWidget() is hours
    assert not hours.ring_shown


def test_arrow_keys_move_a_quarter_hour_up_and_down_and_a_day_left_and_right(
    qapp: QApplication, window: NativeWindow
) -> None:
    hours = grid(window)
    tab_to_grid(window)
    steps = [
        (Qt.Key.Key_Down, (WEDNESDAY, 14 * 60 + 30)),
        (Qt.Key.Key_Down, (WEDNESDAY, 14 * 60 + 45)),
        (Qt.Key.Key_Up, (WEDNESDAY, 14 * 60 + 30)),
        (Qt.Key.Key_Right, (WEDNESDAY + 1, 14 * 60 + 30)),
        (Qt.Key.Key_Left, (WEDNESDAY, 14 * 60 + 30)),
        (Qt.Key.Key_Left, (WEDNESDAY - 1, 14 * 60 + 30)),
        (Qt.Key.Key_Left, (0, 14 * 60 + 30)),
        (Qt.Key.Key_Left, (0, 14 * 60 + 30)),
    ]
    for which, expected in steps:
        key(window, which)
        assert hours.focus_slot() == expected, f"after {which.name}"


def test_arrows_stop_at_the_ends_of_the_day(qapp: QApplication, window: NativeWindow) -> None:
    hours = grid(window)
    tab_to_grid(window)
    for _ in range(100):
        key(window, Qt.Key.Key_Up)
    assert hours.focus_slot() == (WEDNESDAY, 0)
    for _ in range(100):
        key(window, Qt.Key.Key_Down)
    assert hours.focus_slot() == (WEDNESDAY, 24 * 60 - 15)


def test_an_arrow_onto_a_block_focuses_it_and_enter_opens_it(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_piano(qapp, window)
    hours = grid(window)
    opened: list[str] = []

    def look(dialog: BlockDialog) -> int:
        opened.append(dialog.block()["id"])
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(BlockDialog, "exec", look)
    tab_to_grid(window)
    key(window, Qt.Key.Key_Down)
    key(window, Qt.Key.Key_Down)
    assert hours.focus_block() is None, "14:45 is free"
    key(window, Qt.Key.Key_Down)
    assert hours.focus_slot() == (WEDNESDAY, 15 * 60)
    assert hours.focus_block() == ("piano", WEDNESDAY)
    assert window.session.selected_block_id == "piano"
    key(window, Qt.Key.Key_Down)
    assert hours.focus_block() == ("piano", WEDNESDAY), "15:15 is still Piano"
    key(window, Qt.Key.Key_Return)
    assert opened == ["piano"]
    for _ in range(3):
        key(window, Qt.Key.Key_Up)
    assert hours.focus_block() is None
    assert window.session.selected_block_id is None, "a free slot is not a block that Delete could take"


def test_enter_on_a_free_slot_opens_the_free_time_menu(
    qapp: QApplication, window: NativeWindow, menus: list[dict]
) -> None:
    tab_to_grid(window)
    key(window, Qt.Key.Key_Down)
    key(window, Qt.Key.Key_Return)
    asked = [(shown["name"], shown["rows"][0]) for shown in menus]
    assert asked == [("spotMenu", "Add fixed time at 2:30 PM")]


def test_shift_f10_on_a_block_opens_its_menu(
    qapp: QApplication, window: NativeWindow, menus: list[dict]
) -> None:
    add_piano(qapp, window)
    tab_to_grid(window)
    for _ in range(4):
        key(window, Qt.Key.Key_Down)
    key(window, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
    assert [(shown["name"], shown["rows"][0]) for shown in menus] == [("blockMenu", "Open\tEnter")]


def test_delete_takes_away_the_focused_block(qapp: QApplication, window: NativeWindow) -> None:
    add_piano(qapp, window)
    tab_to_grid(window)
    for _ in range(4):
        key(window, Qt.Key.Key_Down)
    key(window, Qt.Key.Key_Delete)
    settled(qapp, window)
    assert not any(block["id"] == "piano" for block in window.session.blocks)


def test_delete_on_a_free_slot_takes_nothing_even_after_a_block_was_chosen(
    qapp: QApplication, window: NativeWindow
) -> None:
    add_piano(qapp, window)
    window.session.select_block("piano", WEDNESDAY)
    tab_to_grid(window)
    key(window, Qt.Key.Key_Delete)
    settled(qapp, window)
    assert any(block["id"] == "piano" for block in window.session.blocks)


def test_escape_leaves_the_grid_for_the_top_bar(qapp: QApplication, window: NativeWindow) -> None:
    tab_to_grid(window)
    key(window, Qt.Key.Key_Escape)
    focus = window.focusWidget()
    assert focus is window.findChild(QPushButton, "viewWeek")


def ring_pixels(hours: HoursCanvas) -> tuple[QColor, QColor]:
    """The colour on the ring's left edge and the colour a few pixels outside it."""
    rect = hours.focus_rect()
    assert rect is not None
    image = hours.grab().toImage()
    row = int(rect.center().y())
    return QColor(image.pixel(int(rect.left()) - 3, row)), QColor(image.pixel(int(rect.left()) - 9, row))


def luminance(colour: QColor) -> float:
    def part(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return 0.2126 * part(colour.redF()) + 0.7152 * part(colour.greenF()) + 0.0722 * part(colour.blueF())


def test_the_focused_slot_has_a_ring_in_the_accent_that_reaches_three_to_one(
    qapp: QApplication, window: NativeWindow
) -> None:
    hours = grid(window)
    tab_to_grid(window)
    ring, around = ring_pixels(hours)
    accent = hours.painter.c("accent")
    assert ring.name() == accent.name()
    lighter, darker = sorted((luminance(ring), luminance(around)), reverse=True)
    assert (lighter + 0.05) / (darker + 0.05) >= 3.0


def test_the_ring_goes_round_a_focused_block(qapp: QApplication, window: NativeWindow) -> None:
    add_piano(qapp, window)
    hours = grid(window)
    tab_to_grid(window)
    for _ in range(4):
        key(window, Qt.Key.Key_Down)
    rect = hours.focus_rect()
    box = hours.block_rect("piano", WEDNESDAY)
    assert rect is not None and box is not None
    local = hours.mapFromGlobal(box.topLeft())
    assert abs(rect.left() - local.x()) <= 1 and abs(rect.top() - local.y()) <= 2
    ring, _around = ring_pixels(hours)
    assert ring.name() == hours.painter.c("accent").name()


def test_no_ring_is_drawn_when_the_grid_is_not_focused(qapp: QApplication, window: NativeWindow) -> None:
    hours = grid(window)
    tab_to_grid(window)
    key(window, Qt.Key.Key_Tab)
    assert not hours.ring_shown


def test_where_time_runs_across_left_and_right_move_the_time_and_up_and_down_the_day(
    qapp: QApplication, window: NativeWindow
) -> None:
    from desktop.native.hours.geometry import Axis
    from desktop.native.layouts.registry import sanitize_layout

    window._layout = sanitize_layout({"main": "mission", "day": "one"})
    window._apply_appearance()
    window._on_week()
    settled(qapp, window)
    lanes = [
        hours for hours in window._week_surfaces() if hours.tracks and hours.tracks[0].axis is Axis.ACROSS
    ]
    assert lanes, "Mission shows a lane for each day"
    hours = lanes[0]
    hours.setFocus(Qt.FocusReason.TabFocusReason)
    day, minute = hours.focus_slot()
    key(window, Qt.Key.Key_Right)
    assert hours.focus_slot() == (day, minute + 15)
    key(window, Qt.Key.Key_Down)
    assert hours.focus_slot() == (day + 1, minute + 15)
    key(window, Qt.Key.Key_Left)
    key(window, Qt.Key.Key_Up)
    assert hours.focus_slot() == (day, minute)
