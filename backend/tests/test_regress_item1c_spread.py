"""Regression for fix-specs.md item 1c: Plan crams homework into today and never uses the weekend.

Inputs are Timmy's 18 test weeks (/workspace/fw184/solver-compare/harness/weeks.json, copied to
backend/tests/data/regress_1c_weeks.json; day 0 = Monday). The engine's solver is called as
backend/solver.py calls it, but with a fixed-work clock in place of the wall clock: each clock read
advances it by PER_CHECK_MS, so the 150 ms budget is the same amount of search on every machine and the
plans are deterministic. 0.001 ms per check matches the app's 150 ms on the box the comparison ran on
(the placed counts equal report.md's "Today" column); 0.004 is Timmy's "4x slower laptop".

Guards kept: week 17's three items all get a time this week (with part A's weekend days offered); no
week places fewer items than today's planner; a priority-1 item is never dropped for a lower one. Part
A (session_days) is also pinned in engine/engine/tests/test_regress_item1c_session_days.rs; part C (fair
share) in engine/engine/tests/test_fair_share.rs and desktop/tests/test_regress_item1c_fair_share.py.

Dropped on purpose (Jonathan, 0.19.0: no daily cap, and part B is not wanted): the week-17 "Friday stays
under the cap and the weekend is used" guard, week 2's "no day over the cap" and "nothing ends later than
a day before its due date", and "no homework starts within 30 min of School's end". Each asserted part B.
"""

from __future__ import annotations

import json
from pathlib import Path

import flexweek_engine  # type: ignore[import-untyped]
import pytest

WEEKS = json.loads((Path(__file__).parent / "data" / "regress_1c_weeks.json").read_text())
BY_NAME = {week["name"].split(".")[0]: week for week in WEEKS}
# Items today's planner places in each week (report.md "Today"), at 1x and at 4x slower.
TODAY = {"1": 3, "2": 8, "3": 22, "4": 60, "5": 8, "6": 10, "7": 6, "8": 6, "9": 9, "10": 6, "11": 25,
         "12": 27, "13": 30, "14": 22, "15": 15, "16": 40, "17": 3, "17b": 3}
TODAY_SLOW = {**TODAY, "10": 5, "15": 14}


def hm(text: str) -> int:
    hours, minutes = map(int, text.split(":"))
    return hours * 60 + minutes


def solve(week: dict, per_check_ms: float = 0.001) -> dict:
    checks = [0]

    def clock() -> float:
        checks[0] += 1
        return checks[0] * per_check_ms

    raw = flexweek_engine.solve(
        json.dumps(week["blocks"]),
        json.dumps(week["deadlines"]) if week.get("deadlines") else None,
        json.dumps(week["slack"]) if week.get("slack") else None,
        [int(x) for x in week["extra_occ"]] if week.get("extra_occ") else None,
        json.dumps(week["work_windows"]) if week.get("work_windows") else None,
        clock,
    )
    return json.loads(raw)


def homework(week: dict) -> dict[str, dict]:
    return {b["id"]: b for b in week["blocks"] if b["kind"] == "flexible" and not b.get("pinned")}


def placed(week: dict, trace: dict) -> dict[str, tuple[int, int, int]]:
    """id -> (day, start, end) for the homework the plan gave a time."""
    items = homework(week)
    out = {}
    for block in trace["placed"]:
        if block["id"] in items and block.get("start"):
            start = hm(block["start"])
            out[block["id"]] = (block["days"][0], start, start + items[block["id"]]["duration_min"])
    return out


# A. Week 17 -------------------------------------------------------------------------------------


def week17_as_the_app_asks() -> dict:
    """Week 17 with each item's days rebuilt the way the app builds them: session_days for its due date
    (the engine's own function), then only today and later (Friday 10:45)."""
    week = json.loads(json.dumps(BY_NAME["17"]))
    due = {"n1": "2026-10-14T23:59", "n2": "2026-10-15T23:59", "n3": "2026-10-16T23:59"}
    now_day = 4
    for block in week["blocks"]:
        if block["id"] in due:
            offered = list(flexweek_engine.reuse_session_days("2026-10-05", json.dumps(due[block["id"]])))
            block["days"] = [day for day in offered if day >= now_day]
    return week


def test_week17_offers_plan_friday_at_least() -> None:
    """Guard: the request is built and solved; all three items get a time this week."""
    week = week17_as_the_app_asks()
    assert len(placed(week, solve(week))) == 3


# No week places fewer items than today; priority 1 is never dropped for a lower one ------------


@pytest.mark.parametrize(("per_check_ms", "floor"), [(0.001, TODAY), (0.004, TODAY_SLOW)], ids=["1x", "4x-slower"])
@pytest.mark.parametrize("name", list(BY_NAME))
def test_no_week_places_fewer_items_than_today(name: str, per_check_ms: float, floor: dict) -> None:
    week = BY_NAME[name]
    count = len(placed(week, solve(week, per_check_ms)))
    assert count >= floor[name], f"{week['name']}: {count} placed, today {floor[name]}"


@pytest.mark.parametrize("per_check_ms", [0.001, 0.004], ids=["1x", "4x-slower"])
@pytest.mark.parametrize("name", list(BY_NAME))
def test_a_priority_1_item_is_never_dropped_for_a_lower_one(name: str, per_check_ms: float) -> None:
    week = BY_NAME[name]
    items = homework(week)
    got = placed(week, solve(week, per_check_ms))
    dropped = [i for i, b in items.items() if b.get("priority") == 1 and i not in got]
    lower = [i for i in got if (items[i].get("priority") or 3) > 1]
    assert not (dropped and lower), f"{week['name']}: priority 1 {dropped} dropped, {len(lower)} lower placed"
