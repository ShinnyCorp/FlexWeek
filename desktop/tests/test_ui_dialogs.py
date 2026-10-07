"""Dialogs read the way the window reads them: after exec() has returned and the dialog is hidden.

Each test here is a control that looked as if it worked and did nothing, or did something else.
Expected behaviour comes from the web editor (frontend/editor.js) where the web has the same control.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton, QScrollArea, QWidget

    from desktop.native.widgets import AvailabilityDialog, BlockDialog


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    application = QApplication.instance() or QApplication(["flexweek-dialog-test"])
    yield application


def school(**fields: object) -> dict:
    return {
        "id": "school",
        "title": "School",
        "kind": "locked",
        "category": "class",
        "start": "08:00",
        "duration_min": 390,
        "days": [0, 1, 2, 3, 4],
        **fields,
    }


def test_ticking_this_day_was_missed_is_still_known_after_the_dialog_closes(qapp: QApplication) -> None:
    """The window asks recover_missed() once exec() returns, when every child reports not visible."""
    dialog = BlockDialog(None, school(), occurrence_day=2)
    dialog.show()
    qapp.processEvents()
    dialog.missed.setChecked(True)
    dialog.accept()
    assert dialog.isVisible() is False
    assert dialog.recover_missed() is True


def test_a_new_block_never_asks_for_a_missed_replan(qapp: QApplication) -> None:
    dialog = BlockDialog(None, day=0, start="16:00")
    dialog.title.setText("Soccer")
    dialog.missed.setChecked(True)
    dialog.accept()
    assert dialog.recover_missed() is False, "the box is not offered for a block that does not exist yet"


def test_unticking_a_missed_day_restores_it(qapp: QApplication) -> None:
    """The web button reads "Restore Wed" and removes that day from missed_days (editor.js)."""
    dialog = BlockDialog(None, school(missed_days=[1, 2]), occurrence_day=2)
    assert dialog.missed.isChecked() is True
    dialog.missed.setChecked(False)
    dialog.accept()
    assert dialog.block()["missed_days"] == [1]
    assert dialog.recover_missed() is False


def ticked(dialog: BlockDialog) -> list[int]:
    return [index for index, check in enumerate(dialog.days) if check.isChecked()]


def test_trying_this_day_only_and_going_back_keeps_the_series_days(qapp: QApplication) -> None:
    """The web leaves the day boxes alone when the scope changes (editor.js, setEditScope).

    Here "This day only" ticked Wednesday alone and going back only re-enabled the boxes, so Save
    took School off Monday, Tuesday, Thursday and Friday.
    """
    dialog = BlockDialog(None, school(), occurrence_day=2)
    dialog.scope_occurrence.setChecked(True)
    assert ticked(dialog) == [2]
    assert not any(check.isEnabled() for check in dialog.days)
    dialog.scope_series.setChecked(True)
    assert ticked(dialog) == [0, 1, 2, 3, 4]
    assert all(check.isEnabled() for check in dialog.days)
    dialog.accept()
    assert dialog.scope() == "series"
    assert dialog.block()["days"] == [0, 1, 2, 3, 4]


def test_restore_preview_keeps_the_chosen_point(qapp: QApplication) -> None:
    from desktop.native.settings import RestoreDialog

    points = [{"id": "p1", "label": "Before", "created_at": "2026-09-18", "weeks_count": 1}]
    preview = {"id": "p1", "changes": {"weeks": {}, "assignments": {}}}
    first = RestoreDialog(None, points, None, None)
    first.show()
    qapp.processEvents()
    first.list.setCurrentRow(0)
    first._preview()
    assert first.selected_id == "p1"
    reopened = RestoreDialog(None, points, preview, None)
    reopened.show()
    qapp.processEvents()
    reopened._restore()
    assert reopened.selected_id == "p1"


def test_going_back_keeps_a_day_the_student_had_already_unticked(qapp: QApplication) -> None:
    dialog = BlockDialog(None, school(), occurrence_day=2)
    dialog.days[4].setChecked(False)
    dialog.scope_occurrence.setChecked(True)
    dialog.scope_series.setChecked(True)
    dialog.accept()
    assert dialog.block()["days"] == [0, 1, 2, 3]


TRACK = "https://open.spotify.com/playlist/37i9dQZF1DX0XUsuxWHRQd"


def test_a_fixed_commitment_keeps_the_spotify_link_that_was_typed(qapp: QApplication) -> None:
    """The Spotify button already opened a block's link, but nothing here could put one there."""
    dialog = BlockDialog(None, school())
    dialog.spotify.setText(TRACK)
    dialog.accept()
    assert dialog.block()["spotify_url"] == TRACK


