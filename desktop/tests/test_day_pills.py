"""Days are picked with pills everywhere (T19 and X7 of the 0.17.0 audit, 5.2 A of 0.17.2): the block
editor's Add fixed time used check boxes while setup used pills, so one choice looked two ways."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QWidget

from desktop.native.calendar import DAYS
from desktop.native.widgets import BlockDialog
from desktop.tests.window_support import free, host, qapp  # noqa: F401


def day_boxes(root: QWidget) -> list[str]:
    """Check boxes named for a day: what the pills replace."""
    return [box.text() for box in root.findChildren(QCheckBox) if box.text() in DAYS]


def pills(root: QWidget) -> list[QPushButton]:
    return [button for button in root.findChildren(QPushButton) if button.property("pill")]


def test_the_block_editor_picks_its_days_with_pills(qapp: QApplication, host: QWidget) -> None:  # noqa: F811
    block = {"id": "s", "title": "Soccer", "kind": "locked", "start": "16:00", "duration_min": 60}
    dialog = BlockDialog(host, {**block, "days": [1]})
    assert day_boxes(dialog) == []
    shown = pills(dialog)
    assert [pill.text() for pill in shown] == list(DAYS)
    assert [pill.isChecked() for pill in shown] == [day == 1 for day in range(7)]
    shown[3].click()
    dialog.accept()
    assert dialog.block()["days"] == [1, 3]
    free(dialog)


def test_routines_school_hours_and_work_hours_pick_days_with_pills(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
) -> None:
    """X7: setup's planning-hours step ticked work hours' days in check boxes. (Availability edits
    each day on its own row since #54, so it has no days to pick.)"""
    from desktop.native.widgets import RoutineDialog, SchoolHoursDialog
    from desktop.native.work_windows import WorkWindowsEditor

    routines = RoutineDialog(host, {}, [], "2026-09-21")
    school = SchoolHoursDialog(host, None)
    work = WorkWindowsEditor([{"days": [0, 2], "start": "16:00", "end": "18:00"}])
    for made in (routines, school, work):
        assert day_boxes(made) == [], type(made).__name__
        assert [pill.text() for pill in pills(made)] == list(DAYS), type(made).__name__
    pills(routines)[6].click()
    assert routines.selected_days() == [0, 1, 2, 3, 4, 5]
    pills(school)[0].click()
    assert school.days.days() == [1, 2, 3, 4]
    pills(work)[4].click()
    assert work.windows()[0]["days"] == [0, 2, 4]
    for made in (routines, school):
        free(made)
    free(work)


def test_alarm_days_are_pills_on_one_row(qapp: QApplication) -> None:  # noqa: F811
    """T21: the alarm's days wrapped into two rows of check boxes, Monday to Thursday then Friday to
    Sunday."""
    from desktop.native.settings import SettingsPage

    page = SettingsPage(None, {"alarms": []}, {}, {})
    page.resize(1280, 800)
    page.show()
    page.nav.setCurrentRow(3)
    qapp.processEvents()
    days = [pill for pill in pills(page) if pill.objectName().startswith("alarmDay")]
    assert [pill.text() for pill in days] == list(DAYS)
    assert [pill.isChecked() for pill in days] == [True] * 5 + [False] * 2
    assert len({pill.mapToGlobal(pill.rect().topLeft()).y() for pill in days}) == 1, "one row"
    assert day_boxes(page) == []
    free(page)


def test_setup_picks_school_and_activity_days_with_pills(qapp: QApplication) -> None:  # noqa: F811
    from desktop.native.setup import ActivityRow, SetupPage

    setup = SetupPage()
    row = ActivityRow("Soccer", [1, 3])
    for made in (setup, row):
        assert day_boxes(made) == []
    assert [pill.isChecked() for pill in pills(row)] == [day in (1, 3) for day in range(7)]
    # The planning-hours step: a row of hours, as its + buttons add.
    setup.work_editor.add_button.click()
    assert day_boxes(setup.work_editor) == []
    assert [pill.text() for pill in pills(setup.work_editor)] == list(DAYS)
    free(row)
    free(setup)
