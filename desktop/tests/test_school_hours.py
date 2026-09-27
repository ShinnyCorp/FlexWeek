"""School hours asks what setup asks, days and times, and saves School as any block is saved."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QPushButton, QWidget

from desktop.native.widgets import SchoolHoursDialog
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    host,
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
)
from desktop.tests.window_support import window as signed_in  # noqa: F401


@pytest.fixture()
def window(qapp: QApplication, signed_in: NativeWindow) -> Iterator[NativeWindow]:
    """Setup skipped, so there is no School yet."""
    signed_in.findChild(QPushButton, "viewWeek").click()
    settled(qapp, signed_in)
    yield signed_in


def answer(monkeypatch: pytest.MonkeyPatch, change: Callable[[SchoolHoursDialog], None] | None) -> list[dict]:
    """School hours as the student sees it, then Save after `change`, or Cancel with none."""
    seen: list[dict] = []

    def run(dialog: SchoolHoursDialog) -> int:
        seen.append(
            {
                "heading": [label.text() for label in dialog.findChildren(QLabel)][0],
                "days": dialog.days.days(),
                "times": (dialog.times.start.hhmm(), dialog.times.end.hhmm()),
            }
        )
        if change is None:
            dialog.reject()
        else:
            change(dialog)
            dialog.accept()
        return dialog.result()

    monkeypatch.setattr(SchoolHoursDialog, "exec", run)
    return seen


def schools(window: NativeWindow) -> list[tuple]:
    return [
        (block["id"], block["kind"], block["title"], block["days"], block["start"], block["duration_min"])
        for block in window.session.blocks
        if block.get("category") == "class"
    ]


def read_back(qapp: QApplication, window: NativeWindow) -> list[tuple]:
    """The week as the server has it, not as the window last drew it."""
    window.session.blocks = []
    window.session.reload()
    settled(qapp, window)
    return schools(window)


def test_school_hours_adds_school_from_days_and_times(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    def four_days_till_three(dialog: SchoolHoursDialog) -> None:
        dialog.days.buttons[4].setChecked(False)
        dialog.times.start.set_minutes(8 * 60 + 15)
        dialog.times.end.set_minutes(15 * 60)

    assert schools(window) == []
    seen = answer(monkeypatch, four_days_till_three)
    window.findChild(QPushButton, "schoolHours").click()
    settled(qapp, window)
    assert seen == [{"heading": "School hours", "days": [0, 1, 2, 3, 4], "times": ("08:00", "14:30")}]
    assert read_back(qapp, window) == [("school", "locked", "School", [0, 1, 2, 3], "08:15", 405)]


def test_school_hours_changes_the_school_already_there(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    answer(monkeypatch, lambda dialog: None)
    window.findChild(QPushButton, "schoolHours").click()
    settled(qapp, window)

    def later(dialog: SchoolHoursDialog) -> None:
        dialog.days.buttons[5].setChecked(True)
        dialog.times.end.set_minutes(15 * 60 + 15)

    seen = answer(monkeypatch, later)
    window.findChild(QPushButton, "schoolHours").click()
    settled(qapp, window)
    assert seen[0]["days"] == [0, 1, 2, 3, 4] and seen[0]["times"] == ("08:00", "14:30")
    assert read_back(qapp, window) == [("school", "locked", "School", [0, 1, 2, 3, 4, 5], "08:00", 435)]
    answer(monkeypatch, None)
    window.findChild(QPushButton, "schoolHours").click()
    settled(qapp, window)
    assert schools(window) == [("school", "locked", "School", [0, 1, 2, 3, 4, 5], "08:00", 435)], "Cancel"


def test_no_day_ticked_takes_school_off_the_calendar(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    answer(monkeypatch, lambda dialog: None)
    window.findChild(QPushButton, "schoolHours").click()
    settled(qapp, window)
    answer(monkeypatch, lambda dialog: dialog.days.set_days([]))
    window.findChild(QPushButton, "schoolHours").click()
    settled(qapp, window)
    # Before reading back: reloading the week says so, in the same toast.
    assert window.toast.text() == "Deleted School."
    assert read_back(qapp, window) == []


def test_an_end_before_the_start_is_said_and_nothing_is_saved(qapp: QApplication, host: QWidget) -> None:
    dialog = SchoolHoursDialog(host, None)
    dialog.times.end.set_minutes(7 * 60)
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error.text() == "End must be after Start."
    assert dialog.block() is None
    buttons = dialog.findChild(QDialogButtonBox)
    save = buttons.button(QDialogButtonBox.StandardButton.Save)
    cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    assert (save.isDefault(), cancel.property("quiet")) == (True, True), "Save filled, Cancel quiet"