def test_an_existing_link_is_shown_so_it_can_be_changed_or_cleared(qapp: QApplication) -> None:
    dialog = BlockDialog(None, school(spotify_url=TRACK))
    assert dialog.spotify.text() == TRACK
    dialog.spotify.clear()
    dialog.accept()
    assert dialog.block()["spotify_url"] is None


def test_a_link_that_is_not_spotify_is_refused_with_a_message(qapp: QApplication) -> None:
    dialog = BlockDialog(None, school())
    dialog.spotify.setText("https://example.com/rickroll")
    dialog.accept()
    assert dialog.isVisible() is False  # never shown, so it cannot be visible either way
    assert dialog.result() != dialog.DialogCode.Accepted
    assert "spotify" in dialog.error.text().lower()


def test_homework_keeps_its_spotify_link_too(qapp: QApplication) -> None:
    from desktop.native.widgets import HomeworkDialog

    dialog = HomeworkDialog(None, None, "2026-09-14")
    dialog.title.setText("Essay")
    dialog.spotify.setText(TRACK)
    dialog.accept()
    assert dialog.assignment()["spotify_url"] == TRACK


def test_the_homework_editor_is_wide_enough_to_read_after_it_was_made_to_scroll(
    qapp: QApplication,
) -> None:
    """A scroll area reports its own width, not its content's, so the dialog came up too narrow to
    read the fields until a minimum was set. It is a form, so as wide as a form's sheet (0.17.2)."""
    from desktop.native.widgets import SHEET_FORM, HomeworkDialog

    dialog = HomeworkDialog(None, None, "2026-09-14")
    dialog.show()
    qapp.processEvents()
    dialog.adjustSize()
    qapp.processEvents()
    assert dialog.width() >= SHEET_FORM
    assert dialog.height() >= 400
    dialog.close()


def test_an_off_grid_estimate_says_to_use_a_multiple_of_fifteen(qapp: QApplication) -> None:
    from desktop.native.widgets import SLOT_HINT, HomeworkDialog

    dialog = HomeworkDialog(None, None, "2026-09-14")
    dialog.title.setText("Essay")
    dialog.estimate.setValue(20)
    dialog.show()
    qapp.processEvents()
    dialog.accept()
    assert dialog.result() != dialog.DialogCode.Accepted
    hint = dialog.findChild(type(dialog.estimate_hint), "homeworkEstimateHint")
    assert hint.text() == SLOT_HINT
    assert hint.isVisible() and hint.property("problem") is True
    assert not dialog.error.isVisible(), "said once, beside the box"
    dialog.close()


def test_homework_optional_fields_sit_behind_more_details(qapp: QApplication) -> None:
    from desktop.native.widgets import HomeworkDialog

    blank = HomeworkDialog(None, None, "2026-09-14")
    blank.show()
    qapp.processEvents()
    assert blank.findChild(type(blank.more_details), "homeworkMoreDetails") is not None
    assert blank._details.isVisible() is False
    blank.more_details.setChecked(True)
    assert blank._details.isVisible() is True
    blank.close()

    filled = HomeworkDialog(
        None,
        {
            "id": "math",
            "title": "Math worksheet",
            "due": "2026-09-14T21:00",
            "estimate_min": 45,
            "revision": 0,
            "course": "Math",
            "notes": "",
            "links": [],
            "checklist": [],
        },
        "2026-09-14",
    )
    filled.show()
    qapp.processEvents()
    assert filled.more_details.isChecked() is True
    assert filled._details.isVisible() is True
    filled.close()


def test_a_fixed_activity_is_a_start_and_an_end_with_the_length_worked_out(qapp: QApplication) -> None:
    """School is 08:00 to 14:30, not 390 minutes. An editable Duration beside End was a second way to
    say the same thing, and the two could disagree."""
    from PySide6.QtCore import QTime
    from PySide6.QtWidgets import QAbstractSpinBox

    dialog = BlockDialog(None, school())
    dialog.show()
    qapp.processEvents()
    assert (dialog.start.time().toString("HH:mm"), dialog.end.time().toString("HH:mm")) == ("08:00", "14:30")
    assert dialog.duration_line.text() == "6 h 30 min"
    assert dialog.findChild(QAbstractSpinBox, "blockDuration") is None
    dialog.end.setTime(QTime(15, 0))
    qapp.processEvents()
    assert dialog.duration_line.text() == "7 h"
    dialog.accept()
    assert dialog.block()["duration_min"] == 420
    dialog.close()


