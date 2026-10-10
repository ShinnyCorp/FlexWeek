"""Regression for fix-specs.md items 1 and 1a (item 1 was Sammy's finding 1): next week keeps the school
and activities set up in Setup, Plan never puts homework in school hours, and "Copy last week's fixed
times" does not say "nothing" while last week holds Setup's blocks.

Driven through a signed-in NativeSession on a real local API, the layer Setup itself writes through
(`set_setup_blocks`), so the test holds whichever way the fix is built (Coder's plan: a standing week
applied on the read path). The last tests are the spec's "this week or every week" checks 3-5.
"""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

from desktop.tests.logic_support import qapp, server, settled, signed_in, wait_until  # noqa: F401,E402

SETUP_HERE = "Your Setup times are already in this week."
NOTHING = "There is nothing to copy from last week yet."

SCHOOL = {
    "id": "school",
    "title": "School",
    "kind": "locked",
    "category": "class",
    "start": "08:30",
    "duration_min": 405,  # 08:30-15:15
    "days": [0, 1, 2, 3, 4],
}
SOCCER = {
    "id": "activity-1",
    "title": "Soccer",
    "kind": "locked",
    "category": "extra",
    "start": "16:00",
    "duration_min": 90,  # 16:00-17:30
    "days": [1, 3],
}
JOB = {
    "id": "activity-2",
    "title": "Saturday job",
    "kind": "locked",
    "category": "work",
    "start": "10:00",
    "duration_min": 240,
    "days": [5],
}
# (day, start_min, end_min) the student is busy in every week from Setup's week on.
BUSY = (
    [(d, 8 * 60 + 30, 15 * 60 + 15) for d in range(5)]
    + [(d, 16 * 60, 17 * 60 + 30) for d in (1, 3)]
    + [(5, 10 * 60, 14 * 60)]
)


def plus_weeks(week_start: str, weeks: int) -> str:
    return (date.fromisoformat(week_start) + timedelta(days=7 * weeks)).isoformat()


def go_to(qapp, session, week: str) -> None:
    session.load_week(week)
    wait_until(qapp, lambda: session.week_start == week and not session.busy)
    settled(qapp, session)


def standing(session) -> dict[str, tuple[str | None, int, list[int]]]:
    return {
        b["id"]: (b.get("start"), b["duration_min"], sorted(b.get("days") or []))
        for b in session.blocks
        if b["id"] in ("school", "activity-1", "activity-2")
    }


EXPECTED = {
    "school": ("08:30", 405, [0, 1, 2, 3, 4]),
    "activity-1": ("16:00", 90, [1, 3]),
    "activity-2": ("10:00", 240, [5]),
}


@pytest.fixture()
def after_setup(qapp, server):  # noqa: F811
    """A new account that finished Setup with School, Soccer and a Saturday job in the week it is in."""
    session = signed_in(qapp, server.origin, "standing_week", create=True)
    session.set_setup_blocks([dict(SCHOOL), dict(SOCCER), dict(JOB)])
    session.save()
    wait_until(qapp, lambda: not session.busy and not session.dirty)
    settled(qapp, session)
    assert standing(session) == EXPECTED
    return session


def homework_overlaps(session, busy: list[tuple[int, int, int]]) -> list[tuple]:
    bad = []
    for block in session.blocks:
        if not block.get("assignment_id") or not block.get("start"):
            continue
        h, m = map(int, block["start"].split(":"))
        start = h * 60 + m
        end = start + block["duration_min"]
        for day in block.get("days") or []:
            for b_day, b_start, b_end in busy:
                if day == b_day and start < b_end and b_start < end:
                    bad.append((block["title"], day, block["start"], block["duration_min"]))
    return bad


