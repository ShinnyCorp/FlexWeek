"""Week-grid edits and Day/Month helpers for the native calendar. No Qt."""

from __future__ import annotations

import json
from datetime import date, datetime

import flexweek_engine  # type: ignore[import-untyped]

LOCKED_CATEGORIES = ("class", "exercise", "extra", "meals", "sleep", "free")
FLEX_CATEGORIES = ("assignments", "study")
WEEKDAYS = [0, 1, 2, 3, 4]
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DAY_FULL = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
FIRST_MONTH = "2000-01"
LAST_MONTH = "2099-12"
SERIES_DRAG_MESSAGE = (
    "{title} repeats on {count} days, so dragging it is ambiguous. Edit the occurrence or the series."
)
# One family (decision 9 of 0.17), worked out from each hue by `family_colours` in tokens.py and held
# to it by test_tokens.py. In a light look `color` is the pale fill and `mark` the strong colour of
# outlines and edges; `dark` and `contrast` are (tone, mark) for the dark looks and High contrast, which
# sink the tone into their own card for a fill.
CATEGORIES = {
    "class": {
        "icon": "house",
        "label": "School",
        "hue": 250,
        "color": "#cfe8ff",
        "mark": "#398ad6",
        "dark": ("#59aaf8", "#59aaf8"),
        "contrast": ("#5ebdff", "#5ebdff"),
        "kind": "locked",
        "preset": {"start": "08:00", "end": "14:30", "days": WEEKDAYS},
    },
    "assignments": {
        "icon": "book-open",
        "label": "Homework",
        "hue": 25,
        "color": "#ffdad6",
        "mark": "#831a1d",
        "dark": ("#f07f77", "#a43b38"),
        "contrast": ("#ff8a82", "#c04442"),
        "kind": "flexible",
        "preset": {"duration_min": 60},
    },
    "study": {
        "icon": "pencil",
        "label": "Study",
        "hue": 320,
        "color": "#f2dbf8",
        "mark": "#ab68ba",
        "dark": ("#cb86db", "#cb86db"),
        "contrast": ("#e493f6", "#e493f6"),
        "kind": "flexible",
        "preset": {"duration_min": 60},
    },
    "exercise": {
        "icon": "target",
        "label": "Sports",
        "hue": 150,
        "color": "#d0eed5",
        "mark": "#399d57",
        "dark": ("#5bbd74", "#5bbd74"),
        "contrast": ("#5fd37f", "#5fd37f"),
        "kind": "locked",
        "preset": {"start": "15:30", "end": "17:00"},
    },
    "extra": {
        "icon": "sparkles",
        "label": "Activity",
        "hue": 200,
        "color": "#c3eef0",
        "mark": "#009ea7",
        "dark": ("#00bec7", "#00bec7"),
        "contrast": ("#00d4df", "#00d4df"),
        "kind": "locked",
        "preset": {"start": "17:00", "end": "18:00"},
    },
    "meals": {
        "icon": "clock",
        "label": "Meals",
        "hue": 70,
        "color": "#f9e0c5",
        "mark": "#bb7400",
        "dark": ("#dc932e", "#dc932e"),
        "contrast": ("#f7a224", "#f7a224"),
        "kind": "locked",
        "preset": {"start": "18:00", "end": "18:30"},
    },
    "sleep": {
        "icon": "moon",
        "label": "Sleep",
        "hue": 280,
        "color": "#c4c8e8",
        "mark": "#5656b0",
        "dark": ("#7174d1", "#7174d1"),
        "contrast": ("#8184f1", "#8184f1"),
        "kind": "locked",
        "preset": {"start": "22:00", "end": "23:00"},
    },
    "free": {
        "label": "Free",
        "hue": 250,
        "color": "#e0e5eb",
        "mark": "#82878c",
        "dark": ("#a0a5ab", "#a0a5ab"),
        "contrast": ("#b3b8be", "#b3b8be"),
        "kind": "locked",
        "preset": {"start": "19:00", "end": "20:00"},
    },
}


def category_title(category: str | None) -> str:
    return str(flexweek_engine.calendar_category_title(category))


def is_series(block: dict) -> bool:
    return bool(flexweek_engine.calendar_is_series(json.dumps(block)))


def monday_of(iso_day: str) -> str:
    return str(flexweek_engine.calendar_monday_of(iso_day))


def date_for_day(week_start: str, day: int) -> str:
    return str(flexweek_engine.calendar_date_for_day(week_start, json.dumps(day)))


def sunday_due(week_start: str) -> str:
    return str(flexweek_engine.calendar_sunday_due(week_start))


def local_stamp(now: datetime | None = None) -> str:
    moment = now or datetime.now()
    return str(flexweek_engine.calendar_local_stamp(moment.strftime("%Y-%m-%dT%H:%M")))


def occupied_intervals(blocks: list[dict], day: int) -> list[tuple[int, int]]:
    found = json.loads(flexweek_engine.calendar_occupied(json.dumps(blocks), json.dumps(day)))
    return [(begin, end) for begin, end in found]


def create_click_range(begin: int, occupied: list[tuple[int, int]]) -> tuple[int, int] | None:
    """Up to an hour from `begin`, which the hand has already put on its step, stopping where the next
    block starts."""
    span = flexweek_engine.calendar_click_range(begin, json.dumps(occupied))
    if span is None:
        return None
    start, stop = json.loads(span)
    return start, stop


def apply_block_times(block: dict, start_min: int, end_min: int, day: int | None = None) -> dict | None:
    """The block at a new time, and on `day` when it moved to another one."""
    raw = flexweek_engine.calendar_apply_times(json.dumps(block), start_min, end_min, day)
    return None if raw is None else json.loads(raw)


