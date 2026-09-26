"""Add homework's Title starts empty, with the category as a hint (0.16 review row R28).

It started filled with the word "Homework", so a student who clicked in and typed got
"HomeworkMath worksheet".
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from desktop.native.widgets import HomeworkDialog
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    PASSWORD,
    USERNAME,
    qapp,
    server,
    signed_out,
    wait_until,
    window,
)


@pytest.mark.parametrize(("category", "hint"), [("assignments", "Homework"), ("study", "Study")])
def test_new_homework_has_an_empty_title_with_the_category_as_its_hint(
    qapp: QApplication,  # noqa: F811
    category: str,
    hint: str,
) -> None:
    dialog = HomeworkDialog(None, today="2026-09-24", category=category)
    assert dialog.title.text() == ""
    assert dialog.title.placeholderText() == hint


def test_typing_the_title_gives_exactly_what_was_typed(qapp: QApplication) -> None:  # noqa: F811
    dialog = HomeworkDialog(None, today="2026-09-24", category="assignments")
    dialog.show()
    dialog.title.setFocus()
    QTest.keyClicks(dialog.title, "Math worksheet")
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.assignment()["title"] == "Math worksheet"
    dialog.close()


def test_saving_with_no_title_asks_for_one_in_words(qapp: QApplication) -> None:  # noqa: F811
    dialog = HomeworkDialog(None, today="2026-09-24", category="assignments")
    dialog.show()
    qapp.processEvents()
    dialog.accept()
    assert dialog.result() != dialog.DialogCode.Accepted
    assert dialog.error.text() == "Give the homework a title."
    assert dialog.error.isVisible()
    dialog.close()


def test_editing_homework_keeps_its_title(qapp: QApplication) -> None:  # noqa: F811
    homework = {
        "id": "essay",
        "title": "History essay",
        "due": "2026-09-25",
        "estimate_min": 60,
        "category": "assignments",
        "revision": 0,
    }
    dialog = HomeworkDialog(None, homework, "2026-09-24")
    assert dialog.title.text() == "History essay"


def test_add_homework_from_the_window_opens_with_the_hint_not_the_word(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, str]] = []

    def run(dialog: HomeworkDialog) -> int:
        seen.append((dialog.title.text(), dialog.title.placeholderText()))
        return 0

    monkeypatch.setattr(HomeworkDialog, "exec", run)
    window._add_homework()
    assert seen == [("", "Homework")]