def plan_in_open_week(qapp, session, title: str) -> None:
    week = session.week_start
    session.add_homework({"id": f"hw-{week}", "title": title, "estimate_min": 120, "revision": 0,
                          "due": (date.fromisoformat(week) + timedelta(days=1)).isoformat()})  # Tuesday
    session.save()
    wait_until(qapp, lambda: not session.busy and not session.dirty)
    monday_6am = datetime.fromisoformat(week) + timedelta(hours=6)
    session.now_ms = lambda: int(monday_6am.timestamp() * 1000)
    session.solve()
    wait_until(qapp, lambda: not session.planning and not session.busy and not session.dirty, timeout=20)
    settled(qapp, session)
    placed = [b for b in session.blocks if b.get("assignment_id") and b.get("start")]
    assert placed, f"Plan placed nothing in {week}; needs_time={session.needs_time}"


def test_plan_in_setups_own_week_keeps_homework_out_of_school_hours(qapp, after_setup) -> None:
    """Guard: passes today and must keep passing."""
    plan_in_open_week(qapp, after_setup, "This week HW")
    assert homework_overlaps(after_setup, BUSY) == []


def test_next_week_shows_setups_school_and_activities(qapp, after_setup) -> None:
    go_to(qapp, after_setup, plus_weeks(after_setup.week_start, 1))
    assert standing(after_setup) == EXPECTED


def test_three_weeks_ahead_shows_setups_school_and_activities(qapp, after_setup) -> None:
    go_to(qapp, after_setup, plus_weeks(after_setup.week_start, 3))
    assert standing(after_setup) == EXPECTED


def test_plan_in_next_week_keeps_homework_out_of_school_and_activity_hours(qapp, after_setup) -> None:
    go_to(qapp, after_setup, plus_weeks(after_setup.week_start, 1))
    plan_in_open_week(qapp, after_setup, "Next week HW")
    assert homework_overlaps(after_setup, BUSY) == []


def test_the_week_before_setup_is_left_alone(qapp, after_setup) -> None:
    """Guard: the standing week never back-fills the past."""
    go_to(qapp, after_setup, plus_weeks(after_setup.week_start, -1))
    assert standing(after_setup) == {}


def test_copy_last_week_never_offers_setup_blocks(qapp, after_setup) -> None:
    """Guard (item 1, acceptance check 6): 'Copy last week' offers only one-off blocks, never School or
    activities."""
    after_setup.add_block({"id": "gym", "title": "Gym", "kind": "locked", "start": "18:00",
                           "duration_min": 60, "days": [2]})
    after_setup.save()
    wait_until(qapp, lambda: not after_setup.busy and not after_setup.dirty)
    go_to(qapp, after_setup, plus_weeks(after_setup.week_start, 1))
    got: list = []
    after_setup.copy_last_week_fixed_rows(got.append)
    wait_until(qapp, lambda: bool(got))
    offered = [row["block"]["title"] for row in (got[0] or [])]
    assert offered == ["Gym"]


# Item 1a -------------------------------------------------------------------------------------


def test_1a_next_week_has_school_soccer_and_job_without_copying(qapp, after_setup) -> None:
    """The spec's 1a guard: Setup, go to next week, the week has School/Soccer/job without copying."""
    go_to(qapp, after_setup, plus_weeks(after_setup.week_start, 1))
    assert standing(after_setup) == EXPECTED


def test_1a_copy_with_only_setup_blocks_last_week_says_they_are_already_here(qapp, after_setup) -> None:
    """Coder's decision: item 1 wins. Copy never offers Setup blocks; the message says where they are."""
    said: list[str] = []
    after_setup.status.connect(said.append)
    go_to(qapp, after_setup, plus_weeks(after_setup.week_start, 1))
    got: list = []
    after_setup.copy_last_week_fixed_rows(got.append)
    wait_until(qapp, lambda: bool(got))
    settled(qapp, after_setup)
    assert not got[0], f"Copy offered rows {got[0]!r}"
    assert SETUP_HERE in said and NOTHING not in said, said


def test_1a_nothing_to_copy_is_said_for_a_truly_empty_week(qapp, server) -> None:  # noqa: F811
    """Guard: a last week with no blocks at all still says there is nothing to copy."""
    session = signed_in(qapp, server.origin, "empty_last_week", create=True)
    said: list[str] = []
    session.status.connect(said.append)
    go_to(qapp, session, plus_weeks(session.week_start, 1))
    got: list = []
    session.copy_last_week_fixed_rows(got.append)
    wait_until(qapp, lambda: bool(got))
    settled(qapp, session)
    assert not got[0] and NOTHING in said and SETUP_HERE not in said, said


