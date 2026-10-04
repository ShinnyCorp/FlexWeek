"""Mission control: the week as an ops board (0.17's Ops board).

Four figures across the top say how today and the week stand: homework planned today, homework due
this week, the free time left today and the minutes of focus. Under them the days are lanes of hours
across the window, with a deadline table on the right, the soonest due first: what each homework
needs, how much of it is placed, where, and the time left. Day is the day as one wide lane, with
what is still to come today and the free time left beside it. Figures are in JetBrains Mono and
words in the look's own face (the catalogue's Data-Dense Dashboard).

The lanes are the shared hours, on the window's hand. A homework not placed yet is picked up from its
row in the table and dropped on a lane.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from functools import partial

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QHelpEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from backend.models import due_sort_key
from desktop.native import icons
from desktop.native.calendar import DAY_FULL, DAYS, category_icon
from desktop.native.fonts import at_scale
from desktop.native.hours.canvas import (
    BOOK,
    HOMEWORK_CATEGORIES,
    NOW_CLEAR,
    TEXT_LEFT,
    TEXT_RIGHT,
    TEXT_TOP,
    TODAY_WASH,
    BlockPainter,
    Drawn,
    HoursCanvas,
    block_layout,
)
from desktop.native.hours.chips import TrayChip
from desktop.native.hours.geometry import Axis, LinearTrack, overlap_columns
from desktop.native.hours.hand import Hand
from desktop.native.hours.zoom import HoursScroll, Scale
from desktop.native.layouts.base import (
    LayoutView,
    Scene,
    base_sheet,
    css,
    empty,
    family,
    free_stretches,
    label,
    plural,
    rules,
    scrolling,
)
from desktop.native.layouts.dial import EVENING
from desktop.native.look import FONT_FAMILIES, category_paint
from desktop.native.tokens import (
    RADIUS_CARD,
    RADIUS_CONTROL,
    WEIGHT_NUMBER,
    WEIGHT_REGULAR,
    WEIGHT_STRONG,
    mix_oklab,
    type_pt,
)
from desktop.native.weekmodel import (
    LEFTOVER,
    Occurrence,
    Waiting,
    WeekModel,
    clock_label,
    length_label,
    range_label,
)
from desktop.native.widgets import FittedLabel, overlay_scroll_bars

# The mock-up draws 08:00 to 22:00 across its lanes, 56 pixels an hour at 1280 wide.
WEEK_SCALE = Scale("mission.week", (40, 56, 72, 96, 120), 56)
DAY_SCALE = Scale("mission.day", (40, 56, 72, 96, 120), 56)
# The row of hours over the lanes, and room before 00:00 and after 24:00 for their labels.
AXIS = 30
LEAD = TAIL = 20
# Between lanes; and from a lane's edge to its blocks, top and bottom (less the track's own 2).
GAP = 5
WEEK_INSET, DAY_INSET = (5, 3), (8, 6)
# The mock-up's measures at Normal text: the day names, a lane the least it may be, Day's one lane,
# the deadline table and the room round everything.
NAMES = 64
LANE_LEAST = 36
# A lane when the table is under the lanes, where the page scrolls anyway.
LANE_UNDER = 52
DAY_LANE, DAY_LEAST = 296, 140
TABLE = 364
AROUND = 16
# The focus figure's line while a timer runs: the minutes it shows are only those already credited.
FOCUS_NOW = {"focusing": "Focusing now", "paused": "Focus paused", "break": "On a break"}
# Minutes kept after the last block, so its end and the hour label there show whole.
END_ROOM = 30
# Clear space kept between the now pill and an hour label beside it.
LABEL_CLEAR = 4
# A block narrower than this is a tick in its category's colour, named on hover.
MIN_BAR = 8
# Hours of lanes the table leaves at the least before it goes under them.
BESIDE_HOURS = 8
MONO = [face.strip() for face in FONT_FAMILIES["mono"].split(",")]


def mono(base: QFont) -> QFont:
    """`base` in JetBrains Mono, the face every figure is in."""
    made = QFont(base)
    made.setFamilies(MONO)
    return made


def clock_length(minutes: int) -> str:
    """A length as the table writes it: "1:30"."""
    hours, rest = divmod(max(minutes, 0), 60)
    return f"{hours}:{rest:02d}"


def left_words(minutes: int) -> str:
    """The time left before a deadline: "3 d 8 h", "8 h", "40 min"."""
    days, rest = divmod(minutes, 24 * 60)
    hours = rest // 60
    if days:
        return f"{days} d {hours} h" if hours else f"{days} d"
    return f"{hours} h" if hours else f"{rest} min"


def names_of(titles: Sequence[str]) -> str:
    """ "Science poster", "Science poster and Spanish vocab", "A, B and C", "A, B and 3 more"."""
    if len(titles) <= 2:
        return " and ".join(titles)
    if len(titles) == 3:
        return f"{titles[0]}, {titles[1]} and {titles[2]}"
    return f"{titles[0]}, {titles[1]} and {len(titles) - 2} more"


@dataclass(frozen=True)
class Homework:
    """A homework as the week holds it: its sessions this week, how many minutes of them have a time,
    where the first of those is, and the ones still waiting for a time."""

    title: str
    due: str | None
    needs: int
    placed: int
    first: tuple[int, int] | None
    waiting: tuple[Waiting, ...]
    done: bool


def week_homework(week: WeekModel) -> list[Homework]:
    """This week's homework, the soonest due first; with one deadline, what waits for a time first,
    then the longest. A homework is its sessions together, or a session with none."""
    found: dict[str, list[Occurrence | Waiting]] = {}
    for entry in (*(item for item in week.occurrences if item.work), *week.waiting):
        found.setdefault(entry.assignment_id or entry.block_id, []).append(entry)
    made = []
    for parts in found.values():
        placed = [part for part in parts if isinstance(part, Occurrence)]
        waiting = tuple(part for part in parts if isinstance(part, Waiting))
        first = min(((part.day, part.start) for part in placed), default=None)
        made.append(
            Homework(
                parts[0].title,
                parts[0].due,
                sum(part.minutes for part in parts),
                sum(part.minutes for part in placed),
                first,
                waiting,
                not waiting and all(part.done for part in placed),
            )
        )
    return sorted(made, key=lambda item: (due_sort_key(item.due), item.placed > 0, -item.needs))


def minutes_left(week: WeekModel, today: int | None, minute: int, due: str | None) -> int | None:
    """Minutes from now until `due`, or None with no deadline or no today in this week to count from."""
    if today is None or not due:
        return None
    day, at = due_sort_key(due)[:2]
    return (day - week.date_of(today)).days * 24 * 60 + at - minute


def _paint(tokens: dict[str, str], category: str) -> tuple[str, str]:
    """A category's fill and mark in the one family, on this design's cards."""
    fill, mark = category_paint(category, {"family": family(tokens), "panel": tokens["surface"]})
    return fill or tokens["surface"], mark or tokens["line"]


def _rows(week: WeekModel, days: tuple[int, ...]) -> tuple[int, ...]:
    """The most blocks each day's lane holds side by side, where blocks share their time."""
    return tuple(
        max((count for _, count in overlap_columns([(item.start, item.end) for item in week.on_day(day)])),
            default=1)
        for day in days
    )


