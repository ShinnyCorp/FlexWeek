"""A click opens a block; a right-click offers what can be done with it, each the way the app already
does it."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QWidget

from desktop.native import window as window_module
from desktop.native.calendar import sunday_due
from desktop.native.hours.chips import TrayChip
from desktop.native.menus import DANGER, ICON, Menu
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


# A placed homework's menu: what changes it, a line, then the two deletes.
EVERY_ROW = ["Open\tEnter", "Duplicate\tCtrl+D", "Copy\tCtrl+C", "Finished", "---", "Delete\tDel"]


@pytest.fixture()
def menus(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Every menu shown, as its items' words, and the item to choose from the next one, by name."""
    seen: dict = {"shown": [], "choose": None, "at": [], "rows": []}

    class Shown(Menu):
        def exec(self, at: QPoint | None = None, *_rest: object) -> object:
            seen["shown"].append([action.text() or "---" for action in self.actions()])
            seen["rows"].append(list(self.actions()))
            seen["at"].append(at)
            wanted = seen["choose"]
            return next((action for action in self.actions() if action.objectName() == wanted), None)

    # The window's own name for it: a method set on Qt's class is not the one Qt's object calls.
    monkeypatch.setattr(window_module, "Menu", Shown)
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
    assert menus["shown"] == [EVERY_ROW]
    assert menus["at"] == [at], "the menu opens where the pointer is"
    chosen = (window.session.selected_block_id, window.session.selected_occurrence_day)
    assert chosen == (essay_id(window), 2)
    right_click(hours, centre(window, "school", 3))
    assert menus["shown"][-1] == ["Open\tEnter", "Duplicate\tCtrl+D", "Copy\tCtrl+C", "---", "Delete\tDel"]
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
    assert window.toast.text() == "Finished History essay."


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
    assert window.toast.text() == "Deleted School."


def test_homework_with_no_time_has_a_menu_too(qapp: QApplication, window: NativeWindow, menus: dict) -> None:
    chips = [chip for chip in window.findChildren(TrayChip) if chip.isVisible()]
    assert [chip.block_id for chip in chips] == [
        next(block["id"] for block in window.session.blocks if block.get("assignment_id") == "math")
    ]
    right_click(chips[0], chips[0].mapToGlobal(chips[0].rect().center()))
    # Nothing to duplicate until it has a time, and no one time to delete: the homework is the entry.
    assert menus["shown"] == [["Open\tEnter", "Finished", "---", "Delete\tDel"]]


