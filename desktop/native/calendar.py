"""Week-grid edits and Day/Month helpers for the native calendar. No Qt."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from uuid import uuid4

from backend.models import due_sort_key
from backend.slots import DAY_END_MIN, DAY_START_MIN, hhmm_to_minutes, minutes_to_hhmm

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
    info = CATEGORIES.get(category or "")
    return info["label"] if info else "Fixed time"


def is_series(block: dict) -> bool:
    return block.get("kind") == "locked" and len(block.get("days") or []) > 1


def monday_of(iso_day: str) -> str:
    day = date.fromisoformat(iso_day)
    return (day - timedelta(days=day.weekday())).isoformat()


def date_for_day(week_start: str, day: int) -> str:
    return (date.fromisoformat(week_start) + timedelta(days=day)).isoformat()


def sunday_due(week_start: str) -> str:
    return date_for_day(week_start, 6) + "T23:59"


def local_stamp(now: datetime | None = None) -> str:
    moment = now or datetime.now()
    return moment.strftime("%Y-%m-%dT%H:%M")


def occupied_intervals(blocks: list[dict], day: int) -> list[tuple[int, int]]:
    intervals = []
    for block in blocks:
        if not block.get("start") or day not in (block.get("days") or []):
            continue
        if day in (block.get("missed_days") or []):
            continue
        begin = hhmm_to_minutes(block["start"])
        intervals.append((begin, begin + block["duration_min"]))
    intervals.sort()
    return intervals


def create_click_range(begin: int, occupied: list[tuple[int, int]]) -> tuple[int, int] | None:
    """Up to an hour from `begin`, which the hand has already put on its step, stopping where the next
    block starts."""
    stop = min(begin + 60, DAY_END_MIN)
    for slot_start, _slot_end in occupied:
        if begin <= slot_start < stop:
            stop = slot_start
            break
    if stop <= begin:
        return None
    return begin, stop


def apply_block_times(block: dict, start_min: int, end_min: int, day: int | None = None) -> dict | None:
    """The block at a new time, and on `day` when it moved to another one."""
    if not block.get("start"):
        return None
    if is_series(block):
        return None
    duration = end_min - start_min
    if duration <= 0 or start_min < DAY_START_MIN or end_min > DAY_END_MIN:
        return None
    updated = deepcopy(block)
    updated["start"] = minutes_to_hhmm(start_min)
    updated["duration_min"] = duration
    if day is not None and list(block.get("days") or []) != [day]:
        updated["days"] = [day]
        if updated.get("completed_day") is not None:
            updated["completed_day"] = day
    return updated


def split_occurrence(blocks: list[dict], block_id: str, day: int) -> tuple[list[dict], str | None]:
    current = next(item for item in blocks if item["id"] == block_id)
    if day not in current["days"] or len(current["days"]) == 1:
        return [deepcopy(item) for item in blocks], None
    remaining = deepcopy(current)
    remaining["days"] = [item for item in current["days"] if item != day]
    remaining["missed_days"] = [
        item for item in remaining.get("missed_days") or [] if item in remaining["days"]
    ]
    occurrence = deepcopy(current)
    new_id = str(uuid4())
    occurrence["id"] = new_id
    occurrence["days"] = [day]
    occurrence["missed_days"] = [day] if day in (current.get("missed_days") or []) else []
    replaced = [remaining if item["id"] == block_id else deepcopy(item) for item in blocks]
    return replaced + [occurrence], new_id


def delete_occurrence(blocks: list[dict], block_id: str, day: int | None) -> list[dict]:
    result = []
    for item in blocks:
        if item["id"] != block_id:
            result.append(deepcopy(item))
            continue
        if day is None or len(item["days"]) <= 1 or day not in item["days"]:
            continue
        kept = deepcopy(item)
        kept["days"] = [value for value in item["days"] if value != day]
        kept["missed_days"] = [value for value in kept.get("missed_days") or [] if value in kept["days"]]
        if kept["days"]:
            result.append(kept)
    return result


def apply_block_edit(
    blocks: list[dict], block: dict, *, scope: str = "series", day: int | None = None
) -> list[dict]:
    current = next((item for item in blocks if item["id"] == block["id"]), None)
    if scope == "occurrence" and current is not None and day is not None and is_series(current):
        split, new_id = split_occurrence(blocks, block["id"], day)
        updated = deepcopy(block)
        updated["id"] = new_id or block["id"]
        updated["days"] = [day]
        updated["missed_days"] = [
            item for item in updated.get("missed_days") or [] if item in updated["days"]
        ]
        return [updated if item["id"] == updated["id"] else item for item in split]
    replaced = False
    result = []
    for item in blocks:
        if item["id"] == block["id"]:
            result.append(deepcopy(block))
            replaced = True
        else:
            result.append(deepcopy(item))
    if not replaced:
        result.append(deepcopy(block))
    return result


def relocate_block(
    source: list[dict],
    block_id: str,
    from_day: int,
    to_day: int,
    dest: list[dict] | None = None,
) -> tuple[list[dict], list[dict] | None, str] | None:
    """One day's copy of a block, moved onto `to_day`. `dest` is None when that day is in the same week."""
    block = next((item for item in source if item["id"] == block_id), None)
    if block is None or from_day not in (block.get("days") or []) or not block.get("start"):
        return None

    def for_date(item: dict) -> dict:
        out = deepcopy(item)
        out["days"] = [to_day]
        if out.get("assignment_id") and out.get("kind") == "flexible" and not out.get("completed"):
            out["pinned"] = True
        if out.get("completed_day") == from_day:
            out["completed_day"] = to_day
        out["missed_days"] = [day for day in out.get("missed_days") or [] if day in out["days"]]
        return out

    if dest is None:
        if is_series(block):
            before = {item["id"] for item in source}
            edited = apply_block_edit(source, deepcopy(block), scope="occurrence", day=from_day)
            made = next((item["id"] for item in edited if item["id"] not in before), block_id)
            return [for_date(item) if item["id"] == made else deepcopy(item) for item in edited], None, made
        return apply_block_edit(source, for_date(block)), None, block_id

    if is_series(block):
        split, new_id = split_occurrence(source, block_id, from_day)
        made = new_id or block_id
        occurrence = next(item for item in split if item["id"] == made)
        source_out = [deepcopy(item) for item in split if item["id"] != made]
        return source_out, [deepcopy(item) for item in dest] + [for_date(occurrence)], made
    source_out = [deepcopy(item) for item in source if item["id"] != block_id]
    return source_out, [deepcopy(item) for item in dest] + [for_date(block)], block_id


