"""Splitting a placed block into focus chunks and breaks.

"Split long homework into focus sessions" was a checkbox the desktop could set and never acted on:
the whole feature lived in the web client. This is that feature, ported, and kept in step with
pomodoroPlan, buildPomodoroBlocks, solveInputBlocks and autoSplitSolvedBlocks in the retired web client.

Two things happen around a solve. Before it, each long flexible block asks for the time its breaks
will need as well, so the solver leaves room for them. After it, each placed block is replaced by its
chunks. Doing only the first would reserve time nothing uses; doing only the second would lay breaks
over whatever the solver put next.

No Qt and no network in here, so the arithmetic can be checked on its own.
"""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from backend.tests.engine_ref.comfort import split_plan
from backend.tests.engine_ref.slots import DAY_END_MIN, SLOT_MIN, hhmm_to_minutes, minutes_to_hhmm

TITLE_MAX = 80
MAX_BLOCKS = 100
BREAK_TITLE = "Pomodoro break"
GRID_REFUSAL = "Grid splitting needs positive 15-minute work and break lengths."


def timers(prefs: dict | None) -> tuple[int, int, int, int]:
    settings = prefs or {}
    return (
        int(settings.get("timer_work_min") or 30),
        int(settings.get("timer_break_min") or 15),
        int(settings.get("timer_long_break_min") or 30),
        max(2, min(12, int(settings.get("timer_long_break_every") or 4))),
    )


def plan_for(duration_min: int, prefs: dict | None) -> dict:
    """The chunks and breaks a block of this length becomes, or a refusal naming the reason.

    The backend's split_plan does the arithmetic but does not police its inputs, and off-grid lengths
    would produce starts the server rejects, so the same guard the web applies is applied here.
    """
    work, brk, long_break, cadence = timers(prefs)
    values = (duration_min, work, brk, long_break)
    if any(not isinstance(value, int) or value <= 0 or value % SLOT_MIN for value in values):
        return {"error": GRID_REFUSAL, "segments": [], "total_min": 0}
    return {"error": None, **split_plan(duration_min, work, brk, long_break, cadence)}


def child_title(title: str, index: int, total: int) -> str:
    """Keep a chunk inside the title limit the server enforces. A source already at the limit would
    otherwise build a title the save rejects, after the week has already been changed."""
    suffix = f" · focus {index}/{total}"
    room = TITLE_MAX - len(suffix)
    head = str(title)
    return (head[:room] if len(head) > room else head) + suffix


def split_children(source: dict, placed: dict, plan: dict) -> list[dict]:
    """One source block becomes its chunks and the breaks between them, laid end to end from where
    the solver put it."""
    parent_id = source.get("pomodoro_parent_id") or source["id"]
    cursor = hhmm_to_minutes(placed["start"])
    total_work = sum(1 for segment in plan["segments"] if segment["role"] == "work")
    first_work = True
    children: list[dict] = []
    for segment in plan["segments"]:
        work = segment["role"] == "work"
        # Only the first chunk inherits the source's focus history, or the same minutes would be
        # counted once per chunk.
        carry = work and first_work
        child = deepcopy(source)
        child.update(
            id=str(uuid4()),
            title=child_title(source["title"], segment["index"], total_work) if work else BREAK_TITLE,
            kind="locked",
            days=[placed["days"][0]],
            start=minutes_to_hhmm(cursor),
            duration_min=segment["duration_min"],
            completed=False,
            missed_days=[],
            focus_sessions=(source.get("focus_sessions") or 0) if carry else 0,
            focus_minutes=(source.get("focus_minutes") or 0) if carry else 0,
            pomodoro_parent_id=parent_id,
            pomodoro_role=segment["role"],
            pomodoro_index=segment["index"],
            category="free" if not work else source.get("category"),
            course=None if not work else source.get("course"),
            spotify_url=None if not work else source.get("spotify_url"),
            earliest=None,
            latest=None,
        )
        if source.get("assignment_id"):
            # Progress belongs to the assignment, and a break is not work on it.
            child["focus_sessions"] = 0
            child["focus_minutes"] = 0
            if not work:
                child.pop("assignment_id", None)
        child.pop("completed_day", None)
        if work:
            first_work = False
        cursor += segment["duration_min"]
        children.append(child)
    return children


def splittable(block: dict, prefs: dict | None) -> bool:
    """A block worth splitting: unfinished homework longer than one chunk that is not already one."""
    work = timers(prefs)[0]
    return (
        block.get("kind") == "flexible"
        and not block.get("completed")
        and not block.get("pomodoro_role")
        and int(block.get("duration_min") or 0) > work
    )


def inflate_for_solve(blocks: list[dict], prefs: dict | None) -> list[dict]:
    """Ask the solver for the time the breaks need too, so the chunks have somewhere to go."""
    if not (prefs or {}).get("auto_split_pomodoro"):
        return blocks
    inflated = []
    for block in blocks:
        plan = plan_for(int(block.get("duration_min") or 0), prefs) if splittable(block, prefs) else None
        if plan is None or plan["error"]:
            inflated.append(block)
            continue
        inflated.append({**block, "duration_min": int(plan["total_min"])})
    return inflated


def split_solved(blocks: list[dict], trace: dict | None, prefs: dict | None) -> tuple[list[dict], int]:
    """Replace each placed block with its chunks. Returns the new week and how many were split."""
    if not (prefs or {}).get("auto_split_pomodoro") or not trace:
        return blocks, 0
    placements = {item["id"]: item for item in (trace.get("placed") or []) if item.get("start")}
    replacements: dict[str, list[dict]] = {}
    final_count = len(blocks)
    for source in blocks:
        placed = placements.get(source["id"])
        if placed is None or not splittable(source, prefs):
            continue
        plan = plan_for(int(source.get("duration_min") or 0), prefs)
        if plan["error"] or not plan["segments"]:
            continue
        if hhmm_to_minutes(placed["start"]) + int(plan["total_min"]) > DAY_END_MIN:
            # The chunks would run off the end of the day, so the block is left whole.
            continue
        children = split_children(source, placed, plan)
        final_count += len(children) - 1
        replacements[source["id"]] = children
    if not replacements or final_count > MAX_BLOCKS:
        return blocks, 0
    split: list[dict] = []
    for block in blocks:
        split.extend(replacements.get(block["id"], [block]))
    return split, len(replacements)
