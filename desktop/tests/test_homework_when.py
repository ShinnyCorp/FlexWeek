"""Under Due, Add and Edit homework asks "Let FlexWeek pick a time" or "Do it at" a day and time
(finding 32 of the 0.17.2 audit). "Do it at" pins the homework's time, so no plan moves it; the other
choice frees it. A drop on the grid pins too, and reopening the homework shows where it was put."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from desktop.native.widgets import HomeworkDialog
from desktop.tests.test_homework_plan import (  # noqa: F401
    opened_with,
    qapp,
    server,
    session_of,
    settled,
    window,
)
from desktop.tests.window_support import free

WEEK = "2026-09-14"
MONDAY_AT_NOON = datetime(2026, 9, 14, 12, 0)


def host(*sessions: dict, now: datetime = MONDAY_AT_NOON) -> QWidget:
    """A parent whose session has this week's blocks and a clock, as the window's session does."""
    parent = QWidget()
    parent.session = SimpleNamespace(  # type: ignore[attr-defined]
        now_ms=lambda: int(now.timestamp() * 1000), blocks=list(sessions), week_start=WEEK
    )
    return parent


def session(**more: object) -> dict:
    return {
        "id": "s1",
        "title": "History essay",
        "kind": "flexible",
        "assignment_id": "essay",
        "duration_min": 60,
        "days": [3],
        "start": "17:00",
        **more,
    }


def homework(due: str = "2026-09-20") -> dict:
    return {
        "id": "essay",
        "title": "History essay",
        "due": due,
        "estimate_min": 60,
        "category": "assignments",
        "revision": 0,
    }


def opened(parent: QWidget, *, assignment: dict | None = None) -> HomeworkDialog:
    dialog = HomeworkDialog(parent, assignment, "2026-09-14")
    dialog.show()
    QApplication.processEvents()
    return dialog


def chosen_day(dialog: HomeworkDialog) -> list[int]:
    return dialog.when_day.days()


def test_new_homework_asks_who_picks_the_time_and_starts_with_flexweek(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    assert [dialog.when.itemText(i) for i in range(dialog.when.count())] == [
        "Let FlexWeek pick a time",
        "Do it at",
    ]
    assert dialog.when.currentData() == "plan"
    assert not dialog.when_day.isVisible() and not dialog.when_time.isVisible()
    assert not dialog.when_note.isVisible(), "the sheet is tall enough already; the choice's name says it"
    free(dialog)
    free(parent)


def test_do_it_at_shows_one_day_and_a_time_and_says_where_it_stays(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    dialog.when.setCurrentIndex(1)
    assert dialog.when_day.isVisible() and dialog.when_time.isVisible()
    dialog.when_day.set_days([3])
    dialog.when_time.setTime(QTime(17, 0))
    assert dialog.when_note.text() == "Pinned to Thu at 17:00. Plan won't move it."
    free(dialog)
    free(parent)


def test_do_it_at_starts_today_at_the_next_sensible_time(qapp: QApplication) -> None:  # noqa: F811
    noon = host()
    dialog = opened(noon)
    dialog.when.setCurrentIndex(1)
    assert chosen_day(dialog) == [0], "Monday is today"
    assert dialog.when_time.time() == QTime(16, 0), "after school, not at noon"
    free(dialog)
    free(noon)

    evening = host(now=datetime(2026, 9, 14, 17, 10))
    late = opened(evening)
    late.when.setCurrentIndex(1)
    assert late.when_time.time() == QTime(17, 15), "never in the past"
    free(late)
    free(evening)


def test_only_one_day_can_be_picked(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    dialog.when.setCurrentIndex(1)
    dialog.when_day.buttons[3].setChecked(True)
    assert chosen_day(dialog) == [3], "ticking Thursday unticks Monday"
    dialog.when_day.buttons[3].setChecked(False)
    assert chosen_day(dialog) == [3], "a day stays picked"
    free(dialog)
    free(parent)


def test_saving_do_it_at_hands_over_the_day_and_time(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    dialog.title.setText("History essay")
    dialog.due.date.setDate(QDate(2026, 9, 20))
    dialog.when.setCurrentIndex(1)
    dialog.when_day.buttons[4].setChecked(True)
    dialog.when_time.setTime(QTime(16, 30))
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.assignment()["fixed_at"] == {"day": 4, "start": "16:30"}
    free(dialog)
    free(parent)


def test_leaving_the_choice_alone_hands_over_nothing(qapp: QApplication) -> None:  # noqa: F811
    parent = host(session(pinned=True))
    placed = opened(parent, assignment=homework())
    placed.accept()
    assert "fixed_at" not in placed.assignment(), "a pin the student did not touch is not sent again"
    free(placed)
    free(parent)

    planned_parent = host(session())
    planned = opened(planned_parent, assignment=homework())
    planned.accept()
    assert "fixed_at" not in planned.assignment()
    free(planned)
    free(planned_parent)


def test_homework_with_a_pinned_time_opens_on_do_it_at_with_that_day_and_time(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent = host(session(pinned=True, days=[3], start="17:00"))
    dialog = opened(parent, assignment=homework())
    assert dialog.when.currentData() == "fixed"
    assert chosen_day(dialog) == [3]
    assert dialog.when_time.time() == QTime(17, 0)
    assert dialog.when_note.text() == "Pinned to Thu at 17:00. Plan won't move it."
    free(dialog)
    free(parent)


def test_homework_flexweek_planned_opens_on_let_flexweek_pick(qapp: QApplication) -> None:  # noqa: F811
    parent = host(session())
    dialog = opened(parent, assignment=homework())
    assert dialog.when.currentData() == "plan"
    free(dialog)
    free(parent)


def test_choosing_let_flexweek_pick_on_pinned_homework_hands_over_a_release(
    qapp: QApplication,  # noqa: F811
) -> None:
    parent = host(session(pinned=True))
    dialog = opened(parent, assignment=homework())
    dialog.when.setCurrentIndex(0)
    dialog.accept()
    assert "fixed_at" in dialog.assignment() and dialog.assignment()["fixed_at"] is None
    free(dialog)
    free(parent)


def test_homework_spread_over_several_times_keeps_the_spread_way(qapp: QApplication) -> None:  # noqa: F811
    parent = host(session(), session(id="s2", days=[4]))
    dialog = opened(parent, assignment=homework())
    assert not dialog.when.isVisible(), "which of its times would Do it at mean?"
    dialog.accept()
    assert "fixed_at" not in dialog.assignment()
    free(dialog)
    free(parent)


def test_do_it_at_after_it_is_due_is_refused_in_words(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent, assignment=homework(due="2026-09-16T14:00"))
    dialog.when.setCurrentIndex(1)
    dialog.when_day.buttons[3].setChecked(True)
    dialog.when_time.setTime(QTime(17, 0))
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.when_problem.isVisible()
    assert dialog.when_problem.text() == "That ends after it is due."
    free(dialog)
    free(parent)


# Through the window and its session


def test_a_new_homework_saved_with_do_it_at_is_pinned_there(
    qapp: QApplication,  # noqa: F811
    window,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    def act(dialog: HomeworkDialog) -> int:
        dialog.title.setText("Chemistry lab")
        dialog.due.date.setDate(dialog.due.date.date().addDays(3))
        dialog.when.setCurrentIndex(1)
        dialog.when_day.buttons[4].setChecked(True)
        dialog.when_time.setTime(QTime(16, 0))
        dialog.accept()
        return QDialog.DialogCode.Accepted

    opened_with(monkeypatch, act)
    window._add_homework()
    settled(qapp, window)
    made = next(a for a in window.session.assignments.values() if a["title"] == "Chemistry lab")
    block = session_of(window, made["id"])
    assert (block["days"], block["start"], block.get("pinned")) == ([4], "16:00", True)


def test_do_it_at_pins_planned_homework_and_let_flexweek_pick_frees_it_again(
    qapp: QApplication,  # noqa: F811
    window,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    window.session.unpin_assignment("essay")
    window.session.save()
    settled(qapp, window)
    assert not session_of(window, "essay").get("pinned"), "the History essay starts planned, not pinned"

    def pin(dialog: HomeworkDialog) -> int:
        dialog.when.setCurrentIndex(1)
        dialog.when_day.buttons[4].setChecked(True)
        dialog.when_time.setTime(QTime(18, 0))
        dialog.accept()
        return QDialog.DialogCode.Accepted

    opened_with(monkeypatch, pin)
    window._edit_homework("essay")
    settled(qapp, window)
    block = session_of(window, "essay")
    assert (block["days"], block["start"], block.get("pinned")) == ([4], "18:00", True)

    def free_it(dialog: HomeworkDialog) -> int:
        assert dialog.when.currentData() == "fixed", "reopened, it says where it was put"
        dialog.when.setCurrentIndex(0)
        dialog.accept()
        return QDialog.DialogCode.Accepted

    opened_with(monkeypatch, free_it)
    window._edit_homework("essay")
    settled(qapp, window)
    block = session_of(window, "essay")
    assert not block.get("pinned"), "Let FlexWeek pick a time clears the pin"


def test_a_drop_on_the_grid_pins_the_homework_and_reopening_shows_where(
    qapp: QApplication,  # noqa: F811
    window,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    window.session.unpin_assignment("essay")
    window.session.save()
    settled(qapp, window)
    block = session_of(window, "essay")
    assert not block.get("pinned")
    # Friday 16:00 to 17:00, dropped by hand.
    window._move_block(block["id"], block["days"][0], 4, 16 * 60, 17 * 60)
    settled(qapp, window)
    moved = session_of(window, "essay")
    assert (moved["days"], moved["start"], moved.get("pinned")) == ([4], "16:00", True)

    seen = opened_with(monkeypatch, lambda dialog: QDialog.DialogCode.Rejected)
    window._edit_homework("essay")
    dialog = seen[-1]
    assert dialog.when.currentData() == "fixed"
    assert chosen_day(dialog) == [4]
    assert dialog.when_time.time() == QTime(16, 0)
