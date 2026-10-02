"""Audit: the engine-backed backend modules against the original Python, on generated inputs.

Run from the engine worktree's root, so `backend` is the live (engine-backed) package and
`backend.tests.engine_ref` the original Python kept beside it.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest import mock

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from backend import app as live_app
from backend import assignments as live_assignments
from backend import availability as live_availability
from backend import comfort as live_comfort
from backend import day as live_day
from backend import explain as live_explain
from backend import models as live_models
from backend import month as live_month
from backend import recovery as live_recovery
from backend import restore as live_restore
from backend import slots as live_slots
from backend import solver as live_solver
from backend import storage as live_storage
from backend import transfer as live_transfer
from backend import weeks as live_weeks
from backend.tests.engine_ref import app_helpers as ref_app_helpers
from backend.tests.engine_ref import assignments as ref_assignments
from backend.tests.engine_ref import availability as ref_availability
from backend.tests.engine_ref import comfort as ref_comfort
from backend.tests.engine_ref import day as ref_day
from backend.tests.engine_ref import explain as ref_explain
from backend.tests.engine_ref import models as ref_models
from backend.tests.engine_ref import month as ref_month
from backend.tests.engine_ref import recovery as ref_recovery
from backend.tests.engine_ref import restore as ref_restore
from backend.tests.engine_ref import slots as ref_slots
from backend.tests.engine_ref import solver as ref_solver
from backend.tests.engine_ref import storage as ref_storage
from backend.tests.engine_ref import transfer as ref_transfer
from backend.tests.engine_ref import weeks as ref_weeks

N = int(os.environ.get("AUDIT_EXAMPLES", "300"))
COMMON = settings(
    max_examples=N,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much, HealthCheck.data_too_large],
    derandomize=True,
)


def plain(value):
    """A result as plain data: pydantic models dumped, tuples as lists."""
    if hasattr(value, "model_dump"):
        return plain(value.model_dump())
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def outcome(call):
    try:
        return ("ok", plain(call()))
    except ValidationError as error:
        return ("raise", "ValidationError", str(error.errors()[0].get("msg")))
    except BaseException as error:  # noqa: BLE001 - a panic surfaces as BaseException
        return ("raise", type(error).__name__, str(error))


def same(live, ref, what=""):
    got, want = outcome(live), outcome(ref)
    assert got == want, f"{what}\n  rust:   {json.dumps(got, default=str)[:1500]}\n  python: {json.dumps(want, default=str)[:1500]}"


# ---------- strategies

quarter = st.sampled_from([0, 15, 30, 45])
minute = st.one_of(quarter, quarter, st.integers(0, 59))
hhmm = st.builds(lambda h, m: f"{h:02d}:{m:02d}", st.integers(0, 23), minute)
grid_hhmm = st.builds(lambda h, m: f"{h:02d}:{m:02d}", st.integers(0, 23), quarter)
day = st.integers(0, 6)
days_unique = st.lists(day, min_size=1, max_size=7, unique=True)
days_any = st.one_of(days_unique, days_unique, st.lists(day, min_size=1, max_size=7))
words = st.text(alphabet="abcdefg XYZ", min_size=1, max_size=12).filter(lambda s: s.strip())
odd_text = st.text(
    alphabet=st.characters(blacklist_categories=["Cs"], max_codepoint=0x1F6FF), min_size=1, max_size=12
).filter(lambda s: s.strip())
title = st.one_of(words, words, odd_text)
course = st.one_of(st.none(), st.sampled_from(["Math", "math", " Math ", "English", "Reading", "Élan", "ética", "STRASSE"]))
category = st.one_of(st.none(), st.sampled_from(["school", "study", "sports", "meal", "Zebra", ""]))
DAY_NAMES = ["Monday", "tuesday", "Wed", "Thursday", "FRIDAY", "saturday", "Sunday", "Fri", "someday"]
deadline_text = st.one_of(
    st.none(),
    hhmm,
    st.builds(lambda name, clock: f"{name} {clock}", st.sampled_from(DAY_NAMES), hhmm),
    st.builds(lambda name, clock: f"{name}, {clock}", st.sampled_from(DAY_NAMES), hhmm),
    st.builds(lambda clock: f"2026-09-09T{clock}", hhmm),
    st.sampled_from(["", "  ", "24:00", "Friday", "9:00", "Friday 9:5"]),
)
MONDAYS = ["2026-09-07", "2026-09-28", "2026-12-28", "2024-02-26", "2099-12-28"]
monday = st.sampled_from(MONDAYS)
iso_day = st.builds(
    lambda y, m, d: f"{y:04d}-{m:02d}-{d:02d}",
    st.sampled_from([2026, 2026, 2026, 2024, 2025, 2099, 2000]),
    st.integers(1, 12),
    st.integers(1, 28),
)
near_day = st.builds(lambda d: f"2026-{9 + (d > 30):02d}-{(d - 1) % 30 + 1:02d}", st.integers(1, 60))
due = st.one_of(
    near_day,
    st.builds(lambda d, clock: f"{d}T{clock}", near_day, hhmm),
    st.builds(lambda d: f"{d}T23:59", near_day),
    st.builds(lambda d, clock: f"{d}T{clock}", iso_day, hhmm),
)


@st.composite
def block_dict(draw, ident=None, kinds=("locked", "flexible")):
    kind = draw(st.sampled_from(kinds))
    days = draw(days_any)
    body: dict = {
        "id": ident or draw(st.text(alphabet="abcdefgh12", min_size=1, max_size=6)),
        "title": draw(title),
        "kind": kind,
        "duration_min": draw(
            st.one_of(st.sampled_from([15, 30, 45, 60, 90, 120, 240, 390]), st.integers(1, 600))
        ),
        "days": days,
        "priority": draw(st.sampled_from([1, 2, 3, 3, 4])),
        "energy": draw(st.sampled_from(["high", "medium", "low"])),
    }
    if draw(st.booleans()):
        body["course"] = draw(course)
    if draw(st.booleans()):
        body["category"] = draw(category)
    if kind == "locked":
        body["start"] = draw(hhmm)
        if draw(st.integers(0, 4)) == 0:
            body["missed_days"] = draw(st.lists(st.sampled_from(days), max_size=3, unique=True))
        if draw(st.integers(0, 5)) == 0:
            body["pomodoro_parent_id"] = draw(st.sampled_from(["p1", "p2"]))
            body["pomodoro_role"] = draw(st.sampled_from(["work", "break"]))
            body["pomodoro_index"] = draw(st.integers(1, 4))
            if body["pomodoro_role"] == "work" and draw(st.booleans()):
                body["assignment_id"] = draw(st.sampled_from(["a1", "a2", "a3"]))
        if draw(st.integers(0, 4)) == 0:
            body["completed"] = True
    else:
        if draw(st.integers(0, 2)) == 0:
            body["start"] = draw(hhmm)
        if draw(st.integers(0, 2)) == 0:
            body["earliest"] = draw(deadline_text)
        if draw(st.integers(0, 3)) == 0:
            body["assignment_id"] = draw(st.sampled_from(["a1", "a2", "a3"]))
        else:
            if draw(st.integers(0, 1)) == 0:
                body["latest"] = draw(deadline_text)
            if draw(st.integers(0, 4)) == 0:
                body["focus_minutes"] = draw(st.integers(0, 200))
                body["focus_sessions"] = draw(st.integers(0, 5))
        if draw(st.integers(0, 3)) == 0:
            body["completed"] = True
            if "start" in body and draw(st.booleans()):
                body["completed_day"] = draw(st.sampled_from(days))
        if "start" in body and len(days) == 1 and draw(st.integers(0, 3)) == 0:
            body["pinned"] = True
    return body


@st.composite
def week_blocks(draw, max_size=7, kinds=("locked", "flexible")):
    count = draw(st.integers(0, max_size))
    blocks = []
    for index in range(count):
        blocks.append(draw(block_dict(ident=f"b{index}", kinds=kinds)))
    for body in blocks:
        try:
            ref_models.TimeBlock.model_validate(body)
        except ValidationError:
            assume(False)
    return blocks


@st.composite
def grid_window(draw, extra=None):
    body = {
        "days": draw(days_unique),
        "start": draw(grid_hhmm),
        "duration_min": draw(st.sampled_from([15, 30, 60, 90, 120, 240, 600])),
    }
    if extra == "study" and draw(st.booleans()):
        body["subject"] = draw(st.sampled_from(["Math", "math ", "English", "Reading", "Ética", "straße"]))
    if extra == "protected":
        body["kind"] = draw(st.sampled_from(["downtime", "commute", "meal"]))
    return body


@st.composite
def work_window(draw):
    start = draw(st.integers(0, 94))
    end = draw(st.integers(start + 1, 96))
    body = {
        "days": draw(days_unique),
        "start": f"{start // 4:02d}:{start % 4 * 15:02d}",
        "end": f"{end // 4:02d}:{end % 4 * 15:02d}",
    }
    if draw(st.integers(0, 2)) == 0:
        body["subject"] = draw(st.sampled_from(["Math", "math", "English", "Ética", "ÉLAN"]))
    return body


def models_of(module, cls, bodies):
    return [getattr(module, cls).model_validate(body) for body in bodies]


def valid(cls, bodies):
    try:
        models_of(ref_models, cls, bodies)
    except ValidationError:
        assume(False)


point = st.tuples(st.integers(0, 6), st.one_of(st.integers(0, 1440), st.sampled_from([0, 900, 1260, 1440])))
slack_point = st.tuples(st.integers(-9, 16), st.integers(0, 1440))
occupancy = st.lists(st.integers(0, (1 << 96) - 1), min_size=7, max_size=7)


@st.composite
def assignment_body(draw, ident):
    done = draw(st.integers(0, 3)) == 0
    body = {
        "id": ident,
        "title": draw(title),
        "course": draw(course),
        "category": draw(category),
        "priority": draw(st.sampled_from([1, 2, 3, 4])),
        "energy": draw(st.sampled_from(["high", "medium", "low"])),
        "spotify_url": None,
        "due": draw(due),
        "estimate_min": draw(st.sampled_from([15, 30, 60, 90, 120, 600])),
        "focus_minutes": draw(st.integers(0, 200)),
        "focus_sessions": draw(st.integers(0, 6)),
        "completed": done,
        "completed_at": "2026-09-08T10:00" if done else None,
    }
    if draw(st.integers(0, 2)) == 0:
        body["notes"] = draw(st.sampled_from(["", " ", "read ch. 3"]))
    if draw(st.integers(0, 3)) == 0:
        body["links"] = [{"label": "x", "url": "https://example.org"}]
    if draw(st.integers(0, 3)) == 0:
        body["checklist"] = [
            {"id": f"c{i}", "text": "t", "done": draw(st.booleans())} for i in range(draw(st.integers(0, 3)))
        ]
    return body


@st.composite
def assignment_rows(draw):
    ids = draw(st.lists(st.sampled_from(["a1", "a2", "a3", "a4", "zz"]), max_size=5, unique=True))
    return [(draw(assignment_body(ident)), draw(st.integers(0, 50))) for ident in ids]


@st.composite
def stored_weeks(draw, mondays=MONDAYS[:2] + ["2026-08-31", "2026-09-14", "2026-09-21", "2026-10-05"]):
    starts = draw(st.lists(st.sampled_from(mondays), max_size=4, unique=True))
    out = []
    for start in starts:
        blocks = draw(week_blocks(max_size=5))
        out.append((start, [ref_models.TimeBlock.model_validate(body).model_dump() for body in blocks]))
    return out


# ---------- the solver


class StepClock:
    """A clock that moves a fixed step per reading, so the budget is a count of readings."""

    def __init__(self, step):
        self.step, self.n = step, 0

    def perf_counter(self):
        self.n += 1
        return self.n * self.step


class StillClock:
    def perf_counter(self):
        return 0.0


@pytest.fixture(autouse=True)
def restore_solver_clocks():
    """Tests here replace the solvers' `time`; a later test in the worker must see the real one."""
    live, ref = live_solver.time, ref_solver.time
    yield
    live_solver.time, ref_solver.time = live, ref