def _lanes(
    days: tuple[int, ...], rows: tuple[int, ...], inset: tuple[int, int], area: QRectF
) -> list[LinearTrack]:
    """A lane per day down the canvas, `GAP` apart, with time across from `LEAD` in to `TAIL` short of
    its right edge, and a lane's room for each of `rows`: blocks that share their time sit side by
    side, each as tall as a block alone. A track lies `inset` inside its lane, so a block sits clear of
    the lane's edge."""
    unit = (area.height() - GAP * (len(days) - 1)) / sum(rows)
    tracks = []
    top = area.top()
    for day, count in zip(days, rows, strict=True):
        lane = QRectF(area.left() + LEAD, top, area.width() - LEAD - TAIL, unit * count)
        tracks.append(LinearTrack(day, lane.adjusted(0, inset[0], 0, -inset[1]), Axis.ACROSS))
        top = lane.bottom() + GAP
    return tracks


def _length(px: int) -> int:
    return 24 * px + LEAD + TAIL


def lanes_end(items: Sequence[Occurrence], now: int | None = None) -> int:
    """The minute the lanes open with at their right edge: 22:00, or the end of the last block or now
    if that is later, so the evening shows, a name is not cut off at the edge and now is not past it."""
    later = [now] if now is not None else []
    return min(max([EVENING, *(item.end for item in items), *later]) + END_ROOM, 24 * 60)


