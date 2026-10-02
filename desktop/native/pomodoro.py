"""Splitting a placed block into focus chunks and breaks.

"Split long homework into focus sessions" was a checkbox the desktop could set and never acted on:
the whole feature lived in the web client. This is that feature, ported, and kept in step with
pomodoroPlan, buildPomodoroBlocks, solveInputBlocks and autoSplitSolvedBlocks in the retired web client.

Two things happen around a solve. Before it, each long flexible block asks for the time its breaks
will need as well, so the solver leaves room for them. After it, each placed block is replaced by its
chunks. Doing only the first would reserve time nothing uses; doing only the second would lay breaks
over whatever the solver put next.

No Qt and no network in here, so the arithmetic can be checked on its own. The engine does the work.
"""

from __future__ import annotations

import json

import flexweek_engine  # type: ignore[import-untyped]

TITLE_MAX = 80
MAX_BLOCKS = 100
BREAK_TITLE = "Pomodoro break"
GRID_REFUSAL = "Grid splitting needs positive 15-minute work and break lengths."


def _prefs(prefs: dict | None) -> str | None:
    return None if prefs is None else json.dumps(prefs)


def timers(prefs: dict | None) -> tuple[int, int, int, int]:
    work, rest, long, every = flexweek_engine.pomo_timers(_prefs(prefs))
    return int(work), int(rest), int(long), int(every)


def plan_for(duration_min: int, prefs: dict | None) -> dict:
    return json.loads(flexweek_engine.pomo_plan_for(duration_min, _prefs(prefs)))


def child_title(title: str, index: int, total: int) -> str:
    """Keep a chunk inside the title limit the server enforces."""
    return str(flexweek_engine.pomo_child_title(title, index, total))


def split_children(source: dict, placed: dict, plan: dict) -> list[dict]:
    """One source block becomes its chunks and the breaks between them."""
    return json.loads(
        flexweek_engine.pomo_split_children(json.dumps(source), json.dumps(placed), json.dumps(plan))
    )


def splittable(block: dict, prefs: dict | None) -> bool:
    """A block worth splitting: unfinished homework longer than one chunk that is not already one."""
    return bool(flexweek_engine.pomo_splittable(json.dumps(block), _prefs(prefs)))


def inflate_for_solve(blocks: list[dict], prefs: dict | None) -> list[dict]:
    """Ask the solver for the time the breaks need too, so the chunks have somewhere to go."""
    return json.loads(flexweek_engine.pomo_inflate_for_solve(json.dumps(blocks), _prefs(prefs)))


def split_solved(blocks: list[dict], trace: dict | None, prefs: dict | None) -> tuple[list[dict], int]:
    """Replace each placed block with its chunks. Returns the new week and how many were split."""
    raw, count = flexweek_engine.pomo_split_solved(
        json.dumps(blocks),
        None if trace is None else json.dumps(trace),
        _prefs(prefs),
    )
    return json.loads(raw), int(count)