READINGS = 4000


def solve_args(draw, blocks):
    ids = [body["id"] for body in blocks]
    args: dict = {}
    if ids and draw(st.booleans()):
        args["deadlines"] = draw(
            st.dictionaries(st.sampled_from(ids + ["ghost"]), st.one_of(st.none(), point), max_size=4)
        )
    if ids and draw(st.booleans()):
        args["slack_deadlines"] = draw(st.dictionaries(st.sampled_from(ids + ["ghost"]), slack_point, max_size=4))
    if draw(st.integers(0, 3)) == 0:
        args["extra_occ"] = draw(occupancy)
    if draw(st.booleans()):
        bodies = draw(st.lists(grid_window(extra="study"), max_size=3))
        valid("StudyWindow", bodies)
        args["study_windows"] = bodies
    if draw(st.integers(0, 2)) > 0:
        bodies = draw(st.lists(work_window(), max_size=3))
        valid("WorkWindow", bodies)
        args["work_windows"] = bodies
    return args


def both_solvers(name, blocks, args, *positional):
    def build(module):
        kwargs = dict(args)
        if "study_windows" in kwargs:
            kwargs["study_windows"] = models_of(module, "StudyWindow", kwargs["study_windows"])
        if "work_windows" in kwargs:
            kwargs["work_windows"] = models_of(module, "WorkWindow", kwargs["work_windows"])
        return kwargs

    def strip(result):
        if result[0] == "ok":
            result[1].pop("solve_ms", None)
        return result

    def lists(module, items):
        return [models_of(module, "TimeBlock", item) if isinstance(item, list) else item for item in items]

    clock = StepClock(0.150 / READINGS)
    ref_solver.time = clock
    want = strip(
        outcome(lambda: getattr(ref_solver, name)(models_of(ref_models, "TimeBlock", blocks), *lists(ref_models, positional), **build(ref_models)))
    )
    # A plan the original ran out of time on is not compared (the contract's guarantee 5).
    assume(clock.n < READINGS)
    live_solver.time = StillClock()
    got = strip(
        outcome(lambda: getattr(live_solver, name)(models_of(live_models, "TimeBlock", blocks), *lists(live_models, positional), **build(live_models)))
    )
    assert got == want, (
        f"{name}\n  blocks: {json.dumps(blocks)}\n  args: {json.dumps(args, default=str)}\n  more: {json.dumps(positional, default=str)}"
        f"\n  rust:   {json.dumps(got, default=str)[:3000]}\n  python: {json.dumps(want, default=str)[:3000]}"
    )


@COMMON
@given(st.data())
def test_solve(data):
    blocks = data.draw(week_blocks())
    both_solvers("solve", blocks, solve_args(data.draw, blocks))


@COMMON
@given(st.data())
def test_reschedule_after_miss(data):
    blocks = data.draw(week_blocks())
    locked = [body for body in blocks if body["kind"] == "locked"]
    missed_id = data.draw(st.sampled_from([body["id"] for body in locked] + ["ghost"]))
    missed_day = data.draw(day)
    previous = data.draw(st.one_of(st.just([]), st.just(blocks), week_blocks(max_size=4, kinds=("flexible",))))
    both_solvers("reschedule_after_miss", blocks, solve_args(data.draw, blocks), missed_id, missed_day, previous)


@COMMON
@given(st.data())
def test_reschedule_running_late(data):
    blocks = data.draw(week_blocks())
    previous = data.draw(st.one_of(st.just([]), st.just(blocks), week_blocks(max_size=4, kinds=("flexible",))))
    both_solvers(
        "reschedule_running_late",
        blocks,
        solve_args(data.draw, blocks),
        data.draw(day),
        data.draw(st.one_of(st.sampled_from([15, 30, 45, 60, 120]), st.integers(1, 300))),
        data.draw(hhmm),
        previous,
    )


def test_reschedule_uses_subject_windows_and_deadline_overrides():
    """Both reschedule functions, with a subject window and a deadline override."""
    blocks = [
        {
            "id": "lesson",
            "title": "Lesson",
            "kind": "locked",
            "days": [0],
            "start": "09:00",
            "duration_min": 60,
        },
        {
            "id": "hw",
            "title": "Essay",
            "kind": "flexible",
            "days": [0],
            "duration_min": 60,
            "course": "STRASSE",
        },
    ]
    previous = [
        {
            "id": "hw",
            "title": "Essay",
            "kind": "flexible",
            "days": [0],
            "start": "16:00",
            "duration_min": 60,
            "course": "STRASSE",
        }
    ]
    args = {
        "work_windows": [{"days": [0], "start": "16:00", "end": "18:00", "subject": "straße"}],
        "deadlines": {"hw": (0, 18 * 60)},
        "slack_deadlines": {"hw": (0, 17 * 60)},
    }
    both_solvers("reschedule_after_miss", blocks, args, "lesson", 0, previous)
    both_solvers("reschedule_running_late", blocks, args, 0, 30, "15:00", previous)


def test_casefold_matches_python_for_every_code_point():
    import flexweek_engine  # type: ignore[import-untyped]

    chunk: list[str] = []
    for code_point in range(0x110000):
        if 0xD800 <= code_point <= 0xDFFF:
            continue
        chunk.append(chr(code_point))
        if len(chunk) == 4096:
            text = "".join(chunk)
            assert flexweek_engine.casefold(text) == text.casefold()
            chunk = []
    if chunk:
        text = "".join(chunk)
        assert flexweek_engine.casefold(text) == text.casefold()


def test_a_clock_error_after_the_first_reading_reaches_the_caller():
    class Boom:
        def __init__(self):
            self.n = 0

        def perf_counter(self):
            self.n += 1
            if self.n > 1:
                raise RuntimeError("clock broke")
            return 0.0

    live_solver.time = Boom()
    block = {"id": "hw", "title": "Essay", "kind": "flexible", "days": [0], "duration_min": 60}
    got = outcome(lambda: live_solver.solve(models_of(live_models, "TimeBlock", [block])))
    assert got[0] == "raise" and got[1] == "RuntimeError" and got[2] == "clock broke"


@COMMON
@given(st.data())
def test_solve_then_placed_week_round_trips(data):
    """A solved week fed back in: the usual second plan."""
    blocks = data.draw(week_blocks(max_size=6))
    ref_solver.time = StepClock(0.150 / READINGS)
    first = outcome(lambda: ref_solver.solve(models_of(ref_models, "TimeBlock", blocks)))
    assume(first[0] == "ok" and ref_solver.time.n < READINGS)
    again = [*first[1]["placed"], *first[1]["unplaced"]]
    again = [ref_models.TimeBlock.model_validate(body).model_dump() for body in again]
    both_solvers("solve", again, solve_args(data.draw, again))


# ---------- availability


@COMMON
@given(st.lists(grid_window(extra="protected"), max_size=4), st.one_of(st.none(), hhmm, st.sampled_from(["24:00", "", "x"])))
def test_occupancy_from_windows(bodies, cutoff):
    valid("ProtectedWindow", bodies)
    same(
        lambda: live_availability.occupancy_from_windows(models_of(live_models, "ProtectedWindow", bodies), cutoff),
        lambda: ref_availability.occupancy_from_windows(models_of(ref_models, "ProtectedWindow", bodies), cutoff),
        f"{bodies} {cutoff!r}",
    )


