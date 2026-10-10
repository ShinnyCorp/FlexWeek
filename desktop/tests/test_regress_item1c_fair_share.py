"""Item 1c, part C: work due after this Sunday gets only a fair share of this week, and Plan details
says how the rest waits for next week. Part B (a daily cap and a gap after school) is not wanted.

Planned on Saturday 07:00, a 2 h Science project due next Wednesday has four plannable days before its
due day (Sat, Sun, Mon, Tue), two of them this week, so 1 h goes in this week.
"""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

pytest.importorskip("PySide6")

from desktop.native.widgets import PlanReview  # noqa: E402
from desktop.tests.logic_support import qapp, server, settled, signed_in, wait_until  # noqa: F401,E402

SATURDAY = 5


def plan_on_saturday(qapp, session, due_in_days: int) -> list[dict]:
    week = session.week_start
    due = (date.fromisoformat(week) + timedelta(days=due_in_days)).isoformat() + "T23:59"
    session.add_homework(
        {"id": "sci", "title": "Science project", "estimate_min": 120, "revision": 0, "due": due}
    )
    session.save()
    wait_until(qapp, lambda: not session.busy and not session.dirty)
    saturday_7 = datetime.fromisoformat(week) + timedelta(days=SATURDAY, hours=7)
    session.now_ms = lambda: int(saturday_7.timestamp() * 1000)
    session.solve()
    wait_until(qapp, lambda: not session.planning and not session.busy and not session.dirty, timeout=20)
    settled(qapp, session)
    return [b for b in session.blocks if b.get("assignment_id") == "sci"]


def test_due_next_wednesday_gets_one_hour_this_weekend(qapp, server) -> None:  # noqa: F811
    session = signed_in(qapp, server.origin, "fair_share", create=True)
    sessions = plan_on_saturday(qapp, session, 9)  # Wednesday of next week
    placed = [b for b in sessions if b.get("start")]
    assert sum(b["duration_min"] for b in placed) == 60, sessions
    assert all(b["days"][0] >= SATURDAY for b in placed), placed
    titles = {b["id"]: b["title"] for b in session.blocks}
    rows = PlanReview().rows_for(session.trace or {}, titles, session.week_start)
    assert "Science project: 1 h this week, 1 h left for next week" in rows, rows


def test_due_this_sunday_is_planned_whole(qapp, server) -> None:  # noqa: F811
    session = signed_in(qapp, server.origin, "fair_share_sunday", create=True)
    sessions = plan_on_saturday(qapp, session, 6)
    assert sum(b["duration_min"] for b in sessions if b.get("start")) == 120, sessions
    assert not (session.trace or {}).get("shares")


def test_planning_again_keeps_the_same_share(qapp, server) -> None:  # noqa: F811
    session = signed_in(qapp, server.origin, "fair_share_again", create=True)
    plan_on_saturday(qapp, session, 9)
    session.solve(everything=True)
    wait_until(qapp, lambda: not session.planning and not session.busy and not session.dirty, timeout=20)
    settled(qapp, session)
    placed = [b for b in session.blocks if b.get("assignment_id") == "sci" and b.get("start")]
    assert sum(b["duration_min"] for b in placed) == 60, placed
