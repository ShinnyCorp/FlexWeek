"""A time typed into each place that asks for one is the time that is saved (finding 1 of the 0.18.1 time
lane). The field's own behaviour is in test_clock_field.py; these say each place keeps what was typed."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from desktop.native.fields import ClockField
from desktop.native.settings import SettingsPage
from desktop.native.weekmodel import set_clock_24h
from desktop.native.widgets import AvailabilityDialog, BlockDialog, HomeworkDialog, SchoolHoursDialog
from desktop.tests.test_setup_wizard import WEEK, opened
from desktop.tests.window_support import host, qapp  # noqa: F401

CLOCKS = pytest.mark.parametrize("twenty_four", [True, False])


def type_over(field: ClockField, text: str) -> None:
    """What a student does: select the whole time and write another."""
    QTest.keyClick(field, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(field, text)


@CLOCKS
def test_setup_school_hours_keep_the_typed_times(qapp: QApplication, twenty_four: bool) -> None:
    set_clock_24h(twenty_four)
    setup = opened(qapp)
    setup._show(WEEK)
    type_over(setup.school_times.start, "8:15 am")
    type_over(setup.school_times.end, "3:15 pm")
    (school,) = setup.week_blocks()
    assert (school["start"], school["duration_min"]) == ("08:15", 7 * 60)
    setup.close()


@CLOCKS
def test_setup_activity_hours_keep_the_typed_times(qapp: QApplication, twenty_four: bool) -> None:
    set_clock_24h(twenty_four)
    setup = opened(qapp)
    setup._show(WEEK)
    row = setup.activities[0]
    row.name.setText("Soccer")
    row.days.set_days([1])
    type_over(row.times.start, "4:45 pm")
    type_over(row.times.end, "1830")
    activity = next(block for block in setup.week_blocks() if block["title"] == "Soccer")
    assert (activity["start"], activity["duration_min"]) == ("16:45", 105)
    setup.close()


@CLOCKS
def test_the_school_hours_sheet_keeps_the_typed_times(
    qapp: QApplication, host: QWidget, twenty_four: bool
) -> None:
    set_clock_24h(twenty_four)
    dialog = SchoolHoursDialog(host)
    type_over(dialog.times.start, "07:45")
    type_over(dialog.times.end, "2:30pm")
    dialog.accept()
    school = dialog.block()
    assert school is not None
    assert (school["start"], school["duration_min"]) == ("07:45", 6 * 60 + 45)


@CLOCKS
def test_the_block_editor_keeps_the_typed_times(qapp: QApplication, host: QWidget, twenty_four: bool) -> None:
    set_clock_24h(twenty_four)
    dialog = BlockDialog(host, day=3, start="16:00", duration_min=60)
    dialog.title.setText("Club")
    type_over(dialog.start, "5:15 pm")
    type_over(dialog.end, "1900")
    dialog.accept()
    block = dialog.block()
    assert (block["title"], block["start"], block["duration_min"]) == ("Club", "17:15", 105)


@CLOCKS
def test_add_homework_keeps_the_typed_due_time(qapp: QApplication, host: QWidget, twenty_four: bool) -> None:
    set_clock_24h(twenty_four)
    dialog = HomeworkDialog(
        host, today="2026-09-24", category="assignments", now=datetime(2026, 9, 24, 10, 0)
    )
    dialog.title.setText("Essay")
    dialog.due.timed.setChecked(True)
    type_over(dialog.due.time, "3:15 pm")
    dialog.accept()
    assert dialog.assignment()["due"] == "2026-09-24T15:15"


@CLOCKS
def test_study_hours_keep_the_typed_times(qapp: QApplication, host: QWidget, twenty_four: bool) -> None:
    set_clock_24h(twenty_four)
    dialog = AvailabilityDialog(host, {})
    type_over(dialog.study_start, "4:30 pm")
    type_over(dialog.study_end, "1800")
    dialog._add_study()
    (window,) = dialog.study_windows()
    assert (window["start"], window["duration_min"]) == ("16:30", 90)


@CLOCKS
def test_an_alarm_keeps_the_typed_time(qapp: QApplication, host: QWidget, twenty_four: bool) -> None:
    set_clock_24h(twenty_four)
    page = SettingsPage(host, {"reminders_enabled": True, "alarms": []}, {}, {})
    type_over(page.alarm_time, "6:45 am")
    page.alarm_name.setText("Wake up")
    page.findChild(QWidget, "addAlarm").click()
    assert [alarm["time"] for alarm in page.updates()["alarms"]] == ["06:45"]
