"""Focus timer math. Wall-clock phases, persist payloads and credit rules. No Qt."""

from __future__ import annotations

from copy import deepcopy

from backend.models import ESTIMATE_MAX_MIN
from backend.slots import hhmm_to_minutes
from backend.weeks import is_week_start
from desktop.native.reuse import occurrence_days
from desktop.native.weekmodel import hhmm_text, length_label

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
    source = prefs or {}
    if phase == "work":
        minutes = int(source.get("timer_work_min") or DEFAULT_TIMERS["timer_work_min"])
    elif phase == "long_break":
        minutes = int(source.get("timer_long_break_min") or DEFAULT_TIMERS["timer_long_break_min"])
    else:
        minutes = int(source.get("timer_break_min") or DEFAULT_TIMERS["timer_break_min"])
    return minutes * 60_000


def format_countdown(milliseconds: int) -> str:
    seconds = max(0, (milliseconds + 999) // 1000)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def remaining_ms(state: dict, now_ms: int) -> int:
    if state.get("running"):
        return max(0, int(state.get("endsAt") or 0) - now_ms)
    return max(0, int(state.get("remainingMs") or 0))


def focus_now(state: dict | None) -> str:
    """What the timer is doing, for a page that only says so: "" when none runs or its session has
    ended, else "focusing", "paused" or "break"."""
    if state is None or state.get("phase") in (None, "ended"):
        return ""
    if state.get("phase") != "work":
        return "break"
    return "focusing" if state.get("running") else "paused"


def more_time_choices(estimate_min: int) -> list[int]:
    return [minutes for minutes in MORE_TIME_CHOICES if estimate_min + minutes <= MAX_ESTIMATE_MIN]


def persist_payload(state: dict | None) -> dict | None:
    if state is None:
        return None
    running = bool(state.get("running"))
    return {
        "assignmentId": state.get("assignmentId"),
        "sessionId": state.get("blockId"),
        "weekStart": state.get("weekStart"),
        "day": state.get("day"),
        "start": state.get("start"),
        "phase": state.get("phase"),
        "cycles": int(state.get("cycles") or 0),
        "endsAt": state.get("endsAt") if running else None,
        "remainingMs": None if running else state.get("remainingMs"),
    }


def restore_state(saved: dict | None, *, assignments: dict, blocks: list[dict], now_ms: int) -> dict | None:
    if not isinstance(saved, dict):
        return None
    phase = saved.get("phase")
    week_start = saved.get("weekStart")
    cycles = saved.get("cycles")
    if (
        phase not in FOCUS_PHASES
        or not isinstance(week_start, str)
        or not is_week_start(week_start)
        or not isinstance(cycles, int)
    ):
        return None
    has_end = isinstance(saved.get("endsAt"), (int, float))
    has_remaining = isinstance(saved.get("remainingMs"), (int, float))
    if not has_end and not has_remaining:
        return None
    assignment_id = saved.get("assignmentId") if isinstance(saved.get("assignmentId"), str) else None
    assignment = assignments.get(assignment_id) if assignment_id else None
    if assignment_id and (assignment is None or assignment.get("completed")):
        return None
    block_id = saved.get("sessionId") if isinstance(saved.get("sessionId"), str) else None
    block = next((item for item in blocks if item["id"] == block_id), None) if block_id else None
    running = isinstance(saved.get("endsAt"), (int, float))
    title = "Quick focus"
    if block_id:
        title = (assignment or block or {"title": "Focus session"})["title"]
    state = {
        "weekStart": week_start,
        "blockId": block_id,
        "assignmentId": assignment["id"] if assignment else None,
        "day": saved.get("day") if isinstance(saved.get("day"), int) else None,
        "start": saved.get("start") if isinstance(saved.get("start"), str) else None,
        "title": title,
        "phase": phase,
        "cycles": cycles,
        "running": running,
        "endsAt": int(saved.get("endsAt") or 0),
        "remainingMs": int(saved.get("remainingMs") or 0),
    }
    if running and state["endsAt"] <= now_ms:
        state["running"] = False
        state["remainingMs"] = 0
        state["expired"] = True
    return state


def begin_state(target: dict, prefs: dict | None, now_ms: int) -> dict:
    duration = phase_duration_ms("work", prefs)
    return {
        **target,
        "phase": "work",
        "cycles": 0,
        "running": True,
        "remainingMs": duration,
        "endsAt": now_ms + duration,
    }


def pause_state(state: dict, now_ms: int) -> dict:
    next_state = deepcopy(state)
    if next_state.get("phase") == "ended":
        return next_state
    if next_state.get("running"):
        next_state["remainingMs"] = remaining_ms(next_state, now_ms)
        next_state["running"] = False
    else:
        next_state["running"] = True
        next_state["endsAt"] = now_ms + int(next_state.get("remainingMs") or 0)
    return next_state


def set_phase(state: dict, phase: str, prefs: dict | None, now_ms: int) -> dict:
    duration = phase_duration_ms(phase, prefs)
    next_state = deepcopy(state)
    next_state["phase"] = phase
    next_state["running"] = True
    next_state["remainingMs"] = duration
    next_state["endsAt"] = now_ms + duration
    return next_state


def break_phase(cycles: int, prefs: dict | None) -> str:
    every = int((prefs or {}).get("timer_long_break_every") or DEFAULT_TIMERS["timer_long_break_every"])
    if cycles > 0 and cycles % every == 0:
        return "long_break"
    return "break"


def credit_target(state: dict, assignment: dict | None, block: dict | None, work_min: int) -> dict | None:
    """Return the mutated homework or block after one completed work phase. None if nothing to credit."""
    if not state.get("blockId"):
        return None
    amount = min(MAX_FOCUS_MINUTES, work_min)
    if state.get("assignmentId"):
        if assignment is None:
            return None
        updated = deepcopy(assignment)
        updated["focus_sessions"] = min(MAX_FOCUS_SESSIONS, int(updated.get("focus_sessions") or 0) + 1)
        updated["focus_minutes"] = min(MAX_FOCUS_MINUTES, int(updated.get("focus_minutes") or 0) + amount)
        return updated
    if block is None:
        return None
    updated = deepcopy(block)
    updated["focus_sessions"] = min(MAX_FOCUS_SESSIONS, int(updated.get("focus_sessions") or 0) + 1)
    updated["focus_minutes"] = min(MAX_FOCUS_MINUTES, int(updated.get("focus_minutes") or 0) + amount)
    return updated


def focus_candidates(blocks: list[dict], assignments: dict, trace: dict | None) -> list[dict]:
    placed = {item["id"]: item for item in (trace or {}).get("placed") or []}
    result = []
    for block in blocks:
        work = block.get("kind") == "flexible" or block.get("pomodoro_role") == "work"
        if not work or block.get("completed"):
            continue
        assignment = assignments.get(block.get("assignment_id"))
        if assignment and assignment.get("completed"):
            continue
        placement = placed.get(block["id"], block if block.get("start") else None)
        if placement is None or not placement.get("start"):
            continue
        result.append(
            {
                "id": block["id"],
                "title": block["title"],
                "day": (placement.get("days") or [None])[0],
                "start": placement["start"],
                "focus_sessions": int((assignment or block).get("focus_sessions") or 0),
                "focus_minutes": int((assignment or block).get("focus_minutes") or 0),
            }
        )
    return result


def now_and_next(blocks: list[dict], day: int, minute: int) -> dict:
    active = []
    for block in blocks or []:
        if not block.get("start") or block.get("completed"):
            continue
        if day in (block.get("missed_days") or []):
            continue
        if day not in occurrence_days(block):
            continue
        active.append(block)
    active.sort(key=lambda item: hhmm_to_minutes(item["start"]))
    current = None
    following = None
    for block in active:
        start = hhmm_to_minutes(block["start"])
        end = start + int(block["duration_min"])
        if current is None and start <= minute < end:
            current = block
        if following is None and start > minute:
            following = block
    return {"current": current, "next": following}


def now_next_line(result: dict, minute: int) -> str:
    parts = []
    current = result.get("current")
    following = result.get("next")
    if current:
        end = hhmm_to_minutes(current["start"]) + int(current["duration_min"])
        parts.append(f"Now: {current['title']} · {length_label(end - minute)} left")
    if following:
        wait = hhmm_to_minutes(following["start"]) - minute
        suffix = "" if current else f" (in {length_label(wait)})"
        parts.append(f"Next: {following['title']} at {hhmm_text(following['start'])}{suffix}")
    return "  →  ".join(parts)