@COMMON
@given(st.lists(grid_window(), max_size=4), st.one_of(st.none(), hhmm))
def test_occupancy_from_grid_windows(bodies, cutoff):
    valid("GridWindow", bodies)
    same(
        lambda: live_availability.occupancy_from_windows(models_of(live_models, "GridWindow", bodies), cutoff),
        lambda: ref_availability.occupancy_from_windows(models_of(ref_models, "GridWindow", bodies), cutoff),
        f"{bodies} {cutoff!r}",
    )


@COMMON
@given(st.integers(-1, 7), st.one_of(hhmm, st.sampled_from(["24:00", "bad", ""])), st.integers(-30, 1500))
def test_lateness_occupancy(d, start, minutes):
    same(
        lambda: live_availability.lateness_occupancy(d, start, minutes),
        lambda: ref_availability.lateness_occupancy(d, start, minutes),
        f"{d} {start!r} {minutes}",
    )


@COMMON
@given(st.lists(grid_window(extra="study"), max_size=4), course, st.integers(-1, 7), st.integers(-15, 1500), st.integers(0, 600))
def test_study_rank(bodies, subject, d, start, duration):
    valid("StudyWindow", bodies)
    same(
        lambda: live_availability.study_rank(models_of(live_models, "StudyWindow", bodies), subject, d, start, duration),
        lambda: ref_availability.study_rank(models_of(ref_models, "StudyWindow", bodies), subject, d, start, duration),
        f"{bodies} {subject!r} {d} {start} {duration}",
    )


@COMMON
@given(st.one_of(st.none(), st.lists(work_window(), max_size=4)))
def test_resolve_work_windows(bodies):
    if bodies is not None:
        valid("WorkWindow", bodies)
    same(
        lambda: live_availability.resolve_work_windows(None if bodies is None else models_of(live_models, "WorkWindow", bodies)),
        lambda: ref_availability.resolve_work_windows(None if bodies is None else models_of(ref_models, "WorkWindow", bodies)),
        f"{bodies}",
    )


@COMMON
@given(st.lists(work_window(), max_size=4), course, st.integers(-1, 7), st.integers(-15, 1500), st.integers(0, 600))
def test_session_inside_work_windows(bodies, subject, d, start, duration):
    valid("WorkWindow", bodies)
    same(
        lambda: live_availability.session_inside_work_windows(models_of(live_models, "WorkWindow", bodies), subject, d, start, duration),
        lambda: ref_availability.session_inside_work_windows(models_of(ref_models, "WorkWindow", bodies), subject, d, start, duration),
        f"{bodies} {subject!r} {d} {start} {duration}",
    )


@COMMON
@given(st.lists(st.integers(0, (1 << 96) - 1), max_size=8), st.lists(st.integers(0, (1 << 96) - 1), max_size=8))
def test_merge_occupancy(base, extra):
    same(lambda: live_availability.merge_occupancy(base, extra), lambda: ref_availability.merge_occupancy(base, extra), f"{base} {extra}")


@COMMON
@given(occupancy, st.integers(-1, 7), st.integers(-30, 1500), st.integers(-30, 1500))
def test_add_occupancy(occ, d, start, end):
    def run(module):
        mine = list(occ)
        module.add_occupancy(mine, d, start, end)
        return mine

    same(lambda: run(live_availability), lambda: run(ref_availability), f"{d} {start} {end}")


@COMMON
@given(
    st.sampled_from([15, 30, 60, 90, 100, 120, 600, 1440]),
    st.integers(0, 300),
    st.integers(0, 300),
    due,
    st.sampled_from([15, 30, 45, 60, 90, 0, -15, 20]),
    st.one_of(near_day, iso_day, st.sampled_from(["2026-02-30", "bad"])),
)
def test_spread_sessions(estimate, focus, planned, due_text, session, start):
    kwargs = dict(estimate_min=estimate, focus_minutes=focus, planned_min=planned, due=due_text, session_min=session, from_date=start)
    assume(session > 0)  # 0 loops for ever in the original
    same(lambda: live_availability.spread_sessions(**kwargs), lambda: ref_availability.spread_sessions(**kwargs), f"{kwargs}")


# ---------- assignments


@COMMON
@given(monday, st.one_of(words, odd_text))
def test_migrated_assignment_id(week, source):
    same(lambda: live_assignments.migrated_assignment_id(week, source), lambda: ref_assignments.migrated_assignment_id(week, source), f"{week} {source!r}")


@COMMON
@given(st.one_of(monday, st.just("2026-09-09"), st.just("bad")), deadline_text, st.one_of(days_any, st.just([])))
def test_due_from_latest(week, latest, days):
    same(lambda: live_assignments.due_from_latest(week, latest, days), lambda: ref_assignments.due_from_latest(week, latest, days), f"{week} {latest!r} {days}")


@COMMON
@given(monday, block_dict())
def test_completed_at_for_block(week, body):
    same(lambda: live_assignments.completed_at_for_block(week, body), lambda: ref_assignments.completed_at_for_block(week, body), f"{week} {body}")


@COMMON
@given(st.one_of(monday, st.just("2026-09-09")), st.one_of(due, st.sampled_from(["bad", "2026-09-09T24:00", "1999-01-01"])))
def test_due_bounds(week, due_text):
    same(lambda: live_assignments.due_placement_bound(week, due_text), lambda: ref_assignments.due_placement_bound(week, due_text), f"bound {week} {due_text}")
    same(lambda: live_assignments.due_slack_point(week, due_text), lambda: ref_assignments.due_slack_point(week, due_text), f"slack {week} {due_text}")


@COMMON
@given(st.data())
def test_prepare_solve(data):
    blocks = data.draw(week_blocks())
    rows = {body["id"]: body for body, _rev in data.draw(assignment_rows())}
    week = data.draw(monday)
    same(
        lambda: live_assignments.prepare_solve(models_of(live_models, "TimeBlock", blocks), week, rows),
        lambda: ref_assignments.prepare_solve(models_of(ref_models, "TimeBlock", blocks), week, rows),
        f"{week}\n blocks {json.dumps(blocks)}\n rows {json.dumps(rows)}",
    )


@COMMON
@given(monday, block_dict(kinds=("flexible",)))
def test_legacy_session(week, body):
    try:
        ref_models.TimeBlock.model_validate(body)
    except ValidationError:
        assume(False)
    same(
        lambda: live_assignments.legacy_session(week, live_models.TimeBlock.model_validate(body)),
        lambda: ref_assignments.legacy_session(week, ref_models.TimeBlock.model_validate(body)),
        f"{week} {json.dumps(body)}",
    )


@COMMON
@given(st.data())
def test_rewrite_session(data):
    body = data.draw(block_dict())
    try:
        ref_models.TimeBlock.model_validate(body)
    except ValidationError:
        assume(False)
    assignment = data.draw(assignment_body("a1"))
    same(
        lambda: live_assignments.rewrite_session(live_models.TimeBlock.model_validate(body), assignment),
        lambda: ref_assignments.rewrite_session(ref_models.TimeBlock.model_validate(body), assignment),
        f"{json.dumps(body)} {json.dumps(assignment)}",
    )


@COMMON
@given(stored_weeks(), st.sampled_from(MONDAYS[:2] + ["2026-09-14", "2000-01-03"]))
def test_planned_minutes_by_id(weeks, from_week):
    same(lambda: live_assignments.planned_minutes_by_id(weeks, from_week), lambda: ref_assignments.planned_minutes_by_id(weeks, from_week), f"{from_week} {json.dumps(weeks)}")


@COMMON
@given(st.integers(-10, 2000), st.integers(-10, 2000), st.integers(-10, 2000))
def test_unplanned_minutes(estimate, focus, planned):
    same(lambda: live_assignments.unplanned_minutes(estimate, focus, planned), lambda: ref_assignments.unplanned_minutes(estimate, focus, planned), f"{estimate} {focus} {planned}")


@COMMON
@given(monday, st.data())
def test_migrate_blocks(week, data):
    blocks = data.draw(week_blocks(max_size=8))
    # Stored weeks from before sessions: plain dicts, as the store holds them.
    stored = [ref_models.TimeBlock.model_validate(body).model_dump() for body in blocks]
    same(lambda: live_assignments.migrate_blocks(week, stored), lambda: ref_assignments.migrate_blocks(week, stored), f"{week} {json.dumps(stored)}")


# ---------- comfort


@COMMON
@given(st.integers(-50, 400), st.integers(-5, 200), st.integers(-5, 400))
def test_snap_minutes(value, low, high):
    same(lambda: live_comfort.snap_minutes(value, low, high), lambda: ref_comfort.snap_minutes(value, low, high), f"{value} {low} {high}")


@COMMON
@given(st.integers(0, 600), st.integers(1, 180), st.integers(0, 60), st.integers(0, 120), st.integers(1, 8))
def test_split_plan(duration, work, rest, long, cadence):
    same(lambda: live_comfort.split_plan(duration, work, rest, long, cadence), lambda: ref_comfort.split_plan(duration, work, rest, long, cadence), f"{duration} {work} {rest} {long} {cadence}")


@COMMON
@given(st.one_of(st.none(), st.integers(0, 600)), st.integers(1, 200), st.integers(1, 90), st.integers(1, 150), st.integers(1, 8))
def test_preview_split(duration, work, rest, long, cadence):
    kwargs = dict(duration_min=duration, timer_work_min=work, timer_break_min=rest, timer_long_break_min=long, timer_long_break_every=cadence)
    same(lambda: live_comfort.preview_split(**kwargs), lambda: ref_comfort.preview_split(**kwargs), f"{kwargs}")


# ---------- day and month


