"""Add and Edit homework with "Spread over days" chosen, through the real window and a real server:
Save keeps the homework as typed and writes its spread sessions the way the old Spread sheet did, with no
second sheet to answer. The clock is held at Thursday 10:00 of the week on screen."""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from desktop.native.calendar import sunday_due
from desktop.native.widgets import HomeworkDialog
from desktop.native.window import NativeWindow
from desktop.tests.test_homework_plan import (  # noqa: F401
    opened_with,
    qapp,
    server,
    session_of,
    settled,
    window,
)


def sessions_of(win: NativeWindow, assignment_id: str) -> list[dict]:
    return sorted(
        (block for block in win.session.blocks if block.get("assignment_id") == assignment_id),
        key=lambda block: (block["days"][0], block.get("start") or ""),
    )


def test_spread_starts_on_the_held_clock_when_selected_day_is_still_wall_friday(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert date.today().weekday() == 4, "needs wall calendar Friday to expose the signup leak"
    window.session.selected_day = date.today().isoformat()
    due = sunday_due(window.session.week_start)[:10]

    def enter(dialog: HomeworkDialog) -> int:
        dialog.show()
        dialog.title.setText("Wall Friday leak")
        dialog.estimate.setValue(180)
        dialog.due.date.setDate(QDate.fromString(due, "yyyy-MM-dd"))
        dialog.spread_choice.setCurrentIndex(1)
        dialog.accept()
        return dialog.result()

    opened_with(monkeypatch, enter)
    window._add_homework()
    settled(qapp, window)
    project = next(
        item for item in window.session.assignments.values() if item["title"] == "Wall Friday leak"
    )
    sessions = sessions_of(window, project["id"])
    assert [(block["days"], block["duration_min"]) for block in sessions] == [([3], 60), ([4], 60), ([5], 60)]


def test_a_new_homework_is_saved_and_spread_over_the_days_to_its_due(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    due = sunday_due(window.session.week_start)[:10]

    def enter(dialog: HomeworkDialog) -> int:
        dialog.show()
        dialog.title.setText("Science project")
        dialog.estimate.setValue(180)
        dialog.due.date.setDate(QDate.fromString(due, "yyyy-MM-dd"))
        dialog.spread_choice.setCurrentIndex(1)
        assert dialog.spread_line.text().startswith("3 × 60 min on different days before it is due")
        dialog.accept()
        return dialog.result()

    opened_with(monkeypatch, enter)
    window._add_homework()
    settled(qapp, window)
    project = next(item for item in window.session.assignments.values() if item["title"] == "Science project")
    assert project["estimate_min"] == 180 and project["due"] == due
    sessions = sessions_of(window, project["id"])
    # Thursday, Friday and Saturday: one 60 minute session a day from today, nothing left whole.
    shape = [(block["days"], block["duration_min"]) for block in sessions]
    assert shape == [([3], 60), ([4], 60), ([5], 60)]
    # As the old Spread sheet wrote them: the preview's ids, each a time that still waits for Plan.
    assert all(block["id"].startswith("b-stage3-") and block["start"] is None for block in sessions)


def test_edit_spreads_a_waiting_homework_and_drops_its_one_waiting_session(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waiting = session_of(window, "math")
    assert not waiting.get("start") and waiting["duration_min"] == 60

    def enter(dialog: HomeworkDialog) -> int:
        dialog.show()
        dialog.estimate.setValue(120)
        dialog.spread_choice.setCurrentIndex(1)
        dialog.accept()
        return dialog.result()

    opened_with(monkeypatch, enter)
    window._edit_homework("math")
    settled(qapp, window)
    sessions = sessions_of(window, "math")
    assert window.session.assignments["math"]["estimate_min"] == 120
    assert [(block["days"], block["duration_min"]) for block in sessions] == [([3], 60), ([4], 60)]
    assert waiting["id"] not in {block["id"] for block in window.session.blocks}


def test_a_time_placed_by_hand_is_replaced_once_flexweek_is_asked_to_pick(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    placed = session_of(window, "essay")
    assert placed["pinned"] and placed["start"] == "19:00"

    def enter(dialog: HomeworkDialog) -> int:
        dialog.show()
        assert not dialog.spread_choice.isVisible(), "a hand-placed time is one time"
        dialog.when.setCurrentIndex(0)
        dialog.estimate.setValue(180)
        dialog.spread_choice.setCurrentIndex(1)
        dialog.accept()
        return dialog.result()

    opened_with(monkeypatch, enter)
    window._edit_homework("essay")
    settled(qapp, window)
    sessions = sessions_of(window, "essay")
    assert placed["id"] not in {block["id"] for block in sessions}
    assert [block["duration_min"] for block in sessions] == [60, 60, 60]
    assert not any(block.get("pinned") for block in sessions)


def test_one_go_still_saves_one_session_and_opens_no_sheet(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def enter(dialog: HomeworkDialog) -> int:
        dialog.show()
        dialog.title.setText("Reading log")
        dialog.estimate.setValue(120)
        dialog.accept()
        return dialog.result()

    opened_with(monkeypatch, enter)
    window._add_homework()
    settled(qapp, window)
    log = next(item for item in window.session.assignments.values() if item["title"] == "Reading log")
    sessions = sessions_of(window, log["id"])
    assert [block["duration_min"] for block in sessions] == [120]
    assert not sessions[0]["id"].startswith("spread-")
