"""0.19.0 wording audit, fix-first findings 1-7, 9, 46 and 47: what a student reads when an import is
confirmed, an undo is said, Plan cannot start, a homework is typed, or a file will not open.
Expected words come from the audit's suggestions (03-wording-audit.md), not from the code's output."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QLabel, QPlainTextEdit, QPushButton, QWidget

from backend.explain import sentence
from desktop.native import window as window_module
from desktop.native.reuse import week_label
from desktop.native.settings import AccountDialog, HelpDialog, TransferPreviewDialog
from desktop.native.widgets import HomeworkDialog
from desktop.native.window import NativeWindow
from desktop.server import LocalServer
from desktop.tests.logic_support import essay, fixed, settled, signed_in
from desktop.tests.window_support import free, qapp, server, signed_out, window  # noqa: F401

PREVIEW = {
    "source_username": "joo2",
    "changes": {
        "weeks": {"added": ["2026-10-05"], "changed": ["2026-10-12", "2026-10-19"], "removed": []},
        "assignments": {"added": [{"id": "a"}, {"id": "b"}, {"id": "c"}], "changed": [], "removed": []},
        "preferences_changed": True,
    },
}


def texts(root: QWidget) -> list[str]:
    return [label.text() for label in root.findChildren(QLabel)]


# Finding 1: the import preview is sentences, not a data dump.


def test_the_import_preview_counts_what_changes_in_words(qapp: QApplication) -> None:
    dialog = TransferPreviewDialog(None, PREVIEW)
    assert dialog.windowTitle() == "Import backup file?"
    assert texts(dialog) == [
        "From joo2's backup: 1 week added, 2 weeks replaced, 3 homework added. "
        "Your settings will be replaced.",
        "FlexWeek saves a restore point first, so you can go back.",
    ]
    assert dialog.findChildren(QPlainTextEdit) == []
    ok = [b for b in dialog.findChildren(QPushButton) if b.text() == "Import"]
    assert len(ok) == 1
    free(dialog)


def test_an_import_that_changes_nothing_says_so(qapp: QApplication) -> None:
    dialog = TransferPreviewDialog(None, {"source_username": "joo2", "changes": {}})
    assert texts(dialog)[0] == "From joo2's backup: Nothing in it is different from your account."
    free(dialog)


# Finding 2: undoing an add says adding.


def test_undo_and_redo_of_an_add_say_adding_and_of_a_change_say_editing(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    block = fixed("school", "School", 0, "08:00")
    session.add_block(block)
    session.save()
    settled(qapp, session)
    session.undo()
    settled(qapp, session)
    assert session.message == "Undid adding School."
    session.redo()
    settled(qapp, session)
    assert session.message == "Redid adding School."
    session.add_block({**block, "title": "Lessons"})
    session.save()
    settled(qapp, session)
    session.undo()
    settled(qapp, session)
    assert session.message == "Undid editing Lessons."


def test_undo_of_new_homework_says_adding_and_of_a_changed_one_says_editing(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    session.add_homework(essay(session))
    session.save()
    settled(qapp, session)
    session.undo()
    settled(qapp, session)
    assert session.message == "Undid adding Essay."
    session.redo()
    settled(qapp, session)
    session.add_homework({**session.assignments["essay"], "notes": "Cite two sources"})
    session.save()
    settled(qapp, session)
    session.undo()
    settled(qapp, session)
    assert session.message == "Undid editing Essay."


# Finding 3: Plan names the real reason it cannot start.


@pytest.mark.parametrize(
    ("planning", "conflict", "pending", "said"),
    [
        (True, False, False, "Planning… one moment."),
        (False, True, True, "This week changed in another window. Reload it from More, then plan again."),
        (False, False, True, "Saving your last change… Plan will work in a moment."),
    ],
)
def test_plan_says_planning_saving_or_out_of_step(
    qapp: QApplication,
    server: LocalServer,
    monkeypatch: pytest.MonkeyPatch,
    planning: bool,
    conflict: bool,
    pending: bool,
    said: str,
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    monkeypatch.setattr(type(session), "planning", property(lambda _self: planning))
    session.conflict = conflict
    session.pending_save = {"weeks": [], "assignments": [], "operation_id": "x"} if pending else None
    session.solve()
    assert session.message == said


def test_the_greyed_tip_names_the_same_three_causes(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = window.session
    session.conflict = True
    assert window._more_tip("solveButton", False) == (
        "This week changed in another window. Reload it from More first."
    )
    session.conflict = False
    monkeypatch.setattr(type(session), "planning", property(lambda _self: True))
    assert window._more_tip("solveButton", False) == "Planning… one moment."
    monkeypatch.undo()
    session.pending_save = {"weeks": [], "assignments": [], "operation_id": "x"}
    assert window._more_tip("solveButton", False) == "Saving your last change… this will work in a moment."
    session.pending_save = None


# Findings 4 and 5: the planner's reasons.


def test_the_two_no_room_reasons_say_who_is_in_the_way_and_what_to_do() -> None:
    assert sentence("NO_SLOT_LEFT") == (
        "Your other homework is using every free gap before it's due. "
        "Move or shorten one, or choose a time yourself."
    )
    assert sentence("LOCKED_OVERLAP") == (
        "Your fixed times and finished work leave no gap long enough for it before it's due. "
        "Shorten it, split it, or change the due date."
    )


def test_the_type_reason_names_the_order_instead_of_priority() -> None:
    reason = sentence("PRIORITY_PREEMPT")
    assert "priority" not in reason.lower()
    assert "tests, then quizzes, then everyday homework, then reading" in reason


def test_the_homework_form_asks_for_a_type_not_a_priority(qapp: QApplication) -> None:
    dialog = HomeworkDialog(None, None, "2026-10-12")
    box = dialog.priority
    assert [box.itemText(i) for i in range(box.count())] == [
        "Test prep",
        "Quiz prep",
        "Everyday homework",
        "Reading",
    ]
    said = texts(dialog)
    assert "Type" in said and "Priority" not in said
    assert "Tests are planned first, then quizzes, then everyday homework, then reading." in said
    free(dialog)


# Finding 7: the pinned time is called pinned (Due by and Do it at stay).


def test_do_it_at_says_pinned_in_the_clock_the_account_uses(qapp: QApplication) -> None:
    from PySide6.QtCore import QTime

    from desktop.native.weekmodel import set_clock_24h

    set_clock_24h(False)
    try:
        dialog = HomeworkDialog(None, None, "2026-10-12")
        dialog.show()
        dialog.when.setCurrentIndex(1)
        dialog.when_day.set_days([3])
        dialog.when_time.setTime(QTime(17, 0))
        assert dialog.when_note.text() == "Pinned to Thu at 5:00 PM. Plan won't move it."
        free(dialog)
    finally:
        set_clock_24h(True)


# Finding 6: an import that cannot happen says why, and replacing asks in a dialog.


def test_a_file_for_another_week_says_nothing_was_imported_and_where_to_go(
    qapp: QApplication, server: LocalServer
) -> None:
    session = signed_in(qapp, server.origin, "alice", create=True)
    other = {**session.week_file(), "week_start": "2026-10-12"}
    other_label = week_label("2026-10-12", session.today_iso())
    assert session.import_week_file(json.dumps(other)) is False
    assert session.message == (
        f"Nothing imported: this file is for {other_label}. Go to that week, then import again."
    )


def test_replacing_a_week_from_a_file_asks_in_a_dialog_with_the_real_choice(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = window.session
    session.add_block(fixed("school", "School", 0, "08:00"))
    path = tmp_path / "week.json"
    path.write_text(json.dumps(session.week_file()))
    asked: list[tuple[str, str, str]] = []

    def refuse(_parent: object, title: str, question: str, yes: str, **_more: object) -> bool:
        asked.append((title, question, yes))
        return False

    monkeypatch.setattr(window_module, "confirm", refuse)
    monkeypatch.setattr(AccountDialog, "exec", lambda dialog: _choose(dialog, "import-week"))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(path), ""))
    window._open_account()
    label = week_label(session.week_start, window._today())
    assert asked == [
        (
            "Replace week",
            f"Replace everything in {label} with this file? Other weeks aren't changed. You can undo this.",
            "Replace week",
        )
    ]


def _choose(dialog: AccountDialog, action: str) -> QDialog.DialogCode:
    dialog.action = action
    return QDialog.DialogCode.Accepted


# Finding 9: file errors carry no system text.


@pytest.mark.parametrize("action", ["import", "import-week"])
def test_a_file_that_will_not_open_says_how_to_choose_one(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, action: str
) -> None:
    missing = tmp_path / "gone.json"
    monkeypatch.setattr(AccountDialog, "exec", lambda dialog: _choose(dialog, action))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(missing), ""))
    window._open_account()
    assert window.session.message == (
        "Couldn't open that file. Choose a FlexWeek backup file (it ends in .json)."
    )


def test_a_file_that_will_not_be_written_says_to_choose_another_folder(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    nowhere = tmp_path / "no-such-folder" / "week.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(nowhere), ""))
    window._write_json("week.json", {})
    assert window.session.message == "Couldn't save there. Choose another folder, like Documents."


def test_manage_account_calls_the_file_a_backup_file(qapp: QApplication, window: NativeWindow) -> None:
    dialog = AccountDialog(window, 0, None)
    names = {b.objectName(): b.text() for b in dialog.findChildren(QPushButton)}
    assert names["exportAccount"] == "Export backup file"
    assert names["importAccount"] == "Import backup file"
    free(dialog)


# Finding 46: Help explains Plan.


def test_help_opens_with_how_planning_works(qapp: QApplication, window: NativeWindow) -> None:
    dialog = HelpDialog(window)
    headings = [label.text() for label in dialog.findChildren(QLabel, "prefsHeading")]
    assert headings[:3] == ["How planning works", "The screens", "Keyboard shortcuts"]
    body = dialog.findChild(QLabel, "helpPlanning").text()
    for part in ("Plan my homework", "Replan all", "Not placed yet", "Details", "Ctrl+K"):
        assert part in body
    free(dialog)


# Finding 47: lost codes.


def test_reset_password_says_what_to_do_without_codes(qapp: QApplication, signed_out: NativeWindow) -> None:
    window = signed_out
    window.forgot_button.click()
    qapp.processEvents()
    note = window.auth_note.text()
    assert note.startswith("Use one of the recovery codes you saved when you made your account.")
    assert "Lost them too?" in note
    assert "Create a new account and import a backup file" in note
    assert "start fresh" in note


def test_create_account_asks_for_a_backup_now_and_then(qapp: QApplication, signed_out: NativeWindow) -> None:
    window = signed_out
    window.auth_switch.click()
    qapp.processEvents()
    assert "Export a backup file now and then" in window.auth_note.text()
