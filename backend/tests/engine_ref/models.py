from __future__ import annotations

import re
from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.tests.engine_ref.slots import clock_to_minutes, on_slot, span_fits_day, start_fits_day
from backend.tests.engine_ref.weeks import FIRST_DAY, LAST_DAY, is_week_start

BlockKind = Literal["locked", "flexible"]
Priority = Literal[1, 2, 3, 4]
Energy = Literal["high", "medium", "low"]
SlackStatus = Literal["ok", "tight", "danger"]
ReasonCode = Literal[
    "LOCKED_OVERLAP",
    "DEADLINE_MISS",
    "NO_SLOT_LEFT",
    "PRIORITY_PREEMPT",
    "ENERGY_MISMATCH",
    "SLEEP_GUARD",
    "WORK_WINDOW_MISS",
    "RESHUFFLE_AFTER_MISS",
]
PomodoroRole = Literal["work", "break"]


# The only Spotify link check there is, now that the web client it mirrored is gone.
SPOTIFY_SHARE = re.compile(
    r"https://open\.spotify\.com/(track|playlist|album|episode|show)/[A-Za-z0-9]+/?(?:[?#].*)?"
)
# Naive local stamp: date, T, hour:minute. No seconds, no timezone, any minute.
NAIVE_STAMP = re.compile(r"(\d{4}-\d{2}-\d{2})T((?:[01]\d|2[0-3]):[0-5]\d)\Z")
NAIVE_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})\Z")
# Date-only due, and the old default T23:59, mean the end of that calendar day.
END_OF_DAY_MIN = 24 * 60
END_OF_DAY_CLOCK = "23:59"
# One homework is at most a day's work; longer work is split into parts.
ESTIMATE_MAX_MIN = 24 * 60


def _iso_day(text: str) -> date:
    day = date.fromisoformat(text)
    if not FIRST_DAY <= day <= LAST_DAY:
        raise ValueError("date must be between 2000-01-01 and 2099-12-31")
    return day


def parse_naive_stamp(value: str) -> tuple[date, int]:
    match = NAIVE_STAMP.fullmatch(value)
    if not match:
        raise ValueError("must be YYYY-MM-DDTHH:MM with no seconds or timezone")
    hour, minute = map(int, match.group(2).split(":"))
    return _iso_day(match.group(1)), hour * 60 + minute


def parse_due(value: str) -> tuple[date, int]:
    """The due day, and the minute work must end by. Date-only and 23:59 are the end of that day."""
    if NAIVE_DATE.fullmatch(value):
        return _iso_day(value), END_OF_DAY_MIN
    match = NAIVE_STAMP.fullmatch(value)
    if not match:
        raise ValueError("must be YYYY-MM-DD or YYYY-MM-DDTHH:MM with no seconds or timezone")
    day = _iso_day(match.group(1))
    clock = match.group(2)
    if clock == END_OF_DAY_CLOCK:
        return day, END_OF_DAY_MIN
    hour, minute = map(int, clock.split(":"))
    return day, hour * 60 + minute


def due_is_timed(value: str) -> bool:
    """True when the due stamp names a clock other than the old end-of-day 23:59."""
    match = NAIVE_STAMP.fullmatch(value)
    return match is not None and match.group(2) != END_OF_DAY_CLOCK


def due_sort_key(due: str | None, item_id: str = "") -> tuple[date, int, str]:
    """When the work must end, then its id. A date with no time, and 23:59, are the end of that day."""
    if not due:
        return date.max, END_OF_DAY_MIN, item_id
    day, minute = parse_due(due)
    return day, minute, item_id


def valid_naive_stamp(value: str) -> str:
    parse_naive_stamp(value)
    return value


def valid_due(value: str) -> str:
    parse_due(value)
    return value


def valid_spotify_url(value: str | None) -> str | None:
    """Accept only share links that the desktop shell can safely open externally."""
    if value is None or value == "":
        return None
    # Matched against the raw string, not urlsplit's normalised view. urlsplit
    # lowercases the scheme and host and tolerates a doubled slash, so it would
    # accept forms the browser's own check rejects; the client would then null
    # the value and the next save would quietly wipe a link the user stored.
    if not SPOTIFY_SHARE.fullmatch(value):
        raise ValueError("spotify_url must be an open.spotify.com share link")
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None or parsed.port is not None:
        raise ValueError("spotify_url must be an open.spotify.com share link")
    return value


