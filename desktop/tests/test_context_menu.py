"""A click opens a block; a right-click offers what can be done with it, each the way the app already
does it."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QPushButton, QWidget

from desktop.native import window as window_module
from desktop.native.calendar import sunday_due
from desktop.native.hours.chips import TrayChip
from desktop.native.widgets import BlockDialog, HomeworkDialog, PreviewDialog
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
)
from desktop.tests.window_support import window as signed_in  # noqa: F401

SCHOOL = {
    "id": "school",
    "kind": "locked",
    "title": "School",
    "category": "class",
    "start": "08:00",
    "duration_min": 390,
    "days": [0, 1, 2, 3, 4],
}


@pytest.fixture()
def window(qapp: QApplication, signed_in: NativeWindow) -> Iterator[NativeWindow]:
    """Today's app on Week: School on weekdays, History essay on Wednesday at 18:00, and Math
    worksheet with no time yet."""
    session = signed_in.session
    signed_in.resize(1280, 860)
    signed_in._layout = {"main": "classic", "day": "one", "options": {}}
    session.add_block(dict(SCHOOL))
    due = sunday_due(session.week_start)
    for key, title in (("essay", "History essay"), ("math", "Math worksheet")):
        session.add_homework({"id": key, "title": title, "due": due, "estimate_min": 60, "revision": 0})
    essay = next(block for block in session.blocks if block.get("assignment_id") == "essay")
    session.place_session(essay["id"], 2, 18 * 60)
    session.save()
    settled(qapp, signed_in)
    signed_in.findChild(QPushButton, "viewWeek").click()
    settled(qapp, signed_in)
    signed_in.week_table.hours.reveal(2, 17 * 60, 19 * 60)
    qapp.processEvents()
    yield signed_in


def essay_id(window: NativeWindow) -> str:
    return next(block["id"] for block in window.session.blocks if block.get("assignment_id") == "essay")


def centre(window: NativeWindow, block_id: str, day: int) -> QPoint:
    box = window.week_table.hours.block_rect(block_id, day)
    assert box is not None, f"{block_id} is not drawn on day {day}"
    return box.center()


def right_click(widget: QWidget, at: QPoint) -> None:
    local = widget.mapFromGlobal(at)
    QApplication.sendEvent(widget, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, local, at))


def click(widget: QWidget, at: QPoint, double: bool = False) -> None:
    local = QPointF(widget.mapFromGlobal(at))
    kinds = [QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease]
    if double:
        kinds += [QEvent.Type.MouseButtonDblClick, QEvent.Type.MouseButtonRelease]
    for kind in kinds:
        held = kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick)
        buttons = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
        event = QMouseEvent(
            kind, local, QPointF(at), Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier
        )
        QApplication.sendEvent(widget, event)


@pytest.fixture()
def menus(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Every menu shown, as its items' words, and the item to choose from the next one, by name."""
    seen: dict = {"shown": [], "choose": None, "at": []}

    class Shown(QMenu):
        def exec(self, at: QPoint | None = None, *_rest: object) -> object:
            seen["shown"].append([action.text() for action in self.actions()])
            seen["at"].append(at)
            wanted = seen["choose"]
            return next((action for action in self.actions() if action.objectName() == wanted), None)

    # The window's own name for it: a method set on Qt's class is not the one Qt's object calls.
    monkeypatch.setattr(window_module, "QMenu", Shown)
    return seen


def opened_dialogs(monkeypatch: pytest.MonkeyPatch, *kinds: type) -> list[str]:
    opened: list[str] = []
    for kind in kinds:

        def run(dialog: QDialog, name: str = kind.__name__) -> int:
            opened.append(name)
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(kind, "exec", run)
    return opened


