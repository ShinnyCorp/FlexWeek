"""Regression (item 2): a time that has already passed is refused everywhere a student can
give homework a time by hand: dropping a block (and its drag preview), Choose a time, and Edit
homework > Do it at. The refusal reads "That's in the past." (controller.PAST_DROP).

The clock is held through `session.now_ms` (grid_support.hold_clock), the injectable clock the window,
the dialogs (`HomeworkDialog._now`) and the planner already read. """

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QTime
from PySide6.QtWidgets import QDialog, QDialogButtonBox

from desktop.native.calendar import sunday_due
from desktop.native.controller import PAST_DROP
from desktop.native.widgets import ChooseTimeDialog, HomeworkDialog
from desktop.native.window import NativeWindow
from desktop.tests.grid_support import (  # noqa: F401
    WEDNESDAY,
    hold_clock,
    qapp,
    server,
    settled,
    signed_in,
    signed_out,
    window,
)
from desktop.tests.window_support import free

TUESDAY, SUNDAY = 1, 6
NOW = 14 * 60 + 7  # the window fixture holds Wednesday 14:07


def homework(qapp, window: NativeWindow, start: str | None = None, day: int = WEDNESDAY) -> dict:
    """The History essay, due Sunday, with one session: waiting for a time, or placed at `start`."""
    session = window.session
    session.add_homework({"id": "essay", "title": "History essay", "due": sunday_due(session.week_start),
                          "estimate_min": 60, "revision": 0})
    session.save()
    settled(qapp, window)
    block = next(b for b in session.blocks if b.get("assignment_id") == "essay")
    if start is not None:
        h, m = map(int, start.split(":"))
        assert session.place_session(block["id"], day, h * 60 + m)
        session.save()
        settled(qapp, window)
    hold_clock(window, WEDNESDAY, NOW)
    return next(b for b in session.blocks if b.get("assignment_id") == "essay")


def where(window: NativeWindow, block_id: str) -> tuple[list[int], str | None]:
    block = next(b for b in window.session.blocks if b["id"] == block_id)
    return block["days"], block.get("start")


# Drag and drop -------------------------------------------------------------------------------


def test_dragging_a_block_to_earlier_today_is_refused_in_preview_and_drop(qapp, window) -> None:
    block = homework(qapp, window, "16:00")
    verdict = window._judge_span(block["id"], WEDNESDAY, WEDNESDAY, 7 * 60, 8 * 60)
    assert (verdict.ok, verdict.words) == (False, PAST_DROP), "the live preview must refuse"
    window._move_block(block["id"], WEDNESDAY, WEDNESDAY, 7 * 60, 8 * 60)
    settled(qapp, window)
    assert where(window, block["id"]) == ([WEDNESDAY], "16:00"), "the drop must leave it where it was"


def test_dropping_homework_that_needs_a_time_on_earlier_today_is_refused(qapp, window) -> None:
    block = homework(qapp, window)
    assert block.get("start") is None
    window._move_block(block["id"], -1, WEDNESDAY, 9 * 60, 10 * 60)
    settled(qapp, window)
    assert where(window, block["id"])[1] is None


def test_dragging_a_block_to_an_earlier_day_is_refused(qapp, window) -> None:
    """Guard: refused today, and must stay refused."""
    block = homework(qapp, window, "16:00")
    verdict = window._judge_span(block["id"], WEDNESDAY, TUESDAY, 16 * 60, 17 * 60)
    assert (verdict.ok, verdict.words) == (False, PAST_DROP)


def test_dragging_a_block_to_later_today_is_allowed(qapp, window) -> None:
    """Guard: a start after now is fine."""
    block = homework(qapp, window, "16:00")
    window._move_block(block["id"], WEDNESDAY, WEDNESDAY, 18 * 60, 19 * 60)
    settled(qapp, window)
    assert where(window, block["id"]) == ([WEDNESDAY], "18:00")