def test_a_fixed_activity_that_ends_before_it_starts_is_refused_beside_the_times(qapp: QApplication) -> None:
    from PySide6.QtCore import QTime

    dialog = BlockDialog(None, school())
    dialog.show()
    qapp.processEvents()
    dialog.end.setTime(QTime(7, 30))
    qapp.processEvents()
    assert dialog.duration_line.text() == "End must be after Start."
    dialog.accept()
    assert dialog.result() != dialog.DialogCode.Accepted
    # Said once, beside the times, as an error; not repeated at the bottom of the form.
    assert dialog.duration_line.property("problem") is True
    assert dialog.error.text() == ""
    dialog.close()


def test_a_fixed_activity_the_editor_cannot_save_is_explained_in_the_apps_words(qapp: QApplication) -> None:
    """The editor checks a block with the server's own rules. Their words ("Value error, spotify_url
    must be an open.spotify.com share link") are not a student's."""
    said = {}
    for field, fill in (("title", "   "), ("days", None), ("spotify", "https://example.com/song")):
        dialog = BlockDialog(None, school())
        if field == "title":
            dialog.title.setText(fill)
        elif field == "days":
            for check in dialog.days:
                check.setChecked(False)
        else:
            dialog.spotify.setText(fill)
        dialog.accept()
        assert dialog.result() != dialog.DialogCode.Accepted
        said[field] = dialog.error.text()
        dialog.close()
    assert said == {
        "title": "Give it a title.",
        "days": "Tick at least one day.",
        "spotify": "That is not a Spotify share link. Paste one that starts with https://open.spotify.com, "
        "or leave it empty.",
    }


def test_a_pasted_block_off_the_quarter_hour_keeps_its_time(qapp: QApplication) -> None:
    """The paste preview offers quarter hours to move to. A block copied from 17:37 showed, and would
    have saved, at 00:00, the first one offered, because 17:37 was not among them."""
    from desktop.native.widgets import PreviewDialog

    pasted = {
        "block": school(id="copy", days=[2], start="17:37", duration_min=43),
        "day": 2,
        "fixed": True,
        "checked": True,
    }
    dialog = PreviewDialog(None, "Paste", "", [pasted], [])
    start = dialog.findChild(QComboBox, "previewStart0")
    length = dialog.findChild(QComboBox, "previewDuration0")
    assert (start.currentText(), length.currentData()) == ("17:37", 43)
    assert [(row["block"]["start"], row["block"]["duration_min"]) for row in dialog.rows()] == [("17:37", 43)]
    dialog.close()


def test_a_bad_username_is_named(qapp: QApplication) -> None:
    from desktop.native.client import USERNAME_ERROR, _error

    err = _error(
        422,
        [
            {
                "type": "string_too_short",
                "loc": ["body", "username"],
                "msg": "String should have at least 3 characters",
                "input": "x",
            }
        ],
    )
    assert err.message == USERNAME_ERROR
    generic = _error(422, [{"type": "value_error", "loc": ["body", "title"], "msg": "title required"}])
    assert "required fields" in generic.message


def test_a_short_password_names_the_field_instead_of_a_generic_check(qapp: QApplication) -> None:
    from desktop.native.client import PASSWORD_LENGTH_HINT, _error

    err = _error(
        422,
        [
            {
                "type": "string_too_short",
                "loc": ["body", "password"],
                "msg": "String should have at least 12 characters",
                "input": "x",
            }
        ],
    )
    assert err.message == PASSWORD_LENGTH_HINT
    generic = _error(422, [{"type": "value_error", "loc": ["body", "title"], "msg": "title required"}])
    assert "required fields" in generic.message
    assert "x" not in err.message