def split_occurrence(blocks: list[dict], block_id: str, day: int) -> tuple[list[dict], str | None]:
    updated, new_id = flexweek_engine.calendar_split(
        json.dumps(blocks), json.dumps(block_id), json.dumps(day)
    )
    return json.loads(updated), new_id


def delete_occurrence(blocks: list[dict], block_id: str, day: int | None) -> list[dict]:
    return json.loads(
        flexweek_engine.calendar_delete(json.dumps(blocks), json.dumps(block_id), json.dumps(day))
    )


def apply_block_edit(
    blocks: list[dict], block: dict, *, scope: str = "series", day: int | None = None
) -> list[dict]:
    return json.loads(
        flexweek_engine.calendar_apply_edit(
            json.dumps(blocks), json.dumps(block), json.dumps(scope), json.dumps(day)
        )
    )


def relocate_block(
    source: list[dict],
    block_id: str,
    from_day: int,
    to_day: int,
    dest: list[dict] | None = None,
) -> tuple[list[dict], list[dict] | None, str] | None:
    """One day's copy of a block, moved onto `to_day`. `dest` is None when that day is in the same week."""
    moved = flexweek_engine.calendar_relocate(
        json.dumps(source),
        json.dumps(block_id),
        json.dumps(from_day),
        json.dumps(to_day),
        None if dest is None else json.dumps(dest),
    )
    if moved is None:
        return None
    source_out, dest_out, made = moved
    return json.loads(source_out), None if dest_out is None else json.loads(dest_out), json.loads(made)


def first_plannable_day(week_start: str, today: date | None = None) -> int:
    today = today or date.today()
    return int(flexweek_engine.calendar_first_day(week_start, today.isoformat()))


def due_day_in_week(due: str | None, week_start: str) -> int | None:
    if not due:
        return None
    return int(flexweek_engine.calendar_due_day(due, week_start))


def days_through(due_day: int | None, first_day: int = 0) -> list[int]:
    return [int(day) for day in flexweek_engine.calendar_days_through(due_day, first_day)]


def month_for_view(iso_day: str) -> str:
    return str(flexweek_engine.calendar_month_for_view(iso_day))


def shifted_month(month: str, amount: int) -> str | None:
    return flexweek_engine.calendar_shifted_month(month, amount)


def month_anchor_date(selected_month: str, today: str) -> str:
    return str(flexweek_engine.calendar_month_anchor(selected_month, today))


def due_soon_for(iso_day: str, assignments: dict[str, dict]) -> list[dict]:
    return json.loads(flexweek_engine.calendar_due_soon(iso_day, json.dumps(assignments)))


# One sentinel, at module scope, because it is compared by identity. Built inside each function it
# would be a different object every call, so "is NOT_TODAY" was never true: the sentinel escaped into
# the agenda as a block's start time and the sort of those starts raised, which took the whole Day
# view down with it.
NOT_TODAY = object()


def placement_on(block: dict, day: int, trace: dict | None) -> str | None | object:
    """Where this block sits on this day: a time, None if it has none, or NOT_TODAY if it is not on
    this day at all."""
    found = json.loads(
        flexweek_engine.calendar_placement(
            json.dumps(block), json.dumps(day), None if trace is None else json.dumps(trace)
        )
    )
    return NOT_TODAY if found.get("not_today") else found["start"]


def agenda_for(
    week_start: str,
    iso_day: str,
    blocks: list[dict],
    assignments: dict[str, dict],
    trace: dict | None,
    day_data: dict | None,
) -> dict:
    return json.loads(
        flexweek_engine.calendar_agenda(
            week_start,
            iso_day,
            json.dumps(blocks),
            json.dumps(assignments),
            None if trace is None else json.dumps(trace),
            None if day_data is None else json.dumps(day_data),
        )
    )


def next_action_for(
    sessions: list[dict],
    due_soon: list[dict],
    assignments: dict[str, dict],
    day_data: dict | None,
) -> dict:
    return json.loads(
        flexweek_engine.calendar_next_action(
            json.dumps(sessions),
            json.dumps(due_soon),
            json.dumps(assignments),
            None if day_data is None else json.dumps(day_data),
        )
    )


# The blocks setup makes, found again by id when setup runs a second time. "sport" is the one the
# first-week card made before setup had pages.
SETUP_SCHOOL_ID = "school"
SETUP_ACTIVITY_PREFIX = "activity-"


def is_setup_block(block: dict) -> bool:
    return bool(flexweek_engine.calendar_setup_block(json.dumps(block)))


def span_problem(
    blocks: list[dict],
    block_id: str,
    day: int,
    start_min: int,
    end_min: int,
    due: tuple[int, int] | None,
) -> str | None:
    """Why a block cannot go at this time, in words, or None. Landing on another block is allowed, as
    in Daily Scheduler: the two sit side by side. What cannot stand is time FlexWeek does not plan in,
    and homework that would end after it is due."""
    return flexweek_engine.calendar_span_problem(day, start_min, end_min, json.dumps(due), type(due).__name__)


def span_clash(blocks: list[dict], block_id: str, day: int, start_min: int, end_min: int) -> str | None:
    """The name of a block this time would sit beside, for the words that go with a drop."""
    return flexweek_engine.calendar_span_clash(
        json.dumps(blocks), json.dumps(block_id), json.dumps(day), start_min, end_min
    )


def category_icon(category: str | None) -> str | None:
    return flexweek_engine.calendar_category_icon(category)
