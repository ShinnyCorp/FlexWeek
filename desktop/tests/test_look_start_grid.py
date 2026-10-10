"""0.18.5 #59: Start from is a grid of small pictures of the looks, not a plain dropdown. Choosing a card
starts the look from it, as choosing in the dropdown did; the arrow keys move between cards and Enter or
Space chooses."""

# ruff: noqa: F811  (pytest fixtures imported by name)

from __future__ import annotations

from collections.abc import Callable

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from desktop.native.look import BASE_LABELS
from desktop.native.look_editor import LookEditor, StartGrid, StartSheet
from desktop.native.window import NativeWindow
from desktop.tests.test_look_editor import open_editor, pump
from desktop.tests.window_support import qapp, server, signed_out, window  # noqa: F401

BASES = list(BASE_LABELS)


def through_sheet(editor: LookEditor, act: Callable[[StartSheet], None]) -> StartSheet:
    """Open the Start from sheet with the button and let `act` drive it; the sheet is closed after if
    `act` left it open, so a test that fails cannot hang the run."""
    seen: list[StartSheet] = []

    def drive() -> None:
        sheet = QApplication.activeModalWidget()
        assert isinstance(sheet, StartSheet)
        seen.append(sheet)
        try:
            act(sheet)
        finally:
            if sheet.isVisible():
                sheet.reject()

    QTimer.singleShot(200, drive)
    editor.start_from.click()
    return seen[0]


def names(sheet: StartSheet) -> list[str]:
    return [card.accessibleName() for card in sheet.looks.cards]


def test_start_from_is_a_button_that_names_the_look_it_started_from(
    qapp: QApplication, window: NativeWindow
) -> None:
    page, editor = open_editor(qapp, window)
    assert isinstance(editor.start_from, QPushButton)
    assert editor.start_from.text() == BASE_LABELS[editor._draft.look["base"]]
    assert editor.start_from.accessibleName().startswith("Start from")
    page.close_page()


def test_the_sheet_has_a_picture_card_for_every_look_and_rings_the_one_started_from(
    qapp: QApplication, window: NativeWindow
) -> None:
    page, editor = open_editor(qapp, window)
    seen: dict[str, object] = {}

    def look(sheet: StartSheet) -> None:
        seen["names"] = names(sheet)
        seen["pictures"] = [card.picture.pixmap() for card in sheet.looks.cards]
        seen["selected"] = [card.accessibleName() for card in sheet.looks.cards if card.is_selected()]

    through_sheet(editor, look)
    assert seen["names"] == list(BASE_LABELS.values())
    assert all(isinstance(picture, QPixmap) and not picture.isNull() for picture in seen["pictures"])
    assert seen["selected"] == [BASE_LABELS[editor._draft.look["base"]]]
    page.close_page()


def test_clicking_a_card_starts_the_look_from_it(qapp: QApplication, window: NativeWindow) -> None:
    page, editor = open_editor(qapp, window)
    assert editor._draft.look["base"] != "dark"

    def click_dark(sheet: StartSheet) -> None:
        card = sheet.looks.cards[BASES.index("dark")]
        QTest.mouseClick(card, Qt.MouseButton.LeftButton)

    sheet = through_sheet(editor, click_dark)
    pump(qapp)
    assert sheet.result() == QDialog.DialogCode.Accepted
    assert editor._draft.look["base"] == "dark"
    assert editor.start_from.text() == "Dark"
    page.close_page()


def test_the_arrow_keys_move_between_cards_and_enter_chooses(
    qapp: QApplication, window: NativeWindow
) -> None:
    page, editor = open_editor(qapp, window)
    start = BASES.index(editor._draft.look["base"])
    assert start + 1 < len(BASES)
    chosen: list[int] = []

    def walk(sheet: StartSheet) -> None:
        sheet.activateWindow()
        grid: StartGrid = sheet.looks
        grid.cards[start].setFocus()
        QTest.keyClick(grid.cards[start], Qt.Key.Key_Right)
        assert grid.cards[start + 1].hasFocus()
        QTest.keyClick(grid.cards[start + 1], Qt.Key.Key_Left)
        assert grid.cards[start].hasFocus()
        QTest.keyClick(grid.cards[start], Qt.Key.Key_Down)
        below = start + grid.columns()
        assert below < len(grid.cards)
        assert grid.cards[below].hasFocus()
        chosen.append(below)
        QTest.keyClick(grid.cards[below], Qt.Key.Key_Return)

    through_sheet(editor, walk)
    pump(qapp)
    assert editor._draft.look["base"] == BASES[chosen[0]]
    assert editor.start_from.text() == BASE_LABELS[BASES[chosen[0]]]
    page.close_page()


def test_space_chooses_and_the_arrows_stop_at_the_ends(qapp: QApplication, window: NativeWindow) -> None:
    page, editor = open_editor(qapp, window)

    def last(sheet: StartSheet) -> None:
        sheet.activateWindow()
        grid: StartGrid = sheet.looks
        grid.cards[0].setFocus()
        QTest.keyClick(grid.cards[0], Qt.Key.Key_Left)
        assert grid.cards[0].hasFocus(), "no wrapping off the first card"
        QTest.keyClick(grid.cards[0], Qt.Key.Key_End)
        assert grid.cards[-1].hasFocus()
        QTest.keyClick(grid.cards[-1], Qt.Key.Key_Right)
        assert grid.cards[-1].hasFocus(), "no wrapping off the last card"
        QTest.keyClick(grid.cards[-1], Qt.Key.Key_Space)

    through_sheet(editor, last)
    pump(qapp)
    assert editor._draft.look["base"] == BASES[-1]
    page.close_page()


def test_escape_closes_the_sheet_and_changes_nothing(qapp: QApplication, window: NativeWindow) -> None:
    page, editor = open_editor(qapp, window)
    before = dict(editor._draft.look)

    def leave(sheet: StartSheet) -> None:
        QTest.keyClick(sheet, Qt.Key.Key_Escape)

    sheet = through_sheet(editor, leave)
    pump(qapp)
    assert sheet.result() == QDialog.DialogCode.Rejected
    assert editor._draft.look == before
    page.close_page()


def test_a_saved_look_is_a_card_after_the_built_in_ones_and_starts_from_that_look(
    qapp: QApplication, window: NativeWindow
) -> None:
    page, editor = open_editor(qapp, window)
    editor._save("Mine")
    pump(qapp)
    editor._start_from("base:dark")
    pump(qapp)
    assert editor._draft.saved_as is None

    def pick_mine(sheet: StartSheet) -> None:
        assert names(sheet) == [*BASE_LABELS.values(), "Mine"]
        QTest.mouseClick(sheet.looks.cards[-1], Qt.MouseButton.LeftButton)

    through_sheet(editor, pick_mine)
    pump(qapp)
    assert editor._draft.saved_as == "Mine"
    assert editor.start_from.text() == "Mine"
    page.close_page()
