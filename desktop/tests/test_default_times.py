"""A new event, Choose a time and Running late start at a time that is still ahead (findings 3 and 5 of
the 0.18.1 time lane): the next quarter hour, rounded up, never one that has passed."""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog

from desktop.native.weekmodel import next_slot
from desktop.native.widgets import BlockDialog, ChooseTimeDialog
from desktop.native.window import NativeWindow
from desktop.tests.test_drag_results import qapp, session_of, settled, wait_until, window  # noqa: F401

MONDAY, THURSDAY, FRIDAY, SUNDAY = 0, 3, 4, 6


def hold_clock(window: NativeWindow, day: int, clock: str) -> None:
    """The window's clock at "HH:MM" or "HH:MM:SS" on a day of the open week."""
    hours, minutes, *seconds = (int(part) for part in clock.split(":"))
    moment = datetime.fromisoformat(window.session.week_start) + timedelta(
        days=day, hours=hours, minutes=minutes, seconds=seconds[0] if seconds else 0
    )
    window.session.now_ms = lambda: int(moment.timestamp() * 1000)


@pytest.mark.parametrize(
    ("now", "ahead", "slot"),
    [
        (0, 0, 0),
        (1, 0, 15),
        (15, 0, 15),
        (16 * 60 + 7, 0, 16 * 60 + 15),
        (23 * 60 + 33, 0, 23 * 60 + 45),
        (23 * 60 + 45, 0, 23 * 60 + 45),
        (23 * 60 + 46, 1, 0),
        (23 * 60 + 59, 1, 0),
    ],
)
def test_the_next_slot_is_the_next_quarter_hour_or_the_first_of_tomorrow(
    now: int, ahead: int, slot: int
) -> None:
    assert next_slot(now) == (ahead, slot)


def test_the_next_slot_keeps_to_the_hours_it_is_given() -> None:
    assert next_slot(3 * 60 + 10, first=6 * 60, last=23 * 60) == (0, 6 * 60), "not before the first"
    assert next_slot(23 * 60 + 1, first=6 * 60, last=23 * 60) == (1, 6 * 60), "none left: tomorrow's first"
    assert next_slot(22 * 60 + 50, first=6 * 60, last=23 * 60) == (0, 23 * 60)


def opened_event(qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    seen: list[tuple] = []

    def look(dialog: BlockDialog) -> int:
        days = [day for day, box in enumerate(dialog.days) if box.isChecked()]
        seen.append((days, dialog.start.time().toString("HH:mm")))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(BlockDialog, "exec", look)
    window._add_fixed()
    return seen


@pytest.mark.parametrize(
    ("day", "now", "opens"),
    [
        (THURSDAY, "23:33", ([THURSDAY], "23:45")),
        (THURSDAY, "23:23", ([THURSDAY], "23:30")),
        (THURSDAY, "16:00", ([THURSDAY], "16:00")),
        (THURSDAY, "16:00:40", ([THURSDAY], "16:00")),
        (THURSDAY, "16:01", ([THURSDAY], "16:15")),
        (THURSDAY, "00:05", ([THURSDAY], "00:15")),
        (THURSDAY, "23:50", ([FRIDAY], "00:00")),
    ],
)
def test_a_new_event_opens_at_the_next_free_quarter_hour(
    qapp: QApplication,
    window: NativeWindow,
    monkeypatch: pytest.MonkeyPatch,
    day: int,
    now: str,
    opens: tuple,
) -> None:
    hold_clock(window, day, now)
    assert opened_event(qapp, window, monkeypatch) == [opens]


def test_a_new_event_on_a_week_that_is_not_this_one_keeps_its_usual_start(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.session.load_week(
        (datetime.fromisoformat(window.session.week_start) + timedelta(days=7)).date().isoformat()
    )
    settled(qapp, window)
    assert opened_event(qapp, window, monkeypatch) == [([MONDAY], "16:00")]


def test_a_new_event_late_on_sunday_opens_on_a_start_that_exists(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tomorrow is another week, which this one cannot hold, so the usual start is kept."""
    hold_clock(window, SUNDAY, "23:50")
    assert opened_event(qapp, window, monkeypatch) == [([MONDAY], "16:00")]


def choose_time_opens(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[int, str]]:
    seen: list[tuple[int, str]] = []

    def look(dialog: ChooseTimeDialog) -> int:
        seen.append((int(dialog.day.currentData()), dialog.start.time().toString("HH:mm")))
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(ChooseTimeDialog, "exec", look)
    window._choose_time(session_of(window, "math")["assignment_id"])
    return seen


@pytest.mark.parametrize(
    ("now", "opens"),
    [
        ("19:40", (THURSDAY, "19:45")),
        ("16:00", (THURSDAY, "16:00")),
        ("16:07", (THURSDAY, "16:15")),
        ("22:50", (THURSDAY, "23:00")),
        ("03:10", (THURSDAY, "06:00")),
    ],
)
def test_choose_a_time_opens_at_the_next_quarter_hour_today(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch, now: str, opens: tuple
) -> None:
    hold_clock(window, THURSDAY, now)
    assert choose_time_opens(qapp, window, monkeypatch) == [opens]


def test_choose_a_time_late_in_the_evening_opens_on_tomorrow_morning(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A one hour session cannot start after 23:00, so at 23:33 none is left today. The box starts at
    06:00, so that is tomorrow's first."""
    hold_clock(window, THURSDAY, "23:33")
    assert choose_time_opens(qapp, window, monkeypatch) == [(FRIDAY, "06:00")]
