"""A week with nothing in it says where to start, and the hours come back with the first thing added."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate, QStandardPaths, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton

from desktop.native.calendar import sunday_due
from desktop.native.layouts.empty import EMPTY_BUTTON, EMPTY_HEADING, EMPTY_LINE
from desktop.native.widgets import HomeworkDialog
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
)
from desktop.tests.window_support import window as signed_in  # noqa: F401


def look_file() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(root) / "flexweek-look.json"


@pytest.fixture()
def window(qapp: QApplication, signed_in: NativeWindow) -> Iterator[NativeWindow]:  # noqa: F811
    """A new account just past setup, with no school block: Today's app, on Week."""
    signed_in.resize(1280, 860)
    signed_in._layout = {"main": "classic", "day": "one", "options": {}}
    signed_in.findChild(QPushButton, "viewWeek").click()
    settled(qapp, signed_in)
    yield signed_in
    look_file().unlink(missing_ok=True)


def shown(window: NativeWindow) -> object:
    return window.planner.currentWidget()


def test_a_new_accounts_week_offers_one_button_instead_of_empty_hours(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,
) -> None:
    assert window.session.blocks == [] and window.session.assignments == {}
    assert shown(window) is window.empty_week
    assert window.week_table.isVisible() is False
    words = [label.text() for label in window.empty_week.findChildren(QLabel)]
    assert words == [EMPTY_HEADING, EMPTY_LINE]
    buttons = [button for button in window.empty_week.findChildren(QPushButton) if button.isVisible()]
    assert [button.text() for button in buttons] == [EMPTY_BUTTON]
    # The top bar stays: where you are, the views, Plan and More.
    for name in ("weekTitle", "viewWeek", "solveButton", "moreButton"):
        assert window.findChild(QLabel if name == "weekTitle" else QPushButton, name).isVisible(), name

    window.findChild(QPushButton, "viewDay").click()
    settled(qapp, window)
    assert shown(window) is window.empty_week, "Today's app's Day of an empty week says the same"
    window.findChild(QPushButton, "viewMonth").click()
    settled(qapp, window)
    assert shown(window) is window.month_grid, "Month is a calendar, empty or not"


def test_the_button_opens_the_homework_editor_and_the_hours_come_back(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[HomeworkDialog] = []

    def add(dialog: HomeworkDialog) -> int:
        opened.append(dialog)
        dialog.title.setText("Math worksheet")
        dialog.due.date.setDate(QDate.fromString(sunday_due(window.session.week_start)[:10], "yyyy-MM-dd"))
        dialog.accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(HomeworkDialog, "exec", add)
    QTest.mouseClick(window.empty_week.add, Qt.MouseButton.LeftButton)
    settled(qapp, window)
    assert len(opened) == 1
    assert [item["title"] for item in window.session.assignments.values()] == ["Math worksheet"]
    wait_until(qapp, lambda: shown(window) is window.week_table)
    assert window.week_table.isVisible()


def test_a_fixed_time_brings_the_hours_back_and_undo_empties_the_week_again(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,
) -> None:
    session = window.session
    session.add_block(
        {"id": "piano", "title": "Piano", "kind": "locked", "category": "extra",
         "start": "17:00", "duration_min": 30, "days": [3]}
    )
    session.save()
    settled(qapp, window)
    assert shown(window) is window.week_table
    session.undo()
    settled(qapp, window)
    assert session.blocks == []
    assert shown(window) is window.empty_week


def test_a_student_with_homework_keeps_the_hours_on_an_empty_week(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,
) -> None:
    """Every week nobody has saved is empty, so next week is empty for everyone. It keeps its hours
    once the student has homework anywhere."""
    session = window.session
    session.add_homework(
        {"id": "essay", "title": "History essay", "due": sunday_due(session.week_start),
         "estimate_min": 60, "revision": 0}
    )
    session.save()
    settled(qapp, window)
    assert shown(window) is window.week_table
    window.findChild(QPushButton, "nextWeek").click()
    wait_until(qapp, lambda: not session.busy)
    settled(qapp, window)
    assert session.blocks == []
    assert shown(window) is window.week_table


def test_a_design_of_its_own_draws_its_own_empty_week(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,
) -> None:
    window._layout = {"main": "bento", "day": "one", "options": {}}
    window._on_week()
    assert shown(window) is not window.empty_week
    assert shown(window).layout_id == "bento"