# This week or every week (acceptance checks 3-5) ----------------------------------------------


def save_and_settle(qapp, session) -> None:
    session.save()
    wait_until(qapp, lambda: not session.busy and not session.dirty)
    settled(qapp, session)


def test_a_missed_wednesday_stays_in_its_own_week(qapp, after_setup) -> None:
    setup_week = after_setup.week_start
    go_to(qapp, after_setup, plus_weeks(setup_week, 1))
    school = next(b for b in after_setup.blocks if b["id"] == "school")
    after_setup.add_block({**school, "missed_days": [2]})
    save_and_settle(qapp, after_setup)
    go_to(qapp, after_setup, plus_weeks(setup_week, 2))
    assert next(b for b in after_setup.blocks if b["id"] == "school").get("missed_days") in (None, [])
    go_to(qapp, after_setup, plus_weeks(setup_week, 1))
    assert next(b for b in after_setup.blocks if b["id"] == "school")["missed_days"] == [2]


def test_deleting_soccer_just_this_week_leaves_it_in_the_week_after(qapp, after_setup) -> None:
    setup_week = after_setup.week_start
    go_to(qapp, after_setup, plus_weeks(setup_week, 1))
    after_setup.delete_block("activity-1")
    save_and_settle(qapp, after_setup)
    go_to(qapp, after_setup, plus_weeks(setup_week, 2))
    assert standing(after_setup) == EXPECTED
    go_to(qapp, after_setup, plus_weeks(setup_week, 1))
    soccer = next(b for b in after_setup.blocks if b["id"] == "activity-1")
    assert soccer["missed_days"] == [1, 3]


def test_deleting_soccer_every_week_takes_it_from_later_weeks_only(qapp, after_setup) -> None:
    setup_week = after_setup.week_start
    go_to(qapp, after_setup, plus_weeks(setup_week, 3))
    after_setup.add_block({"id": "gym", "title": "Gym", "kind": "locked", "start": "18:00",
                           "duration_min": 60, "days": [2]})
    save_and_settle(qapp, after_setup)  # week 3 is saved, with its own copy of Soccer
    go_to(qapp, after_setup, plus_weeks(setup_week, 1))
    after_setup.delete_block("activity-1", every_week=True)
    save_and_settle(qapp, after_setup)
    assert "activity-1" not in standing(after_setup)
    for later in (2, 3):
        go_to(qapp, after_setup, plus_weeks(setup_week, later))
        assert "activity-1" not in standing(after_setup), later
    go_to(qapp, after_setup, setup_week)
    assert standing(after_setup) == EXPECTED


def test_new_school_hours_reach_this_week_on_and_keep_a_later_missed_day(qapp, after_setup) -> None:
    setup_week = after_setup.week_start
    go_to(qapp, after_setup, plus_weeks(setup_week, 2))
    school = next(b for b in after_setup.blocks if b["id"] == "school")
    after_setup.add_block({**school, "missed_days": [2]})
    save_and_settle(qapp, after_setup)
    go_to(qapp, after_setup, plus_weeks(setup_week, 1))
    school = next(b for b in after_setup.blocks if b["id"] == "school")
    after_setup.add_block({**school, "start": "09:00", "duration_min": 360})
    after_setup.stand_open_week()
    save_and_settle(qapp, after_setup)
    assert standing(after_setup)["school"] == ("09:00", 360, [0, 1, 2, 3, 4])
    go_to(qapp, after_setup, plus_weeks(setup_week, 2))
    school = next(b for b in after_setup.blocks if b["id"] == "school")
    assert (school["start"], school["duration_min"], school["missed_days"]) == ("09:00", 360, [2])
    go_to(qapp, after_setup, plus_weeks(setup_week, 5))
    assert standing(after_setup)["school"] == ("09:00", 360, [0, 1, 2, 3, 4])
    go_to(qapp, after_setup, setup_week)
    assert standing(after_setup) == EXPECTED
