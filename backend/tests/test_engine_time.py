"""The original slots and weeks bodies, compared with the engine on the same inputs."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend import slots as engine_slots
from backend import weeks as engine_weeks
from backend.tests.engine_ref import slots as py_slots
from backend.tests.engine_ref import weeks as py_weeks

DATES = (
    "2000-01-01",
    "2000-01-03",
    "2026-09-07",
    "2026-09-08",
    "2026-09-13",
    "2026-10-01",
    "2027-01-01",
    "2099-12-31",
    "2099-12-28",
)
BAD_DATES = (
    "",
    "2026-09-7",
    "not-a-date",
    "2026-13-40",
    "20260907",
    "2026-W37-1",
    "1999-12-31",
    "2100-01-01",
    "2026-02-31",
    "2026-00-01",
)
MONTHS = ("2026-09", "2026-02", "2000-01", "2099-12", "2024-02")
BAD_MONTHS = ("", "2026-9", "2026-09-01", "2026-13", "1999-12", "2100-01", "202609")
TIMES = ("00:00", "06:00", "08:10", "16:00", "23:45", "23:59", "24:00", "24:01", "9:00", "")


def _same_error(left, right) -> None:
    with pytest.raises(Exception) as caught_py:
        left()
    with pytest.raises(type(caught_py.value)) as caught_engine:
        right()
    assert str(caught_engine.value) == str(caught_py.value)


@pytest.mark.parametrize("minutes", [1, 14, 15, 16, 50])
def test_duration_rounds_up_to_quarter_hours(minutes: int) -> None:
    assert engine_slots.duration_to_slots(minutes) == py_slots.duration_to_slots(minutes)


@pytest.mark.parametrize("hhmm", TIMES)
def test_clock_matches_the_python_body(hhmm: str) -> None:
    for call_py, call_engine in (
        (lambda: py_slots.hhmm_to_minutes(hhmm), lambda: engine_slots.hhmm_to_minutes(hhmm)),
        (lambda: py_slots.clock_to_minutes(hhmm), lambda: engine_slots.clock_to_minutes(hhmm)),
        (lambda: py_slots.hhmm_to_slot(hhmm), lambda: engine_slots.hhmm_to_slot(hhmm)),
    ):
        try:
            expected = call_py()
        except Exception:
            _same_error(call_py, call_engine)
        else:
            assert call_engine() == expected


@pytest.mark.parametrize("minutes", list(range(-120, 1500, 7)))
def test_minute_formatting_matches(minutes: int) -> None:
    assert engine_slots.minutes_to_hhmm(minutes) == py_slots.minutes_to_hhmm(minutes)
    assert engine_slots.on_slot(minutes) is py_slots.on_slot(minutes)
    assert engine_slots.start_fits_day(minutes) is py_slots.start_fits_day(minutes)


@pytest.mark.parametrize("value", DATES + BAD_DATES)
def test_week_labels_match_the_python_body(value: str) -> None:
    assert engine_weeks.is_week_start(value) is py_weeks.is_week_start(value)
    assert engine_weeks.is_calendar_date(value) is py_weeks.is_calendar_date(value)
    try:
        expected = py_weeks.monday_of(value)
    except Exception:
        _same_error(lambda: py_weeks.monday_of(value), lambda: engine_weeks.monday_of(value))
    else:
        assert engine_weeks.monday_of(value) == expected


@pytest.mark.parametrize("value", MONTHS + BAD_MONTHS)
def test_months_match_the_python_body(value: str) -> None:
    assert engine_weeks.is_month_label(value) is py_weeks.is_month_label(value)
    try:
        expected = py_weeks.parse_month(value)
    except Exception:
        _same_error(lambda: py_weeks.parse_month(value), lambda: engine_weeks.parse_month(value))
    else:
        assert engine_weeks.parse_month(value) == expected


def test_month_grid_fixtures_match() -> None:
    pairs = (
        (date(2026, 9, 1), date(2026, 9, 30)),
        (date(2000, 1, 1), date(2000, 1, 31)),
        (date(2099, 12, 1), date(2099, 12, 31)),
    )
    for start, end in pairs:
        assert engine_weeks.month_grid(start, end) == py_weeks.month_grid(start, end)


@given(
    hour=st.integers(min_value=-5, max_value=30),
    minute=st.integers(min_value=-5, max_value=70),
)
@settings(max_examples=80)
def test_generated_clocks_match(hour: int, minute: int) -> None:
    text = f"{hour}:{minute:02d}" if minute >= 0 else f"{hour}:{minute}"
    try:
        expected = py_slots.hhmm_to_minutes(text)
    except Exception:
        _same_error(
            lambda: py_slots.hhmm_to_minutes(text),
            lambda: engine_slots.hhmm_to_minutes(text),
        )
    else:
        assert engine_slots.hhmm_to_minutes(text) == expected


@given(day=st.dates(min_value=date(1999, 12, 1), max_value=date(2100, 2, 1)))
@settings(max_examples=60)
def test_generated_dates_match(day: date) -> None:
    text = day.isoformat()
    try:
        expected = py_weeks.monday_of(text)
    except Exception:
        _same_error(lambda: py_weeks.monday_of(text), lambda: engine_weeks.monday_of(text))
    else:
        assert engine_weeks.monday_of(text) == expected
    shifted = day + timedelta(days=3)
    if date(2000, 1, 1) <= day <= date(2099, 12, 31) and date(2000, 1, 1) <= shifted <= date(
        2099, 12, 31
    ):
        assert engine_weeks.month_grid(day, shifted) == py_weeks.month_grid(day, shifted)
