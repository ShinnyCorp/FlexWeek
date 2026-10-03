"""An End of 00:00 means the end of the day, 24:00, and the length counts to it (J1 of the 0.18.1 time
lane). It was refused as "End must be after Start" everywhere an End box was asked for."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QTime
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from desktop.native.fields import ClockField
from desktop.native.setup import QuarterTime
from desktop.native.weekmodel import length_label, set_clock_24h
from desktop.native.widgets import AvailabilityDialog, BlockDialog, SchoolHoursDialog
from desktop.tests.test_clock_field import line_of, select_with_ctrl_a, shown
from desktop.tests.test_setup_wizard import WEEK, opened
from desktop.tests.test_typing_a_time import CLOCKS, type_over
from desktop.tests.window_support import free, host, qapp  # noqa: F401

WAYS = ["24:00", "2400", "00:00", "12:00 am"]


@CLOCKS
@pytest.mark.parametrize("way", WAYS)
def test_the_block_editor_takes_an_end_at_midnight(
    qapp: QApplication, host: QWidget, twenty_four: bool, way: str
) -> None:
    set_clock_24h(twenty_four)
    dialog = BlockDialog(host, day=3, start="22:00", duration_min=60)
    dialog.title.setText("Late club")
    type_over(dialog.end, way)
    assert dialog.duration_line.text() == length_label(120)
    assert dialog.duration_line.property("problem") is False
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted
    block = dialog.block()
    assert (block["start"], block["duration_min"]) == ("22:00", 120)


@CLOCKS
def test_an_event_that_ends_at_midnight_opens_and_saves_as_it_was(
    qapp: QApplication, host: QWidget, twenty_four: bool
) -> None:
    set_clock_24h(twenty_four)
    saved = {
        "id": "late",
        "title": "Late club",
        "kind": "locked",
        "start": "23:00",
        "duration_min": 60,
        "days": [3],
    }
    dialog = BlockDialog(host, saved)
    assert dialog.end.lineEdit().text() == ("24:00" if twenty_four else "12:00 AM")
    assert dialog.duration_line.text() == length_label(60)
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.block()["duration_min"] == 60


def test_the_block_editor_still_refuses_an_end_before_its_start(qapp: QApplication, host: QWidget) -> None:
    dialog = BlockDialog(host, day=3, start="22:00", duration_min=60)
    dialog.title.setText("Club")
    type_over(dialog.end, "21:00")
    dialog.accept()
    assert dialog.result() != dialog.DialogCode.Accepted
    assert dialog.duration_line.text() == "End must be after Start."


@CLOCKS
@pytest.mark.parametrize("way", WAYS)
def test_setup_school_and_activity_hours_take_an_end_at_midnight(
    qapp: QApplication, twenty_four: bool, way: str
) -> None:
    set_clock_24h(twenty_four)
    setup = opened(qapp)
    setup._show(WEEK)
    type_over(setup.school_times.start, "22:00")
    type_over(setup.school_times.end, way)
    row = setup.activities[0]
    row.name.setText("Night shift")
    row.days.set_days([5])
    type_over(row.times.start, "23:00")
    type_over(row.times.end, way)
    assert setup._problem(WEEK) is None
    made = {block["title"]: (block["start"], block["duration_min"]) for block in setup.week_blocks()}
    assert made == {"School": ("22:00", 120), "Night shift": ("23:00", 60)}
    setup.close()


@CLOCKS
@pytest.mark.parametrize("way", WAYS)
def test_the_school_hours_sheet_takes_an_end_at_midnight(
    qapp: QApplication, host: QWidget, twenty_four: bool, way: str
) -> None:
    set_clock_24h(twenty_four)
    dialog = SchoolHoursDialog(host)
    type_over(dialog.times.start, "22:00")
    type_over(dialog.times.end, way)
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted
    school = dialog.block()
    assert school is not None
    assert (school["start"], school["duration_min"]) == ("22:00", 120)


def test_the_school_hours_sheet_opens_on_a_school_that_ends_at_midnight(
    qapp: QApplication, host: QWidget
) -> None:
    school = {
        "id": "school",
        "kind": "locked",
        "title": "School",
        "category": "class",
        "start": "22:00",
        "duration_min": 120,
        "days": [0],
    }
    dialog = SchoolHoursDialog(host, school)
    assert dialog.times.end.hhmm() == "24:00"
    assert dialog.times.span() == ("22:00", 120)


@CLOCKS
@pytest.mark.parametrize("way", WAYS)
def test_study_hours_take_an_end_at_midnight(
    qapp: QApplication, host: QWidget, twenty_four: bool, way: str
) -> None:
    set_clock_24h(twenty_four)
    dialog = AvailabilityDialog(host, {})
    type_over(dialog.study_start, "22:00")
    type_over(dialog.study_end, way)
    dialog._add_study()
    assert dialog.error.text() == ""
    (window,) = dialog.study_windows()
    assert (window["start"], window["duration_min"]) == ("22:00", 120)


def test_a_setup_end_box_steps_up_to_the_end_of_the_day_and_no_further(qapp: QApplication) -> None:
    box = QuarterTime("23:45", end=True)
    box.stepBy(1)
    assert box.minutes() == 24 * 60
    box.stepBy(1)
    assert box.minutes() == 24 * 60
    box.stepBy(-1)
    assert box.hhmm() == "23:45", "and a step down from the end of the day is the quarter before it"


def test_an_end_box_reads_midnight_as_the_end_of_the_day(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
) -> None:
    """J1: 00:00 in an End box is 24:00, drawn as 24:00 (12:00 AM on the 12-hour clock)."""
    for twenty_four, drawn in ((True, "24:00"), (False, "12:00 AM")):
        set_clock_24h(twenty_four)
        field = shown(ClockField(QTime(0, 0), end=True), qapp, host)
        assert line_of(field).text() == drawn
        assert field.minutes() == 24 * 60
        field.setTime(QTime(23, 45))
        QTest.keyClick(field, Qt.Key.Key_Up)
        assert line_of(field).text() == drawn, "one step up from 23:45 is the end of the day"
        assert field.minutes() == 24 * 60
        for way in ("24:00", "2400", "00:00"):
            field.setTime(QTime(9, 0))
            select_with_ctrl_a(field)
            QTest.keyClicks(field, way)
            field.clearFocus()
            field.setFocus()
            assert field.minutes() == 24 * 60, way
            assert line_of(field).text() == drawn, way
        free(field)


def test_a_start_box_keeps_00_00_as_midnight_and_refuses_24_00(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
) -> None:
    set_clock_24h(True)
    field = shown(ClockField(QTime(0, 0)), qapp, host)
    assert line_of(field).text() == "00:00"
    assert field.minutes() == 0
    select_with_ctrl_a(field)
    QTest.keyClicks(field, "24:00")
    field.clearFocus()
    assert field.time() == QTime(0, 0)
    assert line_of(field).text() == "00:00"
    free(field)