@COMMON
@given(st.data())
def test_build_day(data):
    week = data.draw(st.sampled_from(MONDAYS[:2]))
    offset = data.draw(st.integers(-1, 8))
    from datetime import date, timedelta

    agenda = (date.fromisoformat(week) + timedelta(days=offset)).isoformat()
    blocks = [ref_models.TimeBlock.model_validate(body).model_dump() for body in data.draw(week_blocks())]
    rows = data.draw(assignment_rows())
    weeks = data.draw(stored_weeks())
    same(
        lambda: live_day.build_day(agenda, week, blocks, rows, weeks),
        lambda: ref_day.build_day(agenda, week, blocks, rows, weeks),
        f"{agenda} {week}\n blocks {json.dumps(blocks)}\n rows {json.dumps(rows)}\n weeks {json.dumps(weeks)}",
    )


@COMMON
@given(st.data())
def test_is_work_session(data):
    body = data.draw(block_dict())
    same(lambda: live_day.is_work_session(body), lambda: ref_day.is_work_session(body), f"{body}")


def finished_session_without_start_shares_a_day(weeks: list) -> bool:
    """The one month input the original cannot sort and the engine still draws."""
    for _week_start, blocks in weeks:
        for index, block in enumerate(blocks):
            start = block.get("start")
            if not block.get("completed") or (start is not None and start != ""):
                continue
            days = {day for day in block.get("days") or [] if isinstance(day, int)}
            if not days:
                continue
            for other_index, other in enumerate(blocks):
                if other_index == index:
                    continue
                if days & set(other.get("days") or []):
                    return True
    return False


def test_the_month_escape_names_only_a_finished_session_without_a_start():
    shared = [
        (
            "2026-09-14",
            [
                {"id": "done", "completed": True, "days": [0], "kind": "flexible"},
                {"id": "other", "start": "09:00", "days": [0], "kind": "locked"},
            ],
        )
    ]
    alone = [("2026-09-14", [{"id": "done", "completed": True, "days": [0], "kind": "flexible"}])]
    started = [
        (
            "2026-09-14",
            [
                {"id": "done", "completed": True, "start": "09:00", "days": [0], "kind": "flexible"},
                {"id": "other", "start": "10:00", "days": [0], "kind": "locked"},
            ],
        )
    ]
    assert finished_session_without_start_shares_a_day(shared)
    assert not finished_session_without_start_shares_a_day(alone)
    assert not finished_session_without_start_shares_a_day(started)


@COMMON
@given(st.data())
def test_build_month(data):
    label = data.draw(st.sampled_from(["2026-09", "2026-10", "2026-08", "2024-02", "2026-13", "bad"]))
    rows = data.draw(assignment_rows())
    weeks = data.draw(stored_weeks())
    got = outcome(lambda: live_month.build_month(label, rows, weeks))
    want = outcome(lambda: ref_month.build_month(label, rows, weeks))
    # Known difference, left for Jonathan: a finished session with no start, on a day that also
    # has another block, makes the original raise TypeError (None sorted against a string).
    # Rust returns the month. Do not copy that crash. Any other TypeError still fails.
    if (
        want[0] == "raise"
        and want[1] == "TypeError"
        and got[0] == "ok"
        and finished_session_without_start_shares_a_day(weeks)
    ):
        return
    assert got == want, (
        f"{label}\n rows {json.dumps(rows)}\n weeks {json.dumps(weeks)}"
        f"\n  rust:   {json.dumps(got, default=str)[:1500]}\n  python: {json.dumps(want, default=str)[:1500]}"
    )


# ---------- words


def test_sentences():
    for code in ref_explain.REASON_COPY:
        assert live_explain.sentence(code) == ref_explain.sentence(code), code
    assert set(live_explain.REASON_COPY) == set(ref_explain.REASON_COPY)


@COMMON
@given(st.integers(-200, 20000), st.sampled_from(["ok", "tight", "danger"]))
def test_slack_sentence(slack, status):
    same(lambda: live_explain.slack_sentence(slack, status), lambda: ref_explain.slack_sentence(slack, status), f"{slack} {status}")


# ---------- restore points and transfer

json_leaf = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(-(2**53), 2**53),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(alphabet=st.characters(blacklist_categories=["Cs"]), max_size=8),
)
json_value = st.recursive(
    json_leaf,
    lambda inner: st.one_of(st.lists(inner, max_size=4), st.dictionaries(st.text(max_size=5), inner, max_size=4)),
    max_leaves=12,
)


@COMMON
@given(json_value)
def test_canonical_and_state_token(value):
    same(lambda: live_restore.canonical(value), lambda: ref_restore.canonical(value), f"{value!r}")
    if isinstance(value, dict):
        same(lambda: live_restore.state_token(value), lambda: ref_restore.state_token(value), f"{value!r}")


@st.composite
def snapshot(draw):
    weeks = [{"week_start": start, "blocks": blocks} for start, blocks in draw(stored_weeks())]
    assignments = []
    for body, _rev in draw(assignment_rows()):
        stored = json.dumps(body) if draw(st.booleans()) else body
        assignments.append({"id": body["id"], "body": stored, "revision": 1})
    routines = [
        {"id": ident, "name": draw(title), "blocks": draw(st.lists(st.just({"template_id": "t"}), max_size=2)), "revision": draw(st.integers(0, 3)), "extra": draw(st.integers(0, 2))}
        for ident in draw(st.lists(st.sampled_from(["r1", "r2", "r3"]), max_size=3, unique=True))
    ]
    return {"weeks": weeks, "assignments": assignments, "routines": routines, "preferences": draw(st.dictionaries(st.sampled_from(["theme", "clock_24h", "x"]), json_leaf, max_size=3))}


@COMMON
@given(snapshot(), snapshot())
def test_diffs(current, stored):
    same(lambda: live_restore.diff_snapshots(current, stored), lambda: ref_restore.diff_snapshots(current, stored), f"{json.dumps(current)}\n{json.dumps(stored)}")
    same(lambda: live_restore.diff_transfer(current, stored), lambda: ref_restore.diff_transfer(current, stored), f"{json.dumps(current)}\n{json.dumps(stored)}")
    same(lambda: live_restore.state_token(current), lambda: ref_restore.state_token(current), f"{json.dumps(current)}")


@COMMON
@given(snapshot())
def test_transfer(value):
    same(lambda: live_transfer.transfer_apply_envelope(value), lambda: ref_transfer.transfer_apply_envelope(value), "envelope")
    same(lambda: live_transfer.transfer_apply_bytes(value), lambda: ref_transfer.transfer_apply_bytes(value), f"bytes {json.dumps(value)}")
    same(lambda: live_transfer.transfer_fits(value), lambda: ref_transfer.transfer_fits(value), "fits")


def test_transfer_at_the_limit():
    from backend.tests.engine_ref.limits import MAX_BODY

    for pad in range(MAX_BODY - 400, MAX_BODY + 50, 7):
        value = {"weeks": [], "assignments": [], "routines": [], "preferences": {"x": "é" * 3 + "a" * pad}}
        assert live_transfer.transfer_apply_bytes(value) == ref_transfer.transfer_apply_bytes(value), pad
        assert live_transfer.transfer_fits(value) == ref_transfer.transfer_fits(value), pad


# ---------- recovery codes and hashes

code_text = st.one_of(
    st.text(alphabet="0123456789abcdefABCDEF- ", max_size=24),
    st.text(alphabet=st.characters(blacklist_categories=["Cs"]), max_size=12),
)


@COMMON
@given(code_text)
def test_recovery_text(value):
    same(lambda: live_recovery.normalize_recovery_code(value), lambda: ref_recovery.normalize_recovery_code(value), f"normalize {value!r}")
    same(lambda: live_recovery.hash_recovery_code(value), lambda: ref_recovery.hash_recovery_code(value), f"hash {value!r}")
    same(lambda: live_recovery.format_recovery_code(value), lambda: ref_recovery.format_recovery_code(value), f"format {value!r}")
    stored = ref_recovery.hash_recovery_code("ABCD-EF01-2345-6789") if hasattr(ref_recovery, "hash_recovery_code") else ""
    same(lambda: live_recovery.recovery_code_matches(value, stored), lambda: ref_recovery.recovery_code_matches(value, stored), f"matches {value!r}")


def test_generated_recovery_codes_keep_their_shape():
    ours = live_recovery.generate_recovery_codes()
    assert len(ours) == len(set(ours)) == ref_recovery.RECOVERY_CODE_COUNT
    for code in ours:
        assert ref_recovery.RECOVERY_CODE_PATTERN.fullmatch(code), code
        assert ref_recovery.recovery_code_matches(code, live_recovery.hash_recovery_code(code))


@COMMON
@given(st.text(max_size=20))
def test_digest(value):
    same(lambda: live_storage.digest(value), lambda: ref_storage.digest(value), f"{value!r}")


@settings(max_examples=12, deadline=None, derandomize=True)
@given(st.text(max_size=30), st.sampled_from(["00112233445566778899aabbccddeeff", "ffffffffffffffffffffffffffffffff", "00"]))
def test_password_hash(password, salt):
    same(lambda: live_storage.password_hash(password, salt), lambda: ref_storage.password_hash(password, salt), f"{password!r} {salt}")
    encoded = ref_storage.password_hash(password, salt)
    assert live_storage.password_matches(password, encoded) is True
    assert ref_storage.password_matches(password, live_storage.password_hash(password, salt)) is True