class MissionPainter(BlockPainter):
    """Lanes as cards with a rule at each hour, today's washed and edged in the accent. Blocks are the
    category's fill with its mark down the start edge; one too narrow for a bar is a tick. A block
    shows as much of itself as it can without cutting a word; a name that cannot fit goes beside the
    block where the lane is free, then its first word, then its colour alone. The hours are named
    every other hour over the first lane, and the time now is a pill there, a faint line down every
    lane and a strong one down today's."""

    def __init__(self, tokens: dict[str, str], *, day: bool = False) -> None:
        soft = mix_oklab(tokens["line"], tokens["surface"], 0.5)
        super().__init__(
            {
                "window": tokens["bg"],
                "hairline": soft,
                "rule": mix_oklab(tokens["text"], tokens["surface"], 0.07),
                "accent": tokens["accent"],
                "accent_ink": tokens["accent_ink"],
                "accent_text": tokens.get("accent_text", tokens["accent"]),
                "now": tokens.get("now", tokens["accent"]),
                "selection": tokens.get("selection", tokens["accent"]),
                "error": tokens["danger"],
                "text": tokens["text"],
                "muted": tokens["muted"],
                "block_edge": tokens["block_edge"],
            }
        )
        self.tokens = tokens
        self.day = day
        self.inset = DAY_INSET if day else WEEK_INSET
        # Per day, set by the canvas before it paints: the lane's two ends and what takes room on it,
        # blocks and the names already written beside them.
        self.taken: dict[int, tuple[float, float, list[QRectF]]] = {}

    def lane(self, track: LinearTrack) -> QRectF:
        return track.area.adjusted(0, -self.inset[0], 0, self.inset[1])

    def fonts(self, base: QFont) -> tuple[QFont, QFont]:
        title, small = super().fonts(base)
        return title, mono(small)

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        lane = self.lane(track)
        # Day's one lane is today's when now is on it; the canvas marks today only among several.
        today = today or (self.day and self.now_minute is not None)
        card = self.tokens["surface"]
        edge = self.c("hairline")
        if today:
            card = mix_oklab(self.tokens["text"], card, TODAY_WASH)
            edge = QColor(mix_oklab(self.tokens["accent"], edge.name(), 0.45))
        painter.setPen(QPen(edge, 1))
        painter.setBrush(QColor(card))
        painter.drawRoundedRect(lane.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS_CONTROL, RADIUS_CONTROL)
        painter.setPen(QPen(self.c("rule"), 1))
        for minute in range(-(-track.first // 60) * 60, track.last + 1, 60):
            at = track.area.left() + track.offset(minute)
            if lane.left() + 1 < at < lane.right() - 1:
                painter.drawLine(QPointF(at, lane.top() + 1), QPointF(at, lane.bottom() - 1))
        if self.now_minute is not None and not self.day:
            faint = self.c("accent")
            faint.setAlphaF(0.45)
            at = track.area.left() + track.offset(self.now_minute)
            painter.setPen(QPen(faint, 1))
            painter.drawLine(QPointF(at, lane.top() - GAP / 2), QPointF(at, lane.bottom() + GAP / 2))

    def hour_labels(
        self,
        painter: QPainter,
        track: LinearTrack,
        room: float,
        every: int = 60,
        visible: QRectF | None = None,
    ) -> None:
        """Every other hour over the first lane, and the time now on a pill in their row, any hour
        the pill would cover left out. A label cut by the edge of what shows is moved inside it."""
        font = mono(at_scale(painter.font(), "caption", self.scale(painter.font())))
        metrics = QFontMetricsF(font)
        base = self.lane(track).top() - 6
        now = self.now_minute
        pill = None
        if now is not None:
            strong = mono(at_scale(font, "caption", self.scale(font), WEIGHT_STRONG))
            strong_metrics = QFontMetricsF(strong)
            wide = strong_metrics.horizontalAdvance(clock_label(now)) + 12
            tall = strong_metrics.height() + 4
            pill = QRectF(track.area.left() + track.offset(now) - wide / 2, base + 2 - tall, wide, tall)
        painter.setFont(font)
        painter.setPen(self.c("muted"))
        # Every other hour, or every fourth or sixth or twelfth when 12-hour words would run together.
        widest = max(metrics.horizontalAdvance(clock_label(minute)) for minute in (0, 12 * 60))
        room = widest + LABEL_CLEAR
        step = next((span for span in (120, 240, 360) if track.offset(span) - track.offset(0) >= room), 720)
        written: list[tuple[QRectF, str, bool, int]] = []
        for minute in range(-(-track.first // step) * step, track.last + 1, step):
            words = clock_label(minute)
            wide = metrics.horizontalAdvance(words) + 2
            box = QRectF(track.area.left() + track.offset(minute) - wide / 2, base - metrics.height(), wide,
                         metrics.height())
            moved = False
            if visible is not None and box.right() > visible.left() and box.left() < visible.right():
                least = track.area.left() + LEAD
                inside = max(min(box.left(), visible.right() - wide), visible.left(), least)
                moved = inside != box.left()
                box.moveLeft(inside)
            if pill is None or not box.intersects(pill.adjusted(-LABEL_CLEAR, 0, LABEL_CLEAR, 0)):
                written.append((box, words, moved, minute))
        # 00:00 is moved in from the left of the lanes. It used to give way to the next hour and
        # disappear; it stays, and that neighbour gives way instead.
        draw = [(box, words) for box, words, _moved, minute in written if minute == 0]
        for box, words, moved, minute in written:
            if minute == 0:
                continue
            pad = LABEL_CLEAR
            hits_kept = any(box.intersects(other.adjusted(-pad, 0, pad, 0)) for other, _words in draw)
            hits_any = any(
                box.intersects(other.adjusted(-pad, 0, pad, 0))
                for other, _words, _moved, other_minute in written
                if other_minute != minute
            )
            if hits_kept or (moved and hits_any):
                continue
            draw.append((box, words))
        for box, words in draw:
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, words)
        if pill is None:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.c("accent"))
        painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        painter.setPen(self.c("accent_ink"))
        painter.setFont(strong)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, clock_label(now))

    def now(self, painter: QPainter, track: LinearTrack, minute: int) -> None:
        lane = self.lane(track)
        at = track.area.left() + track.offset(minute)
        painter.setPen(QPen(self.c("now"), 2))
        painter.drawLine(QPointF(at, lane.top() - 1), QPointF(at, lane.bottom() + 1))

    def fills(self, drawn: Drawn) -> tuple[QColor, QColor, QColor | None, QColor | None]:
        fill, mark = _paint(self.tokens, drawn.category)
        if drawn.done or drawn.missed:
            paper, muted = QColor(self.tokens["surface"]), QColor(self.tokens["muted"])
            return paper, muted, self.c("hairline"), QColor(mark)
        return QColor(fill), QColor(self.tokens["text"]), None, QColor(mark)

    def _tick(self, rect: QRectF, drawn: Drawn) -> bool:
        return not drawn.held and rect.width() < MIN_BAR

    def block(self, painter: QPainter, rect: QRectF, drawn: Drawn, visible: QRectF) -> None:
        if not self._tick(rect, drawn):
            super().block(painter, rect, drawn, visible)
            return
        mark = QColor(_paint(self.tokens, drawn.category)[1])
        if drawn.done or drawn.missed:
            mark = QColor(mix_oklab(mark.name(), self.tokens["surface"], 0.45))
        top = rect.top() + 8
        icon_paint = None
        if category_icon(drawn.category) is not None:
            size = round(QFontMetricsF(self.fonts(painter.font())[0]).ascent())
            fill, ink, _outline, edge = self.fills(drawn)
            colour = self._book_colour(drawn, ink, fill, edge) or ink
            at = QPointF(rect.center().x() - size / 2, top)
            icon_box = QRectF(at.x(), at.y(), size, size)
            pad = NOW_CLEAR + 3
            backdrop = icon_box.adjusted(-pad, -pad, pad, pad)
            if self.now_track is not None:
                card = QColor(mix_oklab(self.tokens["text"], self.tokens["surface"], TODAY_WASH))
                painter.fillRect(backdrop, card)
            icon_paint = (at, size, colour, category_icon(drawn.category) or BOOK)
            top += size + 3
        bar = QRectF(rect.center().x() - 3, top, 6, max(rect.bottom() - 8 - top, 6))
        if drawn.chosen:
            painter.setPen(QPen(self.c("selection"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(bar.adjusted(-4, -4, 4, 4), RADIUS_CONTROL, RADIUS_CONTROL)
        shape = QPainterPath()
        shape.addRoundedRect(bar, 3, 3)
        painter.fillPath(shape, mark)
        self.crossing(painter, bar, [])
        if icon_paint is not None:
            at, size, colour, name = icon_paint
            self._book(painter, at, size, colour, name)

    def words(
        self,
        painter: QPainter,
        rect: QRectF,
        drawn: Drawn,
        ink: QColor,
        visible: QRectF,
        fill: QColor | None = None,
        edge: QColor | None = None,
    ) -> list[QRectF]:
        if (drawn.held or not self._tick(rect, drawn)) and (
            drawn.held or self._whole(painter.font(), rect, drawn, visible)
        ):
            return super().words(painter, rect, drawn, ink, visible, fill, edge)
        beside = self._beside(painter, rect, drawn, visible)
        if beside:
            return [*beside, *self._bare(painter, rect, drawn, ink, fill, edge)]
        first = replace(drawn, title=drawn.title.split()[0] if drawn.title.split() else drawn.title)
        if self._whole(painter.font(), rect, first, visible):
            return super().words(painter, rect, first, ink, visible, fill, edge)
        return self._bare(painter, rect, drawn, ink, fill, edge)

    def _whole(self, font: QFont, rect: QRectF, drawn: Drawn, visible: QRectF) -> bool:
        """Whether the block says something with no word cut, as `words` would lay it out."""
        title, small = self.fonts(font)
        left = rect.left() + TEXT_LEFT
        if rect.right() - visible.left() > 2 * QFontMetricsF(title).lineSpacing():
            left = max(left, visible.left() + TEXT_TOP)
        room = QRectF(
            QPointF(left, rect.top() + TEXT_TOP), QPointF(rect.right() - TEXT_RIGHT, rect.bottom() - 1)
        )
        tight = QRectF(room.left(), rect.top(), room.width(), rect.height())
        shown = (self.measures["show_times"], self.measures["show_lengths"])
        book = category_icon(drawn.category) is not None
        lay = block_layout(drawn, title, small, room, tight=tight, book=book, shown=shown)
        return bool(lay) and not any(line.text.endswith("…") for line in lay)

    def _bare(
        self,
        painter: QPainter,
        rect: QRectF,
        drawn: Drawn,
        ink: QColor,
        fill: QColor | None,
        edge: QColor | None,
    ) -> list[QRectF]:
        """No words: the category keeps its icon at the top of the block."""
        if category_icon(drawn.category) is None:
            return []
        size = round(QFontMetricsF(self.fonts(painter.font())[0]).ascent())
        if rect.width() < size + 4:
            return []
        colour = self._book_colour(drawn, ink, fill or self.c("window"), edge)
        at = QPointF(rect.center().x() - size / 2 + 1, rect.top() + 7)
        return [self._book(painter, at, size, colour or ink, category_icon(drawn.category) or BOOK)]

    def _book(self, painter: QPainter, at: QPointF, size: int, colour: QColor,
              icon_name: str = BOOK) -> QRectF:
        """Draws the icon and returns where."""
        ratio = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
        painter.drawPixmap(at, icons.pixmap(icon_name, colour.name(), size, ratio))
        return QRectF(at.x(), at.y(), size, size)

    def _beside(self, painter: QPainter, rect: QRectF, drawn: Drawn, visible: QRectF) -> list[QRectF]:
        """The name, and its start if there is room, written beside the block where its row of the
        lane is free, as a Gantt chart labels a short bar: after it, else before it. On up to two
        lines, with no word broken, and clear of the lane's edges and of the edges of what shows."""
        found = self.taken.get(drawn.span.day)
        if found is None:
            return []
        first, last, taken = found
        first, last = max(first, visible.left()), min(last, visible.right())
        title, small = self.fonts(painter.font())
        tm, sm = QFontMetricsF(title), QFontMetricsF(small)
        row = [box for box in taken if box.top() < rect.bottom() and box.bottom() > rect.top()]
        ends = rect.left(), rect.right()
        after = min([max(box.left(), ends[1]) for box in row if box.right() > ends[1] + 0.5] + [last])
        before = max([min(box.right(), ends[0]) for box in row if box.left() < ends[0] - 0.5] + [first])
        top = rect.top() + 2
        room = rect.bottom() + sm.lineSpacing() - top
        start = clock_label(drawn.span.start)
        for with_time in (True, False):
            for right in (True, False):
                free = (after - rect.right() if right else rect.left() - before) - 10
                lines = _whole_lines(drawn.title, tm, free)
                if not lines or (with_time and sm.horizontalAdvance(start) > free):
                    continue
                tall = len(lines) * tm.lineSpacing() + (sm.lineSpacing() if with_time else 0)
                if tall > room:
                    continue
                wide = max([tm.horizontalAdvance(line) for line in lines]
                           + ([sm.horizontalAdvance(start)] if with_time else []))
                left = rect.right() + 5 if right else rect.left() - 5 - wide
                align = Qt.AlignmentFlag.AlignLeft if right else Qt.AlignmentFlag.AlignRight
                painter.setPen(self.c("text"))
                painter.setFont(title)
                written: list[QRectF] = []
                for at, line in enumerate(lines):
                    box = QRectF(left, top + at * tm.lineSpacing(), wide, tm.height())
                    painter.drawText(box, align | Qt.AlignmentFlag.AlignTop, line)
                    written.append(box)
                if with_time:
                    painter.setPen(self.c("muted"))
                    painter.setFont(small)
                    box = QRectF(left, top + len(lines) * tm.lineSpacing(), wide, sm.height())
                    painter.drawText(box, align | Qt.AlignmentFlag.AlignTop, start)
                    written.append(box)
                taken.append(QRectF(left - 5, rect.top(), wide + 10, rect.height()))
                return written
        return []


def _whole_lines(text: str, metrics: QFontMetricsF, width: float, most: int = 2) -> list[str]:
    """`text` in at most `most` lines of `width` with no word broken, or none if it will not go."""
    lines: list[str] = []
    for word in text.split():
        if metrics.horizontalAdvance(word) > width:
            return []
        if lines and metrics.horizontalAdvance(f"{lines[-1]} {word}") <= width:
            lines[-1] += f" {word}"
        else:
            lines.append(word)
    return lines if len(lines) <= most else []


class MissionCanvas(HoursCanvas):
    """Lanes whose day names belong to the scroll's side strip. A block's name and times come up on
    hover, which is how a tick is named."""

    def __init__(
        self, hand: Hand, painter: MissionPainter, lay_out: Callable[[QRectF], list[LinearTrack]]
    ) -> None:
        super().__init__(hand, painter, lay_out, header=AXIS)
        self.names: dict[int, DayName] = {}

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if isinstance(self.painter, MissionPainter):
            self.painter.taken = {
                track.day: (
                    track.area.left(),
                    track.area.right(),
                    [rect for drawn, rect in self.drawn(track) if not drawn.held],
                )
                for track in self.tracks
            }
        super().paintEvent(event)

    def day_name(self, day: int) -> QPoint:
        name = self.names.get(day)
        if name is None or not name.isVisible():
            return super().day_name(day)
        return name.mapToGlobal(name.rect().center())

    def event(self, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent):
            hit = self._block_at(QPointF(event.pos()))
            if hit is not None:
                QToolTip.showText(event.globalPos(), f"{hit[0].title}\n{hit[0].detail}", self)
                return True
        return super().event(event)

    def reveal(self, day: int, first: int, last: int) -> None:
        """Bring the stretch on screen in the lanes, with room beyond its last minute so a held block
        does not start them scrolling, and then in the page, which scrolls in a short window."""
        area = self._scroll_area()
        track = self.track_for(day, first) or self.track_for(day)
        if area is None or track is None:
            return
        for minute in (last, first):
            local = track.point_for(min(max(minute, track.first), track.last)).toPoint()
            area.ensureVisible(local.x(), local.y(), 60, 20)
        page = _page_of(area)
        if page is not None:
            inside = self.mapTo(page.widget(), track.point_for(first).toPoint())
            page.ensureVisible(inside.x(), inside.y(), 20, round(track.area.height()))

    def in_view(self, day: int, minute: int) -> bool:
        if not super().in_view(day, minute):
            return False
        page = _page_of(self._scroll_area())
        track = self.track_for(day, minute)
        if page is None or track is None:
            return True
        port = page.viewport()
        at = self.mapTo(port, track.point_for(minute).toPoint())
        return port.rect().adjusted(-2, -2, 2, 2).contains(at)


def _page_of(widget: QWidget | None) -> QScrollArea | None:
    """The scroll area holding this one: the page the lanes sit on."""
    found = widget.parentWidget() if widget is not None else None
    while found is not None and not isinstance(found, QScrollArea):
        found = found.parentWidget()
    return found


class DayName(QPushButton):
    """A day's name beside its lane with its date under it, today's in an accent chip. On Week a
    click opens the day."""

    def __init__(self, day: int, name: str, opens: bool) -> None:
        super().__init__()
        self.day = day
        self.setObjectName(name)
        self.setProperty("kind", "name")
        # As tall as its lane, where a button would keep to the height of a line.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        column.addStretch(1)
        self.title = label(DAYS[day], "missionDayName")
        # Two labels shown in turn: Qt keeps a label's padding from its first styling.
        self.date = label("", "missionDate")
        self.chip = label("", "missionChip")
        for part in (self.title, self.date, self.chip):
            part.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            part.setIndent(0)
            column.addWidget(part, 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)
        self.setAccessibleName(f"Show {DAY_FULL[day]}" if opens else DAY_FULL[day])
        if opens:
            self.setProperty("day_target", day)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(f"Open {DAY_FULL[day]}")
        else:
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_date(self, number: int, today: bool) -> None:
        self.date.setText(str(number))
        self.chip.setText(str(number))
        self.date.setVisible(not today)
        self.chip.setVisible(today)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, 0)


class Wrapped(QLabel):
    """Words that wrap, whose least height is all their lines at the width they have. A wrapped label
    asks for one line, and a card squeezed in a short window cut the rest."""

    def __init__(self, text: str, name: str, rich: bool = False) -> None:
        super().__init__(text)
        self.setObjectName(name)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        tall = self.heightForWidth(self.width())
        if tall != self.minimumHeight():
            self.setMinimumHeight(tall)


class WholeRows(QWidget):
    """Rows one under another, as many as have room to show whole, in order. When some do not, the
    last row's room says "and N more", counting the row it replaces, so nothing is cut at the card's
    foot and the card says what it leaves out. Beside the lanes they ask for no more room than the
    first row, so the lanes, not the rows, set the page's height. Under the lanes, where the page
    scrolls, `every` row shows."""

    def __init__(self, rows: list[QWidget], name: str, every: bool) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setProperty("rows", True)
        self.rows = rows
        self.every = every
        self.more = QLabel()
        self.more.setObjectName("missionMore")
        self.more.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        for row in rows:
            column.addWidget(row)
        column.addWidget(self.more)
        column.addStretch(1)
        if not every:
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
            self.setMinimumHeight(self._tall(rows[0]) if rows else 0)
        self._show()

    def _tall(self, row: QWidget) -> int:
        tall = row.heightForWidth(self.width()) if row.hasHeightForWidth() else row.sizeHint().height()
        return min(max(tall, row.minimumHeight()), row.maximumHeight())

    def _show(self) -> None:
        """Every row if all have room, else the first that fit less the last of them, whose room
        goes to "and N more". The last row shown has no rule under it."""
        tall = [self._tall(row) for row in self.rows]
        fit = 0
        room = self.height()
        for height in tall:
            room -= height
            if room < 0:
                break
            fit += 1
        whole = self.every or fit == len(self.rows) or len(self.rows) < 2
        shown = len(self.rows) if whole else max(fit, 1) - 1
        for at, row in enumerate(self.rows):
            row.setVisible(at < shown)
        self.more.setVisible(not whole)
        if not whole:
            self.more.setText(f"and {len(self.rows) - shown} more")
            self.more.setFixedHeight(tall[shown])
        for at, row in enumerate(self.rows):
            last = whole and at == shown - 1
            if row.property("last") != last:
                row.setProperty("last", last)
                row.style().unpolish(row)
                row.style().polish(row)

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._show()


class Bar(QWidget):
    """A thin bar of how much of something there is: a hairline track and the accent over `share`."""

    def __init__(self, share: float, track: str, fill: str, tall: int) -> None:
        super().__init__()
        self.setObjectName("missionBar")
        self.share, self.track, self.fill = min(max(share, 0.0), 1.0), QColor(track), QColor(fill)
        self.setFixedHeight(tall)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.track)
        painter.fillRect(QRectF(0, 0, self.width() * self.share, self.height()), self.fill)
        painter.end()


class OpenChip(TrayChip):
    """A session of homework that has no time yet, as its row in the table says so: "Not placed
    yet", in the accent. Drag it onto a lane to give it a time; a click opens it."""

    def __init__(self, hand: Hand, waiting: Waiting, words: str) -> None:
        super().__init__(hand, waiting)
        self.setText(words)
        self.setProperty("kind", "open")

    def _fit(self) -> None:
        # Its words are always whole: they are short, and the title is in the row beside it.
        return

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 2, self.fontMetrics().height() + 2)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()


class Strip(QFrame):
    """The figures side by side while each has the room its words need, two over two when not."""

    def __init__(self, cards: list[QFrame], gap: int) -> None:
        super().__init__()
        self.setObjectName("missionStrip")
        # The width the page gives it, whatever its figures would like: side by side or two over two
        # follows from that.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.cards, self.gap = cards, gap
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(gap)
        self.across = 0
        self._place(len(cards))

    def _place(self, across: int) -> None:
        if across == self.across:
            return
        self.across = across
        for card in self.cards:
            self.grid.removeWidget(card)
        for at, card in enumerate(self.cards):
            self.grid.addWidget(card, at // across, at % across)
        for column in range(len(self.cards)):
            self.grid.setColumnStretch(column, 1 if column < across else 0)

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        count = len(self.cards)
        least = max(card.minimumSizeHint().width() for card in self.cards)
        self._place(count if self.width() >= least * count + self.gap * (count - 1) else 2)


class MissionView(LayoutView):
    layout_id = "mission"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        # A view's minimum height must not become the window's: inside a scroll area, what does not fit
        # scrolls and the window keeps its size.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._page = QWidget()
        self._page.setObjectName("missionPage")
        self._root = QVBoxLayout(self._page)
        outer.addWidget(scrolling(self._page, "missionScroll"))
        self._scrolls: dict[str, HoursScroll] = {}

    @property
    def cramped(self) -> bool:
        """Too narrow for the table beside the lanes. It holds the only handle on homework not placed
        yet, so it stays beside them, where it is seen whole in a short window, for as long as the
        lanes keep `BESIDE_HOURS` of the day."""
        scale = self._scene.scale if self._scene is not None else 1.0
        need = (TABLE + NAMES + 3 * AROUND) * scale + BESIDE_HOURS * WEEK_SCALE.default
        return 0 < self.width() < need

    def shown_day(self, scene: Scene) -> int:
        if scene.surface == "day" and scene.iso_day:
            for day in range(7):
                if scene.week.date_of(day).isoformat() == scene.iso_day:
                    return day
        return scene.today if scene.today is not None else 0

    def render(self, scene: Scene, week_changed: bool) -> None:
        px = scene.px
        self.setStyleSheet(self._sheet(scene))
        # The hours keep their place and zoom when the rest of the board is built again.
        for kept in self._scrolls.values():
            _detach(self._root, kept)
        empty(self._root)
        self._root.setContentsMargins(px(AROUND), px(4), px(AROUND), px(AROUND))
        self._root.setSpacing(px(12))
        is_day = scene.surface == "day"
        if scene.options.get("figures") != "hide":
            self._root.addWidget(self._strip(scene))
        main = QVBoxLayout()
        main.setSpacing(px(12))
        hours = self._hours(scene, "day" if is_day else "week")
        main.addWidget(hours, 3 if is_day else 1)
        if is_day:
            main.addLayout(self._day_cards(scene), 2)
        table = self._table(scene)
        if self.cramped:
            self._root.addLayout(main, 1)
            self._root.addWidget(table)
        else:
            body = QHBoxLayout()
            body.setSpacing(px(AROUND))
            body.addLayout(main, 1)
            table.setFixedWidth(px(TABLE))
            body.addWidget(table)
            self._root.addLayout(body, 1)
        for kept in self._scrolls.values():
            kept.setVisible(kept is hours)

    # The lanes

    def _hours(self, scene: Scene, key: str) -> HoursScroll:
        px, week = scene.px, scene.week
        is_day = key == "day"
        day = self.shown_day(scene)
        days = (day,) if is_day else tuple(range(7))
        rows = (1,) if is_day else _rows(week, days)
        lay_out = partial(_lanes, days, rows, DAY_INSET if is_day else WEEK_INSET)
        scroll = self._scrolls.get(key)
        if scroll is None:
            canvas = MissionCanvas(self.hand, MissionPainter(scene.tokens, day=is_day), lay_out)
            canvas.setObjectName("missionHours")
            canvas.setAccessibleName(
                "The day's hours in one lane" if is_day else "The week's hours in seven lanes"
            )
            canvas.setAccessibleDescription(
                "Drag a block to move it, pull its left or right end to resize it, "
                "or drag empty time to add something. Click a block to open it."
            )
            scroll = HoursScroll(
                canvas,
                DAY_SCALE if is_day else WEEK_SCALE,
                _length,
                name="missionDay" if is_day else "missionWeek",
                gutter=px(NAMES),
                axis=Axis.ACROSS,
            )
            self.keep_zoom(scroll)
            names = QWidget()
            names.setObjectName("missionNames")
            column = QVBoxLayout(names)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(GAP)
            scroll.set_header(names)
            self._scrolls[key] = scroll
        canvas = scroll.canvas
        assert isinstance(canvas, MissionCanvas)
        self._names(scene, canvas, scroll, days, rows, not is_day)
        canvas.set_painter(MissionPainter(scene.tokens, day=is_day))
        canvas._lay_out = lay_out
        canvas.relayout()
        items = week.on_day(day) if is_day else week.occurrences
        canvas.set_week(items, scene.today, scene.minute)
        at_now = scene.today is not None and scene.minute is not None and (not is_day or day == scene.today)
        scroll.open_at(
            (week.week_start, day) if is_day else week.week_start,
            lanes_end(items, scene.minute if at_now else None),
            end=True,
            keep=scene.minute if at_now else None,
        )
        if is_day:
            # The mock-up's height, or less in a short window beside the table, where what is still to
            # come today is the point. Under the table the page scrolls anyway.
            scroll.setMinimumHeight(px(AXIS) + px(DAY_LANE if self.cramped else DAY_LEAST))
            scroll.setMaximumHeight(px(AXIS) + px(DAY_LANE))
        else:
            lane = LANE_UNDER if self.cramped else LANE_LEAST
            scroll.setMinimumHeight(px(AXIS) + sum(rows) * px(lane) + 6 * GAP)
        return scroll

    def _names(self, scene: Scene, canvas: MissionCanvas, scroll: HoursScroll, days: tuple[int, ...],
               rows: tuple[int, ...], opens: bool) -> None:
        """The day names in the strip beside the lanes, one for each lane and as tall."""
        column = scroll.header.findChild(QWidget, "missionNames").layout()
        if tuple(canvas.names) != days:
            for name in canvas.names.values():
                name.setParent(None)
                name.deleteLater()
            canvas.names = {}
            for day in days:
                made = DayName(day, f"missionDay{day}", opens)
                if opens:
                    made.clicked.connect(lambda _=False, chosen=day: self._open_day(chosen))
                column.addWidget(made, 1)
                canvas.names[day] = made
        for (day, name), count in zip(canvas.names.items(), rows, strict=True):
            name.set_date(scene.week.date_of(day).day, day == scene.today)
            column.setStretchFactor(name, count)

    def _open_day(self, day: int) -> None:
        if self._scene is not None:
            self.day_activated.emit(self._scene.week.date_of(day).isoformat())

    # The figures

    def _strip(self, scene: Scene) -> Strip:
        week, today, minute = scene.week, scene.today, scene.minute
        first, last = week.date_of(0).isoformat(), week.date_of(6).isoformat()
        this_week = [item for item in week_homework(week) if first <= (item.due or "")[:10] <= last]
        due = [item for item in this_week if not item.done]
        if today is None:
            planned = free = (self._number(scene, "–"), "Today is in another week.")
        else:
            work = [item for item in week.on_day(today) if item.work]
            said = "Nothing planned"
            if work:
                said = f"{html.escape(work[0].title)} at {self._figure(clock_label(work[0].start))}"
            planned = (self._length(scene, sum(item.minutes for item in work)), said)
            left = sum(end - start for start, end in free_stretches(week.on_day(today), minute, EVENING))
            until = self._figure(clock_label(EVENING))
            free = (self._length(scene, left), f"Until {until}" if minute < EVENING else f"Past {until}")
        waiting = sum(1 for item in due if item.waiting)
        finished = len(this_week) - len(due)
        if due:
            line = f"{self._figure(len(due) - waiting)} placed, {self._figure(waiting)} not placed yet"
        else:
            line = f"{self._figure(finished)} finished" if finished else "Nothing is due this week."
        counted = (self._number(scene, len(due)), line)
        credited = "On this week's homework" if week.focus_min else "None yet this week"
        focus = (self._length(scene, week.focus_min), FOCUS_NOW.get(scene.focus, credited))
        cards = [
            self._card(scene, "missionPlanned", "Planned today", "calendar", *planned),
            self._card(scene, "missionDue", "Due this week", "book-open", *counted),
            self._card(scene, "missionFree", "Free time left today", "clock", *free),
            self._card(scene, "missionFocus", "Focus minutes", "timer", *focus),
        ]
        return Strip(cards, scene.px(12))

    def _card(self, scene: Scene, name: str, words: str, icon: str, value: str, line: str) -> QFrame:
        card = QFrame()
        card.setObjectName(name)
        card.setProperty("card", True)
        box = QVBoxLayout(card)
        box.setContentsMargins(scene.px(14), scene.px(12), scene.px(14), scene.px(10))
        box.setSpacing(scene.px(2))
        head = QHBoxLayout()
        head.addWidget(label(words, "missionLabel"))
        head.addStretch(1)
        mark = QLabel()
        mark.setObjectName("missionFigureIcon")
        mark.setPixmap(icons.pixmap(icon, scene.tokens["muted"], 16, self.devicePixelRatioF()))
        head.addWidget(mark)
        box.addLayout(head)
        for text, part in ((value, "Value"), (line, "Line")):
            shown = QLabel(text)
            shown.setObjectName(f"{name}{part}")
            shown.setTextFormat(Qt.TextFormat.RichText)
            box.addWidget(shown)
        return card

    def _figure(self, text: str) -> str:
        """A figure in the words of a line: in the mono face and the text colour."""
        ink = self._scene.tokens["text"] if self._scene is not None else ""
        return f'<span style="font-family:{FONT_FAMILIES["mono"]}; color:{ink}">{text}</span>'

    def _number(self, scene: Scene, value: int | str) -> str:
        size = type_pt("display", scene.scale)
        return (
            f'<span style="font-family:{FONT_FAMILIES["mono"]}; font-size:{size}pt; '
            f'font-weight:{WEIGHT_NUMBER}">{value}</span>'
        )

    def _length(self, scene: Scene, minutes: int) -> str:
        """ "3 h 20 min" as a figure: the numbers large in the mono face, the units in the body's."""
        unit = f'font-size:{type_pt("heading", scene.scale)}pt; color:{scene.tokens["muted"]}'
        hours, rest = divmod(max(minutes, 0), 60)
        parts = []
        if hours:
            parts.append(f'{self._number(scene, hours)}<span style="{unit}">&nbsp;h</span>')
        if rest or not hours:
            parts.append(f'{self._number(scene, rest)}<span style="{unit}">&nbsp;min</span>')
        return "&nbsp;&nbsp;".join(parts)

    # The deadline table

    def _table(self, scene: Scene) -> QFrame:
        px, week, tokens = scene.px, scene.week, scene.tokens
        card = QFrame()
        card.setObjectName("missionDeadlines")
        card.setProperty("card", True)
        box = QVBoxLayout(card)
        box.setContentsMargins(px(14), px(12), px(14), px(12))
        box.setSpacing(0)
        counted = scene.today is not None
        head = QHBoxLayout()
        head.addWidget(label("Deadlines", "missionLabel"))
        head.addStretch(1)
        head.addWidget(label("By time left" if counted else "By when due", "missionMuted"))
        box.addLayout(head)
        homework = week_homework(week)
        todo = [item for item in homework if not item.done]
        if not todo:
            box.addSpacing(px(10))
            words = LEFTOVER["all_finished"] if homework else LEFTOVER["no_homework"]
            box.addWidget(Wrapped(f"{words}.", "missionHint"))
            box.addStretch(1)
            return card
        heads = self._row_grid(scene)
        for column, words in enumerate(("Homework", "Needs", "Left" if counted else "Due")):
            heads.addWidget(label(words, "missionColumn"), 0, column,
                            Qt.AlignmentFlag.AlignRight if column else Qt.AlignmentFlag.AlignLeft)
        rule = QFrame()
        rule.setObjectName("missionColumns")
        rule.setLayout(heads)
        box.addSpacing(px(10))
        box.addWidget(rule)
        soft = mix_oklab(tokens["line"], tokens["surface"], 0.5)
        rows: list[QWidget] = []
        chips = 0
        for item in todo:
            row = QFrame()
            row.setObjectName("missionDeadline")
            grid = self._row_grid(scene)
            row.setLayout(grid)
            grid.setContentsMargins(0, px(14), 0, px(13))
            grid.setVerticalSpacing(px(8))
            title = QHBoxLayout()
            title.setSpacing(px(5))
            book = QLabel()
            book.setObjectName("missionBook")
            book.setPixmap(icons.pixmap(BOOK, tokens["text"], px(13), self.devicePixelRatioF()))
            title.addWidget(book)
            name = FittedLabel(minimum=px(40))
            name.setObjectName("missionDeadlineTitle")
            name.set_full_text(item.title)
            name.setToolTip(item.title)
            title.addWidget(name, 1)
            grid.addLayout(title, 0, 0)
            needs = label(clock_length(item.needs), "missionFigure")
            grid.addWidget(needs, 0, 1, Qt.AlignmentFlag.AlignRight)
            left = minutes_left(week, scene.today, scene.minute, item.due)
            if left is None:
                when = _due_day(item.due, short=True)
                gone = False
            else:
                gone = left <= 0
                when = "Past due" if gone else left_words(left)
            said = label(when, "missionLeft")
            said.setProperty("gone", gone)
            grid.addWidget(said, 0, 2, Qt.AlignmentFlag.AlignRight)
            bar = Bar(item.placed / item.needs if item.needs else 0.0, soft, tokens["accent"], max(px(3), 3))
            holder = QHBoxLayout()
            holder.setContentsMargins(px(18), 0, 0, 0)
            holder.addWidget(bar)
            grid.addLayout(holder, 1, 0, Qt.AlignmentFlag.AlignVCenter)
            state = QVBoxLayout()
            state.setSpacing(px(2))
            if item.first is not None and not item.waiting:
                day, start = item.first
                placed = QLabel(f"Placed {DAYS[day]} {self._figure(clock_label(start))}")
                placed.setObjectName("missionPlaced")
                placed.setTextFormat(Qt.TextFormat.RichText)
                state.addWidget(placed, 0, Qt.AlignmentFlag.AlignRight)
            for waiting in item.waiting:
                words = "Not placed yet"
                if item.placed:
                    words = f"{length_label(waiting.minutes)} not placed yet"
                chip = OpenChip(self.hand, waiting, words)
                chip.setObjectName(f"missionWaiting{chips}")
                chip.clicked.connect(
                    lambda _=False, block_id=waiting.block_id: self.block_activated.emit(block_id)
                )
                state.addWidget(chip, 0, Qt.AlignmentFlag.AlignRight)
                chips += 1
            grid.addLayout(state, 1, 1, 1, 2)
            rows.append(row)
        box.addWidget(self._scrolled(scene, "missionDeadlineRows", rows), 1)
        dues = {(item.due or "")[:10] for item in todo}
        foot = "The bar is how much of each is placed in the week."
        if len(todo) == 1:
            foot = "The bar is how much of it is placed in the week."
        elif len(dues) == 1 and "" not in dues:
            foot = f"All {len(todo)} are due {_due_day(todo[0].due)}. {foot}"
        box.addSpacing(px(12))
        box.addWidget(Wrapped(foot, "missionFoot"))
        return card

    def _row_grid(self, scene: Scene) -> QGridLayout:
        """The table's three columns: the homework, what it needs and the time left."""
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, scene.px(6))
        grid.setHorizontalSpacing(scene.px(12))
        grid.setColumnStretch(0, 1)
        grid.setColumnMinimumWidth(1, scene.px(52))
        grid.setColumnMinimumWidth(2, scene.px(80))
        return grid

    # Day

    def _day_cards(self, scene: Scene) -> QHBoxLayout:
        """What is still to come today and the free time left, side by side under the lane; another
        day's list, alone."""
        pair = QHBoxLayout()
        pair.setSpacing(scene.px(12))
        day = self.shown_day(scene)
        if day == scene.today:
            pair.addWidget(self._up_next(scene), 1)
            pair.addWidget(self._free(scene), 1)
        else:
            pair.addWidget(self._day_list(scene, day), 1)
        return pair

    def _list_card(
        self, scene: Scene, name: str, words: str, aside: str, rows: list[QWidget], foot: str = ""
    ) -> QFrame:
        """A card of rows under a label, with a line at its foot."""
        card = QFrame()
        card.setObjectName(name)
        card.setProperty("card", True)
        box = QVBoxLayout(card)
        box.setContentsMargins(scene.px(14), scene.px(12), scene.px(14), scene.px(12))
        box.setSpacing(0)
        head = QHBoxLayout()
        head.addWidget(label(words, "missionLabel"))
        head.addStretch(1)
        side = QLabel(aside)
        side.setObjectName("missionMuted")
        side.setTextFormat(Qt.TextFormat.RichText)
        head.addWidget(side)
        box.addLayout(head)
        box.addSpacing(scene.px(8))
        box.addWidget(WholeRows(rows, f"{name}Rows", every=self.cramped), 1)
        if foot:
            box.addSpacing(scene.px(12))
            box.addWidget(Wrapped(foot, "missionFoot", rich=True))
        return card

    def _scrolled(self, scene: Scene, name: str, rows: list[QWidget]) -> QScrollArea:
        """Rows in a scroll area of their own. Beside the lanes they ask for no height, so the lanes,
        not the rows, set the page's, and they scroll in a short window. Under the lanes the page
        scrolls, and they are shown whole."""
        page = QWidget()
        page.setObjectName(name)
        page.setProperty("rows", True)
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        for row in rows:
            column.addWidget(row)
        column.addStretch(1)
        area = scrolling(page, f"{name}Scroll")
        area.setProperty("rows", True)
        page.setAutoFillBackground(False)
        overlay_scroll_bars(area)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if self.cramped:
            area.setMinimumHeight(page.sizeHint().height())
        else:
            area.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
            area.setMinimumHeight(scene.px(48))
        return area

    def _list_row(self, scene: Scene, parts: list[QWidget]) -> QFrame:
        row = QFrame()
        row.setObjectName("missionListRow")
        row.setFixedHeight(scene.px(48))
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(scene.px(12))
        for at, part in enumerate(parts):
            line.addWidget(part, 1 if at == 1 else 0)
        return row

    def _what(self, scene: Scene, item: Occurrence) -> QWidget:
        """A block's name after its category's dot, or the book for homework."""
        holder = QWidget()
        holder.setObjectName("missionWhat")
        line = QHBoxLayout(holder)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(scene.px(8))
        mark = QLabel()
        if item.category in HOMEWORK_CATEGORIES:
            mark.setObjectName("missionBook")
            mark.setPixmap(icons.pixmap(BOOK, scene.tokens["text"], scene.px(13), self.devicePixelRatioF()))
        else:
            dot = scene.px(8)
            mark.setObjectName("missionDot")
            mark.setFixedSize(dot, dot)
            colour = _paint(scene.tokens, item.category)[1]
            mark.setStyleSheet(f"background: {colour}; border-radius: {dot // 2}px;")
        line.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        name = FittedLabel(minimum=scene.px(40))
        name.setObjectName("missionRowTitle")
        name.set_full_text(item.title)
        line.addWidget(name, 1)
        return holder

    def _up_next(self, scene: Scene) -> QFrame:
        """What is still to come today, when each starts, and what the next day starts with."""
        week, today, minute = scene.week, scene.today, scene.minute
        assert today is not None
        coming = [item for item in week.day_queue(today, minute).queue if item.start > minute]
        rows: list[QWidget] = [
            self._list_row(
                scene,
                [
                    label(clock_label(item.start), "missionWhen"),
                    self._what(scene, item),
                    label(f"in {length_label(item.start - minute)}", "missionIn"),
                ],
            )
            for item in coming
        ]
        if not coming:
            heading, title, _line = week.leftover_parts(today)
            waits = week.leftover_kind(today) == "needs_time"
            words = f"{title} is not placed yet." if waits else f"{heading}."
            rows.append(Wrapped(words, "missionHint"))
        foot = ""
        after = today + 1
        tomorrow = week.on_day(after) if after < 7 else ()
        if tomorrow:
            then = tomorrow[0]
            at = self._figure(clock_label(then.start))
            foot = f"Then {DAY_FULL[after]}: {html.escape(then.title)} at {at}."
        aside = f"{self._figure(len(coming))} more today"
        return self._list_card(scene, "missionUpNext", "Up next", aside, rows, foot)

    def _free(self, scene: Scene) -> QFrame:
        """The free time left before the evening, each stretch with a bar against the longest, and
        whether what is not placed yet has room in it."""
        week, today, minute = scene.week, scene.today, scene.minute
        assert today is not None
        stretches = free_stretches(week.on_day(today), minute, EVENING)
        total = sum(end - start for start, end in stretches)
        until = self._figure(clock_label(EVENING))
        longest = max((end - start for start, end in stretches), default=1)
        soft = mix_oklab(scene.tokens["line"], scene.tokens["surface"], 0.5)
        rows: list[QWidget] = [
            self._list_row(
                scene,
                [
                    label(range_label(start, end), "missionWhen"),
                    Bar((end - start) / longest, soft, scene.tokens["accent"], max(scene.px(3), 3)),
                    label(clock_length(end - start), "missionFigure"),
                ],
            )
            for start, end in stretches
        ]
        if not stretches:
            none = f"No free time left before {clock_label(EVENING)}."
            rows.append(Wrapped(none, "missionHint"))
        waiting = week.waiting
        needs = sum(item.minutes for item in waiting)
        titles = html.escape(names_of([item.title for item in waiting]))
        amount = self._figure(clock_length(needs)) + (" in all" if len(waiting) > 1 else "")
        if not waiting:
            foot = "Nothing is waiting for a time."
        elif needs <= total:
            foot = f"Room for {titles}, {amount}, before {until}."
        else:
            verb = "need" if len(waiting) > 1 else "needs"
            foot = f"{titles} {verb} {amount}, more than is free before {until}."
        aside = f"{self._figure(clock_length(total))} until {until}"
        return self._list_card(scene, "missionFreeTime", "Free time left", aside, rows, foot)

    def _day_list(self, scene: Scene, day: int) -> QFrame:
        """Another day's blocks, when each starts and how long it is."""
        items = scene.week.on_day(day)
        rows: list[QWidget] = [
            self._list_row(
                scene,
                [
                    label(clock_label(item.start), "missionWhen"),
                    self._what(scene, item),
                    label(clock_length(item.minutes), "missionFigure"),
                ],
            )
            for item in items
        ]
        if not items:
            rows.append(Wrapped("Nothing planned.", "missionHint"))
        total = sum(item.minutes for item in items)
        aside = f"{plural(len(items), 'thing')}, {self._figure(length_label(total))} in all"
        return self._list_card(scene, "missionDayList", DAY_FULL[day], aside, rows)

    def _sheet(self, scene: Scene) -> str:
        tokens = scene.tokens
        text, muted, accent, surface = tokens["text"], tokens["muted"], tokens["accent"], tokens["surface"]
        soft = mix_oklab(tokens["line"], surface, 0.5)
        figures = FONT_FAMILIES["mono"]

        def size(role: str) -> str:
            return f"{type_pt(role, scene.scale)}pt"

        chip = round(20 * scene.scale)
        clear = css(background="transparent")
        caption = css(color=muted, font_size=size("caption"))
        return base_sheet(self.objectName(), tokens) + rules(
            self.objectName(),
            {
                "#missionScroll, #missionPage": css(background=tokens["bg"]),
                # Plain widgets on the page, which the window's stylesheet would paint its page colour.
                "#missionWeekHeader, #missionDayHeader, #missionWeekZoom, #missionDayZoom": clear,
                "#missionNames, #missionWhat, #qt_scrollarea_vcontainer, #qt_scrollarea_hcontainer": clear,
                'QScrollArea[rows="true"], QWidget[rows="true"]': clear,
                "QLabel": css(color=text, font_size=size("body")),
                'QFrame[card="true"]': css(
                    background=surface, border=f"1px solid {soft}", border_radius=f"{RADIUS_CARD}px"
                ),
                # Styled for their rules, and clear so the window's page colour is not drawn.
                "QFrame#missionColumns": css(background="transparent", border_bottom=f"1px solid {soft}"),
                "QFrame#missionDeadline, QFrame#missionListRow": css(
                    background="transparent", border_bottom=f"1px solid {soft}"
                ),
                'QFrame#missionListRow[last="true"]': css(border_bottom="none"),
                "QFrame#missionStrip": clear,
                "QLabel#missionLabel, QLabel#missionColumn": css(
                    color=muted, font_size=size("caption"), font_weight=WEIGHT_STRONG
                ),
                "QLabel#missionMuted, QLabel#missionHint, QLabel#missionIn, QLabel#missionMore": caption,
                "QLabel#missionFoot": caption,
                "QLabel#missionPlannedLine, QLabel#missionDueLine, QLabel#missionFreeLine, "
                "QLabel#missionFocusLine": caption,
                "QLabel#missionPlaced": caption,
                "QLabel#missionFigure, QLabel#missionLeft, QLabel#missionWhen": css(font_family=figures),
                'QLabel#missionLeft[gone="true"]': css(color=tokens["danger"], font_weight=WEIGHT_STRONG),
                "QLabel#missionDate": css(color=muted, font_size=size("caption"), font_family=figures),
                "QLabel#missionDayName": css(font_weight=WEIGHT_STRONG),
                "QLabel#missionChip": css(
                    background=accent,
                    color=tokens["accent_ink"],
                    font_family=figures,
                    font_size=size("caption"),
                    font_weight=WEIGHT_STRONG,
                    border_radius=f"{chip // 2}px",
                    padding=f"0 {round(6 * scene.scale)}px",
                    min_height=f"{chip}px",
                    max_height=f"{chip}px",
                ),
                'QPushButton[kind="name"]': css(
                    background="transparent",
                    border="none",
                    border_radius=f"{RADIUS_CONTROL}px",
                    padding="0",
                    min_height="0",
                    text_align="left",
                ),
                'QPushButton[kind="name"]:hover': css(background=mix_oklab(text, tokens["bg"], 0.05)),
                'QPushButton[kind="name"][keyfocus="true"]:focus': css(border=f"2px solid {accent}"),
                'QPushButton[kind="open"]': css(
                    background="transparent",
                    color=accent,
                    border="none",
                    padding="0",
                    min_height="0",
                    font_size=size("caption"),
                    font_weight=WEIGHT_STRONG,
                    text_align="right",
                ),
                'QPushButton[kind="open"]:hover': css(text_decoration="underline"),
                'QPushButton[kind="open"][keyfocus="true"]:focus': css(border=f"2px solid {accent}"),
                "QLabel#missionDeadlineTitle, QLabel#missionRowTitle": css(font_weight=WEIGHT_REGULAR),
            },
        )


def _due_day(due: str | None, short: bool = False) -> str:
    """When homework is due, as the table says it: "Sunday 27", or "Sun 27" in a column."""
    if not due:
        return ""
    day = date.fromisoformat(due[:10])
    return f"{(DAYS if short else DAY_FULL)[day.weekday()]} {day.day}"


def _detach(layout: QLayout, widget: QWidget) -> bool:
    """Take a retained scroll out of nested layouts before clearing the page."""
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is widget:
            layout.takeAt(index)
            widget.hide()
            return True
        inner = item.layout()
        if inner is not None and _detach(inner, widget):
            return True
    return False
