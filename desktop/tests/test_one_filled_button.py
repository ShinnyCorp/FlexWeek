"""One filled button per dialog: its answer (design review R10).

Every button is drawn filled in the accent unless it is marked otherwise, so a dialog grew two, three
or four of them: More details beside Save, Routines' Save, Apply, Delete and Close. Each dialog is
opened with sample data and its buttons are read off the screen, so a button drawn plain by its
name counts as plain and a new filled one is caught however it got its fill.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable, Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QWidget

    from desktop.native import look_editor, settings, widgets
    from desktop.native.look import pack_stylesheet, resolved_palette
    from desktop.native.widgets import control_art
    from desktop.tests.test_ui_dialogs import _dialog_classes, school
    from desktop.tests.window_support import still


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-one-filled-button-test"])


HOMEWORK = {"id": "essay", "title": "Essay", "due": "2026-09-27T23:59", "estimate_min": 60, "revision": 0}
RESTORE_POINT = {"id": "a", "label": "Monday", "weeks_count": 2}
ROUTINE = {"weekdays": {"id": "weekdays", "name": "School weeks", "blocks": [school()]}}


def makers() -> dict[type, list[Callable[[QWidget], QDialog]]]:
    pasted = {
        "block": school(id="copy", days=[2], start="16:00", duration_min=60),
        "day": 2,
        "fixed": True,
        "checked": True,
    }
    windows = {"work_windows": [{"days": [0, 1], "start": "16:00", "end": "18:00"}]}
    return {
        widgets.BlockDialog: [
            lambda host: widgets.BlockDialog(host, school(), occurrence_day=1),
            lambda host: widgets.BlockDialog(host, None),
        ],
        widgets.HomeworkDialog: [
            lambda host: widgets.HomeworkDialog(host, HOMEWORK, "2026-09-21", waiting=True, pinned=True),
            lambda host: widgets.HomeworkDialog(host, None, "2026-09-21"),
        ],
        widgets.PreviewDialog: [lambda host: widgets.PreviewDialog(host, "Paste", "", [pasted], [school()])],
        widgets.ChooseTimeDialog: [
            lambda host: widgets.ChooseTimeDialog(
                host, {**HOMEWORK, "duration_min": 60, "days": [1]}, "2026-09-21", [1, 2], [school()], None, 1
            )
        ],
        widgets.RoutineDialog: [
            lambda host: widgets.RoutineDialog(host, {}, [school()], "2026-09-21"),
            lambda host: widgets.RoutineDialog(host, ROUTINE, [school()], "2026-09-21"),
        ],
        widgets.LateDialog: [lambda host: widgets.LateDialog(host, "School")],
        widgets.SpreadDialog: [
            lambda host: widgets.SpreadDialog(host, {**HOMEWORK, "unplanned_min": 120}, "2026-09-21")
        ],
        widgets.AvailabilityDialog: [lambda host: widgets.AvailabilityDialog(host, windows, ["Math"])],
        widgets.SchoolHoursDialog: [
            lambda host: widgets.SchoolHoursDialog(host, school()),
            lambda host: widgets.SchoolHoursDialog(host, None),
        ],
        widgets.Dialog: [lambda host: widgets.Dialog(host)],
        widgets.ConfirmSheet: [
            lambda host: widgets.ConfirmSheet(
                host,
                "Sign out",
                "Sure?",
                (("stay", "Cancel", "outlined"), ("yes", "Sign out", "")),
                default="stay",
            )
        ],
        look_editor.ColourSheet: [lambda host: look_editor.ColourSheet(host, "#3d6fc4")],
        settings.RestoreDialog: [
            lambda host: settings.RestoreDialog(host, [RESTORE_POINT], None, None)
        ],
        settings.AccountDialog: [lambda host: settings.AccountDialog(host, 3, {"username": "student"})],
        settings.AlarmRingDialog: [
            lambda host: settings.AlarmRingDialog(host, {"name": "Wake up", "time": "06:45"}, "")
        ],
        settings.TransferPreviewDialog: [lambda host: settings.TransferPreviewDialog(host, {})],
        settings.AboutDialog: [lambda host: settings.AboutDialog(host, {"mode": "local"}, "FlexWeek")],
        settings.HelpDialog: [lambda host: settings.HelpDialog(host)],
        settings.UpdateDialog: [
            lambda host: settings.UpdateDialog(host, {"version": "9.9.9", "notes": "", "url": ""}, "0.13.0")
        ],
    }


def filled(dialog: QDialog, accent: str) -> list[str]:
    """The buttons on screen painted in the accent, read from a picture of each."""
    shown = []
    for button in dialog.findChildren(QPushButton):
        if not button.isVisibleTo(dialog) or button.width() < 8:
            continue
        # A ticked day is a choice shown, like a segment, not a second thing to press.
        if button.isCheckable() and (button.property("pill") or button.objectName() == "setupChip"):
            continue
        # Most of it in the accent. One pixel near the left edge could land on a link's accent words,
        # "Skip this version", depending on the font, and called it filled.
        image = button.grab().toImage()
        wanted = QColor(accent)
        points = [(x, y) for x in range(0, image.width(), 3) for y in range(0, image.height(), 3)]
        inked = sum(1 for x, y in points if image.pixelColor(x, y) == wanted)
        if inked > len(points) / 2:
            shown.append(button.text() or button.objectName())
    return shown


@pytest.mark.parametrize("pack", ["light-frost", "dark-frost"])
def test_every_dialog_has_at_most_one_filled_button(qapp: QApplication, pack: str) -> None:
    made = makers()
    assert set(made) == _dialog_classes(), "a dialog is missing here: add a way to make it"
    palette = resolved_palette(pack, False, None, "default")
    host = QWidget()
    host.setStyleSheet(pack_stylesheet(pack, False, None, "default", palette, control_art(palette)))
    host.show()
    loud = {}
    try:
        for kind, ways in made.items():
            for index, make in enumerate(ways):
                dialog = make(host)
                dialog.show()
                for _ in range(3):
                    qapp.processEvents()
                # What a dialog holds fades in as it opens, and a button caught mid-fade is not filled.
                still(dialog)
                found = filled(dialog, palette["accent"])
                if len(found) > 1:
                    loud[f"{kind.__name__}#{index}"] = found
                dialog.close()
                dialog.deleteLater()
    finally:
        host.deleteLater()
        qapp.processEvents()
    assert loud == {}


def test_the_filled_button_is_the_answer(qapp: QApplication) -> None:
    """The ones that were loud before are outlined (More details) or quiet (Apply, Delete, Close), and the
    answer beside them is still filled."""
    homework = widgets.HomeworkDialog(None, HOMEWORK, "2026-09-21")
    assert homework.more_details.property("outline") is True, "outlined: as words alone it was not seen"
    routines = widgets.RoutineDialog(None, ROUTINE, [school()], "2026-09-21")
    names = {button.objectName(): button for button in routines.findChildren(QPushButton)}
    assert not names["saveRoutine"].property("quiet")
    # Close is the sheet's own x in its corner now, quiet like the rest.
    for name in ("applyRoutine", "deleteRoutine", "sheetClose"):
        assert names[name].property("quiet") is True, name
    late = widgets.LateDialog(None, "School")
    assert late.findChild(QPushButton, "latePreview").property("outlined") is True
    assert not late.accept_button.property("quiet")


def test_routines_and_running_late_say_what_each_part_is_for(qapp: QApplication) -> None:
    """R18: Routines was a list box, an empty box, a date and four filled buttons, and Running late
    an empty box, with nothing saying what either was for. As sheets (0.17.2) each part is a heading
    and a sentence on the one card, not a card inside it."""
    from PySide6.QtWidgets import QFrame, QLabel

    routines = widgets.RoutineDialog(None, {}, [school()], "2026-09-21")
    assert routines.findChildren(QFrame, "dialogCard") == [], "no card inside the card"
    titles = [label.text() for label in routines.findChildren(QLabel, "cardTitle")]
    assert titles == ["Make a routine from this week", "Use a saved routine"]
    notes = routines.findChildren(QLabel, "cardNote")
    assert len(notes) == 2 and all(note.text() for note in notes)
    empty = routines.findChild(QLabel, "routineEmpty")
    assert empty.text() == "No routines saved yet." and not empty.isHidden()
    assert routines.list.isHidden(), "no empty box where the routines would be"
    late = widgets.LateDialog(None, "School")
    assert late.findChild(QLabel, "sheetTitle").text() == "Running late"
    assert late.findChild(QLabel, "cardNote").text()
    assert late.changes.isHidden(), "the list of moves shows once there is a preview"
    late.show_trace({"moves": [], "unplaced": []}, {})
    assert not late.changes.isHidden()


class _Session:
    """What the focus panel reads, for a Quick focus that is running or has ended, or no timer."""

    def __init__(self, phase: str | None) -> None:
        self.focus = None if phase is None else {"title": "Quick focus", "phase": phase, "running": True}
        self.assignments: dict = {}

    def now_next_text(self) -> str:
        return ""

    def now_ms(self) -> int:
        return 0

    def focus_tasks(self) -> list:
        return []


@pytest.mark.parametrize(("phase", "answer"), [("work", "Focus screen"), ("ended", "Finished")])
def test_quick_focus_is_a_card_with_one_filled_button(qapp: QApplication, phase: str, answer: str) -> None:
    from PySide6.QtWidgets import QFrame, QLabel

    panel = settings.FocusPanel()
    panel.set_state(_Session(phase))
    card = panel.findChild(QFrame, "dialogCard")
    assert card.isVisibleTo(panel)
    assert card.findChild(QLabel, "focusTask").text() == "Quick focus"
    assert card.findChild(QLabel, "cardNote").text()
    loud = [
        button.text()
        for button in card.findChildren(QPushButton)
        if button.isVisibleTo(panel) and not button.property("quiet")
    ]
    assert loud == [answer]
    panel.set_state(_Session(None))
    assert not card.isVisibleTo(panel), "no card while no timer runs"