def valid_http_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("link url must be an http or https URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("link url must be an http or https URL")
    return value


class TimeBlock(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=80)
    kind: BlockKind
    # Any minute: a student's own times are kept as typed. Only the planner works in quarter hours.
    duration_min: int = Field(gt=0, le=7140)
    days: list[int] = Field(min_length=1, max_length=7)
    priority: Priority = 3
    energy: Energy = "medium"
    earliest: str | None = Field(default=None, max_length=40)
    latest: str | None = Field(default=None, max_length=40)
    start: str | None = Field(default=None, max_length=5)
    course: str | None = Field(default=None, max_length=40)
    category: str | None = Field(
        default=None,
        max_length=32,
        exclude_if=lambda value: value is None,
    )
    completed: bool = Field(
        default=False,
        exclude_if=lambda value: value is False,
    )
    completed_day: int | None = Field(
        default=None,
        ge=0,
        le=6,
        exclude_if=lambda value: value is None,
    )
    missed_days: list[int] = Field(
        default_factory=list,
        max_length=7,
        exclude_if=lambda value: not value,
    )
    spotify_url: str | None = Field(default=None, max_length=500, exclude_if=lambda value: value is None)
    focus_sessions: int = Field(default=0, ge=0, le=9999, exclude_if=lambda value: value == 0)
    focus_minutes: int = Field(default=0, ge=0, le=71400, exclude_if=lambda value: value == 0)
    pomodoro_parent_id: str | None = Field(
        default=None, min_length=1, max_length=80, exclude_if=lambda value: value is None
    )
    pomodoro_role: PomodoroRole | None = Field(default=None, exclude_if=lambda value: value is None)
    pomodoro_index: int | None = Field(default=None, ge=1, le=999, exclude_if=lambda value: value is None)
    # Homework the student placed by hand. No plan moves it; a fixed block over it still takes its time.
    pinned: bool = Field(default=False, exclude_if=lambda value: value is False)
    assignment_id: str | None = Field(
        default=None, min_length=1, max_length=80, exclude_if=lambda value: value is None
    )

    _spotify_url = field_validator("spotify_url")(valid_spotify_url)

    @field_validator("days")
    @classmethod
    def days_in_week(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("days must be in 0..6 (Mon..Sun)")
        return value

    @field_validator("missed_days")
    @classmethod
    def missed_days_in_week(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value) or any(day < 0 or day > 6 for day in value):
            raise ValueError("missed_days must be unique values in 0..6")
        return value

    @model_validator(mode="after")
    def block_state_is_consistent(self) -> TimeBlock:
        if self.pinned and (self.kind != "flexible" or self.start is None or len(self.days) != 1):
            raise ValueError("pinned requires a flexible block with a start on one day")
        if self.missed_days and self.kind != "locked":
            raise ValueError("only locked blocks can have missed days")
        if not set(self.missed_days).issubset(self.days):
            raise ValueError("missed days must be occurrences of the block")
        if self.completed_day is not None and (
            self.kind != "flexible"
            or not self.completed
            or self.start is None
            or self.completed_day not in self.days
        ):
            raise ValueError(
                "completed_day requires a completed flexible block with a start on a candidate day"
            )
        if self.assignment_id is not None:
            if self.latest is not None:
                raise ValueError("a session cannot carry latest")
            if self.focus_minutes or self.focus_sessions:
                raise ValueError("session focus must be 0")
            if self.kind == "flexible":
                return self
            if self.kind == "locked" and self.pomodoro_role == "work":
                return self
            raise ValueError("assignment_id is only valid on a work session or a pomodoro work chunk")
        return self


class AssignmentLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1, max_length=500)

    _url = field_validator("url")(valid_http_url)

    @field_validator("label")
    @classmethod
    def label_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("link label required")
        return value


class ChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=80)
    done: bool = False

    @field_validator("text")
    @classmethod
    def text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("checklist text required")
        return value


class AssignmentContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=80)
    course: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, max_length=32)
    priority: Priority = 3
    energy: Energy = "medium"
    spotify_url: str | None = Field(default=None, max_length=500)
    due: str
    estimate_min: int = Field(le=ESTIMATE_MAX_MIN)
    focus_minutes: int = Field(default=0, ge=0, le=71400)
    focus_sessions: int = Field(default=0, ge=0, le=9999)
    completed: bool = False
    completed_at: str | None = None
    notes: str = Field(default="", max_length=4000, exclude_if=lambda value: value == "")
    links: list[AssignmentLink] = Field(
        default_factory=list, max_length=20, exclude_if=lambda value: not value
    )
    checklist: list[ChecklistItem] = Field(
        default_factory=list, max_length=40, exclude_if=lambda value: not value
    )

    _spotify_url = field_validator("spotify_url")(valid_spotify_url)
    _due = field_validator("due")(valid_due)

    @field_validator("completed_at")
    @classmethod
    def completed_at_stamp(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return valid_naive_stamp(value)

    @field_validator("title")
    @classmethod
    def title_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title required")
        return value

    @field_validator("estimate_min")
    @classmethod
    def estimate_is_slot_aligned(cls, value: int) -> int:
        if value <= 0 or value % 15 != 0:
            raise ValueError("estimate_min must be a positive multiple of 15")
        return value

    @model_validator(mode="after")
    def completed_at_matches_completed(self) -> AssignmentContent:
        if self.completed and self.completed_at is None:
            raise ValueError("completed_at is required when completed")
        if not self.completed and self.completed_at is not None:
            raise ValueError("completed_at must be null when not completed")
        ids = [item.id for item in self.checklist]
        if len(ids) != len(set(ids)):
            raise ValueError("checklist ids must be unique")
        return self


class Assignment(AssignmentContent):
    revision: int = Field(ge=0, le=2**53 - 1)


class RoutineBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=80)
    days: list[int] = Field(min_length=1, max_length=7)
    start: str
    duration_min: int = Field(gt=0, le=7140)
    category: str | None = Field(default=None, max_length=32)
    course: str | None = Field(default=None, max_length=40)
    priority: Priority = 3
    energy: Energy = "medium"
    spotify_url: str | None = Field(default=None, max_length=500)

    _spotify_url = field_validator("spotify_url")(valid_spotify_url)

    @field_validator("title")
    @classmethod
    def title_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title required")
        return value

    @field_validator("days")
    @classmethod
    def days_in_week(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value) or any(day < 0 or day > 6 for day in value):
            raise ValueError("days must be unique values in 0..6")
        return value

    @field_validator("start")
    @classmethod
    def start_is_hhmm(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("invalid start time")
        return value

    @model_validator(mode="after")
    def block_fits_the_day(self) -> RoutineBlock:
        hour, minute = map(int, self.start.split(":"))
        start = hour * 60 + minute
        if not span_fits_day(start, self.duration_min):
            raise ValueError("block must fit between 00:00 and 24:00")
        return self


class Routine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    blocks: list[RoutineBlock] = Field(max_length=100)
    revision: int = Field(ge=0, le=2**53 - 1)

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name required")
        return value

    @field_validator("blocks")
    @classmethod
    def template_ids_are_unique(cls, blocks: list[RoutineBlock]) -> list[RoutineBlock]:
        if len({block.template_id for block in blocks}) != len(blocks):
            raise ValueError("template ids must be unique")
        return blocks

    @model_validator(mode="after")
    def occurrences_do_not_overlap(self) -> Routine:
        for day in range(7):
            intervals: list[tuple[int, int]] = []
            for block in self.blocks:
                if day not in block.days:
                    continue
                hour, minute = map(int, block.start.split(":"))
                start = hour * 60 + minute
                end = start + block.duration_min
                if any(start < other_end and other_start < end for other_start, other_end in intervals):
                    raise ValueError("routine blocks overlap")
                intervals.append((start, end))
        return self


class WorkWindow(BaseModel):
    """Hard hours the planner may use. Hand-placed blocks are not bound by this."""

    model_config = ConfigDict(extra="forbid")
    days: list[int] = Field(min_length=1, max_length=7)
    start: str = Field(min_length=5, max_length=5)
    end: str = Field(min_length=5, max_length=5)
    subject: str | None = Field(
        default=None, min_length=1, max_length=40, exclude_if=lambda value: value is None
    )

    @field_validator("days")
    @classmethod
    def days_in_week(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value) or any(day < 0 or day > 6 for day in value):
            raise ValueError("days must be unique values in 0..6")
        return value

    @field_validator("start")
    @classmethod
    def start_is_on_the_grid(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("start must be HH:MM")
        hour, minute = map(int, value.split(":"))
        start = hour * 60 + minute
        if not (start_fits_day(start) and on_slot(start)):
            raise ValueError("start must be on the 00:00–24:00 grid")
        return value

    @field_validator("end")
    @classmethod
    def end_is_on_the_grid(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d|24:00", value):
            raise ValueError("end must be HH:MM, or 24:00")
        end = clock_to_minutes(value)
        if not on_slot(end) or end <= 0 or end > 24 * 60:
            raise ValueError("end must be on the 00:00–24:00 grid")
        return value

    @field_validator("subject")
    @classmethod
    def subject_is_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("subject must not be blank")
        return trimmed

    @model_validator(mode="after")
    def end_is_after_start(self) -> WorkWindow:
        if clock_to_minutes(self.end) <= clock_to_minutes(self.start):
            raise ValueError("end must be after start")
        return self


class Move(BaseModel):
    block_id: str
    reason: ReasonCode
    from_day: int | None = Field(default=None, ge=0, le=6)
    from_start: str | None = None
    to_day: int | None = Field(default=None, ge=0, le=6)
    to_start: str | None = None


class Explanation(BaseModel):
    block_id: str
    message: str
    reason: ReasonCode | None = None
    slack_min: int | None = Field(default=None, ge=0)
    slack_status: SlackStatus | None = None


class SolveTrace(BaseModel):
    placed: list[TimeBlock]
    unplaced: list[TimeBlock]
    moves: list[Move]
    explanations: list[Explanation]
    failed_constraints: list[ReasonCode]
    solve_ms: float
    complete: bool
    work_windows: list[WorkWindow] = Field(default_factory=list)
    work_windows_defaulted: bool = False


class WeekRequest(BaseModel):
    blocks: list[TimeBlock] = Field(max_length=100)

    @field_validator("blocks")
    @classmethod
    def valid_week(cls, blocks: list[TimeBlock]) -> list[TimeBlock]:
        ids = {block.id for block in blocks}
        if len(ids) != len(blocks):
            raise ValueError("block ids must be unique")
        for block in blocks:
            if not block.title.strip() or len(set(block.days)) != len(block.days):
                raise ValueError("title and unique days required")
            if block.kind == "locked" and not block.start:
                raise ValueError("locked blocks need a start")
            if block.start:
                if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", block.start):
                    raise ValueError("invalid start time")
                hour, minute = map(int, block.start.split(":"))
                start = hour * 60 + minute
                if not span_fits_day(start, block.duration_min):
                    raise ValueError("block must fit between 00:00 and 24:00")
            for bound in (block.earliest, block.latest):
                if bound and not re.fullmatch(
                    r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) )?"
                    r"(?:[01]\d|2[0-3]):[0-5]\d",
                    bound,
                ):
                    raise ValueError("invalid deadline or earliest time")
        if any(block.pomodoro_parent_id in ids for block in blocks if block.pomodoro_parent_id):
            raise ValueError("a pomodoro parent cannot be stored with the chunks split from it")
        return blocks


class GridWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: list[int] = Field(min_length=1, max_length=7)
    start: str = Field(min_length=5, max_length=5)
    duration_min: int = Field(le=7140)

    @field_validator("days")
    @classmethod
    def days_in_week(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value) or any(day < 0 or day > 6 for day in value):
            raise ValueError("days must be unique values in 0..6")
        return value

    @field_validator("start")
    @classmethod
    def start_is_on_the_grid(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("start must be HH:MM")
        hour, minute = map(int, value.split(":"))
        start = hour * 60 + minute
        if not (start_fits_day(start) and on_slot(start)):
            raise ValueError("start must be on the 00:00–24:00 grid")
        return value

    @field_validator("duration_min")
    @classmethod
    def duration_is_slot_aligned(cls, value: int) -> int:
        if value <= 0 or not on_slot(value):
            raise ValueError("duration_min must be a positive multiple of 15")
        return value

    @model_validator(mode="after")
    def window_fits_the_grid(self) -> GridWindow:
        hour, minute = map(int, self.start.split(":"))
        start = hour * 60 + minute
        if not span_fits_day(start, self.duration_min):
            raise ValueError("window must fit the 00:00–24:00 grid")
        return self


class StudyWindow(GridWindow):
    """A preferred study time. With a subject, it is preferred for that subject's homework only."""

    subject: str | None = Field(
        default=None, min_length=1, max_length=40, exclude_if=lambda value: value is None
    )

    @field_validator("subject")
    @classmethod
    def subject_is_trimmed(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("subject must not be blank")
        return trimmed


class ProtectedWindow(GridWindow):
    kind: Literal["downtime", "commute", "meal"]


class SpreadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_min: int = Field(ge=15, le=180)
    from_date: str

    @field_validator("session_min")
    @classmethod
    def session_is_slot_aligned(cls, value: int) -> int:
        if value % 15 != 0:
            raise ValueError("session_min must be a multiple of 15")
        return value

    @field_validator("from_date")
    @classmethod
    def from_date_is_calendar_day(cls, value: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("from_date must be YYYY-MM-DD")
        day = date.fromisoformat(value)
        if not FIRST_DAY <= day <= LAST_DAY:
            raise ValueError("from_date must be between 2000-01-01 and 2099-12-31")
        return value


class RecoveryRequest(BaseModel):
    missed_block_id: str = Field(min_length=1, max_length=80)
    missed_day: int = Field(ge=0, le=6)
    previous_placed: list[TimeBlock] = Field(max_length=100)

    @field_validator("previous_placed")
    @classmethod
    def previous_ids_are_unique(cls, blocks: list[TimeBlock]) -> list[TimeBlock]:
        if len({block.id for block in blocks}) != len(blocks):
            raise ValueError("previous placement ids must be unique")
        return blocks


class RunningLateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: int = Field(ge=0, le=6)
    minutes: Literal[15, 30, 60]
    from_start: str = Field(min_length=5, max_length=5)
    previous_placed: list[TimeBlock] = Field(max_length=100)

    @field_validator("from_start")
    @classmethod
    def from_start_is_on_the_grid(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("from_start must be HH:MM")
        hour, minute = map(int, value.split(":"))
        start = hour * 60 + minute
        if not (start_fits_day(start) and on_slot(start)):
            raise ValueError("from_start must be on the 00:00–24:00 grid")
        return value

    @field_validator("previous_placed")
    @classmethod
    def previous_ids_are_unique(cls, blocks: list[TimeBlock]) -> list[TimeBlock]:
        if len({block.id for block in blocks}) != len(blocks):
            raise ValueError("previous placement ids must be unique")
        return blocks


class SolveRequest(WeekRequest):
    recover: RecoveryRequest | None = None
    running_late: RunningLateRequest | None = None
    week_start: str | None = None

    @field_validator("week_start")
    @classmethod
    def week_start_is_a_monday(cls, value: str | None) -> str | None:
        if value is not None and not is_week_start(value):
            raise ValueError("week_start must be a Monday from 2000-01-03 through 2099-12-28, or 1999-12-27")
        return value

    @model_validator(mode="after")
    def missed_occurrence_exists(self) -> SolveRequest:
        if self.week_start is None and any(block.assignment_id for block in self.blocks):
            raise ValueError("week_start is required when a block has assignment_id")
        if self.recover is not None and self.running_late is not None:
            raise ValueError("recover and running_late cannot both be set")
        if self.recover is None:
            return self
        matches = [block for block in self.blocks if block.id == self.recover.missed_block_id]
        if (
            not matches
            or matches[0].kind != "locked"
            or self.recover.missed_day not in matches[0].days
            or self.recover.missed_day in matches[0].missed_days
        ):
            raise ValueError("missed occurrence must identify a locked block on that day")
        return self