@settings(max_examples=40, deadline=None, derandomize=True)
@given(
    st.sampled_from(
        [
            "",
            "scrypt",
            "scrypt$32768$8$3$00$00",
            "scrypt$1024$8$1$00112233445566778899aabbccddeeff$" + "0" * 64,
            "scrypt$32768$8$3$zz$zz",
            "scrypt$32768$8$3$00112233445566778899aabbccddeeff",
            "bcrypt$32768$8$3$00112233445566778899aabbccddeeff$" + "0" * 64,
            "scrypt$x$8$3$00112233445566778899aabbccddeeff$" + "0" * 64,
            "scrypt$32768$8$3$00112233445566778899AABBCCDDEEFF$ACFA1AD8D5C639D068E6988715F03DD7B1ACDB99C998707B1632762596FD2B16",
            "scrypt$32768$8$3$00112233445566778899aabbccddeeff$acfa1ad8d5c639d068e6988715f03dd7b1acdb99c998707b1632762596fd2b16",
            "scrypt$32768$8$3$00112233445566778899aabbccddeeff$acfa1ad8d5c639d068e6988715f03dd7b1acdb99c998707b1632762596fd2b16$extra",
        ]
    )
)
def test_password_matches_on_stored_shapes(encoded):
    same(lambda: live_storage.password_matches("secret", encoded), lambda: ref_storage.password_matches("secret", encoded), f"{encoded!r}")


def test_recorded_backend_fixtures_match():
    """Inputs the backend tests already use, run through both copies."""
    from pathlib import Path

    data = Path(__file__).resolve().parents[1] / "data"
    for name in ("demo_alex.json", "demo_jordan.json"):
        blocks = json.loads((data / name).read_text())
        same(
            lambda blocks=blocks: live_day.build_day("2026-09-08", "2026-09-07", blocks, [], [("2026-09-07", blocks)]),
            lambda blocks=blocks: ref_day.build_day("2026-09-08", "2026-09-07", blocks, [], [("2026-09-07", blocks)]),
            name,
        )
        same(
            lambda blocks=blocks: live_month.build_month("2026-09", [], [("2026-09-07", blocks)]),
            lambda blocks=blocks: ref_month.build_month("2026-09", [], [("2026-09-07", blocks)]),
            name,
        )
        snapshot = {
            "weeks": [{"week_start": "2026-09-07", "blocks": blocks}],
            "assignments": [],
            "routines": [],
            "preferences": {},
        }
        same(lambda snapshot=snapshot: live_restore.canonical(snapshot), lambda snapshot=snapshot: ref_restore.canonical(snapshot), name)
        same(
            lambda snapshot=snapshot: live_transfer.transfer_apply_bytes(snapshot),
            lambda snapshot=snapshot: ref_transfer.transfer_apply_bytes(snapshot),
            name,
        )

    lesson = {
        "id": "lesson",
        "title": "Lesson",
        "kind": "locked",
        "start": "17:37",
        "duration_min": 45,
        "days": [1],
    }
    same(
        lambda: live_day.build_day("2026-09-08", "2026-09-07", [lesson], [], []),
        lambda: ref_day.build_day("2026-09-08", "2026-09-07", [lesson], [], []),
        "lesson",
    )
    spreads = [
        dict(estimate_min=120, focus_minutes=0, planned_min=0, due="2026-09-15T23:59", session_min=60, from_date="2026-09-14"),
        dict(estimate_min=90, focus_minutes=0, planned_min=0, due="2026-09-15T23:59", session_min=45, from_date="2026-09-16"),
        dict(estimate_min=120, focus_minutes=7, planned_min=0, due="2026-09-15T23:59", session_min=60, from_date="2026-09-14"),
        dict(estimate_min=60, focus_minutes=53, planned_min=0, due="2026-09-15T23:59", session_min=60, from_date="2026-09-14"),
    ]
    for kwargs in spreads:
        same(
            lambda kwargs=kwargs: live_availability.spread_sessions(**kwargs),
            lambda kwargs=kwargs: ref_availability.spread_sessions(**kwargs),
            str(kwargs),
        )
    for code in ref_explain.REASON_COPY:
        same(lambda code=code: live_explain.sentence(code), lambda code=code: ref_explain.sentence(code), code)
    for clock in ("00:00", "06:00", "23:00", "16:00", "23:45", "08:10", "24:00", "8", "17:37"):
        same(lambda clock=clock: live_slots.hhmm_to_minutes(clock), lambda clock=clock: ref_slots.hhmm_to_minutes(clock), clock)
        same(lambda clock=clock: live_slots.hhmm_to_slot(clock), lambda clock=clock: ref_slots.hhmm_to_slot(clock), clock)
    for minutes in (0, 6 * 60, 23 * 60, 1440):
        same(lambda minutes=minutes: live_slots.minutes_to_hhmm(minutes), lambda minutes=minutes: ref_slots.minutes_to_hhmm(minutes), str(minutes))
    for latest, days in (
        ("Thursday 21:00", [0, 1, 2, 3, 4]),
        ("Wednesday 07:45", [0, 1, 2]),
        ("2026-09-10T21:00", [0, 1, 2, 3]),
        ("21:00", [0, 1, 4]),
        (None, [0]),
        ("", [0]),
    ):
        same(
            lambda latest=latest, days=days: live_slots.parse_deadline(latest, days),
            lambda latest=latest, days=days: ref_slots.parse_deadline(latest, days),
            str(latest),
        )
    for day in (
        "2026-09-07", "2026-09-08", "2026-09-13", "2026-09-7", "not-a-date", "2026-13-40",
        "20260907", "2026-W37-1", "2000-01-01", "2000-01-03", "2099-12-31", "1999-12-31",
        "2100-01-01", "2026-10-01", "2027-01-01",
    ):
        same(lambda day=day: live_weeks.monday_of(day), lambda day=day: ref_weeks.monday_of(day), day)
        same(lambda day=day: live_weeks.is_week_start(day), lambda day=day: ref_weeks.is_week_start(day), day)
        same(lambda day=day: live_weeks.is_calendar_date(day), lambda day=day: ref_weeks.is_calendar_date(day), day)
    for label in ("2026-09", "2026-02", "2000-01", "2099-12", "", "2026-9", "2026-13", "1999-12", "2100-01"):
        same(lambda label=label: live_weeks.parse_month(label), lambda label=label: ref_weeks.parse_month(label), label)
        same(lambda label=label: live_weeks.is_month_label(label), lambda label=label: ref_weeks.is_month_label(label), label)
    for args in ((25, 1, 180), (5, 1, 60), (1, 1, 180), (30, 1, 180)):
        same(lambda args=args: live_comfort.snap_minutes(*args), lambda args=args: ref_comfort.snap_minutes(*args), str(args))
    same(lambda: live_comfort.split_plan(90, 30, 15, 15, 4), lambda: ref_comfort.split_plan(90, 30, 15, 15, 4), "split")
    for slack, status in ((29, "danger"), (135, "tight"), (300, "ok"), (0, "danger")):
        same(
            lambda slack=slack, status=status: live_explain.slack_sentence(slack, status),
            lambda slack=slack, status=status: ref_explain.slack_sentence(slack, status),
            status,
        )
    same(
        lambda: live_recovery.normalize_recovery_code("A1B2-C3D4-E5F6-7890"),
        lambda: ref_recovery.normalize_recovery_code("A1B2-C3D4-E5F6-7890"),
        "recovery",
    )
    same(
        lambda: live_recovery.hash_recovery_code("a1b2-c3d4-e5f6-7890"),
        lambda: ref_recovery.hash_recovery_code("a1b2-c3d4-e5f6-7890"),
        "recovery-hash",
    )


# ---------- subjects that differ by case beyond ASCII (the original folds with str.casefold)


def test_subject_windows_fold_case_as_python_does():
    homework = {"id": "hw", "title": "Essay", "kind": "flexible", "days": [0], "duration_min": 60}
    pairs = [("ética", "Ética"), ("STRASSE", "straße"), ("ÉLAN", "élan"), ("Math", "math")]
    for course_name, subject in pairs:
        blocks = [{**homework, "course": course_name}]
        both_solvers("solve", blocks, {"work_windows": [{"days": [0], "start": "16:00", "end": "18:00", "subject": subject}]})
        both_solvers("solve", blocks, {"study_windows": [{"days": [0], "start": "20:00", "duration_min": 60, "subject": subject}]})


def test_a_fake_clock_does_not_outlast_its_test(tmp_path):
    """Two tests in a fresh pytest run: the first fakes both clocks, the second must find the real ones."""
    (tmp_path / "test_leak.py").write_text(
        textwrap.dedent(
            """
            import time

            from backend import solver as live_solver
            from backend.tests.engine_ref import solver as ref_solver
            from backend.tests.test_engine_parity import restore_solver_clocks  # noqa: F401


            def test_one_fakes_the_clocks():
                live_solver.time = ref_solver.time = object()


            def test_two_sees_the_real_clocks():
                assert live_solver.time is time
                assert ref_solver.time is time
            """
        )
    )
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(tmp_path), str(tmp_path)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[2])},
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "2 passed" in run.stdout, run.stdout


# ---------- adapters: logic that moved in this slice

# One argument has to miss i64 so the wide path always runs. Integers past 2^53 also take it,
# even when they fit in i64, because f64 cannot hold them exactly.
_WIDE_INT = st.one_of(
    st.integers(min_value=2**63, max_value=2**400),
    st.integers(min_value=-(2**400), max_value=-(2**63) - 1),
)
_ANY_INT = st.integers(min_value=-(2**400), max_value=2**400)


@COMMON
@given(_WIDE_INT, _ANY_INT, _ANY_INT, st.integers(0, 2))
def test_snap_minutes_wide_integers(wide, other_a, other_b, slot):
    args = [other_a, other_b]
    args.insert(slot, wide)
    value, low, high = args
    same(
        lambda: live_comfort.snap_minutes(value, low, high),
        lambda: ref_comfort.snap_minutes(value, low, high),
        f"{value} {low} {high}",
    )