def first_plannable_day(week_start: str, today: date | None = None) -> int:
    today = today or date.today()
    monday = date.fromisoformat(week_start)
    if monday <= today <= monday + timedelta(days=6):
        return today.weekday()
    return 0


def due_day_in_week(due: str | None, week_start: str) -> int | None:
    if not due:
        return None
    return (date.fromisoformat(due[:10]) - date.fromisoformat(week_start)).days


def days_through(due_day: int | None, first_day: int = 0) -> list[int]:
    last = 6 if due_day is None else min(due_day, 6)
    if last < 0:
        return []
    if last < first_day:
        return [last]
    return [day for day in range(7) if first_day <= day <= last]


def month_for_view(iso_day: str) -> str:
    month = iso_day[:7]
    if month < FIRST_MONTH:
        return FIRST_MONTH
    if month > LAST_MONTH:
        return LAST_MONTH
    return month


def shifted_month(month: str, amount: int) -> str | None:
    year, month_number = (int(part) for part in month.split("-"))
    index = year * 12 + (month_number - 1) + amount
    nxt_year, nxt_month = divmod(index, 12)
    label = f"{nxt_year:04d}-{nxt_month + 1:02d}"
    if label < FIRST_MONTH or label > LAST_MONTH:
        return None
    return label


def month_anchor_date(selected_month: str, today: str) -> str:
    if today[:7] == selected_month:
        return today
    return selected_month + "-01"


def due_soon_for(iso_day: str, assignments: dict[str, dict]) -> list[dict]:
    tomorrow = (date.fromisoformat(iso_day) + timedelta(days=1)).isoformat()
    items = [
        item
        for item in assignments.values()
        if not item.get("completed") and item.get("due", "9999")[:10] <= tomorrow
    ]
    return sorted(items, key=lambda item: due_sort_key(item.get("due"), str(item.get("id") or "")))


def _is_work_session(block: dict) -> bool:
    return block.get("kind") == "flexible" or (
        block.get("kind") == "locked" and block.get("pomodoro_role") == "work" and block.get("assignment_id")
    )


