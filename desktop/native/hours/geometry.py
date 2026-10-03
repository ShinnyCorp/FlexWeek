"""Where minutes are: the geometry every design's hours share.

A track is one day's stretch of time inside a painted widget, between the minutes at its two ends.
Most are straight (`LinearTrack`): a rectangle, which way time runs, and a turn for a card laid at an
angle. My day's dial is round (`DialTrack`). A widget can hold several tracks (a week of columns, a
day cut into tiles). The hand needs only what `Track` names, so it treats every shape alike.
Everything here is plain arithmetic on Qt's point and rectangle types, so it is tested with numbers
and knows nothing about gestures or painting.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QTransform

from backend.slots import DAY_END_MIN, DAY_START_MIN, SLOT_MIN

FIRST, LAST = DAY_START_MIN, DAY_END_MIN
# The minutes a student can have a drag move by; the first is what an account starts with.
DRAG_STEPS = (5, 15)
# Space between blocks that share a time, and between a block and its track's sides.
GAP = 2.0
# Space between a block and the next one back to back with it.
BETWEEN = 3.0


class Axis(Enum):
    DOWN = "down"
    ACROSS = "across"


@dataclass(frozen=True)
class Span:
    day: int
    start: int
    end: int

    @property
    def minutes(self) -> int:
        return self.end - self.start


def snap(minute: float, step: int) -> int:
    return round(minute / step) * step


def next_slot(minute: int, first: int = FIRST, last: int = LAST - SLOT_MIN) -> tuple[int, int]:
    """Where a new thing starts when asked for at `minute`: (days ahead, minute) of the next quarter hour,
    now rounded up, kept between `first` and `last`. With none left today, the first one tomorrow."""
    slot = max(-(-minute // SLOT_MIN) * SLOT_MIN, first)
    return (0, slot) if slot <= last else (1, first)


def drag_step(chosen: object) -> int:
    """The step a preference names, or the first one for anything else."""
    return chosen if isinstance(chosen, int) and chosen in DRAG_STEPS else DRAG_STEPS[0]


class Track(Protocol):
    """One day's minutes on a surface, whatever its shape. Minutes run from `first` to `last`, and a
    block on the track lies wholly between them."""

    @property
    def day(self) -> int: ...

    @property
    def first(self) -> int: ...

    @property
    def last(self) -> int: ...

    def minute_at(self, point: QPointF) -> float:
        """The minute under a point, past either end too."""
        ...

    def contains(self, point: QPointF) -> bool: ...

    def point_for(self, minute: int) -> QPointF:
        """A point on the track at a minute, in the owning widget's coordinates."""
        ...