def test_snap_minutes_past_i64_and_overflow():
    cases = [
        (10**19, 1, 10**20),
        (10**19, 1, 180),
        (-(10**19), 1, 180),
        (10**20, 0, 10**21),
        (2**63, 1, 2**63),
        (2**63, 1, 180),
        (-(2**63), -100, 180),
        (10**18, 10**18, 10**18 + 50),
        (2**100, 1, 2**100),
        (2**80 + 7, 1, 2**100),
        (10**6, -40, 50),
        (-(10**19), -(10**19), -1),
        (2**53 + 3, 1, 2**60),
        (2**1027, 1, 2**1027),
        (2**64, 1, 10**20),
        (2**64 - 1, 1, 10**20),
    ]
    for value, low, high in cases:
        same(
            lambda value=value, low=low, high=high: live_comfort.snap_minutes(value, low, high),
            lambda value=value, low=low, high=high: ref_comfort.snap_minutes(value, low, high),
            f"{value} {low} {high}",
        )
    same(
        lambda: live_comfort.snap_minutes(10**400, 1, 10**400),
        lambda: ref_comfort.snap_minutes(10**400, 1, 10**400),
        "overflow",
    )


def test_resolve_work_windows_empty_matches_missing():
    same(
        lambda: live_availability.resolve_work_windows(None),
        lambda: ref_availability.resolve_work_windows(None),
        "none",
    )
    same(
        lambda: live_availability.resolve_work_windows([]),
        lambda: ref_availability.resolve_work_windows([]),
        "empty",
    )


def test_empty_solver_windows_default_like_the_original():
    block = {"id": "hw", "title": "Essay", "kind": "flexible", "days": [0], "duration_min": 60}
    both_solvers("solve", [block], {})
    both_solvers("solve", [block], {"work_windows": [], "study_windows": []})


def test_recovery_codes_follow_the_same_draws():
    import secrets

    sequence = [
        bytes.fromhex("0011223344556677"),
        bytes.fromhex("0011223344556677"),
        bytes.fromhex("ab"),
        bytes.fromhex("aabbccddeeff0011"),
    ]
    live_draws = iter(sequence)
    ref_draws = iter(sequence)
    token_bytes, token_hex = secrets.token_bytes, secrets.token_hex

    def live_draw(_n: int) -> bytes:
        return next(live_draws)

    def ref_draw(_n: int) -> str:
        return next(ref_draws).hex()

    secrets.token_bytes = live_draw
    secrets.token_hex = ref_draw
    try:
        same(
            lambda: live_recovery.generate_recovery_codes(2),
            lambda: ref_recovery.generate_recovery_codes(2),
            "draws",
        )
        same(
            lambda: live_recovery.generate_recovery_codes(0),
            lambda: ref_recovery.generate_recovery_codes(0),
            "zero",
        )
        same(
            lambda: live_recovery.generate_recovery_codes(-3),
            lambda: ref_recovery.generate_recovery_codes(-3),
            "negative",
        )
    finally:
        secrets.token_bytes = token_bytes
        secrets.token_hex = token_hex


def test_recovery_code_matches_ascii_length_and_non_ascii():
    code = "0011-2233-4455-6677"
    stored = ref_recovery.hash_recovery_code(code)
    same(
        lambda: live_recovery.recovery_code_matches(code, stored),
        lambda: ref_recovery.recovery_code_matches(code, stored),
        "equal",
    )
    same(
        lambda: live_recovery.recovery_code_matches(code, stored[:-1]),
        lambda: ref_recovery.recovery_code_matches(code, stored[:-1]),
        "short",
    )
    same(
        lambda: live_recovery.recovery_code_matches(code, "é"),
        lambda: ref_recovery.recovery_code_matches(code, "é"),
        "non-ascii",
    )
    same(
        lambda: live_recovery.recovery_code_matches(code, "\x7f" * 64),
        lambda: ref_recovery.recovery_code_matches(code, "\x7f" * 64),
        "del",
    )
    same(
        lambda: live_recovery.recovery_code_matches("nope", stored),
        lambda: ref_recovery.recovery_code_matches("nope", stored),
        "presented",
    )


def test_password_matches_without_a_salt_is_index_error():
    for encoded in ("", "nosalt", "scrypt"):
        same(
            lambda encoded=encoded: live_storage.password_matches("secret", encoded),
            lambda encoded=encoded: ref_storage.password_matches("secret", encoded),
            encoded,
        )


def test_create_session_stores_digest_and_week_expiry(tmp_path, monkeypatch):
    token = "fixed-session-token"
    now = 1_700_000_000
    monkeypatch.setattr(live_storage.secrets, "token_urlsafe", lambda _n: token)
    monkeypatch.setattr(live_storage.time, "time", lambda: now)
    live_path = tmp_path / "live.sqlite"
    ref_path = tmp_path / "ref.sqlite"
    live_storage.initialize(live_path)
    ref_storage.initialize(ref_path)
    with live_storage.connect(live_path) as db:
        user = db.insert_user("ada", "hash")
        db.execute("INSERT INTO sessions VALUES (?, ?, ?)", ("old", user, 100))
        got = live_storage.create_session(db, user)
        row = db.execute("SELECT token_hash, user_id, expires FROM sessions").fetchall()
    with ref_storage.connect(ref_path) as db:
        db.execute("INSERT INTO users(username, password_hash) VALUES (?, ?)", ("ada", "hash"))
        user_ref = db.execute("SELECT id FROM users").fetchone()[0]
        db.execute("INSERT INTO sessions VALUES (?, ?, ?)", ("old", user_ref, 100))
        want = ref_storage.create_session(db, user_ref)
        row_ref = db.execute("SELECT token_hash, user_id, expires FROM sessions").fetchall()
    assert got == want == token
    assert [(item[0], item[1], item[2]) for item in row] == [(item[0], item[1], item[2]) for item in row_ref]
    assert row[0][2] == now + 7 * 24 * 60 * 60


def test_initialize_dates_a_legacy_week_with_the_same_monday(tmp_path):
    def legacy(path):
        import sqlite3

        db = sqlite3.connect(path)
        db.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL)"
        )
        db.execute("INSERT INTO users(username, password_hash) VALUES ('ada', 'x')")
        db.execute("CREATE TABLE weeks (user_id INTEGER, blocks TEXT, revision INTEGER)")
        db.execute("INSERT INTO weeks VALUES (1, '[]', 0)")
        db.commit()
        db.close()

    live_path = tmp_path / "live.sqlite"
    ref_path = tmp_path / "ref.sqlite"
    legacy(live_path)
    legacy(ref_path)
    live_storage.initialize(live_path)
    ref_storage.initialize(ref_path)
    import sqlite3

    def week_start(path):
        db = sqlite3.connect(path)
        row = db.execute("SELECT week_start FROM weeks").fetchone()
        db.close()
        return row[0]

    assert week_start(live_path) == week_start(ref_path)


@COMMON
@given(st.one_of(st.none(), st.integers(-5, 5), st.lists(st.integers(-3, 3), max_size=3), st.text(max_size=12)))
def test_transfer_fits_on_non_dicts(value):
    same(
        lambda: live_transfer.transfer_fits(value),
        lambda: ref_transfer.transfer_fits(value),
        repr(value),
    )


# ---------- the helpers of backend/app.py
#
# The `ref_*` functions are the helper bodies as they were in Python before their rules moved into
# the engine (backend/tests/engine_ref/app_helpers.py has the ones that read the database; the rest
# are copied from the pre-port server, with the imports pointed at engine_ref).


def ref_payload_digest(value):
    return hashlib.sha256(ref_restore.canonical(value).encode()).hexdigest()


def ref_assignment_view(body, revision, planned):
    return {
        **body,
        "revision": revision,
        "planned_min": planned,
        "unplanned_min": ref_assignments.unplanned_minutes(
            int(body["estimate_min"]), int(body["focus_minutes"]), planned
        ),
    }


def ref_rewrite_blocks(blocks, assignments):
    rewritten = []
    for block in blocks:
        if block.assignment_id:
            rewritten.append(ref_assignments.rewrite_session(block, assignments[block.assignment_id]))
        else:
            rewritten.append(block)
    return rewritten


def ref_rewrite_stored_blocks(blocks, assignments):
    rewritten = []
    for raw in blocks:
        aid = raw.get("assignment_id")
        if not aid or aid not in assignments:
            rewritten.append(raw)
            continue
        rewritten.append(
            ref_assignments.rewrite_session(ref_models.TimeBlock.model_validate(raw), assignments[aid]).model_dump()
        )
    return rewritten


def ref_require_own_assignments(db, user_id, ids):
    loaded = ref_app_helpers.load_assignment_rows(db, user_id, ids)
    found = {key: json.loads(body) for key, (body, _revision) in loaded.items()}
    if found.keys() != ids:
        raise ref_app_helpers.HTTPException(422, live_app.ASSIGNMENT_UNKNOWN)
    return found


def ref_solve_availability(stored):
    if stored is None:
        return [0] * 7, [], []
    availability = json.loads(stored or "{}")
    protected = [ref_models.ProtectedWindow.model_validate(item) for item in availability.get("protected") or []]
    study = [ref_models.StudyWindow.model_validate(item) for item in availability.get("study_windows") or []]
    work = [ref_models.WorkWindow.model_validate(item) for item in availability.get("work_windows") or []]
    return ref_availability.occupancy_from_windows(protected, availability.get("day_cutoff")), study, work


