"""Numbers and times without Qt's tiny arrows (T20 of the 0.17.0 audit, 5.2 A of 0.17.2): a length or
a count is − value +, a homework's length has 15/30/45/60/90 pills under it, and a clock time is typed.
Setup, Focus and Alerts each had big boxes with arrows too small to hit."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QDateEdit, QSpinBox, QWidget

from desktop.native.fields import QUICK_LENGTHS, Stepper
from desktop.native.settings import SettingsPage
from desktop.native.setup import SetupPage
from desktop.native.widgets import AvailabilityDialog, BlockDialog, ChooseTimeDialog, HomeworkDialog
from desktop.tests.window_support import free, host, qapp  # noqa: F401

WEEK = "2026-09-21"
FOCUS, ALERTS = 2, 3


def arrows(root: QWidget) -> list[str]:
    """Every number or time box in `root` that still draws Qt's arrows. A date's drop-down is not one,
    nor the year box in a date's month, which is a window of its own."""
    return [
        box.objectName() or type(box).__name__
        for box in root.findChildren(QAbstractSpinBox)
        if not isinstance(box, QDateEdit)
        and box.window() is root.window()
        and box.buttonSymbols() != QAbstractSpinBox.ButtonSymbols.NoButtons
    ]


def unstepped(root: QWidget) -> list[str]:
    """Number boxes not held in a − value + stepper."""
    return [
        box.objectName() or type(box).__name__
        for box in root.findChildren(QSpinBox)
        if box.window() is root.window() and not isinstance(box.parentWidget(), Stepper)
    ]


def test_no_number_or_time_in_the_sheets_setup_or_settings_has_arrows(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
) -> None:
    block = {"id": "s", "title": "Soccer", "kind": "locked", "start": "16:00", "duration_min": 60}
    homework = {"id": "e", "title": "Essay", "due": WEEK, "estimate_min": 60, "duration_min": 60, "days": [1]}
    setup = SetupPage()
    setup.add_homework.click()
    made = [
        HomeworkDialog(host, today=WEEK),
        BlockDialog(host, {**block, "days": [1]}),
        ChooseTimeDialog(host, homework, WEEK, [1, 2], [], None, 1),
        AvailabilityDialog(host, {}),
        SettingsPage(None, {"alarms": []}, {}, {}),
        setup,
    ]
    for root in made:
        assert arrows(root) == [], type(root).__name__
        assert unstepped(root) == [], type(root).__name__
    for root in made:
        free(root)


def test_a_homework_length_steps_by_a_quarter_and_has_quick_lengths(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
) -> None:
    dialog = HomeworkDialog(host, today=WEEK)
    stepper = dialog.estimate.parentWidget()
    assert isinstance(stepper, Stepper)
    assert [chip.text() for chip in stepper.chips] == [str(minutes) for minutes in QUICK_LENGTHS] == [
        "15", "30", "45", "60", "90",
    ]
    assert [chip.isChecked() for chip in stepper.chips] == [False, False, False, True, False]
    stepper.more.click()
    assert dialog.estimate.value() == 75
    assert not any(chip.isChecked() for chip in stepper.chips)
    stepper.chips[0].click()
    assert dialog.estimate.value() == 15
    assert stepper.chips[0].isChecked() and not stepper.less.isEnabled(), "nothing under 15 minutes"
    stepper.less.click()
    assert dialog.estimate.value() == 15
    stepper.chips[2].click()
    stepper.less.click()
    assert dialog.estimate.value() == 30 and stepper.chips[1].isChecked()
    free(dialog)


def test_a_stepper_greys_with_its_box(qapp: QApplication) -> None:  # noqa: F811
    """Setup turns the reminder lead off with its switch; the − and + went on looking pressable."""
    setup = SetupPage()
    setup.reminders.setChecked(True)
    stepper = setup.lead.parentWidget()
    assert stepper.more.isEnabled()
    setup.reminders.setChecked(False)
    assert not setup.lead.isEnabled() and not stepper.more.isEnabled() and not stepper.less.isEnabled()
    free(setup)


def test_volume_reads_80_percent_and_the_timer_preset_is_as_wide_as_the_fields(
    qapp: QApplication,  # noqa: F811
) -> None:
    page = SettingsPage(None, {"alarms": [], "alert_volume": 80}, {}, {})
    page.resize(1280, 800)
    page.show()
    page.nav.setCurrentRow(FOCUS)
    for _ in range(4):
        qapp.processEvents()
    assert page.volume.text() == "80%"
    body = page.stack.widget(FOCUS).widget()

    def edges(widget: QWidget) -> tuple[int, int]:
        left = widget.mapTo(body, QPoint()).x()
        return left, left + widget.width()

    assert edges(page.preset_timer) == edges(page.focus_steppers[0]), "the preset as wide as the fields"
    assert len({edges(stepper) for stepper in page.focus_steppers}) == 1
    free(page)
