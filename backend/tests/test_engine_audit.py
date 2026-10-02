"""Cases from the engine audit that the generated parity file does not draw."""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]

from backend import assignments as live_assignments
from backend import availability as live_availability
from backend import comfort as live_comfort
from backend import models as live_models
from backend import restore as live_restore
from backend import slots as live_slots
from backend import solver as live_solver
from backend import weeks as live_weeks
from backend.tests.engine_ref import assignments as ref_assignments
from backend.tests.engine_ref import availability as ref_availability
from backend.tests.engine_ref import comfort as ref_comfort
from backend.tests.engine_ref import models as ref_models
from backend.tests.engine_ref import restore as ref_restore
from backend.tests.engine_ref import slots as ref_slots
from backend.tests.engine_ref import solver as ref_solver
from backend.tests.engine_ref import weeks as ref_weeks


def outcome(fn):
    try:
        return ("ok", fn())
    except Exception as exc:
        return (type(exc).__name__, str(exc))


def same(live, ref, label):
    got, want = outcome(live), outcome(ref)
    assert got == want, f"{label}\n  rust:   {got}\n  python: {want}"


def test_probe4_inputs_match():
    arabic = "٣"
    for due in (
        f"2026-09-09T1{arabic}:00",
        f"2026-09-0{arabic}",
        f"2026-09-09T12:0{arabic}",
        "2026-09-09T12:00\n",
        "2026-09-09 ",
        "２０２６-09-09",
    ):
        same(
            lambda due=due: live_assignments.due_placement_bound("2026-09-07", due),
            lambda due=due: ref_assignments.due_placement_bound("2026-09-07", due),
            due,
        )
        same(
            lambda due=due: live_assignments.due_slack_point("2026-09-07", due),
            lambda due=due: ref_assignments.due_slack_point("2026-09-07", due),
            due,
        )
        same(
            lambda due=due: live_availability.spread_sessions(
                estimate_min=60, focus_minutes=0, planned_min=0, due=due, session_min=30, from_date="2026-09-08"
            ),
            lambda due=due: ref_availability.spread_sessions(
                estimate_min=60, focus_minutes=0, planned_min=0, due=due, session_min=30, from_date="2026-09-08"
            ),
            due,
        )
    for clock in (
        f"1{arabic}:00",
        "12:00\n",
        " 12:00",
        "12:00 ",
        "+1:00",
        "1e:00",
        "12:60",
        "-1:00",
        "12：00",
        "012:00",
        "1_2:00",
        "12:0_0",
    ):
        same(lambda clock=clock: live_slots.hhmm_to_minutes(clock), lambda clock=clock: ref_slots.hhmm_to_minutes(clock), clock)
        same(lambda clock=clock: live_slots.clock_to_minutes(clock), lambda clock=clock: ref_slots.clock_to_minutes(clock), clock)
        same(
            lambda clock=clock: live_availability.lateness_occupancy(1, clock, 30),
            lambda clock=clock: ref_availability.lateness_occupancy(1, clock, 30),
            clock,
        )
    same(lambda: live_comfort.split_plan(50, 25, 5, 15, 0), lambda: ref_comfort.split_plan(50, 25, 5, 15, 0), "cadence")
    same(lambda: live_weeks.parse_month("0000-01"), lambda: ref_weeks.parse_month("0000-01"), "month")
    same(lambda: live_restore.canonical({"a": 2**64}), lambda: ref_restore.canonical({"a": 2**64}), "canonical")
    block = {
        "id": "b",
        "title": "t",
        "kind": "flexible",
        "duration_min": 30,
        "days": [0],
        "start": "10:00",
        "completed": True,
        "completed_day": 10**9,
    }
    same(
        lambda: live_assignments.completed_at_for_block("2026-09-07", block),
        lambda: ref_assignments.completed_at_for_block("2026-09-07", block),
        "completed",
    )


def test_int_parser_matches_python_for_every_code_point():
    def check(chars: list[str]) -> None:
        got = flexweek_engine.int_chars("".join(chars))
        for ch, item in zip(chars, got, strict=True):
            want = outcome(lambda ch=ch: int(ch))
            if want[0] == "ok":
                want = ("ok", str(want[1]))
            assert item == want, (repr(ch), item, want)

    chunk: list[str] = []
    for code_point in range(0x110000):
        if 0xD800 <= code_point <= 0xDFFF:
            continue
        chunk.append(chr(code_point))
        if len(chunk) == 4096:
            check(chunk)
            chunk = []
    if chunk:
        check(chunk)


def test_int_parser_matches_python_on_longer_text():
    for text in ("1_2", "\x1c12", "  8", "'", "\x00", "+3", "1__2", "١٢", "\x1c"):
        got = flexweek_engine.int_text(text)
        want = outcome(lambda text=text: int(text))
        if want[0] == "ok":
            want = ("ok", str(want[1]))
        assert got == want, (repr(text), got, want)


def test_a_panic_becomes_runtime_error():
    try:
        flexweek_engine.panic_probe()
    except RuntimeError as exc:
        assert str(exc) == "probe"
    else:
        raise AssertionError("the panic did not become RuntimeError")


def test_a_pinned_block_with_no_start_is_a_move_to_nowhere():
    pin = {"id": "pin", "title": "Pinned", "kind": "flexible", "days": [0], "start": "", "duration_min": 30, "pinned": True}
    hw = {"id": "hw", "title": "Essay", "kind": "flexible", "days": [0], "duration_min": 60}
    previous = [pin]

    def moves(module, models):
        trace = module.reschedule_running_late(
            [models.TimeBlock(**pin), models.TimeBlock(**hw)],
            0,
            30,
            "15:00",
            [models.TimeBlock(**previous[0])],
        )
        return [(item.block_id, item.from_start, item.to_start, item.to_day) for item in trace.moves]

    assert moves(live_solver, live_models) == moves(ref_solver, ref_models)


def test_the_last_supported_week_does_not_invent_year_10000():
    same(
        lambda: live_assignments.due_from_latest("9999-12-31", None, [0]),
        lambda: ref_assignments.due_from_latest("9999-12-31", None, [0]),
        "due",
    )
    same(
        lambda: live_assignments.due_placement_bound("9999-12-31", "2026-09-09"),
        lambda: ref_assignments.due_placement_bound("9999-12-31", "2026-09-09"),
        "bound",
    )


def test_file_separator_is_stripped_before_a_subject_is_folded():
    window = ref_models.StudyWindow(days=[0], start="16:00", duration_min=120, subject="ética")
    want = ref_availability.study_rank([window], "Ética", 0, 16 * 60, 60)
    raw = json.dumps([{"days": [0], "start": "16:00", "duration_min": 120, "subject": "\x1cética"}])
    got = flexweek_engine.study_rank(raw, "\x1cÉtica", 0, 16 * 60, 60)
    assert got == want


def test_a_window_start_in_other_digits_is_read_as_int_reads_it():
    # The pattern's `\d` takes "1٠" and int() reads it as 10, so the window runs 10:00 to 12:00.
    body = {"days": [0], "start": "1٠:00", "duration_min": 120}
    live = [live_models.StudyWindow(**body)]
    ref = [ref_models.StudyWindow(**body)]
    for start_min, rank in ((10 * 60, 1), (0, 2)):
        assert ref_availability.study_rank(ref, None, 0, start_min, 60) == rank
        assert live_availability.study_rank(live, None, 0, start_min, 60) == rank
