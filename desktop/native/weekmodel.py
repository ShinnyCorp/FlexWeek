"""One reading of the week, shared by every layout.

The week table works out where a block sits inside its own set_week. Seven more views each doing that
would be seven chances to disagree about what is on Thursday, so the rules live here once: a solver
placement wins unless the block is finished, a finished session stays on the day it was finished, and
flexible work with no start is waiting for a time. Risk is the solver's own verdict from the trace,
never a threshold invented by a view.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta

import flexweek_engine  # type: ignore[import-untyped]

SLACK_WORDS = {"danger": "Cutting it close", "tight": "Tight", "ok": "Plenty of time"}
_SLACK_ORDER = {"danger": 0, "tight": 1, None: 2, "ok": 3}
NOT_PLANNED = "Not planned yet."
# A homework session is saved with no category unless the student picked one. It is still homework.
HOMEWORK = "assignments"
END_OF_DAY = 24 * 60
LEFTOVER = {
    "needs_time": "Not placed yet",
    "no_homework": "No homework added",
    "all_finished": "All homework finished",
    "calendar_only": "Nothing else scheduled today",
}


def minute_of(hhmm: str) -> int:
    return int(flexweek_engine.week_minute_of(hhmm))


def set_clock_24h(on: bool) -> bool:
    """Whether this changed the clock, so the caller knows to redraw."""
    return bool(flexweek_engine.week_set_clock_24h(on))


def clock_text(minute: int) -> str:
    """16:00, or 4:00 PM on the 12-hour clock. The end of the day, 24:00, is 12:00 AM."""
    return str(flexweek_engine.week_clock_text(minute))


def hhmm_text(hhmm: str) -> str:
    """A saved "16:00" as the clock writes it."""
    return str(flexweek_engine.week_hhmm_text(hhmm))


def time_format() -> str:
    """For a QTimeEdit, which draws its own time rather than asking clock_text."""
    return str(flexweek_engine.week_time_format())


def clock_label(minute: int) -> str:
    return str(flexweek_engine.week_clock_label(minute))


def short_clock(minute: int) -> str:
    """16:00, or 4 PM on the 12-hour clock: a time on a block, where room is short."""
    return str(flexweek_engine.week_short_clock(minute))


def range_label(start: int, end: int) -> str:
    """16:00–17:30, or on the 12-hour clock as short as it still reads: 4–5:30 PM, 11 AM–12:30 PM."""
    return str(flexweek_engine.week_range_label(start, end))


def length_label(minutes: int) -> str:
    return str(flexweek_engine.week_length_label(minutes))


def planned_line(planned_min: int, done_min: int) -> str:
    return str(flexweek_engine.week_planned_line(planned_min, done_min))


def due_label(due: str | None, week_start: str) -> str:
    """A deadline as a student says it: Sun 27 Sep, or Sun 27 Sep, 09:00 when a time is set."""
    return str(flexweek_engine.week_due_label(due, week_start))


def moved_words(block: dict, from_day: int, day: int, start: int, end: int) -> str:
    """What a drag did to `block`, as it was before, now that it is on `day` from `start` to `end`."""
    return str(flexweek_engine.week_moved_words(json.dumps(block), from_day, day, start, end))


def added_words(block: dict) -> str:
    """A block just made: "Added Club on Thu 16:00.", or without a day and time when it has several days."""
    return str(flexweek_engine.week_added_words(json.dumps(block)))


def dated_words(title: str, iso: str) -> str:
    """What carrying a block to another date on Month did, such as "Moved History essay to Fri 25 Sep"."""
    return str(flexweek_engine.week_dated_words(title, iso))


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
    # Minutes the focus timer has credited to this week's homework, and to its blocks without any.
    focus_min: int = 0

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
    raw = json.loads(
        flexweek_engine.week_build(
            week_start,
            json.dumps(blocks),
            json.dumps(assignments or {}),
            None if trace is None else json.dumps(trace),
        )
    )
    return WeekModel(
        raw["week_start"],
        tuple(Occurrence(**item) for item in raw["occurrences"]),
        tuple(Waiting(**item) for item in raw["waiting"]),
        int(raw["focus_min"]),
    )