def test_a_click_opens_a_block_once_even_as_part_of_a_double_click(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = opened_dialogs(monkeypatch, BlockDialog, HomeworkDialog)
    hours = window.week_table.hours
    click(hours, centre(window, "school", 1))
    assert opened == ["BlockDialog"]
    click(hours, centre(window, essay_id(window), 2), double=True)
    assert opened == ["BlockDialog", "HomeworkDialog"], "one editor for a double-click, not two"
    assert window.session.selected_block_id == essay_id(window)


def test_a_right_click_offers_four_things_and_finished_only_for_homework(
    qapp: QApplication, window: NativeWindow, menus: dict
) -> None:
    hours = window.week_table.hours
    at = centre(window, essay_id(window), 2)
    before = [dict(block) for block in window.session.blocks]
    right_click(hours, at)
    assert menus["shown"] == [["Open", "Duplicate\tCtrl+D", "Finished", "Delete"]]
    assert menus["at"] == [at], "the menu opens where the pointer is"
    chosen = (window.session.selected_block_id, window.session.selected_occurrence_day)
    assert chosen == (essay_id(window), 2)
    right_click(hours, centre(window, "school", 3))
    assert menus["shown"][-1] == ["Open", "Duplicate\tCtrl+D", "Delete"]
    assert window.session.selected_occurrence_day == 3
    assert window.session.blocks == before, "choosing nothing changes nothing"


def test_open_and_duplicate_take_the_editors_and_ctrl_ds_path(
    qapp: QApplication, window: NativeWindow, menus: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = opened_dialogs(monkeypatch, HomeworkDialog, PreviewDialog)
    hours = window.week_table.hours
    menus["choose"] = "blockMenuOpen"
    right_click(hours, centre(window, essay_id(window), 2))
    assert opened == ["HomeworkDialog"]
    menus["choose"] = "blockMenuDuplicate"
    right_click(hours, centre(window, "school", 4))
    assert opened == ["HomeworkDialog", "PreviewDialog"]


def test_finished_finishes_the_homework_with_an_undo(
    qapp: QApplication, window: NativeWindow, menus: dict
) -> None:
    menus["choose"] = "blockMenuFinished"
    right_click(window.week_table.hours, centre(window, essay_id(window), 2))
    settled(qapp, window)
    assert window.session.assignments["essay"]["completed"] is True
    assert window.action_notice_text.text() == "Finished History essay."


def test_delete_asks_first_and_takes_school_off_that_day_only(
    qapp: QApplication, window: NativeWindow, menus: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []
    answer = [False]

    def confirm(_parent: object, _title: str, question: str, _yes: str, **_named: object) -> bool:
        asked.append(question)
        return answer[0]

    monkeypatch.setattr(window_module, "confirm", confirm)
    menus["choose"] = "blockMenuDelete"
    hours = window.week_table.hours
    right_click(hours, centre(window, "school", 2))
    assert asked == ["Delete School on Wednesday? You can undo this."]
    assert hours.block_rect("school", 2) is not None, "Cancel deletes nothing"
    answer[0] = True
    right_click(hours, centre(window, "school", 2))
    settled(qapp, window)
    school = [block for block in window.session.blocks if block["title"] == "School"]
    days = sorted(day for block in school for day in block["days"])
    assert days == [0, 1, 3, 4]
    assert window.action_notice_text.text() == "Deleted School."


def test_homework_with_no_time_has_a_menu_too(qapp: QApplication, window: NativeWindow, menus: dict) -> None:
    chips = [chip for chip in window.findChildren(TrayChip) if chip.isVisible()]
    assert [chip.block_id for chip in chips] == [
        next(block["id"] for block in window.session.blocks if block.get("assignment_id") == "math")
    ]
    right_click(chips[0], chips[0].mapToGlobal(chips[0].rect().center()))
    assert menus["shown"] == [["Open", "Finished", "Delete"]], "nothing to duplicate until it has a time"


def test_a_months_chip_has_the_same_menu_but_only_in_the_open_week(
    qapp: QApplication, window: NativeWindow, menus: dict
) -> None:
    window.findChild(QPushButton, "viewMonth").click()
    canvas = window.month_grid.canvas
    wait_until(qapp, lambda: bool(canvas.cells))
    monday = date.fromisoformat(window.session.week_start)
    wednesday = (monday + timedelta(days=2)).isoformat()
    canvas.reveal(wednesday)
    qapp.processEvents()
    right_click(canvas, canvas.chip_point(essay_id(window), wednesday))
    assert menus["shown"] == [["Open", "Duplicate\tCtrl+D", "Finished", "Delete"]]
    this_week = {(monday + timedelta(days=offset)).isoformat() for offset in range(7)}
    elsewhere = [cell for cell in canvas.cells if cell.iso not in this_week]
    assert elsewhere, "the month shows a week other than this one"
    school_there = [
        cell for cell in elsewhere if any(chip.block_id == "school" for chip in cell.chips)
    ]
    for cell in school_there[:1] or elsewhere[:1]:
        canvas.reveal(cell.iso)
        qapp.processEvents()
        at = canvas.chip_point("school", cell.iso) if cell in school_there else canvas.cell_point(cell.iso)
        right_click(canvas, at)
    assert len(menus["shown"]) == 1, "another week's School is not this week's, so it has no menu here"