def ref_preferences_from_row(row):
    availability = json.loads(row["availability_json"] or "{}")
    comfort = json.loads(row["comfort_json"] or "{}")
    return live_app.Preferences(
        theme=row["theme"],
        reminders_enabled=bool(row["reminders_enabled"]),
        reminder_lead_min=int(row["reminder_lead_min"]),
        reminder_sound=bool(row["reminder_sound"]),
        reminder_dnd_override=bool(row["reminder_dnd_override"]),
        timer_work_min=int(row["timer_work_min"]),
        timer_break_min=int(row["timer_break_min"]),
        timer_long_break_min=int(row["timer_long_break_min"]),
        timer_long_break_every=int(row["timer_long_break_every"]),
        auto_split_pomodoro=bool(row["auto_split_pomodoro"]),
        default_spotify_url=row["default_spotify_url"],
        alarms=json.loads(row["alarms_json"]),
        protected=availability.get("protected") or [],
        study_windows=availability.get("study_windows") or [],
        work_windows=availability.get("work_windows") or [],
        day_cutoff=availability.get("day_cutoff"),
        alert_volume=comfort.get("alert_volume", 80),
        end_chime=bool(comfort.get("end_chime", False)),
        tray_notifications=bool(comfort.get("tray_notifications", True)),
        start_at_login=bool(comfort.get("start_at_login", False)),
        preferred_view=comfort.get("preferred_view"),
        sidebar_collapsed=bool(comfort.get("sidebar_collapsed", False)),
        sidebar_width_px=comfort.get("sidebar_width_px"),
        theme_pack=comfort.get("theme_pack", "system"),
        accent=comfort.get("accent", "default"),
        accent_chips=bool(comfort.get("accent_chips", False)),
        motion=comfort.get("motion"),
        alarm_tone=comfort.get("alarm_tone", "chime"),
        planning_style=comfort.get("planning_style", "suggest"),
        drag_step_min=comfort.get("drag_step_min", 5),
        clock_24h=bool(comfort.get("clock_24h", True)),
        setup=comfort.get("setup"),
    ).model_dump()


@COMMON
@given(json_value)
def test_payload_digest(value):
    same(lambda: live_app.payload_digest(value), lambda: ref_payload_digest(value), f"{value!r}")


def test_payload_digest_on_what_json_cannot_write():
    for value in ([object()], {1, 2}, {"a": float("nan")}, {1: "a", "b": 2}, "lone \ud800"):
        same(lambda value=value: live_app.payload_digest(value), lambda value=value: ref_payload_digest(value), repr(value))


estimate_value = st.one_of(
    st.sampled_from([15, 30, 60, 90, 600]),
    st.sampled_from([None, "45", "x", "", " 7 ", 4.5, -2.5, True, False, [1], {"a": 1}]),
    st.integers(min_value=-300, max_value=3000),
)


@COMMON
@given(
    st.fixed_dictionaries(
        {"estimate_min": estimate_value, "focus_minutes": estimate_value},
        optional={
            "id": st.just("a1"),
            "revision": st.integers(0, 9),
            "planned_min": st.integers(0, 9),
            "unplanned_min": st.integers(0, 9),
            "notes": st.just("n"),
        },
    ),
    st.integers(0, 10**6),
    st.integers(-500, 3000),
    st.sets(st.sampled_from(["estimate_min", "focus_minutes"]), max_size=2),
)
def test_assignment_view(body, revision, planned, dropped):
    body = {key: value for key, value in body.items() if key not in dropped}
    same(
        lambda: live_app.assignment_view(body, revision, planned),
        lambda: ref_assignment_view(body, revision, planned),
        f"{body!r} {revision} {planned}",
    )


@COMMON
@given(st.one_of(st.none(), st.integers(), st.lists(st.integers(), max_size=2), st.text(max_size=3)))
def test_assignment_view_on_a_body_that_is_not_a_dict(body):
    same(
        lambda: live_app.assignment_view(body, 1, 0),
        lambda: ref_assignment_view(body, 1, 0),
        repr(body),
    )


assignments_by_id = st.fixed_dictionaries({"a1": assignment_body("a1"), "a2": assignment_body("a2")})


@st.composite
def blocks_naming_assignments(draw, ids):
    bodies = draw(week_blocks(max_size=6))
    named = []
    for body in bodies:
        aid = draw(st.sampled_from(ids))
        named.append({**body, "assignment_id": aid} if aid is not None else {k: v for k, v in body.items() if k != "assignment_id"})
    for body in named:
        try:
            ref_models.TimeBlock.model_validate(body)
        except ValidationError:
            assume(False)
    return named


@COMMON
@given(blocks_naming_assignments([None, None, "a1", "a2", "zz", ""]), assignments_by_id)
def test_rewrite_blocks(bodies, assignments):
    same(
        lambda: live_app.rewrite_blocks(models_of(live_models, "TimeBlock", bodies), assignments),
        lambda: ref_rewrite_blocks(models_of(ref_models, "TimeBlock", bodies), assignments),
        f"{bodies!r}",
    )


@COMMON
@given(blocks_naming_assignments([None, "a1", "a2", "zz"]), assignments_by_id)
def test_rewrite_stored_blocks(bodies, assignments):
    same(
        lambda: live_app.rewrite_stored_blocks(bodies, assignments),
        lambda: ref_rewrite_stored_blocks(bodies, assignments),
        f"{bodies!r}",
    )


@COMMON
@given(
    st.lists(
        st.one_of(
            block_dict(),
            st.fixed_dictionaries({"id": st.just("x"), "assignment_id": st.sampled_from(["a1", "zz", "", None, 7, 0, 1.5, [1], {"k": 1}, True])}),
            st.just("not a dict"),
            st.just(None),
        ),
        max_size=4,
    ),
    assignments_by_id,
)
def test_rewrite_stored_blocks_on_rows_that_do_not_fit(blocks, assignments):
    same(
        lambda: live_app.rewrite_stored_blocks(blocks, assignments),
        lambda: ref_rewrite_stored_blocks(blocks, assignments),
        f"{blocks!r}",
    )


def test_rewrite_stored_blocks_on_a_list_of_nothing_in_particular():
    for blocks in ([], {}, "", {"a": 1}, "abc", 5, None):
        same(
            lambda blocks=blocks: live_app.rewrite_stored_blocks(blocks, {}),
            lambda blocks=blocks: ref_rewrite_stored_blocks(blocks, {}),
            repr(blocks),
        )


class TwoDatabases:
    """The same account in the engine's connection and in the original's sqlite3 connection."""

    def __init__(self, folder):
        self.live_path = Path(folder) / "live.sqlite"
        self.ref_path = Path(folder) / "ref.sqlite"
        live_storage.initialize(self.live_path)
        ref_storage.initialize(self.ref_path)

    def __enter__(self):
        self.live_cm = live_storage.connect(self.live_path)
        self.ref_cm = ref_storage.connect(self.ref_path)
        self.live = self.live_cm.__enter__()
        self.ref = self.ref_cm.__enter__()
        self.live.insert_user("ada", "hash")
        self.ref.execute("INSERT INTO users(username, password_hash) VALUES (?, ?)", ("ada", "hash"))
        return self

    def __exit__(self, *exc):
        self.ref_cm.__exit__(*exc)
        return self.live_cm.__exit__(*exc)

    def add_assignment(self, user, ident, body):
        self.live.insert_assignment(user, ident, body)
        self.ref.execute("INSERT INTO assignments(user_id, id, body, revision) VALUES (?, ?, ?, 1)", (user, ident, body))

    def add_week(self, user, start, encoded):
        # `save_week` skips a missing week whose body is already `[]`, so an empty-block week
        # would never land in the live database. Insert the row on both sides the same way.
        self.live.execute(
            "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?, ?, ?, 1)",
            (user, start, encoded),
        )
        self.ref.execute(
            "INSERT INTO weeks(user_id, week_start, blocks, revision) VALUES (?, ?, ?, 1)",
            (user, start, encoded),
        )

    def rows(self, table):
        sql = f"SELECT * FROM {table} ORDER BY 1, 2"
        return (
            [tuple(row) for row in self.live.execute(sql).fetchall()],
            [tuple(row) for row in self.ref.execute(sql).fetchall()],
        )


@COMMON
@given(st.sets(st.sampled_from(["a1", "a2", "a3", "zz", ""]), max_size=5), st.sets(st.sampled_from(["a1", "a2"])))
def test_require_own_assignments(wanted, stored):
    with tempfile.TemporaryDirectory() as folder, TwoDatabases(folder) as pair:
        live_storage_user = pair.live.insert_user("bob", "hash")
        pair.ref.execute("INSERT INTO users(username, password_hash) VALUES (?, ?)", ("bob", "hash"))
        for ident in sorted(stored):
            pair.add_assignment(1, ident, json.dumps({"id": ident, "n": 1}))
        pair.add_assignment(live_storage_user, "a3", json.dumps({"id": "a3"}))
        same(
            lambda: live_app.require_own_assignments(pair.live, 1, set(wanted)),
            lambda: ref_require_own_assignments(pair.ref, 1, set(wanted)),
            f"{wanted!r} {stored!r}",
        )


def test_require_own_assignments_reads_the_bodies_before_it_compares():
    with tempfile.TemporaryDirectory() as folder, TwoDatabases(folder) as pair:
        pair.add_assignment(1, "a1", "{not json")
        for ids in ({"a1"}, {"a1", "zz"}, {"zz"}, set()):
            same(
                lambda ids=ids: live_app.require_own_assignments(pair.live, 1, set(ids)),
                lambda ids=ids: ref_require_own_assignments(pair.ref, 1, set(ids)),
                repr(ids),
            )