@dataclass(frozen=True)
class LinearTrack:
    """A day's minutes laid along a straight line: down a column or across a lane.

    `area` is where the track lies before it is turned; `turn` is degrees clockwise about the area's
    centre, for a card laid at an angle. Points in and out are in the owning widget's coordinates.
    """

    day: int
    area: QRectF
    axis: Axis = Axis.DOWN
    first: int = FIRST
    last: int = LAST
    turn: float = 0.0
    _into: QTransform = field(init=False, repr=False, compare=False)
    _back: QTransform = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        centre = self.area.center()
        into = QTransform()
        into.translate(centre.x(), centre.y())
        into.rotate(self.turn)
        into.translate(-centre.x(), -centre.y())
        object.__setattr__(self, "_into", into)
        object.__setattr__(self, "_back", into.inverted()[0])

    @property
    def transform(self) -> QTransform:
        """From the track's own upright frame to the widget: what a painter sets to draw on it."""
        return self._into

    @property
    def length(self) -> float:
        return self.area.height() if self.axis is Axis.DOWN else self.area.width()

    def per_minute(self) -> float:
        return self.length / (self.last - self.first)

    def upright(self, point: QPointF) -> QPointF:
        return self._back.map(point)

    def minute_at(self, point: QPointF) -> float:
        """The minute under a point, past either end too: a drag that leaves the track keeps a time."""
        local = self.upright(point)
        along = local.y() - self.area.top() if self.axis is Axis.DOWN else local.x() - self.area.left()
        return self.first + along / self.per_minute()

    def contains(self, point: QPointF) -> bool:
        return self.area.contains(self.upright(point))

    def offset(self, minute: float) -> float:
        """How far along the track, from its start edge, a minute lies."""
        return (minute - self.first) * self.per_minute()

    def rect_for(self, start: int, end: int, column: int = 0, columns: int = 1) -> QRectF:
        """Where a span is drawn, in the track's upright frame, as one of `columns` side by side. A
        pixel in from its start and two from its end, so two blocks back to back are three apart and
        never read as one (decision 14 of 0.17)."""
        start, end = max(start, self.first), min(end, self.last)
        if self.axis is Axis.DOWN:
            width = (self.area.width() - 2 * GAP) / columns
            return QRectF(
                self.area.left() + GAP + column * width,
                self.area.top() + self.offset(start) + 1,
                width - GAP,
                max(self.offset(end) - self.offset(start) - BETWEEN, 4.0),
            )
        height = (self.area.height() - 2 * GAP) / columns
        return QRectF(
            self.area.left() + self.offset(start) + 1,
            self.area.top() + GAP + column * height,
            max(self.offset(end) - self.offset(start) - BETWEEN, 4.0),
            height - GAP,
        )

    def point_for(self, minute: int) -> QPointF:
        """The middle of the track at a minute, in the widget's coordinates."""
        if self.axis is Axis.DOWN:
            upright = QPointF(self.area.center().x(), self.area.top() + self.offset(minute))
        else:
            upright = QPointF(self.area.left() + self.offset(minute), self.area.center().y())
        return self._into.map(upright)


@dataclass(frozen=True)
class DialTrack:
    """A day's minutes round a ring, as My day's dial draws them: `sweep` degrees centred on the top
    of the face, clockwise from `first` to `last`, between `inner` and `outer` radius about `centre`.
    The gap at the bottom belongs to no time."""

    day: int
    centre: QPointF
    inner: float
    outer: float
    first: int = FIRST
    last: int = LAST
    sweep: float = 300.0

    def turn_at(self, point: QPointF) -> float:
        """Degrees clockwise from the top of the face."""
        return math.degrees(math.atan2(point.x() - self.centre.x(), -(point.y() - self.centre.y())))

    def minute_at(self, point: QPointF) -> float:
        half = self.sweep / 2
        turn = min(max(self.turn_at(point), -half), half)
        return self.first + (turn + half) / self.sweep * (self.last - self.first)

    def contains(self, point: QPointF) -> bool:
        reach = math.hypot(point.x() - self.centre.x(), point.y() - self.centre.y())
        return self.inner <= reach <= self.outer and abs(self.turn_at(point)) <= self.sweep / 2

    def point_for(self, minute: int) -> QPointF:
        share = (min(max(minute, self.first), self.last) - self.first) / (self.last - self.first)
        turn = math.radians(-self.sweep / 2 + share * self.sweep)
        radius = (self.inner + self.outer) / 2
        return QPointF(self.centre.x() + radius * math.sin(turn), self.centre.y() - radius * math.cos(turn))


def overlap_columns(spans: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Side by side for spans that overlap: each one's column and how many share its time, in the
    order given. Daily Scheduler's assign_overlap_cols. By position, not by value, since a repeating
    block dragged onto another of its days can be two equal spans."""
    order = sorted(range(len(spans)), key=lambda at: spans[at])
    ends: list[int] = []
    column = [0] * len(spans)
    for at in order:
        start = spans[at][0]
        free = next((index for index, end in enumerate(ends) if end <= start), len(ends))
        if free == len(ends):
            ends.append(0)
        ends[free] = spans[at][1]
        column[at] = free
    return [
        (
            column[at],
            max(column[other] for other, (s, e) in enumerate(spans) if s < end and start < e) + 1,
        )
        for at, (start, end) in enumerate(spans)
    ]