def test_work_windows_can_be_added_edited_and_removed_in_settings(qapp: QApplication) -> None:
    dialog = AvailabilityDialog(None, {}, ["Math"])
    dialog.show()
    qapp.processEvents()
    editor = dialog.work_editor
    assert editor.windows() == []
    assert "any time of day" in editor.findChild(QLabel, "workWindowsMessage").text()

    editor.findChild(QPushButton, "workWindowPresetAfterschool").click()
    row = editor.findChild(QWidget, "workWindowRow")
    editor.set_subjects(["Math", "Reading"])
    assert row.findChild(QComboBox, "workWindowSubject").findText("Reading") >= 0
    row.findChild(QComboBox, "workWindowStart").setCurrentText("15:45")
    row.findChild(QComboBox, "workWindowEnd").setCurrentText("18:15")
    row.findChild(QComboBox, "workWindowSubject").setEditText("Biology")
    row.findChild(QWidget, "workWindowDay4").setChecked(False)
    assert dialog.work_windows() == [
        {"days": [0, 1, 2, 3], "start": "15:45", "end": "18:15", "subject": "Biology"}
    ]

    editor.findChild(QPushButton, "workWindowAdd").click()
    qapp.processEvents()
    scroll = dialog.findChild(QScrollArea)
    assert dialog.width() >= 640
    assert scroll.horizontalScrollBar().maximum() == 0
    rows = editor.findChildren(QWidget, "workWindowRow")
    rows[1].findChild(QComboBox, "workWindowEnd").setCurrentText("24:00")
    rows[0].findChild(QPushButton, "workWindowRemove").click()
    qapp.processEvents()
    assert dialog.work_windows() == [
        {"days": [0, 1, 2, 3, 4], "start": "16:00", "end": "24:00"}
    ]
    assert "only planned between" in editor.findChild(QLabel, "workWindowsMessage").text()
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted


def test_touching_and_overlapping_work_windows_are_kept(qapp: QApplication) -> None:
    windows = [
        {"days": [0], "start": "15:00", "end": "17:00"},
        {"days": [0], "start": "17:00", "end": "19:00"},
        {"days": [0], "start": "16:00", "end": "18:00"},
    ]
    dialog = AvailabilityDialog(None, {"work_windows": windows})
    assert dialog.work_editor.problem() is None
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.work_windows() == windows


def test_work_window_limit_and_reset_in_settings(qapp: QApplication) -> None:
    dialog = AvailabilityDialog(None, {})
    editor = dialog.work_editor
    editor.set_windows([{"days": [0], "start": "16:00", "end": "17:00"} for _ in range(21)])
    assert len(dialog.work_windows()) == 21
    assert not editor.findChild(QPushButton, "workWindowAdd").isEnabled()
    assert editor.findChild(QLabel, "workWindowsLimit").text() == "21 is the most you can add."
    editor.set_windows([])
    assert editor.findChild(QLabel, "workWindowsLimit").text() == "", "nothing to say below the limit"
    assert dialog.work_windows() == []
    assert editor.findChild(QPushButton, "workWindowAdd").isEnabled()


def test_work_window_end_before_start_is_refused_beside_end(qapp: QApplication) -> None:
    dialog = AvailabilityDialog(
        None,
        {"work_windows": [{"days": [5, 6], "start": "10:00", "end": "12:00"}]},
    )
    dialog.show()
    qapp.processEvents()
    row = dialog.work_editor.findChild(QWidget, "workWindowRow")
    row.findChild(QComboBox, "workWindowEnd").setCurrentText("09:45")
    qapp.processEvents()
    error = row.findChild(QLabel, "validationError")
    assert error.text() == "End must be after Start."
    assert error.isVisible()
    assert dialog.work_editor.problem() == "End must be after Start."
    dialog.accept()
    assert dialog.result() != dialog.DialogCode.Accepted
    assert dialog.error.text() == ""

    row.findChild(QComboBox, "workWindowEnd").setCurrentText("12:00")
    qapp.processEvents()
    assert error.text() == ""
    assert dialog.work_editor.problem() is None
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted


def _homework(due: str) -> dict:
    return {
        "id": "oral",
        "title": "French oral",
        "due": due,
        "estimate_min": 30,
        "revision": 0,
        "notes": "",
        "links": [],
        "checklist": [],
    }


def test_new_homework_is_due_on_a_day_and_a_time_only_when_asked(qapp: QApplication) -> None:
    from desktop.native.widgets import HomeworkDialog

    dialog = HomeworkDialog(None, None, "2026-09-14")
    dialog.show()
    qapp.processEvents()
    assert dialog.due.value() == "2026-09-15", "tomorrow, whatever the hour"
    assert not dialog.due.time.isVisible(), "no time box until the student says it is due at one"
    dialog.due.timed.setChecked(True)
    assert dialog.due.time.isVisible()
    assert dialog.due.value() == "2026-09-15T15:00", "the end of the school day, 15:00 with none saved"
    dialog.close()


def test_an_old_end_of_day_due_is_kept_as_stored_until_the_deadline_changes(qapp: QApplication) -> None:
    from PySide6.QtCore import QDate

    from desktop.native.widgets import HomeworkDialog

    kept = HomeworkDialog(None, _homework("2026-09-20T23:59"), "2026-09-14")
    assert not kept.due.timed.isChecked(), "23:59 was the old way of saying no time"
    kept.title.setText("French oral, part 2")
    kept.accept()
    assert kept.assignment()["due"] == "2026-09-20T23:59"

    moved = HomeworkDialog(None, _homework("2026-09-20T23:59"), "2026-09-14")
    moved.due.date.setDate(QDate(2026, 9, 18))
    moved.accept()
    assert moved.assignment()["due"] == "2026-09-18"