def test_stretching_the_end_of_a_block_already_under_way_is_allowed(qapp, window) -> None:
    """Guard: a block that started at 14:00 may keep its start while its end moves (spec item 2)."""
    block = homework(qapp, window, "14:00")
    verdict = window._judge_span(block["id"], WEDNESDAY, WEDNESDAY, 14 * 60, 16 * 60)
    assert verdict.ok, verdict.words


# Choose a time -------------------------------------------------------------------------------


def choose(qapp, window, monkeypatch, day: int, minute: int) -> tuple[bool, str]:
    seen: list[tuple[bool, str]] = []

    def pick(dialog: ChooseTimeDialog) -> int:
        dialog.day.set_days([day])
        dialog.start.setTime(QTime(minute // 60, minute % 60))
        dialog._check()
        ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
        seen.append((ok, dialog.problem.text() if dialog.problem.isVisibleTo(dialog) else ""))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(ChooseTimeDialog, "exec", pick)
    window._choose_time("essay")
    assert len(seen) == 1, "Choose a time did not open"
    return seen[0]


@pytest.mark.parametrize(
    ("day", "minute"), [(TUESDAY, 16 * 60), (WEDNESDAY, 14 * 60)], ids=["Tue16:00", "Wed14:00"]
)
def test_choose_a_time_refuses_a_past_time(qapp, window, monkeypatch, day, minute) -> None:
    homework(qapp, window)
    assert choose(qapp, window, monkeypatch, day, minute) == (False, PAST_DROP)


def test_choose_a_time_accepts_later_today(qapp, window, monkeypatch) -> None:
    """Guard."""
    homework(qapp, window)
    ok, _problem = choose(qapp, window, monkeypatch, WEDNESDAY, 14 * 60 + 15)
    assert ok


def test_choose_a_time_never_suggests_a_past_time(qapp, window, monkeypatch) -> None:
    homework(qapp, window)
    hold_clock(window, SUNDAY, 23 * 60 + 30)
    seen: list[tuple[int, int, bool]] = []

    def look(dialog: ChooseTimeDialog) -> int:
        day, start = dialog.choice()
        seen.append((day, start, dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(ChooseTimeDialog, "exec", look)
    window._choose_time("essay")
    day, start, ok = seen[0]
    said = f"suggested day {day} {start // 60:02d}:{start % 60:02d}"
    assert (day, start) >= (SUNDAY, 23 * 60 + 30) or not ok, said


# Do it at ------------------------------------------------------------------------------------


def do_it_at(qapp, window, day: int, minute: int) -> tuple[int, str]:
    session = window.session
    dialog = HomeworkDialog(window, session.assignments["essay"])
    try:
        dialog.when.setCurrentIndex(1)  # "Do it at"
        dialog.when_day.set_days([day])
        dialog._pick_day()
        dialog.when_time.setTime(QTime(minute // 60, minute % 60))
        dialog.accept()
        qapp.processEvents()
        problem = dialog.when_problem.text() if dialog.when_problem.isVisibleTo(dialog) else ""
        return dialog.result(), problem
    finally:
        dialog.hide()
        free(dialog)


@pytest.mark.parametrize(
    ("day", "minute"), [(WEDNESDAY, 9 * 60), (TUESDAY, 18 * 60)], ids=["Wed09:00", "Tue18:00"]
)
def test_do_it_at_refuses_a_past_time_and_keeps_the_sheet_open(qapp, window, day, minute) -> None:
    homework(qapp, window)
    result, problem = do_it_at(qapp, window, day, minute)
    assert (result, problem) == (QDialog.DialogCode.Rejected.value, PAST_DROP)


def test_do_it_at_saves_later_today(qapp, window) -> None:
    """Guard."""
    homework(qapp, window)
    result, problem = do_it_at(qapp, window, WEDNESDAY, 18 * 60)
    assert (result, problem) == (QDialog.DialogCode.Accepted.value, "")