# One sentinel, at module scope, because it is compared by identity. Built inside each function it
# would be a different object every call, so "is NOT_TODAY" was never true: the sentinel escaped into
# the agenda as a block's start time and the sort of those starts raised, which took the whole Day
# view down with it.
NOT_TODAY = object()


def placement_on(block: dict, day: int, trace: dict | None) -> str | None | object:
    """Where this block sits on this day: a time, None if it has none, or NOT_TODAY if it is not on
    this day at all."""
    placed = next((item for item in (trace or {}).get("placed", []) if item["id"] == block["id"]), None)
    if placed and placed.get("start"):
        return placed["start"] if day in placed["days"] else NOT_TODAY
    if block.get("start"):
        return block["start"] if day in (block.get("days") or []) else NOT_TODAY
    return None


def agenda_for(
    week_start: str,
    iso_day: str,
    blocks: list[dict],
    assignments: dict[str, dict],
    trace: dict | None,
    day_data: dict | None,
) -> dict:
    day_index = (date.fromisoformat(iso_day) - date.fromisoformat(week_start)).days
    sessions: list[dict] = []
    fixed: list[dict] = []
    if 0 <= day_index <= 6:
        for block in blocks:
            if day_index not in (block.get("days") or []):
                continue
            if day_index in (block.get("missed_days") or []):
                continue
            start = placement_on(block, day_index, trace)
            if start is NOT_TODAY:
                continue
            row = {"block": block, "start": start}
            if _is_work_session(block):
                sessions.append(row)
            elif block.get("kind") == "locked":
                fixed.append(row)

    def in_clock_order(row: dict) -> tuple[str, str]:
        start = row["start"]
        return (start if isinstance(start, str) and start else "99:99", str(row["block"]["id"]))

    sessions.sort(key=in_clock_order)
    fixed.sort(key=in_clock_order)
    due_soon = due_soon_for(iso_day, assignments)
    return {
        "day_index": day_index,
        "due_soon": due_soon,
        "sessions": sessions,
        "fixed": fixed,
        "next_action": next_action_for(sessions, due_soon, assignments, day_data),
    }


def next_action_for(
    sessions: list[dict],
    due_soon: list[dict],
    assignments: dict[str, dict],
    day_data: dict | None,
) -> dict:
    for row in sessions:
        assignment = assignments.get(row["block"].get("assignment_id") or "")
        if row["start"] and not row["block"].get("completed") and not (assignment or {}).get("completed"):
            return {"kind": "start", "id": row["block"]["id"]}
    unplanned = {
        item["id"]: item.get("unplanned_min") or 0 for item in (day_data or {}).get("due_soon") or []
    }
    for item in due_soon:
        if unplanned.get(item["id"], 0) > 0:
            return {"kind": "plan", "id": item["id"]}
    return {"kind": "add"}


# The blocks setup makes, found again by id when setup runs a second time. "sport" is the one the
# first-week card made before setup had pages.
SETUP_SCHOOL_ID = "school"
SETUP_ACTIVITY_PREFIX = "activity-"


def is_setup_block(block: dict) -> bool:
    block_id = str(block.get("id") or "")
    return block_id in {SETUP_SCHOOL_ID, "sport"} or block_id.startswith(SETUP_ACTIVITY_PREFIX)


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
    if start_min < DAY_START_MIN or end_min > DAY_END_MIN:
        return "That is outside the hours FlexWeek plans in, so it stayed where it was."
    if due is not None and (day, end_min) > due:
        return "That ends after it is due, so it stayed where it was."
    return None


def span_clash(blocks: list[dict], block_id: str, day: int, start_min: int, end_min: int) -> str | None:
    """The name of a block this time would sit beside, for the words that go with a drop."""
    for other in blocks:
        if other["id"] == block_id or not other.get("start"):
            continue
        if day not in (other.get("days") or []) or day in (other.get("missed_days") or []):
            continue
        if other.get("completed") and other.get("completed_day") not in (None, day):
            continue
        begin = hhmm_to_minutes(other["start"])
        if start_min < begin + int(other["duration_min"]) and begin < end_min:
            return str(other.get("title") or "another block")
    return None


def category_icon(category: str | None) -> str | None:
    return "book-open" if category == "homework" else CATEGORIES.get(category or "", {}).get("icon")