def test_a_due_time_is_shown_and_can_be_taken_away(qapp: QApplication) -> None:
    from PySide6.QtCore import QTime

    from desktop.native.widgets import HomeworkDialog

    dialog = HomeworkDialog(None, _homework("2026-09-17T10:15"), "2026-09-14")
    assert dialog.due.timed.isChecked() and dialog.due.time.time() == QTime(10, 15)
    dialog.due.time.setTime(QTime(8, 30))
    dialog.accept()
    assert dialog.assignment()["due"] == "2026-09-17T08:30"

    untimed = HomeworkDialog(None, _homework("2026-09-17T10:15"), "2026-09-14")
    untimed.due.timed.setChecked(False)
    untimed.accept()
    assert untimed.assignment()["due"] == "2026-09-17"


def _dialog_classes() -> set[type]:
    from PySide6.QtWidgets import QDialog

    import desktop.native.window  # noqa: F401 - brings in every module that defines a dialog

    found, waiting = set(), [QDialog]
    while waiting:
        for kind in waiting.pop().__subclasses__():
            waiting.append(kind)
            if kind.__module__.startswith("desktop.native."):
                found.add(kind)
    return found


def test_every_dialog_is_freed_once_it_has_closed_and_is_let_go(qapp: QApplication) -> None:
    """PySide gives an exec()'d dialog to Python, to be freed with its last reference. A button
    wired to a lambda that named the dialog kept that reference inside Qt, where the garbage
    collector cannot reach it, so the dialog outlived its use. At quit PySide then deleted it and the
    window it belongs to one after the other, and FlexWeek crashed on the way out: "shared QObject
    was deleted directly", then a bus error."""
    import gc
    import weakref

    from PySide6.QtCore import QTimer

    from desktop.native import look_editor, settings, widgets

    homework = {"id": "essay", "title": "Essay", "due": "2026-09-27T23:59", "estimate_min": 60, "revision": 0}
    pasted = {
        "block": school(id="copy", days=[2], start="16:00", duration_min=60),
        "day": 2,
        "fixed": True,
        "checked": True,
    }
    made = {
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
        widgets.BlockDialog: [lambda host: widgets.BlockDialog(host, school(), occurrence_day=1)],
        widgets.HomeworkDialog: [
            lambda host: widgets.HomeworkDialog(host, homework, "2026-09-21", waiting=True, pinned=True),
            lambda host: widgets.HomeworkDialog(host, None, "2026-09-21"),
        ],
        widgets.PreviewDialog: [lambda host: widgets.PreviewDialog(host, "Paste", "", [pasted], [school()])],
        widgets.ChooseTimeDialog: [
            lambda host: widgets.ChooseTimeDialog(
                host, {**homework, "duration_min": 60, "days": [1]}, "2026-09-21", [1, 2], [school()], None, 1
            )
        ],
        widgets.RoutineDialog: [lambda host: widgets.RoutineDialog(host, {}, [school()], "2026-09-21")],
        widgets.LateDialog: [lambda host: widgets.LateDialog(host, "School")],
        widgets.SpreadDialog: [
            lambda host: widgets.SpreadDialog(host, {**homework, "unplanned_min": 120}, "2026-09-21")
        ],
        widgets.AvailabilityDialog: [lambda host: widgets.AvailabilityDialog(host, {}, ["Math"])],
        widgets.SchoolHoursDialog: [
            lambda host: widgets.SchoolHoursDialog(host, school()),
            lambda host: widgets.SchoolHoursDialog(host, None),
        ],
        settings.RestoreDialog: [lambda host: settings.RestoreDialog(host, [], None, None)],
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
    assert set(made) == _dialog_classes(), "a dialog is missing here: add a way to make it"
    host = QWidget()
    host.show()
    kept = []
    for kind, makers in made.items():
        for make in makers:
            dialog = make(host)
            QTimer.singleShot(0, dialog.reject)
            dialog.exec()
            gone = weakref.ref(dialog)
            del dialog
            gc.collect()
            if gone() is not None:
                kept.append(kind.__name__)
                gone().deleteLater()
                qapp.processEvents()
    host.deleteLater()
    assert kept == [], f"still alive after closing and being let go: {kept}"
