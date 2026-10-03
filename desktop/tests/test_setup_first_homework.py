"""Setup's First homework page (finding 2 of the 0.17.2 audit): its calendar drew only the weekday
letters and one square, because the month's grid Qt makes again when the popup opens was not the one
the calendar had kept. The date also began on a Sunday, a day with no school."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QTableView

from desktop.native.setup import FIRST, SetupPage, next_school_day
from desktop.tests.test_date_picker import cells, ink, same
from desktop.tests.test_setup_look import dressed, qapp  # noqa: F401
from desktop.tests.window_support import free  # noqa: F401


def next_weekday(after: date, wanted: set[int]) -> date:
    day = after + timedelta(days=1)
    while day.weekday() not in wanted:
        day += timedelta(days=1)
    return day


def test_the_calendar_in_setup_draws_its_day_numbers_once_it_is_open(qapp, dressed) -> None:  # noqa: F811
    setup, palette = dressed
    setup._show(FIRST)
    for _ in range(10):
        qapp.processEvents()
    field = setup.homework_rows[0].due.date
    QTest.mouseClick(
        field,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(field.width() - 6, field.height() // 2),
    )
    month = field.calendarWidget()
    for _ in range(200):
        qapp.processEvents()
        if month.parentWidget().isVisible():
            break
        QTest.qWait(10)
    for _ in range(8):
        qapp.processEvents()
    assert month.parentWidget().isVisible()
    view, shown = cells(month)
    picture = view.viewport().grab().toImage()
    picked = field.date()
    plain = [day for day in shown if day.month() == month.monthShown() and day != picked]
    wednesday = next(day for day in plain if day.dayOfWeek() == 3)
    assert same(ink(picture, shown[wednesday], palette["panel"]), palette["text"]), "a day number is drawn"
    assert view.model().index(0, 0).data() == "M", "and the weekday row"
    assert isinstance(view, QTableView)


def test_first_homework_is_due_on_the_next_school_day(qapp, dressed) -> None:  # noqa: F811
    setup, _palette = dressed
    setup._show(FIRST)
    expected = next_weekday(date.today(), {0, 1, 2, 3, 4})
    assert setup.homework_rows[0].due.value() == expected.isoformat()


def test_a_date_nobody_touched_follows_the_school_days_picked_earlier(qapp, dressed) -> None:  # noqa: F811
    setup, _palette = dressed
    setup.school_days.set_days([1])
    setup._show(FIRST)
    assert setup.homework_rows[0].due.value() == next_weekday(date.today(), {1}).isoformat()


def test_a_date_the_student_chose_is_left_where_it_is(qapp, dressed) -> None:  # noqa: F811
    setup, _palette = dressed
    row = setup.homework_rows[0]
    row.due.set_value("2031-05-06")
    setup.school_days.set_days([2])
    setup._show(FIRST)
    assert row.due.value() == "2031-05-06"


def test_with_no_school_days_it_is_due_tomorrow() -> None:
    assert next_school_day([], date(2026, 10, 3)) == "2026-10-04"
    # Saturday 3 Oct 2026: the next of Monday to Friday is Monday the 5th.
    assert next_school_day([0, 1, 2, 3, 4], date(2026, 10, 3)) == "2026-10-05"
    assert next_school_day([4], date(2026, 10, 2)) == "2026-10-09", "after today, not today"


def test_the_page_is_a_setup_page(qapp, dressed) -> None:  # noqa: F811
    setup, _palette = dressed
    assert isinstance(setup, SetupPage)
