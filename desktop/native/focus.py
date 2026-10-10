"""Focus timer math. Wall-clock phases, persist payloads and credit rules. No Qt."""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]

from backend.models import ESTIMATE_MAX_MIN
from desktop.native.wire import plain

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
    return int(flexweek_engine.focus_phase_ms(json.dumps(phase), json.dumps(prefs)))


def work_minutes(state: dict | None, prefs: dict | None) -> int:
    """The length of the work phase running, which is the length it began with. A timer length
    changed in Settings applies to the next phase, so it must not change this one's credit."""
    kept = None if state is None else state.get("workMin")
    if isinstance(kept, int) and not isinstance(kept, bool) and kept > 0:
        return kept
    return phase_duration_ms("work", prefs) // 60_000


def phase_total_ms(state: dict, prefs: dict | None) -> int:
    """How long the phase `state` is in was set to run, for the ring and the minutes spent."""
    if state.get("phase") == "work":
        return work_minutes(state, prefs) * 60_000
    return phase_duration_ms(str(state.get("phase")), prefs)


def format_countdown(milliseconds: int) -> str:
    return str(flexweek_engine.focus_countdown(milliseconds))


def remaining_ms(state: dict, now_ms: int) -> int:
    return int(flexweek_engine.focus_remaining(json.dumps(state), now_ms))


def focus_now(state: dict | None) -> str:
    """What the timer is doing, for a page that only says so: "" when none runs or its session has
    ended, else "focusing", "paused" or "break"."""
    return str(flexweek_engine.focus_now(json.dumps(state)))


def more_time_choices(estimate_min: int) -> list[int]:
    return list(flexweek_engine.focus_more_time(estimate_min))


def persist_payload(state: dict | None) -> dict | None:
    raw = flexweek_engine.focus_persist(json.dumps(state))
    if raw is None:
        return None
    payload = json.loads(raw)
    if state is not None and state.get("workMin") is not None:
        payload["workMin"] = state["workMin"]
    return payload


def restore_state(saved: dict | None, *, assignments: dict, blocks: list[dict], now_ms: int) -> dict | None:
    raw = flexweek_engine.focus_restore(plain(saved), json.dumps(assignments), json.dumps(blocks), now_ms)
    if raw is None:
        return None
    state = json.loads(raw)
    if isinstance(saved, dict) and saved.get("workMin") is not None:
        state["workMin"] = saved["workMin"]
    return state


def begin_state(target: dict, prefs: dict | None, now_ms: int) -> dict:
    state = json.loads(flexweek_engine.focus_begin(json.dumps(target), json.dumps(prefs), now_ms))
    state["workMin"] = phase_duration_ms("work", prefs) // 60_000
    return state


def pause_state(state: dict, now_ms: int) -> dict:
    return json.loads(flexweek_engine.focus_pause(json.dumps(state), now_ms))


def set_phase(state: dict, phase: str, prefs: dict | None, now_ms: int) -> dict:
    moved = json.loads(
        flexweek_engine.focus_set_phase(json.dumps(state), json.dumps(phase), json.dumps(prefs), now_ms)
    )
    if phase == "work":
        moved["workMin"] = phase_duration_ms("work", prefs) // 60_000
    return moved


def break_phase(cycles: int, prefs: dict | None) -> str:
    return str(flexweek_engine.focus_break_phase(cycles, json.dumps(prefs)))


def credit_target(state: dict, assignment: dict | None, block: dict | None, work_min: int) -> dict | None:
    """Return the mutated homework or block after one completed work phase. None if nothing to credit."""
    raw = flexweek_engine.focus_credit(
        json.dumps(state), json.dumps(assignment), json.dumps(block), work_min
    )
    return None if raw is None else json.loads(raw)


def focus_candidates(blocks: list[dict], assignments: dict, trace: dict | None) -> list[dict]:
    return json.loads(
        flexweek_engine.focus_candidates(json.dumps(blocks), json.dumps(assignments), json.dumps(trace))
    )


def now_and_next(blocks: list[dict], day: int, minute: int) -> dict:
    return json.loads(flexweek_engine.focus_now_next(json.dumps(blocks), json.dumps(day), minute))


def now_next_line(result: dict, minute: int) -> str:
    return str(flexweek_engine.focus_now_next_line(json.dumps(result), minute))
