"""The Due row of Add and Edit homework (finding 32 of the 0.17.2 audit): a switch called "Due by" with
the time beside it, and a deadline that has already passed is refused where it was set."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QWidget

from desktop.native.widgets import HomeworkDialog
from desktop.tests.window_support import free, qapp  # noqa: F401

TODAY = "2026-09-14"
NOW = datetime(2026, 9, 14, 15, 0)


def clocked() -> QWidget:
    """A parent whose session says it is 15:00 on 14 Sep 2026, as the window's session does."""
    parent = QWidget()
    parent.session = SimpleNamespace(
        now_ms=lambda: int(NOW.timestamp() * 1000), blocks=[], week_start="2026-09-14"
    )  # type: ignore[attr-defined]
    return parent


def homework(due: str, **more: object) -> dict:
    return {
        "id": "essay",
        "title": "History essay",
        "due": due,
        "estimate_min": 60,
        "category": "assignments",
        "revision": 0,
        **more,
    }


def saved(dialog: HomeworkDialog) -> bool:
    dialog.show()
    dialog.accept()
    return dialog.result() == dialog.DialogCode.Accepted


def test_the_time_choice_is_called_due_by_and_says_what_it_does(qapp: QApplication) -> None:  # noqa: F811
    parent = clocked()
    dialog = HomeworkDialog(parent, today=TODAY)
    dialog.show()
    qapp.processEvents()
    switch = dialog.due.timed
    assert isinstance(switch, QCheckBox) and switch.text() == "Due by"
    assert "At a set time" not in [box.text() for box in dialog.findChildren(QCheckBox)]
    assert not dialog.due.hint.isVisible(), "no time chosen, nothing to explain"
    switch.setChecked(True)
    assert dialog.due.hint.isVisible()
    assert dialog.due.hint.text() == "FlexWeek plans it before this time."
    switch.setChecked(False)
    assert not dialog.due.hint.isVisible()
    free(dialog)
    free(parent)


def test_a_day_that_has_passed_is_refused_beside_the_date(qapp: QApplication) -> None:  # noqa: F811
    parent = clocked()
    dialog = HomeworkDialog(parent, today=TODAY)
    dialog.title.setText("History essay")
    dialog.due.date.setDate(QDate(2026, 9, 13))
    assert not saved(dialog)
    assert dialog.due.problem.text() == "That time has already passed."
    assert dialog.due.problem.isVisible()
    assert dialog.due.problem.objectName() == "validationError", "the sheet's error colour"
    assert not dialog.error.isVisible(), "beside the field, not in the form's last line"
    # Picking a day that has not passed takes the words away and saves.
    dialog.due.date.setDate(QDate(2026, 9, 15))
    assert not dialog.due.problem.isVisible()
    assert saved(dialog)
    assert dialog.assignment()["due"] == "2026-09-15"
    free(dialog)
    free(parent)


def test_a_time_earlier_today_is_refused_and_a_later_one_is_not(qapp: QApplication) -> None:  # noqa: F811
    parent = clocked()
    dialog = HomeworkDialog(parent, today=TODAY)
    dialog.title.setText("History essay")
    dialog.due.timed.setChecked(True)
    dialog.due.time.setTime(QTime(14, 0))
    assert not saved(dialog), "14:00 is an hour ago at 15:00"
    assert dialog.due.problem.text() == "That time has already passed."
    dialog.due.time.setTime(QTime(15, 30))
    assert saved(dialog)
    assert dialog.assignment()["due"] == "2026-09-14T15:30"
    free(dialog)
    free(parent)


def test_a_day_with_no_time_is_due_at_the_end_of_it_so_today_is_fine(qapp: QApplication) -> None:  # noqa: F811
    parent = clocked()
    dialog = HomeworkDialog(parent, today=TODAY)
    dialog.title.setText("History essay")
    assert dialog.due.value() == TODAY
    assert saved(dialog)
    free(dialog)
    free(parent)


def test_old_homework_can_still_be_edited_and_finished_when_its_deadline_is_not_touched(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent = clocked()
    late = HomeworkDialog(parent, homework("2026-09-10"), TODAY)
    late.title.setText("History essay, part 2")
    assert saved(late), "a deadline that was already past when it was opened is not the student's new mistake"
    assert late.assignment()["due"] == "2026-09-10"
    free(late)

    finishing = HomeworkDialog(parent, homework("2026-09-10"), TODAY)
    finishing.due.date.setDate(QDate(2026, 9, 11))
    finishing.completed.setChecked(True)
    assert saved(finishing), "finished work has no deadline left to miss"
    free(finishing)
    free(parent)


def test_a_new_deadline_on_old_homework_is_checked_too(qapp: QApplication) -> None:  # noqa: F811
    parent = clocked()
    dialog = HomeworkDialog(parent, homework("2026-09-20"), TODAY)
    dialog.due.date.setDate(QDate(2026, 9, 12))
    assert not saved(dialog)
    assert dialog.due.problem.text() == "That time has already passed."
    free(dialog)
    free(parent)


def test_the_problem_line_is_named_for_screen_readers(qapp: QApplication) -> None:  # noqa: F811
    dialog = HomeworkDialog(None, today=TODAY)
    labels = [label for label in dialog.findChildren(QLabel) if label.accessibleName() == "Due date problem"]
    assert len(labels) == 1
    free(dialog)
