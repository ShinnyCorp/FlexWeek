"""Focus timer math. Wall-clock phases, persist payloads and credit rules. No Qt."""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]

from backend.models import ESTIMATE_MAX_MIN

FOCUS_PHASES = ("work", "break", "long_break", "ended")
FOCUS_PHASE_LABEL = {
    "work": "Focus session",
    "break": "Break",
    "long_break": "Long break",
    "ended": "Session finished",
}
MAX_ESTIMATE_MIN = ESTIMATE_MAX_MIN
MAX_FOCUS_MINUTES = 71400
MAX_FOCUS_SESSIONS = 9999
MORE_TIME_CHOICES = (15, 30, 45, 60, 90, 120, 180, 240)
DEFAULT_TIMERS = {
    "timer_work_min": 30,
    "timer_break_min": 15,
    "timer_long_break_min": 30,
    "timer_long_break_every": 4,
}


def phase_duration_ms(phase: str, prefs: dict | None) -> int:
    return int(flexweek_engine.focus_phase_ms(phase, None if prefs is None else json.dumps(prefs)))


def format_countdown(milliseconds: int) -> str:
    return str(flexweek_engine.focus_countdown(milliseconds))


def remaining_ms(state: dict, now_ms: int) -> int:
    return int(flexweek_engine.focus_remaining(json.dumps(state), now_ms))


def focus_now(state: dict | None) -> str:
    """What the timer is doing, for a page that only says so: "" when none runs or its session has
    ended, else "focusing", "paused" or "break"."""
    return str(flexweek_engine.focus_now(None if state is None else json.dumps(state)))


def more_time_choices(estimate_min: int) -> list[int]:
    return [int(minutes) for minutes in flexweek_engine.focus_more_time(estimate_min)]


def persist_payload(state: dict | None) -> dict | None:
    raw = flexweek_engine.focus_persist(None if state is None else json.dumps(state))
    return None if raw is None else json.loads(raw)


def restore_state(saved: dict | None, *, assignments: dict, blocks: list[dict], now_ms: int) -> dict | None:
    raw = flexweek_engine.focus_restore(
        None if saved is None else json.dumps(saved),
        json.dumps(assignments),
        json.dumps(blocks),
        now_ms,
    )
    return None if raw is None else json.loads(raw)


def begin_state(target: dict, prefs: dict | None, now_ms: int) -> dict:
    return json.loads(
        flexweek_engine.focus_begin(json.dumps(target), None if prefs is None else json.dumps(prefs), now_ms)
    )


def pause_state(state: dict, now_ms: int) -> dict:
    return json.loads(flexweek_engine.focus_pause(json.dumps(state), now_ms))


def set_phase(state: dict, phase: str, prefs: dict | None, now_ms: int) -> dict:
    return json.loads(
        flexweek_engine.focus_set_phase(
            json.dumps(state), phase, None if prefs is None else json.dumps(prefs), now_ms
        )
    )


def break_phase(cycles: int, prefs: dict | None) -> str:
    return str(flexweek_engine.focus_break_phase(cycles, None if prefs is None else json.dumps(prefs)))


def credit_target(state: dict, assignment: dict | None, block: dict | None, work_min: int) -> dict | None:
    """Return the mutated homework or block after one completed work phase. None if nothing to credit."""
    raw = flexweek_engine.focus_credit(
        json.dumps(state),
        None if assignment is None else json.dumps(assignment),
        None if block is None else json.dumps(block),
        work_min,
    )
    return None if raw is None else json.loads(raw)


def focus_candidates(blocks: list[dict], assignments: dict, trace: dict | None) -> list[dict]:
    return json.loads(
        flexweek_engine.focus_candidates(
            json.dumps(blocks), json.dumps(assignments), None if trace is None else json.dumps(trace)
        )
    )


def now_and_next(blocks: list[dict], day: int, minute: int) -> dict:
    return json.loads(flexweek_engine.focus_now_next(json.dumps(blocks or []), day, minute))


def now_next_line(result: dict, minute: int) -> str:
    return str(flexweek_engine.focus_now_next_line(json.dumps(result), minute))
