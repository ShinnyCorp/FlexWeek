"""One short and one long date format (#102): the app's date text comes from the engine, with the year
shown only when it is not the current year. `today` is always passed, so no test depends on the clock."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest

from desktop.native.calendar import day_long, day_short, month_title, week_range
from desktop.native.reuse import capacity_problem, week_label
from desktop.native.weekmodel import dated_words, due_label, set_clock_24h

THIS_YEAR = "2026-10-09"


@pytest.fixture(autouse=True)
def twenty_four_hour_clock() -> Iterator[None]:
    set_clock_24h(True)
    yield
    set_clock_24h(True)


def test_a_short_day_is_weekday_day_month() -> None:
    assert day_short("2026-10-01", THIS_YEAR) == "Thu 1 Oct"
    assert day_short(date(2026, 10, 1), date(2026, 10, 9)) == "Thu 1 Oct"


def test_a_long_day_has_no_comma_after_the_weekday() -> None:
    assert day_long("2026-10-01", THIS_YEAR) == "Thursday 1 October"


def test_another_year_adds_the_year_to_both_forms() -> None:
    assert day_short("2027-01-08", THIS_YEAR) == "Fri 8 Jan 2027"
    assert day_long("2027-01-08", THIS_YEAR) == "Friday 8 January 2027"


def test_a_week_is_named_by_its_range_and_a_new_year_week_puts_the_year_on_its_end() -> None:
    assert week_range("2026-09-28", THIS_YEAR) == "28 Sep – 4 Oct"
    assert week_range("2026-10-05", THIS_YEAR) == "5 – 11 Oct"
    assert week_range("2026-12-28", THIS_YEAR) == "28 Dec – 3 Jan 2027"


def test_a_month_title_always_has_its_year() -> None:
    assert month_title("2026-10-01") == "October 2026"
    assert month_title("2026-10-01", short=True) == "Oct 2026"


def test_a_due_date_with_a_time_follows_the_clock_setting() -> None:
    assert due_label("2026-10-01T21:00", THIS_YEAR) == "Thu 1 Oct, 21:00"
    assert due_label("2027-01-08", THIS_YEAR) == "Fri 8 Jan 2027"
    set_clock_24h(False)
    assert due_label("2026-10-01T21:00", THIS_YEAR) == "Thu 1 Oct, 9:00 PM"


def test_the_toast_after_moving_homework_names_the_date_the_same_way() -> None:
    assert dated_words("History essay", "2026-10-01", THIS_YEAR) == "Moved History essay to Thu 1 Oct."


def test_the_capacity_toast_names_the_week_by_its_range_not_its_iso_date() -> None:
    label = week_label("2026-09-28", THIS_YEAR)
    assert capacity_problem(100, 1, label) == (
        "Week of 28 Sep – 4 Oct would exceed 100 blocks. Uncheck an item or remove a block first."
    )
