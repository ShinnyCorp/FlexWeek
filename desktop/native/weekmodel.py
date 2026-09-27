"""One reading of the week, shared by every layout.

The week table works out where a block sits inside its own set_week. Seven more views each doing that
would be seven chances to disagree about what is on Thursday, so the rules live here once: a solver
placement wins unless the block is finished, a finished session stays on the day it was finished, and
flexible work with no start is waiting for a time. Risk is the solver's own verdict from the trace,
never a threshold invented by a view.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from backend.models import due_is_timed, due_sort_key
from desktop.native.calendar import DAY_FULL, DAYS, _is_work_session, is_series

SLACK_WORDS = {"danger": "Cutting it close", "tight": "Tight", "ok": "Plenty of time"}
_SLACK_ORDER = {"danger": 0, "tight": 1, None: 2, "ok": 3}
NOT_PLANNED = "Not planned yet."
# A homework session is saved with no category unless the student picked one. It is still homework.
HOMEWORK = "assignments"
END_OF_DAY = 24 * 60
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
LEFTOVER = {
    "needs_time": "Not placed yet",
    "no_homework": "No homework added",
    "all_finished": "All homework finished",
    "calendar_only": "Nothing else scheduled today",
}


def minute_of(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")[:2]
    return int(hours) * 60 + int(minutes)


# Settings > This computer > Clock, set by the window from the account's preferences. Every time on
# screen is written by clock_text, so one switch changes them all; what is saved stays HH:MM.
_clock = {"24h": True}


def set_clock_24h(on: bool) -> bool:
    """Whether this changed the clock, so the caller knows to redraw."""
    changed = _clock["24h"] != on
    _clock["24h"] = on
    return changed


def clock_text(minute: int) -> str:
    """16:00, or 4:00 PM on the 12-hour clock. The end of the day, 24:00, is 12:00 AM."""
    hours, minutes = divmod(minute, 60)
    if _clock["24h"]:
        return f"{hours:02d}:{minutes:02d}"
    half = "AM" if hours % 24 < 12 else "PM"
    return f"{hours % 12 or 12}:{minutes:02d} {half}"


def hhmm_text(hhmm: str) -> str:
    """A saved "16:00" as the clock writes it."""
    return clock_text(minute_of(hhmm))


def time_format() -> str:
    """For a QTimeEdit, which draws its own time rather than asking clock_text."""
    return "HH:mm" if _clock["24h"] else "h:mm AP"


def clock_label(minute: int) -> str:
    return clock_text(minute)


def _twelve(minute: int) -> tuple[str, str]:
    """4 or 5:30, and its half of the day, as a short 12-hour time is written."""
    hours, minutes = divmod(minute, 60)
    shown = f"{hours % 12 or 12}" + (f":{minutes:02d}" if minutes else "")
    return shown, "AM" if hours % 24 < 12 else "PM"


def short_clock(minute: int) -> str:
    """16:00, or 4 PM on the 12-hour clock: a time on a block, where room is short."""
    if _clock["24h"]:
        return clock_text(minute)
    shown, half = _twelve(minute)
    return f"{shown} {half}"


def range_label(start: int, end: int) -> str:
    """16:00–17:30, or on the 12-hour clock as short as it still reads: 4–5:30 PM, 11 AM–12:30 PM."""
    if _clock["24h"]:
        return f"{clock_text(start)}–{clock_text(end)}"
    first, first_half = _twelve(start)
    last, last_half = _twelve(end)
    if first_half == last_half:
        return f"{first}–{last} {last_half}"
    return f"{first} {first_half}–{last} {last_half}"


def length_label(minutes: int) -> str:
    hours, rest = divmod(max(minutes, 0), 60)
    if not hours:
        return f"{rest} min"
    return f"{hours} h {rest} min" if rest else f"{hours} h"


def planned_line(planned_min: int, done_min: int) -> str:
    if planned_min <= 0:
        return "Nothing planned yet"
    done = "0 done" if done_min <= 0 else f"{length_label(done_min)} done"
    return f"{length_label(planned_min)} planned · {done}"


def due_label(due: str | None, week_start: str) -> str:
    """A deadline as a student says it: Sun 27 Sep, or Sun 27 Sep, 09:00 when a time is set."""
    if not due:
        return ""
    day = date.fromisoformat(due[:10])
    words = f"{DAYS[day.weekday()]} {day.day} {_MONTHS[day.month - 1]}"
    if due_is_timed(due):
        words += f", {hhmm_text(due[11:16])}"
    return words


def moved_words(block: dict, from_day: int, day: int, start: int, end: int) -> str:
    """What a drag did to `block`, as it was before, now that it is on `day` from `start` to `end`:
    "Moved History essay to Fri 18:00.", "History essay now ends at 20:30.", "Placed Math worksheet
    on Thu 17:45." A block that repeats moved only the day it was picked up from, so that day is
    named."""
    title = block.get("title") or "the block"
    if not block.get("start"):
        return f"Placed {title} on {DAYS[day]} {clock_label(start)}."
    if is_series(block):
        title = f"{DAY_FULL[from_day]}'s {title}"
    was = minute_of(block["start"])
    was_end = was + int(block["duration_min"])
    if day == from_day and start == was and end != was_end:
        return f"{title} now ends at {clock_label(end)}."
    if day == from_day and end == was_end and start != was:
        return f"{title} now starts at {clock_label(start)}."
    return f"Moved {title} to {DAYS[day]} {clock_label(start)}."


def added_words(block: dict) -> str:
    """A block just made: "Added Club on Thu 16:00.", or without a day and time when it has several
    days or no time yet."""
    title = block.get("title") or "a block"
    days = block.get("days") or []
    if block.get("start") and len(days) == 1:
        return f"Added {title} on {DAYS[days[0]]} {hhmm_text(block['start'])}."
    return f"Added {title}."


def dated_words(title: str, iso: str) -> str:
    """What carrying a block to another date on Month did, such as "Moved History essay to Fri 25 Sep"."""
    return f"Moved {title} to {due_label(iso, '')}."


@dataclass(frozen=True)
class Occurrence:
    """One block on one day, with its time already resolved."""

    block_id: str
    title: str
    category: str
    day: int
    start: int
    end: int
    work: bool
    done: bool
    missed: bool
    assignment_id: str | None
    due: str | None
    slack: str | None
    # Put there by hand: no plan moves it.
    pinned: bool = False

    @property
    def minutes(self) -> int:
        return self.end - self.start

    @property
    def live(self) -> bool:
        """Still something to do: fixed blocks always, homework until it is done or missed."""
        return not (self.work and (self.done or self.missed))

    @property
    def slack_words(self) -> str:
        return SLACK_WORDS.get(self.slack or "", "")


@dataclass(frozen=True)
class Waiting:
    """Homework that has no time yet, with the reason the solver gave if it gave one."""

    block_id: str
    title: str
    category: str
    minutes: int
    assignment_id: str | None
    due: str | None
    reason: str


@dataclass(frozen=True)
class DayQueue:
    current: Occurrence | None
    queue: tuple[Occurrence, ...]


@dataclass(frozen=True)
class WeekModel:
    week_start: str
    occurrences: tuple[Occurrence, ...] = ()
    waiting: tuple[Waiting, ...] = ()

    def date_of(self, day: int) -> date:
        return date.fromisoformat(self.week_start) + timedelta(days=day)

    def on_day(self, day: int) -> tuple[Occurrence, ...]:
        return tuple(item for item in self.occurrences if item.day == day)

    def load_min(self, day: int) -> int:
        return sum(item.minutes for item in self.on_day(day) if item.work)

    def open_work(self) -> tuple[Occurrence, ...]:
        """Homework still to do, the most squeezed first."""
        items = [item for item in self.occurrences if item.work and item.live]
        return tuple(sorted(items, key=lambda item: (_SLACK_ORDER[item.slack], item.day, item.start)))

    def due_today_unplaced(self, today: int | None) -> tuple[Waiting, ...]:
        """Homework due today that still needs a time. Every screen reads this, not its own filter."""
        if today is None:
            return ()
        iso = self.date_of(today).isoformat()
        return tuple(item for item in self.waiting if (item.due or "").startswith(iso))

    def leftover_kind(self, today: int | None) -> str:
        """Which of the four empty-day states this week is in, once nothing placed is still ahead."""
        if today is not None and self.due_today_unplaced(today):
            return "needs_time"
        homework = [item for item in self.occurrences if item.work]
        if not homework and not self.waiting:
            return "calendar_only" if self.occurrences else "no_homework"
        if not any(item.live for item in homework) and not self.waiting:
            return "all_finished"
        return "calendar_only"

    def leftover_words(self, today: int | None) -> str:
        return LEFTOVER[self.leftover_kind(today)]

    def leftover_parts(self, today: int | None) -> tuple[str, str, str]:
        """Kicker, title, line. When homework needs a time, the title is its name."""
        kind = self.leftover_kind(today)
        heading = LEFTOVER[kind]
        if kind == "needs_time":
            first = self.due_today_unplaced(today)[0]
            due = due_label(first.due, self.week_start)
            return heading, first.title, f"Due {due}" if due else "Due today"
        return heading, heading, ""

    def minutes_left_today(self, today: int | None, minute: int) -> int:
        """Placed remaining homework today, plus unplaced homework due today."""
        if today is None:
            return 0
        total = 0
        for item in self.on_day(today):
            if item.work and item.live and item.end > minute:
                total += item.end - max(item.start, minute)
        total += sum(item.minutes for item in self.due_today_unplaced(today))
        return total

    def day_queue(self, day: int, minute: int) -> DayQueue:
        """What a day screen is about: the thing on now, then the rest of the day in order.

        Homework wins over the fixed block around it, because a study hall inside School is the part
        the student has to act on.
        """
        live = [item for item in self.on_day(day) if item.live]
        running = sorted(
            (item for item in live if item.start <= minute < item.end),
            key=lambda item: (not item.work, item.start),
        )
        current = running[0] if running else None
        later = tuple(item for item in live if item.start > minute)
        return DayQueue(current, ((current,) if current else ()) + later)


def build_week(
    week_start: str,
    blocks: list[dict],
    assignments: dict[str, dict] | None = None,
    trace: dict | None = None,
) -> WeekModel:
    homework = assignments or {}
    placed = {item["id"]: item for item in (trace or {}).get("placed") or []}
    notes = {item["block_id"]: item for item in (trace or {}).get("explanations") or []}
    occurrences: list[Occurrence] = []
    waiting: list[Waiting] = []
    for original in blocks:
        block = original if original.get("completed") else placed.get(original["id"], original)
        assignment = homework.get(original.get("assignment_id") or "") or {}
        work = _is_work_session(original)
        done = bool(block.get("completed") or assignment.get("completed"))
        note = notes.get(original["id"]) or {}
        if not block.get("start"):
            if work and not done:
                waiting.append(
                    Waiting(
                        block_id=original["id"],
                        title=original.get("title") or "Untitled",
                        category=original.get("category") or HOMEWORK,
                        minutes=int(original.get("duration_min") or 0),
                        assignment_id=original.get("assignment_id"),
                        due=assignment.get("due"),
                        reason=note.get("message") or NOT_PLANNED,
                    )
                )
            continue
        days = block.get("days") or []
        if block.get("completed") and block.get("completed_day") is not None:
            days = [block["completed_day"]]
        start = minute_of(block["start"])
        end = min(start + int(block.get("duration_min") or 0), END_OF_DAY)
        for day in days:
            occurrences.append(
                Occurrence(
                    block_id=original["id"],
                    title=block.get("title") or "Untitled",
                    category=block.get("category") or (HOMEWORK if work else ""),
                    day=day,
                    start=start,
                    end=end,
                    work=work,
                    done=done,
                    missed=day in (original.get("missed_days") or []),
                    assignment_id=original.get("assignment_id"),
                    due=assignment.get("due"),
                    slack=note.get("slack_status"),
                    pinned=bool(block.get("pinned")),
                )
            )
    occurrences.sort(key=lambda item: (item.day, item.start, item.block_id))
    waiting.sort(key=lambda item: due_sort_key(item.due, item.block_id))
    return WeekModel(week_start, tuple(occurrences), tuple(waiting))