@COMMON
@given(
    st.lists(block_dict(kinds=("flexible", "locked")), max_size=5, unique_by=lambda body: body["id"]),
    st.integers(0, 4),
    st.integers(1, 6),
    monday,
    st.booleans(),
)
def test_adopt_legacy_deadlines(bodies, existing, cap, week_start, twice):
    for body in bodies:
        try:
            ref_models.TimeBlock.model_validate(body)
        except ValidationError:
            assume(False)
    with (
        tempfile.TemporaryDirectory() as folder,
        TwoDatabases(folder) as pair,
        mock.patch.object(live_app, "MAX_ASSIGNMENTS", cap),
        mock.patch.object(ref_app_helpers, "MAX_ASSIGNMENTS", cap),
    ):
        for index in range(existing):
            pair.add_assignment(1, f"old{index}", json.dumps({"id": f"old{index}"}))
        runs = 2 if twice else 1
        for run in range(runs):
            same(
                lambda: live_app.adopt_legacy_deadlines(pair.live, 1, week_start, models_of(live_models, "TimeBlock", bodies)),
                lambda: ref_app_helpers.adopt_legacy_deadlines(pair.ref, 1, week_start, models_of(ref_models, "TimeBlock", bodies)),
                f"run {run} {bodies!r} {existing} {cap}",
            )
            got, want = pair.rows("assignments")
            assert got == want, f"run {run} {bodies!r}"


def test_adopt_legacy_deadlines_when_a_new_body_fails_its_model():
    block = {
        "id": "essay",
        "title": "Draft",
        "kind": "flexible",
        "duration_min": 100,
        "days": [0],
        "latest": "Thursday 21:00",
    }
    with tempfile.TemporaryDirectory() as folder, TwoDatabases(folder) as pair:
        same(
            lambda: live_app.adopt_legacy_deadlines(pair.live, 1, "2026-09-07", models_of(live_models, "TimeBlock", [block])),
            lambda: ref_app_helpers.adopt_legacy_deadlines(pair.ref, 1, "2026-09-07", models_of(ref_models, "TimeBlock", [block])),
            "a duration that is not a multiple of 15",
        )
        got, want = pair.rows("assignments")
        assert got == want


@COMMON
@given(
    st.lists(
        st.tuples(
            st.text(alphabet="abc é\"", max_size=6),
            st.sets(st.sampled_from(["rp-t1", "rp-t2", "rp-t3", "rp-t4", "unknown", ""]), max_size=3),
        ),
        min_size=1,
        max_size=6,
    ),
    st.integers(1, 4),
    st.lists(st.tuples(monday, week_blocks(max_size=2)), max_size=2, unique_by=lambda item: item[0]),
    assignment_rows(),
)
def test_insert_restore_point(steps, limit, weeks, assignments):
    tokens = iter(f"t{index}" for index in range(1, 40))
    stamps = iter(f"2026-10-02T10:{index:02d}" for index in range(0, 60))
    with (
        tempfile.TemporaryDirectory() as folder,
        TwoDatabases(folder) as pair,
        mock.patch.object(live_app, "MAX_RESTORE_POINTS", limit),
        mock.patch.object(ref_app_helpers, "MAX_RESTORE_POINTS", limit),
    ):
        for start, blocks in weeks:
            encoded = json.dumps(blocks, sort_keys=True, separators=(",", ":"))
            pair.add_week(1, start, encoded)
        for body, _revision in assignments:
            encoded = live_app.encode_assignment(live_models.AssignmentContent.model_validate(body))
            pair.add_assignment(1, body["id"], encoded)
        for label, keep in steps:
            token, stamp = next(tokens), next(stamps)
            with (
                mock.patch("secrets.token_hex", lambda _size, token=token: token),
                mock.patch.object(live_app, "naive_now", lambda stamp=stamp: stamp),
                mock.patch.object(ref_app_helpers, "naive_now", lambda stamp=stamp: stamp),
            ):
                same(
                    lambda label=label, keep=keep: live_app.insert_restore_point(pair.live, 1, label, set(keep)),
                    lambda label=label, keep=keep: ref_app_helpers.insert_restore_point(
                        pair.ref, 1, label, set(keep)
                    ),
                    f"{label!r} {keep!r}",
                )
            got, want = pair.rows("restore_points")
            assert got == want, f"{label!r} {keep!r}"


def test_insert_restore_point_without_a_keep_set():
    with tempfile.TemporaryDirectory() as folder, TwoDatabases(folder) as pair:
        with (
            mock.patch("secrets.token_hex", lambda _size: "t0"),
            mock.patch.object(live_app, "naive_now", lambda: "2026-10-02T10:00"),
            mock.patch.object(ref_app_helpers, "naive_now", lambda: "2026-10-02T10:00"),
        ):
            same(
                lambda: live_app.insert_restore_point(pair.live, 1, "Before"),
                lambda: ref_app_helpers.insert_restore_point(pair.ref, 1, "Before"),
                "no keep set",
            )
        got, want = pair.rows("restore_points")
        assert got == want


BASE_ROW = {
    "theme": "dark",
    "reminders_enabled": 1,
    "reminder_lead_min": 10,
    "reminder_sound": 0,
    "reminder_dnd_override": 0,
    "timer_work_min": 25,
    "timer_break_min": 5,
    "timer_long_break_min": 15,
    "timer_long_break_every": 4,
    "auto_split_pomodoro": 1,
    "default_spotify_url": None,
    "alarms_json": "[]",
    "availability_json": "{}",
    "comfort_json": "{}",
}
COMFORT_VALUES: dict[str, list] = {
    "alert_volume": [0, 55, 100, 101, None, "x"],
    "end_chime": [True, False, 0, 1, None],
    "tray_notifications": [True, False, 0, 1, None],
    "start_at_login": [True, False, 0, 1],
    "preferred_view": [None, "week", "day", "bogus"],
    "sidebar_collapsed": [True, False, 0],
    "sidebar_width_px": [None, 240, 10, "x"],
    "theme_pack": ["system", "paper", "bogus", None],
    "accent": ["default", "teal", "bogus"],
    "accent_chips": [True, False, 1],
    "motion": [None, "full", "reduced", "bogus"],
    "alarm_tone": ["chime", "bell", "bogus"],
    "planning_style": ["suggest", "auto", "bogus"],
    "drag_step_min": [5, 15, 7, None],
    "clock_24h": [True, False, 0],
    "setup": [None, {"step": 1}, {"finished_at": "2026-10-02T09:00"}, 5],
}
comfort_json = st.one_of(
    st.just("{}"),
    st.just(""),
    st.just("null"),
    st.just("[]"),
    st.just("{oops"),
    st.sets(st.sampled_from(sorted(COMFORT_VALUES)), max_size=8).flatmap(
        lambda picks: st.fixed_dictionaries(
            {key: st.sampled_from(list(COMFORT_VALUES[key])) for key in picks}
        ).map(json.dumps)
    ),
)
availability_json = st.one_of(
    st.just("{}"),
    st.just(""),
    st.just("[]"),
    st.just("{oops"),
    st.builds(
        lambda protected, study, work, cutoff: json.dumps(
            {
                key: value
                for key, value in (
                    ("protected", protected),
                    ("study_windows", study),
                    ("work_windows", work),
                    ("day_cutoff", cutoff),
                )
                if value is not ...
            }
        ),
        st.one_of(st.just(...), st.lists(grid_window(extra="protected"), max_size=2), st.just([]), st.none()),
        st.one_of(st.just(...), st.lists(grid_window(extra="study"), max_size=2), st.just([])),
        st.one_of(st.just(...), st.lists(work_window(), max_size=2), st.just([])),
        st.one_of(st.just(...), st.none(), st.sampled_from(["22:00", "21:30", "", "bogus"])),
    ),
)
row_changes = st.fixed_dictionaries(
    {},
    optional={
        "theme": st.sampled_from(["light", "dark", "system", "bogus"]),
        "reminders_enabled": st.sampled_from([0, 1, 2, None, "yes"]),
        "reminder_lead_min": st.sampled_from([0, 10, 120, 500, "15", 7.9, -1]),
        "timer_work_min": st.sampled_from([25, 0, 200, "30"]),
        "timer_long_break_every": st.sampled_from([4, 1, 13]),
        "default_spotify_url": st.sampled_from([None, "https://open.spotify.com/playlist/abc", "https://example.com"]),
        "alarms_json": st.sampled_from(["[]", "[", "null", '[{"id": "a", "time": "07:30", "days": [0], "label": "Up"}]']),
    },
)


@COMMON
@given(row_changes, availability_json, comfort_json, st.sets(st.sampled_from(sorted(BASE_ROW)), max_size=2))
def test_preferences_from_row(changes, availability, comfort, dropped):
    row = {**BASE_ROW, **changes, "availability_json": availability, "comfort_json": comfort}
    row = {key: value for key, value in row.items() if key not in dropped}
    same(lambda: live_app.preferences_from_row(row), lambda: ref_preferences_from_row(row), repr(row))


@COMMON
@given(st.sampled_from([None, "", "{}", "null", "[]", "{oops", '{"protected": null}', '{"day_cutoff": 5}']))
def test_preferences_from_row_with_other_text_in_the_json_columns(text):
    for column in ("availability_json", "comfort_json"):
        row = {**BASE_ROW, column: text}
        same(
            lambda row=row: live_app.preferences_from_row(row),
            lambda row=row: ref_preferences_from_row(row),
            repr(row),
        )


@COMMON
@given(availability_json, st.booleans())
def test_solve_availability(stored, missing):
    value = None if missing else stored
    same(lambda: live_app.solve_availability(value), lambda: ref_solve_availability(value), repr(value))


def test_solve_availability_on_text_that_is_not_a_dict_of_windows():
    for stored in (None, "", "{}", "null", "[]", "5", '{"protected": 5}', '{"protected": {"a": 1}}',
                   '{"study_windows": "ab"}', '{"work_windows": [1]}', '{"protected": [{"days": [9]}]}'):
        same(lambda stored=stored: live_app.solve_availability(stored), lambda stored=stored: ref_solve_availability(stored), repr(stored))