def test_delete_homework_asks_first_and_takes_it_away_with_an_undo(
    qapp: QApplication, window: NativeWindow, menus: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    def answer(_parent: object, title: str, words: str, _yes: str) -> bool:
        asked.append(title)
        return True

    monkeypatch.setattr(window_module, "confirm", answer)
    chip = next(chip for chip in window.findChildren(TrayChip) if chip.isVisible())
    menus["choose"] = "blockMenuDelete"
    right_click(chip, chip.mapToGlobal(chip.rect().center()))
    settled(qapp, window)
    assert asked == ["Delete homework"]
    assert "math" not in window.session.assignments
    assert window.toast.text() == "Deleted Math worksheet."
    assert window.toast.button.text() == "Undo"
    window.toast.button.click()
    settled(qapp, window)
    assert window.session.assignments["math"]["title"] == "Math worksheet"


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
    assert menus["shown"] == [EVERY_ROW]
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


def test_the_menu_has_an_icon_on_every_row_and_red_only_for_deleting(
    qapp: QApplication, window: NativeWindow, menus: dict
) -> None:
    """Decision 22: icons, a separator before the deletes, and the error red for Delete and Delete
    homework alone (Red means a problem, decision 8)."""
    right_click(window.week_table.hours, centre(window, essay_id(window), 2))
    rows = [action for action in menus["rows"][0] if not action.isSeparator()]
    assert all(action.property(ICON) for action in rows), [action.text() for action in rows]
    red = [action.text() for action in rows if action.property(DANGER)]
    assert red == ["Delete\tDel"]


def test_a_delete_row_is_painted_red_and_the_rest_in_the_text_colour(
    qapp: QApplication, window: NativeWindow
) -> None:
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QColor

    from desktop.native.look import resolved_palette
    from desktop.native.menus import menu_colours

    palette = resolved_palette("light-frost", False, None)
    menu = Menu(window)
    menu.set_colours(menu_colours(palette, lifted=False))
    menu.add("Open", "pencil")
    menu.addSeparator()
    menu.add("Delete", "trash", danger=True)
    menu.popup(QPoint(100, 100))
    qapp.processEvents()
    image = menu.grab().toImage()

    def colours_in(words: str) -> set[str]:
        box = menu.actionGeometry(next(action for action in menu.actions() if action.text() == words))
        return {
            image.pixelColor(x, y).name()
            for x in range(box.left(), box.right())
            for y in range(box.top(), box.bottom())
        }

    red, ink = QColor(palette["error"]).name(), QColor(palette["text"]).name()
    assert red in colours_in("Delete") and ink not in colours_in("Delete")
    assert ink in colours_in("Open") and red not in colours_in("Open")
    menu.close()


# What an empty spot offers: nothing is copied yet, so Paste is greyed and says why on its row.
SPOT_ROWS = ["Add fixed time at 17:00", "Add homework due this day", "Paste"]


def free_spot(hours: object, minute: int = 17 * 60 + 5) -> QPoint:
    """Tuesday at a minute, where nothing is: School ends 14:30 and the essay is on Wednesday."""
    hours.hand.step = 15
    hours.reveal(1, minute, minute + 30)
    QApplication.processEvents()
    return hours.point_for(1, minute)


def test_a_right_click_on_free_time_offers_what_can_be_added_there(
    qapp: QApplication, window: NativeWindow, menus: dict
) -> None:
    hours = window.week_table.hours
    before = [dict(block) for block in window.session.blocks]
    right_click(hours, free_spot(hours))
    assert menus["shown"] == [SPOT_ROWS]
    assert not menus["rows"][0][2].isEnabled()
    assert menus["rows"][0][2].toolTip() == "Copy a block or a day first."
    # The step the pointer is in: 17:20 is past the 17:15 step's start, not at 17:30.
    right_click(hours, free_spot(hours, 17 * 60 + 20))
    assert menus["shown"][-1][0] == "Add fixed time at 17:15"
    assert window.session.blocks == before, "choosing nothing changes nothing"
    right_click(hours, centre(window, "school", 3))
    assert menus["shown"][-1] == ["Open\tEnter", "Duplicate\tCtrl+D", "Copy\tCtrl+C", "---", "Delete\tDel"]


def test_add_fixed_time_opens_the_sheet_on_that_day_at_that_time(
    qapp: QApplication, window: NativeWindow, menus: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[list[int], str]] = []

    def look(dialog: BlockDialog) -> int:
        seen.append(([day for day, box in enumerate(dialog.days) if box.isChecked()], dialog.start.text()))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(BlockDialog, "exec", look)
    hours = window.week_table.hours
    menus["choose"] = "spotMenuFixed"
    right_click(hours, free_spot(hours))
    assert seen == [([1], "17:00")]


def test_add_homework_opens_the_sheet_due_on_that_day(
    qapp: QApplication, window: NativeWindow, menus: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def look(dialog: HomeworkDialog) -> int:
        seen.append(dialog.assignment()["due"])
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(HomeworkDialog, "exec", look)
    hours = window.week_table.hours
    menus["choose"] = "spotMenuHomework"
    right_click(hours, free_spot(hours))
    tuesday = date.fromisoformat(window.session.week_start) + timedelta(days=1)
    assert seen == [tuesday.isoformat()]


def test_paste_is_offered_once_something_is_copied_and_pastes_there(
    qapp: QApplication, window: NativeWindow, menus: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[tuple[object, object]] = []
    real = type(window.session).paste_proposals

    def spy(session: object, day: object = None, start: object = None, **named: object) -> object:
        asked.append((day, start))
        return real(session, day, start, **named)

    monkeypatch.setattr(type(window.session), "paste_proposals", spy)
    opened = opened_dialogs(monkeypatch, PreviewDialog)
    window.session.select_block("school", 3)
    window.session.copy_selected()
    hours = window.week_table.hours
    menus["choose"] = "spotMenuPaste"
    right_click(hours, free_spot(hours))
    assert menus["shown"][0][2] == "Paste"
    assert menus["rows"][0][2].isEnabled()
    assert asked == [(1, "17:00")]
    assert opened == ["PreviewDialog"]


def press(widget: QWidget, key: Qt.Key, mods: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> None:
    QApplication.sendEvent(widget, QKeyEvent(QEvent.Type.KeyPress, key, mods))


@pytest.mark.parametrize(
    ("key", "mods"),
    [(Qt.Key.Key_Menu, Qt.KeyboardModifier.NoModifier), (Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)],
)
def test_the_menu_key_and_shift_f10_ask_for_the_chosen_blocks_menu(
    qapp: QApplication, window: NativeWindow, menus: dict, key: Qt.Key, mods: Qt.KeyboardModifier
) -> None:
    hours = window.week_table.hours
    hours.hand.select("school", 3)
    hours.setFocus()
    press(hours, key, mods)
    assert [rows[0] for rows in menus["shown"]] == ["Open\tEnter"]


@pytest.mark.parametrize(
    ("key", "mods"),
    [(Qt.Key.Key_Menu, Qt.KeyboardModifier.NoModifier), (Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)],
)
def test_the_menu_key_and_shift_f10_ask_at_the_next_free_time_after_now_when_nothing_is_chosen(
    qapp: QApplication, window: NativeWindow, menus: dict, key: Qt.Key, mods: Qt.KeyboardModifier
) -> None:
    # School runs to 14:30 on weekdays, so from Thursday 14:07 the next free quarter hour is 14:30.
    thursday = datetime.fromisoformat(window.session.week_start) + timedelta(days=3, hours=14, minutes=7)
    window.session.now_ms = lambda: int(thursday.timestamp() * 1000)
    window._fill_classic()
    qapp.processEvents()
    hours = window.week_table.hours
    hours.hand.clear_selection()
    hours.setFocus()
    press(hours, key, mods)
    assert [rows[0] for rows in menus["shown"]] == ["Add fixed time at 14:30"]
    assert hours.focus_slot() == (3, 14 * 60 + 30)


@pytest.mark.parametrize("design", ["timeline", "mission", "bento", "retro", "clay"])
def test_every_design_with_shared_hours_has_the_free_time_menu(
    qapp: QApplication, window: NativeWindow, menus: dict, design: str
) -> None:
    from desktop.native.layouts.registry import sanitize_layout

    # Clay's cards beside the day in front show the stretch of the day the front card has scrolled to,
    # and that card opens at now. Before about 09:00 that stretch ends before 17:00, so Tuesday would
    # have no track there unless it was the day in front. Wednesday noon keeps Tuesday's card in range.
    noon = datetime.fromisoformat(window.session.week_start) + timedelta(days=2, hours=12)
    window.session.now_ms = lambda: int(noon.timestamp() * 1000)
    window._layout = sanitize_layout({"main": design, "day": "one"})
    window._apply_appearance()
    window._on_week()
    settled(qapp, window)
    shown = window.planner.currentWidget().hours_surfaces()
    canvases = [surface for surface in shown if surface.track_for(1, 17 * 60)]
    assert canvases, f"{design} shows no hours with Tuesday in them"
    hours = canvases[0]
    right_click(hours, free_spot(hours))
    assert [rows[0] for rows in menus["shown"]] == ["Add fixed time at 17:00"]


def test_day_has_the_free_time_menu_at_its_own_day(
    qapp: QApplication, window: NativeWindow, menus: dict
) -> None:
    window.findChild(QPushButton, "viewDay").click()
    settled(qapp, window)
    hours = window.day_view.hours
    day = date.fromisoformat(window.session.selected_day).weekday()
    hours.reveal(day, 17 * 60, 17 * 60 + 30)
    qapp.processEvents()
    right_click(hours, hours.point_for(day, 17 * 60 + 5))
    assert [rows[0] for rows in menus["shown"]] == ["Add fixed time at 17:00"]
