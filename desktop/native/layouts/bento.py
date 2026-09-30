"""Bento: the week as tiles on the look's page (0.17's Bento and Today tiles, one design).

Its Hero option picks the big tile. Week, as Bento always was: the week's hours are the hero, with
Next, Due soon, the week's homework load and Not placed yet as smaller tiles around it; Day keeps the
tiles and puts the day's summary and free time beside its hours. Today: today's hours are the hero,
beside what is next and the week at a glance, and the other six days are small tiles in a row, each
with its first item, its load and its homework. Pointing at a day tile readies it, and a click swaps it
into the hero; on Day the hero is the day open, beside its summary.

Every hours surface here is the shared hours on the window's hand. The tiles are cards with soft
shadows and the colour is in the blocks; a colourway of Bento's own paints the hero alone.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date
from functools import cached_property

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QFontMetricsF, QPainter, QPainterPath, QPen, QPixmap
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

from backend.models import due_sort_key, parse_due
from desktop.native import icons
from desktop.native.calendar import CATEGORIES, DAY_FULL, DAYS
from desktop.native.fonts import at_scale, time_font
from desktop.native.hours.canvas import (
    HOMEWORK_CATEGORIES,
    TEXT_LEFT,
    TEXT_RIGHT,
    Drawn,
    HoursCanvas,
    Started,
    word_elide,
)
from desktop.native.hours.chips import TrayChip
from desktop.native.hours.classic import ClassicPainter, Share, day_shares, open_hours
from desktop.native.hours.geometry import FIRST, LAST, LinearTrack
from desktop.native.hours.hand import Hand
from desktop.native.hours.zoom import OPENS, HoursScroll, Scale
from desktop.native.layouts.base import (
    NARROW_WIDTH,
    LayoutView,
    Scene,
    base_sheet,
    css,
    empty,
    family,
    label,
    plural,
    rules,
    scrolling,
    short_length,
)
from desktop.native.look import category_paint, look_measures
from desktop.native.motion import duration, moves
from desktop.native.tokens import (
    RADIUS_CARD,
    RADIUS_CONTROL,
    RADIUS_SHEET,
    SHADOW_LARGE,
    SHADOW_SMALL,
    WEIGHT_REGULAR,
    WEIGHT_STRONG,
    fit_lightness,
    mix_oklab,
    type_pt,
)
from desktop.native.weekmodel import (
    END_OF_DAY,
    HOMEWORK,
    Occurrence,
    Waiting,
    WeekModel,
    clock_label,
    length_label,
    range_label,
)
from desktop.native.widgets import overlay_scroll_bars

WEEK_SCALE = Scale("bento.week", (32, 44, 64, 96, 128), 44)
# One day's hours: Day's, and the Today hero's. At 44 pixels an hour a half-hour block still says its
# name and an hour's says it on two lines, as the mock-up draws them at its 42; and a school day from
# its first block to an hour after its last nearly fills a laptop's hero.
DAY_SCALE = Scale("bento.day", (32, 44, 64, 96, 128, 160), 44)
# Room above 00:00 and below 24:00 for their hour labels, and the labels' column.
PAD, GUTTER = 10, 56
# The mock-up's measures at Normal text, in pixels: the gap between tiles; the small tiles' columns
# beside the week; the side of Day's hero and of the Today hero.
GAP = 16
SIDE = 212
DAY_SIDE = 264
HERO_SIDE = 372
# The day the bars measure against and the free time runs to, as the mock-up draws them.
DAY_START, DAY_END = OPENS, 22 * 60
# Free time shorter than this is not listed.
LEAST_FREE = 30
# Due soon lists this many and counts the rest.
DUE_ROWS = 5
# How far a day tile rises as it lifts, and how long it takes (the Bento Box Grid entry's hover).
RISE, LIFT_MS = 2, 200


def planned_words(minutes: int) -> str:
    """The week's figure in whole hours, "47 h planned", as a glance reads it."""
    if minutes <= 0:
        return "Nothing planned"
    return f"{round(minutes / 60)} h planned" if minutes >= 60 else f"{length_label(minutes)} planned"


def paint_of(tokens: dict[str, str], category: str) -> tuple[str, str]:
    """A category's fill and mark in the one family, on this design's cards."""
    fill, mark = category_paint(category, {"family": family(tokens), "panel": tokens["surface"]})
    return fill or tokens["surface"], mark or tokens["line"]


def free_slots(items: tuple[Occurrence, ...], now: int | None) -> list[tuple[int, int]]:
    """The free time between a day's blocks, from its first to the end of the day; from `now` on when
    it is today. A stretch under LEAST_FREE is not free time, unless now cuts one that was."""
    live = sorted((item for item in items if item.live), key=lambda item: item.start)
    at = live[0].start if live else DAY_START
    slots = []
    for item in live:
        if item.start - at >= LEAST_FREE:
            slots.append((at, item.start))
        at = max(at, item.end)
    if DAY_END - at >= LEAST_FREE:
        slots.append((at, DAY_END))
    if now is None:
        return slots
    return [(max(start, now), end) for start, end in slots if end > now]


@dataclass(frozen=True)
class Coming:
    """What Next says: its label, the name, when and how long, the pill beside that, its category, and
    what comes after it."""

    label: str
    title: str
    when: str
    pill: str = ""
    category: str = ""
    then: tuple[Occurrence, ...] = ()


def coming(scene: Scene) -> Coming | None:
    """What is on now or next today, and the two after it. None on a week that is not this one."""
    if scene.today is None:
        return None
    queue = scene.week.day_queue(scene.today, scene.minute)
    if not queue.queue:
        kicker, title, line = scene.week.leftover_parts(scene.today)
        return Coming("Next" if kicker == title else kicker, title, line)
    first, then = queue.queue[0], queue.queue[1:3]
    when = f"{clock_label(first.start)} · {length_label(first.minutes)}"
    if first == queue.current:
        return Coming(
            "Now", first.title, when, f"{length_label(first.end - scene.minute)} left", first.category, then
        )
    return Coming(
        "Next", first.title, when, f"in {length_label(first.start - scene.minute)}", first.category, then
    )


@dataclass(frozen=True)
class Due:
    """Homework Due soon lists: how long all of it takes, where its first placed session is, and
    whether any of it still waits for a time."""

    block_id: str
    title: str
    due: str | None
    minutes: int
    at: tuple[int, int] | None
    waiting: bool


def due_soon(week: WeekModel) -> list[Due]:
    """Homework still to do, whether placed or waiting, soonest due first."""
    parts: dict[str, list[Occurrence | Waiting]] = {}
    for item in (*(entry for entry in week.occurrences if entry.work and entry.live), *week.waiting):
        parts.setdefault(item.assignment_id or item.block_id, []).append(item)
    listed = []
    for items in parts.values():
        placed = sorted(
            (item for item in items if isinstance(item, Occurrence)), key=lambda item: (item.day, item.start)
        )
        first = placed[0] if placed else items[0]
        listed.append(
            Due(
                first.block_id,
                first.title,
                first.due,
                sum(item.minutes for item in items),
                (placed[0].day, placed[0].start) if placed else None,
                any(isinstance(item, Waiting) for item in items),
            )
        )
    return sorted(listed, key=lambda due: due_sort_key(due.due, due.title))


def time_left(due: str, today: date, minute: int) -> tuple[str, str, bool]:
    """Due soon's figure: how long is left, when it is due, and whether it has run out. The line says
    "due", so it is never read as a time the homework is placed at, which its row says."""
    day, by = parse_due(due)
    days = (day - today).days
    name = f"{DAY_FULL[day.weekday()]} {day.day}"
    if days < 0 or (days == 0 and by <= minute):
        return "Past due", f"was due {name}" if days else f"was due at {clock_label(by)}", True
    if days == 0:
        until = "left · due by the end of today" if by == END_OF_DAY else f"left · due at {clock_label(by)}"
        return length_label(by - minute), until, False
    return plural(days, "day"), f"left · due {name}", False


def due_here(week: WeekModel, day: int) -> int:
    """How many homework still to do are due on `day`."""
    iso = week.date_of(day).isoformat()
    return sum(1 for due in due_soon(week) if (due.due or "").startswith(iso))


@dataclass(frozen=True)
class Ink:
    """The colours a part of the board is drawn in, from what it sits on: a card, or a hero that a
    colourway of Bento's own paints."""

    ground: str
    text: str
    muted: str
    line: str
    track: str
    accent: str
    tint: str


def card_ink(tokens: dict[str, str]) -> Ink:
    ground, text = tokens["surface"], tokens["text"]
    tint = mix_oklab(tokens["accent"], ground, 0.10)
    return Ink(
        ground,
        text,
        tokens["muted"],
        mix_oklab(tokens["line"], ground, 0.5),
        mix_oklab(text, ground, 0.08),
        # Accent words on the accent's tint take the nearest shade that reads, as the dial's do.
        fit_lightness(tokens["accent"], (tint,), 4.5),
        tint,
    )


def hero_ink(tokens: dict[str, str]) -> Ink:
    """The hero's colours: its colourway's, or a card's when it names none, as Match my look does."""
    if "hero" not in tokens:
        return card_ink(tokens)
    ground, ink = tokens["hero"], tokens["hero_ink"]
    return Ink(
        ground,
        ink,
        tokens["hero_muted"],
        mix_oklab(ink, ground, 0.22),
        mix_oklab(ink, ground, 0.18),
        ink,
        mix_oklab(ink, ground, 0.18),
    )


def swatch(category: str, tokens: dict[str, str], ratio: float, scale: float = 1.0) -> QPixmap:
    """A category in small, as its blocks are drawn: the fill with the 3-pixel edge. Homework's carries
    the book as well, so it is told apart without its colour."""
    fill, mark = paint_of(tokens, category)
    book = category in HOMEWORK_CATEGORIES
    side = round((16 if book else 12) * scale)
    made = QPixmap(round(side * ratio), round(side * ratio))
    made.setDevicePixelRatio(ratio)
    made.fill(Qt.GlobalColor.transparent)
    painter = QPainter(made)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    shape = QPainterPath()
    shape.addRoundedRect(QRectF(0, 0, side, side), 3, 3)
    painter.fillPath(shape, QColor(fill))
    painter.setClipPath(shape)
    painter.fillRect(QRectF(0, 0, 3, side), QColor(mark))
    if book:
        size = round(side * 0.66)
        painter.drawPixmap(
            QPointF(2 + (side - 2 - size) / 2, (side - size) / 2),
            icons.pixmap("book-open", tokens["text"], size, ratio),
        )
    painter.end()
    return made


def paint_parts(painter: QPainter, rect: QRectF, parts: list[tuple[str, int]], gap: float = 2.0) -> None:
    """A thin bar in parts, each its colour for its share of the whole, inside a pill."""
    shown = [(colour, minutes) for colour, minutes in parts if minutes > 0]
    total = sum(minutes for _, minutes in shown)
    if not total or rect.width() <= 0:
        return
    room = rect.width() - gap * (len(shown) - 1)
    shape = QPainterPath()
    shape.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
    painter.save()
    painter.setClipPath(shape)
    at = rect.left()
    for index, (colour, minutes) in enumerate(shown):
        wide = rect.right() - at if index == len(shown) - 1 else max(room * minutes / total, 3.0)
        painter.fillRect(QRectF(at, rect.top(), wide, rect.height()), QColor(colour))
        at += wide + gap
    painter.restore()


def shares_of(week: WeekModel, day: int) -> list[Share]:
    """A day's time by category, in the order the legend names them."""
    order = list(CATEGORIES)
    return sorted(
        day_shares(week, day),
        key=lambda share: order.index(share.category) if share.category in order else len(order),
    )


def day_parts(week: WeekModel, day: int, tokens: dict[str, str], track: str) -> list[tuple[str, int]]:
    """A day's time by category in their marks, then what is left of its day in `track`."""
    shares = shares_of(week, day)
    planned = sum(share.minutes for share in shares)
    parts = [(paint_of(tokens, share.category)[1], share.minutes) for share in shares]
    return [*parts, (track, max(DAY_END - DAY_START - planned, 0))]


class Stack(QWidget):
    """A thin bar in parts: a day's time by category and what is left of it, or the homework placed
    out of all of it."""

    def __init__(self, name: str, tall: int) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setFixedHeight(tall)
        self.parts: list[tuple[str, int]] = []

    def show_parts(self, parts: list[tuple[str, int]]) -> None:
        self.parts = parts
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_parts(painter, QRectF(self.rect()), self.parts)
        painter.end()


class LoadBars(QWidget):
    """The week's homework by day: a bar each in homework's mark, today's slot washed, and the day's
    letter under it."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("bentoLoadBars")
        self.minutes = [0] * 7
        self.today: int | None = None
        self.ink = Ink(*("#000000",) * 7)
        self.mark, self.scale = "#000000", 1.0
        self.setMinimumHeight(60)

    def show_load(self, minutes: list[int], today: int | None, ink: Ink, mark: str, scale: float) -> None:
        self.minutes, self.today, self.ink, self.mark, self.scale = minutes, today, ink, mark, scale
        self.setAccessibleName("Homework by day")
        self.setAccessibleDescription(
            ". ".join(
                f"{DAY_FULL[day]}: {length_label(each) if each else 'none'}"
                for day, each in enumerate(minutes)
            )
        )
        self.update()

    def _slots(self) -> list[QRectF]:
        wide = self.width() / 7
        return [QRectF(day * wide, 0, wide, self.height()) for day in range(7)]

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = at_scale(self.font(), "caption", self.scale, WEIGHT_REGULAR)
        line = QFontMetricsF(font).height()
        most = max(self.minutes) or 1
        bar = 16 * self.scale
        for day, slot in enumerate(self._slots()):
            track = QRectF(slot.left(), 0, slot.width(), slot.height() - line - 8 * self.scale)
            if day == self.today:
                wash = QPainterPath()
                wash.addRoundedRect(track, RADIUS_CONTROL, RADIUS_CONTROL)
                painter.fillPath(wash, QColor(mix_oklab(self.ink.text, self.ink.ground, 0.04)))
            if self.minutes[day]:
                tall = track.height() * self.minutes[day] / most
                shape = QPainterPath()
                shape.addRoundedRect(
                    QRectF(slot.center().x() - bar / 2, track.bottom() - tall, bar, tall + 4), 4, 4
                )
                painter.save()
                painter.setClipRect(QRectF(slot.left(), 0, slot.width(), track.bottom()))
                painter.fillPath(shape, QColor(self.mark))
                painter.restore()
            painter.fillRect(QRectF(slot.left(), track.bottom(), slot.width(), 1), QColor(self.ink.line))
            chosen = day == self.today
            painter.setFont(
                at_scale(self.font(), "caption", self.scale, WEIGHT_STRONG if chosen else WEIGHT_REGULAR)
            )
            painter.setPen(QColor(self.ink.text if chosen else self.ink.muted))
            painter.drawText(
                QRectF(slot.left(), slot.bottom() - line, slot.width(), line),
                Qt.AlignmentFlag.AlignCenter,
                DAYS[day][0],
            )
        painter.end()

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            at = event.pos()
            for day, slot in enumerate(self._slots()):
                if slot.contains(QPointF(at)):
                    each = self.minutes[day]
                    QToolTip.showText(
                        event.globalPos(), f"{DAY_FULL[day]}: {length_label(each) if each else 'none'}", self
                    )
                    return True
        return super().event(event)


class Glance(QWidget):
    """The week at a glance: seven thin columns of its blocks in their colours, no words, today
    outlined with the time now across it."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("bentoGlance")
        self.columns: list[list[tuple[int, int, str, str]]] = [[] for _ in range(7)]
        self.span = (DAY_START, DAY_END)
        self.today: int | None = None
        self.minute = 0
        self.ink = Ink(*("#000000",) * 7)
        self.scale = 1.0
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    def show_week(
        self, week: WeekModel, today: int | None, minute: int, tokens: dict[str, str], ink: Ink, scale: float
    ) -> None:
        starts = [item.start for item in week.occurrences]
        ends = [item.end for item in week.occurrences]
        self.span = (min([DAY_START, *starts]) // 60 * 60, -(-max([DAY_END, *ends]) // 60) * 60)
        self.columns = [
            [(item.start, item.end, *paint_of(tokens, item.category)) for item in week.on_day(day)]
            for day in range(7)
        ]
        self.today, self.minute, self.ink, self.scale = today, minute, ink, scale
        self.setAccessibleName("The week at a glance")
        self.setAccessibleDescription(
            ". ".join(
                f"{DAY_FULL[day]}: {length_label(sum(end - start for start, end, _, _ in blocks))} planned"
                for day, blocks in enumerate(self.columns)
            )
        )
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = at_scale(self.font(), "caption", self.scale, WEIGHT_REGULAR)
        line = QFontMetricsF(font).height()
        gap = 8 * self.scale
        wide = (self.width() - gap * 6) / 7
        tall = self.height() - line - gap
        first, last = self.span
        per = tall / max(last - first, 1)
        accent = QColor(self.ink.accent)
        for day, blocks in enumerate(self.columns):
            left = day * (wide + gap)
            track = QRectF(left, 0, wide, tall)
            shape = QPainterPath()
            shape.addRoundedRect(track, RADIUS_CONTROL, RADIUS_CONTROL)
            painter.fillPath(shape, QColor(mix_oklab(self.ink.text, self.ink.ground, 0.06)))
            painter.save()
            painter.setClipPath(shape)
            for start, end, fill, mark in blocks:
                box = QRectF(left + 3, (start - first) * per + 1, wide - 6, max((end - start) * per - 2, 2))
                block = QPainterPath()
                block.addRoundedRect(box, 2, 2)
                painter.fillPath(block, QColor(fill))
                painter.fillRect(QRectF(box.left(), box.top(), 3, box.height()), QColor(mark))
            painter.restore()
            chosen = day == self.today
            if chosen:
                painter.setPen(QPen(accent, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(track.adjusted(-1, -1, 1, 1), RADIUS_CONTROL + 1, RADIUS_CONTROL + 1)
                if first <= self.minute <= last:
                    at = (self.minute - first) * per
                    painter.fillRect(QRectF(left - 2, at - 1, wide + 4, 2), accent)
            painter.setFont(
                at_scale(self.font(), "caption", self.scale, WEIGHT_STRONG if chosen else WEIGHT_REGULAR)
            )
            painter.setPen(QColor(self.ink.text if chosen else self.ink.muted))
            painter.drawText(
                QRectF(left, self.height() - line, wide, line), Qt.AlignmentFlag.AlignCenter, DAYS[day]
            )
        painter.end()


class Chip(TrayChip):
    """Homework not placed yet, drawn as a block of it: its category's fill with the edge, the book,
    its name and how long it takes under it. Drag it onto the hours to give it a time; a click opens
    it."""

    def __init__(self, hand: Hand, waiting: Waiting, tokens: dict[str, str], scale: float) -> None:
        super().__init__(hand, waiting)
        self.setText(waiting.title)
        self.tokens, self.scale = tokens, scale
        self.length = length_label(waiting.minutes)
        self.fill, self.mark = paint_of(tokens, waiting.category or HOMEWORK)
        # A long name shortens at a word; it never widens its tile.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def _fit(self) -> None:
        # Painted whole each time, the name shortened in the paint.
        return

    def _fonts(self) -> tuple[QFont, QFont]:
        # Both weights named: the window's stylesheet sets a button's font at 600.
        title = at_scale(self.font(), "body", self.scale, WEIGHT_STRONG)
        return title, time_font(at_scale(self.font(), "caption", self.scale, WEIGHT_REGULAR))

    def _pad(self) -> tuple[float, float, float]:
        """Its padding at the top and foot, at the edge's side, and at the other."""
        return 8 * self.scale, (3 + 12) * self.scale, 12 * self.scale

    def sizeHint(self) -> QSize:  # noqa: N802
        title, small = self._fonts()
        pad, left, right = self._pad()
        book = QFontMetricsF(title).ascent() + 6
        wide = max(
            QFontMetricsF(title).horizontalAdvance(self._title),
            QFontMetricsF(small).horizontalAdvance(self.length),
        )
        tall = 2 * pad + QFontMetricsF(title).lineSpacing() + QFontMetricsF(small).lineSpacing()
        return QSize(round(left + book + wide + right), round(tall))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(round(96 * self.scale), self.sizeHint().height())

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect())
        shape = QPainterPath()
        shape.addRoundedRect(box, RADIUS_CONTROL, RADIUS_CONTROL)
        painter.fillPath(shape, QColor(self.fill))
        painter.save()
        painter.setClipPath(shape)
        painter.fillRect(QRectF(0, 0, 3, box.height()), QColor(self.mark))
        painter.restore()
        if self.hasFocus():
            painter.setPen(QPen(QColor(self.tokens["accent"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box.adjusted(1, 1, -1, -1), RADIUS_CONTROL - 1, RADIUS_CONTROL - 1)
        title, small = self._fonts()
        pad, left, right = self._pad()
        metrics = QFontMetricsF(title)
        icon = round(metrics.ascent())
        ink = self.tokens["text"]
        painter.drawPixmap(
            QPointF(left, pad + (metrics.height() - icon) / 2),
            icons.pixmap("book-open", ink, icon, self.devicePixelRatioF()),
        )
        at = left + icon + 6
        painter.setFont(title)
        painter.setPen(QColor(ink))
        room = box.width() - at - right
        painter.drawText(
            QRectF(at, pad, room, metrics.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            word_elide(self._title, metrics, room),
        )
        painter.setFont(small)
        painter.setPen(QColor(mix_oklab(ink, self.fill, 0.72)))
        painter.drawText(
            QRectF(at, pad + metrics.lineSpacing(), room, QFontMetricsF(small).height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            self.length,
        )
        painter.end()


class Legend(QWidget):
    """The week's categories with their swatches: rows aligned right that wrap where room runs out,
    as the hero's heading has them, or `columns` to a row, as the Today hero's side has them."""

    def __init__(self, items: list[tuple[QPixmap, str]], colour: str, scale: float, columns: int = 0) -> None:
        super().__init__()
        self.setObjectName("bentoLegend")
        self.items, self.colour, self.scale, self.columns = items, colour, scale, columns
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setAccessibleName("Colours: " + ", ".join(name for _, name in items))

    def _font(self) -> QFont:
        return at_scale(self.font(), "caption", self.scale, WEIGHT_REGULAR)

    def _widths(self) -> list[float]:
        metrics = QFontMetricsF(self._font())
        return [
            mark.deviceIndependentSize().width() + 8 * self.scale + metrics.horizontalAdvance(name)
            for mark, name in self.items
        ]

    def _gap(self) -> float:
        return (16 if self.columns else 12) * self.scale

    def _line(self) -> float:
        return max(QFontMetricsF(self._font()).height(), 16 * self.scale) + 4 * self.scale

    def _rows(self, width: float) -> list[list[int]]:
        indexes = list(range(len(self.items)))
        if self.columns:
            return [indexes[at : at + self.columns] for at in range(0, len(indexes), self.columns)]
        widths, gap = self._widths(), self._gap()
        rows: list[list[int]] = [[]]
        used = 0.0
        for index in indexes:
            if rows[-1] and used + gap + widths[index] > width:
                rows.append([])
                used = 0.0
            used += (gap if rows[-1] else 0) + widths[index]
            rows[-1].append(index)
        return rows

    def _columns(self) -> list[float]:
        """Where each column starts, when the legend has columns."""
        widths = self._widths()
        wide = [
            max((widths[at] for at in range(column, len(widths), self.columns)), default=0)
            for column in range(self.columns)
        ]
        return [sum(wide[:column]) + self._gap() * column for column in range(self.columns)]

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return round(len(self._rows(width)) * self._line())

    def sizeHint(self) -> QSize:  # noqa: N802
        widths = self._widths()
        if self.columns:
            starts = self._columns()
            wide = max((starts[at % self.columns] + widths[at] for at in range(len(widths))), default=0)
        else:
            wide = sum(widths) + self._gap() * max(len(widths) - 1, 0)
        return QSize(round(wide), self.heightForWidth(round(wide)))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(round(max(self._widths(), default=0)), round(self._line()))

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        font = self._font()
        painter.setFont(font)
        painter.setPen(QColor(self.colour))
        widths, gap, line = self._widths(), self._gap(), self._line()
        starts = self._columns() if self.columns else []
        for number, row in enumerate(self._rows(self.width())):
            used = sum(widths[at] for at in row) + gap * (len(row) - 1)
            left = 0.0 if self.columns else self.width() - used
            for place, at in enumerate(row):
                mark, name = self.items[at]
                x = starts[place] if self.columns else left
                size = mark.deviceIndependentSize()
                top = number * line + (line - size.height()) / 2
                painter.drawPixmap(QPointF(x, top), mark)
                box = QRectF(x + size.width() + 8 * self.scale, number * line, widths[at], line)
                painter.drawText(box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
                left += widths[at] + gap
        painter.end()


class DayHead(QPushButton):
    """A day's name over its column on the week's hero, "Mon 21", today's date in an accent chip. A
    click opens the day."""

    def __init__(self, day: int) -> None:
        super().__init__()
        self.day = day
        self.setObjectName(f"bentoDayName{day}")
        self.setProperty("day_target", day)
        self.setAccessibleName(f"Show {DAY_FULL[day]}")
        self.setToolTip(f"Open {DAY_FULL[day]}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.number, self.today = "", False
        self.ink = Ink(*("#000000",) * 7)
        self.accent, self.accent_ink, self.scale = "#000000", "#ffffff", 1.0

    def show_date(self, number: int, today: bool, ink: Ink, tokens: dict[str, str], scale: float) -> None:
        self.number, self.today, self.ink, self.scale = str(number), today, ink, scale
        self.accent, self.accent_ink = tokens["accent"], tokens["accent_ink"]
        self.setText(f"{DAYS[self.day]} {number}")
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, round(36 * self.scale))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(1, 3, -1, -3)
        if self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(mix_oklab(self.ink.text, self.ink.ground, 0.05)))
            painter.drawRoundedRect(box, RADIUS_CONTROL, RADIUS_CONTROL)
        if self.hasFocus() and self.property("keyfocus"):
            painter.setPen(QPen(QColor(self.accent), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box.adjusted(1, 1, -1, -1), RADIUS_CONTROL, RADIUS_CONTROL)
        name = at_scale(self.font(), "body", self.scale, WEIGHT_STRONG if self.today else WEIGHT_REGULAR)
        figure = at_scale(self.font(), "body", self.scale, WEIGHT_STRONG)
        words, number = QFontMetricsF(name), QFontMetricsF(figure)
        gap = 6 * self.scale
        chip = (
            max(26 * self.scale, number.horizontalAdvance(self.number) + 10 * self.scale) if self.today else 0
        )
        date_wide = chip or number.horizontalAdvance(self.number)
        # "Mon 21" where it fits, "M 21" where it does not, and the date alone below that.
        said = next(
            (
                words_
                for words_ in (DAYS[self.day], DAYS[self.day][0], "")
                if words.horizontalAdvance(words_) + gap + date_wide <= box.width() - 4
            ),
            "",
        )
        wide = words.horizontalAdvance(said) + (gap if said else 0)
        left = (box.width() - wide - date_wide) / 2 + box.left()
        middle = box.center().y()
        painter.setFont(name)
        painter.setPen(QColor(self.ink.text if self.today else self.ink.muted))
        painter.drawText(QPointF(left, middle + words.ascent() / 2 - words.descent() / 2), said)
        at = left + wide
        painter.setFont(figure)
        if self.today:
            pill = QRectF(at, middle - 13 * self.scale, chip, 26 * self.scale)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.accent))
            painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
            painter.setPen(QColor(self.accent_ink))
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, self.number)
        else:
            painter.setPen(QColor(self.ink.text))
            painter.drawText(QPointF(at, middle + number.ascent() / 2 - number.descent() / 2), self.number)
        painter.end()

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        super().leaveEvent(event)
        self.update()


@dataclass(frozen=True)
class TileDay:
    """What a day tile says: its name and date, its first item and how many follow, its time by
    category, its homework, and how many homework are due that day."""

    day: int
    date: int
    first: Occurrence | None
    more: int
    parts: tuple[tuple[str, int], ...]
    planned: int
    homework: int
    due: int
    today: bool


class DayTile(QPushButton):
    """One of the other days on the Today hero's board. Pointed at or reached with the keyboard it lifts
    with the large shadow and offers to take the hero's place; a click swaps it in."""

    def __init__(
        self, shown: TileDay, tokens: dict[str, str], radius: int, scale: float, board: Board
    ) -> None:
        super().__init__(f"{DAYS[shown.day]} {shown.date}")
        self.shown, self.tokens, self.radius, self.scale, self.board = shown, tokens, radius, scale, board
        self.ink = card_ink(tokens)
        self.setObjectName(f"bentoDay{shown.day}")
        self.setProperty("day_target", shown.day)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"Show {DAY_FULL[shown.day]} here")
        self.setAccessibleDescription(self._said())
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.lift = 0.0
        # Reduce motion and Off lift it at once and in place: the shadow and the edge, no rise.
        self.moves = moves()
        self._lifting = QVariantAnimation(self)
        self._lifting.setDuration(duration(LIFT_MS))
        self._lifting.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._lifting.valueChanged.connect(self._lifted)

    def _said(self) -> str:
        shown = self.shown
        parts = [f"{DAY_FULL[shown.day]} {shown.date}"]
        if shown.first is not None:
            parts.append(f"first {shown.first.title} at {clock_label(shown.first.start)}")
        parts.append(f"{length_label(shown.planned)} planned" if shown.planned else "nothing planned")
        if shown.homework:
            parts.append(f"{shown.homework} homework")
        if shown.due:
            parts.append(f"{shown.due} due")
        return ", ".join(parts)

    @property
    def ready(self) -> bool:
        return self.underMouse() or self.hasFocus()

    def _fonts(self) -> dict[str, QFont]:
        base = self.font()
        return {
            "name": at_scale(base, "body", self.scale, WEIGHT_REGULAR),
            "date": at_scale(base, "heading", self.scale, WEIGHT_STRONG),
            "flag": at_scale(base, "caption", self.scale, WEIGHT_STRONG),
            "title": at_scale(base, "body", self.scale, WEIGHT_STRONG),
            "small": time_font(at_scale(base, "caption", self.scale, WEIGHT_REGULAR)),
        }

    def sizeHint(self) -> QSize:  # noqa: N802
        fonts = self._fonts()
        lines = [QFontMetricsF(fonts[name]).lineSpacing() for name in ("date", "title", "small", "small")]
        return QSize(0, round(RISE + 24 * self.scale + sum(lines) + 16 * self.scale))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def card(self) -> QRectF:
        """The card as drawn now, in its own coordinates: room left above it to rise into."""
        rise = RISE * self.lift if self.moves else 0.0
        return QRectF(self.rect()).adjusted(0, RISE - rise, 0, -rise)

    def _aim(self, lifted: bool) -> None:
        target = 1.0 if lifted else 0.0
        self._lifting.stop()
        if not self.moves:
            self._lifted(target)
            return
        self._lifting.setStartValue(self.lift)
        self._lifting.setEndValue(target)
        self._lifting.start()

    def _lifted(self, value: object) -> None:
        self.lift = float(value)
        self.update()
        self.board.update()

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        self._aim(True)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._aim(self.hasFocus())

    def focusInEvent(self, event: object) -> None:  # noqa: N802
        super().focusInEvent(event)
        self._aim(True)

    def focusOutEvent(self, event: object) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self._aim(self.underMouse())

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink, shown, scale = self.ink, self.shown, self.scale
        card = self.card()
        shape = QPainterPath()
        shape.addRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), self.radius, self.radius)
        painter.fillPath(shape, QColor(ink.ground))
        dark = family(self.tokens) == "dark"
        if self.lift > 0 or dark:
            edge = QColor(self.tokens["accent"]) if self.lift > 0 else QColor(self.tokens["line"])
            if not dark:
                edge.setAlphaF(self.lift)
            painter.setPen(QPen(edge, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(shape)
        fonts = self._fonts()
        inside = card.adjusted(16 * scale, 12 * scale, -16 * scale, -12 * scale)
        date_metrics = QFontMetricsF(fonts["date"])
        head = QRectF(inside.left(), inside.top(), inside.width(), date_metrics.lineSpacing())
        baseline = head.top() + date_metrics.ascent()
        painter.setFont(fonts["name"])
        painter.setPen(QColor(ink.muted))
        name = DAYS[shown.day]
        painter.drawText(QPointF(head.left(), baseline), name)
        at = head.left() + QFontMetricsF(fonts["name"]).horizontalAdvance(name) + 5 * scale
        painter.setFont(fonts["date"])
        number = str(shown.date)
        if shown.today:
            chip = QRectF(
                at - 4 * scale, head.top(), date_metrics.horizontalAdvance(number) + 8 * scale, head.height()
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.tokens["accent"]))
            painter.drawRoundedRect(chip, chip.height() / 2, chip.height() / 2)
            painter.setPen(QColor(self.tokens["accent_ink"]))
            painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, number)
        else:
            painter.setPen(QColor(ink.text))
            painter.drawText(QPointF(at, baseline), number)
        self._flags(painter, head, fonts["flag"], at + date_metrics.horizontalAdvance(number) + 8 * scale)
        top = head.bottom() + 8 * scale
        title_metrics, small_metrics = QFontMetricsF(fonts["title"]), QFontMetricsF(fonts["small"])
        tall = title_metrics.lineSpacing() + small_metrics.lineSpacing()
        text_left = inside.left() + 3 + 8 * scale
        room = inside.right() - text_left
        if shown.first is not None:
            painter.fillRect(
                QRectF(inside.left(), top + 2, 3, tall - 4),
                QColor(paint_of(self.tokens, shown.first.category)[1]),
            )
            painter.setFont(fonts["title"])
            painter.setPen(QColor(ink.text))
            painter.drawText(
                QRectF(text_left, top, room, title_metrics.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                word_elide(shown.first.title, title_metrics, room),
            )
            when = clock_label(shown.first.start)
            more = f"{when} · {shown.more} more"
            if shown.more and small_metrics.horizontalAdvance(more) <= room:
                when = more
            painter.setFont(fonts["small"])
            painter.setPen(QColor(ink.muted))
            painter.drawText(
                QRectF(text_left, top + title_metrics.lineSpacing(), room, small_metrics.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                small_metrics.elidedText(when, Qt.TextElideMode.ElideRight, room),
            )
        else:
            painter.setFont(fonts["small"])
            painter.setPen(QColor(ink.muted))
            painter.drawText(
                QRectF(inside.left(), top, inside.width(), tall),
                Qt.AlignmentFlag.AlignLeft,
                "Nothing planned",
            )
        foot = QRectF(
            inside.left(), inside.bottom() - small_metrics.height(), inside.width(), small_metrics.height()
        )
        if self.ready:
            self._offer(painter, foot, fonts["flag"])
        else:
            words = short_length(shown.planned) if shown.planned else ""
            wide = small_metrics.horizontalAdvance(words) + (8 * scale if words else 0)
            bar = QRectF(foot.left(), foot.center().y() - 3 * scale, foot.width() - wide, 6 * scale)
            paint_parts(painter, bar, list(shown.parts))
            painter.setFont(fonts["small"])
            painter.setPen(QColor(ink.muted))
            painter.drawText(foot, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, words)
        painter.end()

    def _flags(self, painter: QPainter, head: QRectF, font: QFont, taken: float) -> None:
        """ "5 due" and the day's homework count with the book, at the right of its name, as many as fit
        clear of it, due first."""
        metrics = QFontMetricsF(font)
        scale, shown = self.scale, self.shown
        tall, icon = 20 * scale, round(12 * scale)
        right = head.right()
        top = head.center().y() - tall / 2
        painter.setFont(font)
        flags = [(f"{shown.due} due", False)] if shown.due else []
        flags += [(str(shown.homework), True)] if shown.homework else []
        for words, book in flags:
            wide = metrics.horizontalAdvance(words) + 16 * scale + (icon + 4 * scale if book else 0)
            if right - wide < taken:
                return
            box = QRectF(right - wide, top, wide, tall)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(paint_of(self.tokens, HOMEWORK)[0] if book else self.ink.track))
            painter.drawRoundedRect(box, RADIUS_CONTROL, RADIUS_CONTROL)
            if book:
                painter.drawPixmap(
                    QPointF(box.left() + 8 * scale, box.center().y() - icon / 2),
                    icons.pixmap("book-open", self.tokens["text"], icon, self.devicePixelRatioF()),
                )
            painter.setPen(QColor(self.tokens["text"]))
            words_box = box.adjusted(8 * scale + (icon + 4 * scale if book else 0), 0, -8 * scale, 0)
            painter.drawText(words_box, Qt.AlignmentFlag.AlignCenter, words)
            right = box.left() - 4 * scale

    def _offer(self, painter: QPainter, foot: QRectF, font: QFont) -> None:
        """ "Show Friday here" in the accent where the load was: the tile is ready to swap in."""
        icon = round(14 * self.scale)
        painter.drawPixmap(
            QPointF(foot.left(), foot.center().y() - icon / 2),
            icons.pixmap("maximize-2", self.ink.accent, icon, self.devicePixelRatioF()),
        )
        painter.setFont(font)
        painter.setPen(QColor(self.ink.accent))
        room = foot.adjusted(icon + 8 * self.scale, 0, 0, 0)
        words = f"Show {DAY_FULL[self.shown.day]} here"
        painter.drawText(
            room,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetricsF(font).elidedText(words, Qt.TextElideMode.ElideRight, room.width()),
        )


class Board(QWidget):
    """The page the tiles sit on. It draws each tile's soft shadow, and a day tile's large one as it
    lifts: a shadow effect on the hero would draw its hours again through a picture at every step of
    a drag."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("bentoBoard")
        self.tiles: list[QWidget] = []
        self.page, self.dark, self.radius = "#ffffff", False, RADIUS_SHEET

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(self.page))
        painter.setPen(Qt.PenStyle.NoPen)
        for tile in self.tiles:
            if not tile.isVisible():
                continue
            if isinstance(tile, DayTile):
                self._shadow(painter, tile.card().translated(QPointF(tile.pos())), tile.lift)
            else:
                self._shadow(painter, QRectF(tile.geometry()), 0.0)
        painter.end()

    def _shadow(self, painter: QPainter, card: QRectF, lift: float) -> None:
        """The small shadow, or `lift` of the way to the large one: rings of black under the card,
        outermost first, that add up to its opacity under the card and fade out at its blur."""
        small, large = SHADOW_SMALL, SHADOW_LARGE
        down = small.y + (large.y - small.y) * lift
        blur = small.blur + (large.blur - small.blur) * lift
        weak, strong = (
            (small.dark_opacity, large.dark_opacity) if self.dark else (small.opacity, large.opacity)
        )
        opacity = weak + (strong - weak) * lift
        steps = max(1, round(blur / 3))
        for step in range(steps):
            grow = blur / 2 * (steps - step) / steps
            painter.setBrush(QColor(0, 0, 0, max(1, round(255 * opacity / steps))))
            painter.drawRoundedRect(
                card.translated(0, down).adjusted(-grow, -grow, grow, grow),
                self.radius + grow,
                self.radius + grow,
            )


class BentoPainter(ClassicPainter):
    """The hero's hours on their card: a rule at each hour, today washed on the week, the time now as a
    line with its time on a pill in the gutter, and blocks in the category family with their 3-pixel
    edge. A block's name and times are in the caption size, as the mock-up writes them, so a
    half-hour block still says its name."""

    def __init__(self, tokens: dict[str, str], *, wide: bool = False) -> None:
        soft = mix_oklab(tokens["line"], tokens["surface"], 0.5)
        super().__init__(
            {
                "window": tokens["surface"],
                "panel": tokens["surface"],
                "hairline": soft,
                "rule": soft,
                "accent": tokens["accent"],
                "accent_ink": tokens["accent_ink"],
                "error": tokens["danger"],
                "text": tokens["text"],
                "muted": tokens["muted"],
            },
            wide=wide,
        )
        self.tokens = tokens

    @cached_property
    def measures(self) -> dict:
        # The week's narrow columns say a block's name and times; a day says its length too.
        return {**look_measures(None), "show_lengths": self.wide}

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        """Hour rules across the day and today's wash, with no rule between the days, as drawn; the
        time now crosses the rest of the week faintly."""
        area = track.area
        if today:
            wash = self.c("text")
            wash.setAlphaF(0.03)
            painter.fillRect(area, wash)
        painter.setPen(QPen(self.c("rule"), 1))
        for minute in range(-(-track.first // 60) * 60, track.last + 1, 60):
            at = area.top() + track.offset(minute)
            painter.drawLine(QPointF(area.left(), at), QPointF(area.right(), at))
        if not today and self.now_minute is not None and not self.wide:
            faint = self.c("accent")
            faint.setAlphaF(0.45)
            at = area.top() + track.offset(self.now_minute)
            painter.setPen(QPen(faint, 1))
            painter.drawLine(QPointF(area.left(), at), QPointF(area.right(), at))

    def fills(self, drawn: Drawn) -> tuple[QColor, QColor, QColor | None, QColor | None]:
        fill, mark = paint_of(self.tokens, drawn.category)
        if drawn.done or drawn.missed:
            paler = mix_oklab(fill, self.tokens["surface"], 0.5)
            return QColor(paler), QColor(self.tokens["muted"]), None, QColor(mark)
        return QColor(fill), QColor(self.tokens["text"]), None, QColor(mark)

    def fonts(self, base: QFont) -> tuple[QFont, QFont]:
        scale = self.scale(base)
        title = at_scale(base, "caption", scale, WEIGHT_STRONG)
        return title, time_font(at_scale(base, "caption", scale, WEIGHT_REGULAR))

    def words(
        self,
        painter: QPainter,
        rect: QRectF,
        drawn: Drawn,
        ink: QColor,
        visible: QRectF,
        fill: QColor | None = None,
        edge: QColor | None = None,
    ) -> None:
        """A week's column too narrow for a block's times says when it starts, as Retro's week does,
        rather than its name alone: "School" and "08:00", not "School"."""
        if not self.wide and not drawn.held:
            small = QFontMetricsF(self.fonts(painter.font())[1])
            if small.horizontalAdvance(drawn.times) > rect.width() - TEXT_LEFT - TEXT_RIGHT:
                drawn = Started(**vars(drawn))
        super().words(painter, rect, drawn, ink, visible, fill, edge)


class BentoCanvas(HoursCanvas):
    """Hours whose days are named by buttons above them, not on the canvas: the week's day names, or
    the Today hero's name of its day."""

    def __init__(self, hand: Hand, painter: BentoPainter, *, week: bool, gutter: float) -> None:
        super().__init__(hand, painter, self._seven if week else self._one, gutter=gutter)
        self.day = 0
        self.day_buttons: dict[int, QPushButton] = {}

    @staticmethod
    def _seven(area: QRectF) -> list[LinearTrack]:
        wide = area.width() / 7
        return [
            LinearTrack(
                day, QRectF(area.left() + day * wide + 2, area.top() + PAD, wide - 4, area.height() - 2 * PAD)
            )
            for day in range(7)
        ]

    def _one(self, area: QRectF) -> list[LinearTrack]:
        return [LinearTrack(self.day, area.adjusted(0, PAD, -4, -PAD))]

    def day_name(self, day: int) -> QPoint:
        pick = self.day_buttons.get(day)
        if pick is not None and pick.isVisible():
            return pick.mapToGlobal(pick.rect().center())
        return super().day_name(day)


class BentoHours(HoursScroll):
    """Hours that open at now in the middle, as every design's hours open (decision 12 of 0.17), and
    a day or week without now as the mock-up frames it: the first block a quarter of an hour under
    the top. Only opening is framed so: a time asked for later is the time shown."""

    # The first block's start, set each render; None frames nothing.
    first: int | None = None

    def open_at(self, key: object, minute: int, above: int | None = 90) -> None:
        if above is not None and self.first is not None:
            minute, above = self.first, 15
        super().open_at(key, minute, above)


class Row(QPushButton):
    """A button laid out as lines of words, as tall as its words: a QPushButton sizes itself to its
    own text and left the lines inside it no room."""

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.layout().sizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.layout().minimumSize()


def _length(px: int) -> int:
    return round((LAST - FIRST) / 60 * px) + 2 * PAD


def _detach(layout: QLayout, widget: QWidget, host: QWidget) -> bool:
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is widget:
            layout.takeAt(index)
            widget.hide()
            widget.setParent(host)
            return True
        child = item.widget()
        if child is not None and child.layout() is not None and _detach(child.layout(), widget, host):
            return True
        inner = item.layout()
        if inner is not None and _detach(inner, widget, host):
            return True
    return False


def _say(text: str, name: str, role: str = "", *, wrap: bool = False) -> QLabel:
    made = label(text, name, wrap=wrap)
    if role:
        made.setProperty("role", role)
    return made


def _rule() -> QFrame:
    """A hairline across a tile, between what is next and what follows it."""
    made = _frame("bentoRule")
    made.setFixedHeight(1)
    return made


def _frame(name: str, box: QLayout | None = None) -> QFrame:
    made = QFrame()
    made.setObjectName(name)
    if box is not None:
        made.setLayout(box)
        box.setContentsMargins(0, 0, 0, 0)
    return made


class BentoView(LayoutView):
    layout_id = "bento"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._board = Board()
        self._grid = QGridLayout(self._board)
        outer.addWidget(scrolling(self._board, "bentoScroll"))
        self._scrolls: dict[str, HoursScroll] = {}
        # The text size the hours were made at: their gutter is fixed when made.
        self._made_at: float | None = None
        # The day a click swapped into the Today hero, and the week it belongs to.
        self._picked: tuple[str, int] | None = None

    @property
    def cramped(self) -> bool:
        """Too narrow for the week beside its tiles. Larger text needs more room for the same seven
        columns, so the threshold grows with it."""
        scale = self._scene.scale if self._scene is not None else 1.0
        return 0 < self.width() < NARROW_WIDTH * max(scale, 1.0)

    def shown_day(self, scene: Scene) -> int:
        if scene.surface == "day" and scene.iso_day:
            for day in range(7):
                if scene.week.date_of(day).isoformat() == scene.iso_day:
                    return day
        return scene.today if scene.today is not None else 0

    def hero_day(self, scene: Scene) -> int:
        """The day the Today hero shows: the day open on Day; on Week, one a click swapped in, else
        today, else Monday."""
        if scene.surface == "day":
            return self.shown_day(scene)
        if self._picked is not None and self._picked[0] == scene.week.week_start:
            return self._picked[1]
        return scene.today if scene.today is not None else 0

    # Rendering

    def render(self, scene: Scene, week_changed: bool) -> None:
        if self._made_at != scene.scale:
            for kept in self._scrolls.values():
                kept.setParent(None)
                kept.deleteLater()
            self._scrolls, self._made_at = {}, scene.scale
        self.setStyleSheet(self._sheet(scene))
        for kept in self._scrolls.values():
            _detach(self._grid, kept, self._board)
        empty(self._grid)
        for index in range(8):
            self._grid.setColumnStretch(index, 0)
            self._grid.setColumnMinimumWidth(index, 0)
            self._grid.setRowStretch(index, 0)
            self._grid.setRowMinimumHeight(index, 0)
        px = scene.px
        self._grid.setContentsMargins(px(GAP), px(8), px(GAP), px(GAP))
        self._grid.setSpacing(px(GAP))
        board = self._board
        board.tiles = []
        board.page, board.dark = scene.tokens["bg"], family(scene.tokens) == "dark"
        board.radius = self._radius(scene)
        if scene.options.get("hero") == "today":
            self._render_today(scene)
        else:
            self._render_week(scene)
        board.update()

    def _radius(self, scene: Scene) -> int:
        return RADIUS_CONTROL if scene.options.get("corners") == "square" else RADIUS_SHEET

    # The week as the hero

    def _render_week(self, scene: Scene) -> None:
        is_day = scene.surface == "day"
        day = self.shown_day(scene)
        if is_day:
            hero, body = self._hero(scene, *self._day_heading(scene, day), legend=False)
            self._hours_into(body, scene, self._hours(scene, "day", day))
            body.addWidget(self._day_side(scene, day, DAY_SIDE))
        else:
            total = sum(item.minutes for item in scene.week.occurrences)
            hero, body = self._hero(scene, "This week", planned_words(total), "calendar-days", legend=True)
            self._hours_into(body, scene, self._hours(scene, "week", day))
        tiles = [
            self._next_tile(scene),
            self._due_tile(scene),
            self._load_tile(scene),
            self._tray_tile(scene, is_day),
        ]
        grid, px = self._grid, scene.px
        nxt, due, load, tray = tiles
        if self.cramped:
            # Not placed yet stays beside the hours, where a drag onto them starts. Under them, it was
            # past the bottom of a small window with large text.
            grid.setColumnStretch(0, 1)
            for tile in (load, tray):
                tile.setFixedWidth(px(SIDE))
            grid.addWidget(hero, 0, 0)
            grid.addWidget(tray, 0, 1)
            grid.setRowMinimumHeight(0, px(420))
            if nxt is not None:
                grid.addWidget(nxt, 1, 0, 1, 2)
            grid.addWidget(due, 2, 0)
            grid.addWidget(load, 2, 1)
        else:
            grid.setColumnStretch(0, 1)
            grid.addWidget(hero, 0, 0, 3, 1)
            if nxt is not None:
                grid.addWidget(nxt, 0, 1, 1, 2)
            for tile in (due, load, tray):
                tile.setFixedWidth(px(SIDE))
            grid.addWidget(due, 1, 1, 2, 1)
            grid.addWidget(load, 1, 2)
            grid.addWidget(tray, 2, 2)
            grid.setRowStretch(1, 1)
            grid.setRowStretch(2, 1)

    def _day_heading(self, scene: Scene, day: int) -> tuple[str, str, str]:
        """The hero's title, its line, and its icon on Day."""
        if day == scene.today:
            return "Today", self._day_line(scene, day), "sun"
        return f"{DAY_FULL[day]} {scene.week.date_of(day).day}", self._day_line(scene, day), "calendar-days"

    def _day_line(self, scene: Scene, day: int) -> str:
        """ "3 still to come · 1 homework" today, "9 h 45 min planned · 1 homework" on another day."""
        items = scene.week.on_day(day)
        planned = sum(item.minutes for item in items)
        work = sum(1 for item in items if item.work)
        parts = []
        ahead = (
            sum(1 for item in items if item.live and item.start > scene.minute) if day == scene.today else 0
        )
        if ahead:
            parts.append(f"{ahead} still to come")
        elif planned:
            parts.append(f"{length_label(planned)} planned")
        if work:
            parts.append(f"{work} homework")
        return " · ".join(parts) or "Nothing planned"

    def _hero_frame(self, scene: Scene) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
        """The hero tile, and the row in it for the hours and a side."""
        hero = self._tile_frame("bentoHero")
        painted = "hero" in scene.tokens
        hero.setProperty("painted", painted)
        box = QVBoxLayout(hero)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        body = QHBoxLayout()
        px = scene.px
        body.setSpacing(px(8 if painted else 16))
        body.setContentsMargins(px(8), 0, px(8 if painted else 16), px(8 if painted else 4))
        return hero, box, body

    def _hero(
        self, scene: Scene, title: str, line: str, icon: str, *, legend: bool
    ) -> tuple[QFrame, QHBoxLayout]:
        """The hero tile with its heading across the top, and the row under it."""
        hero, box, body = self._hero_frame(scene)
        px = scene.px
        head = QHBoxLayout()
        head.setContentsMargins(px(16), px(16), px(16), px(8))
        head.setSpacing(px(16))
        heading = self._heading(scene, title, line, icon, hero_ink(scene.tokens))
        head.addLayout(heading, 0)
        head.setAlignment(heading, Qt.AlignmentFlag.AlignTop)
        head.addStretch(1)
        if legend:
            head.addWidget(self._legend(scene, hero_ink(scene.tokens)), 1, Qt.AlignmentFlag.AlignTop)
        box.addLayout(head)
        box.addLayout(body, 1)
        return hero, body

    def _heading(self, scene: Scene, title: str | QWidget, line: str, icon: str, ink: Ink) -> QHBoxLayout:
        """The hero's icon in its square, its title, and the line under it."""
        px = scene.px
        row = QHBoxLayout()
        row.setSpacing(px(12))
        mark = QLabel()
        mark.setObjectName("bentoHeroIcon")
        mark.setFixedSize(px(36), px(36))
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(icons.pixmap(icon, ink.accent, px(18), self.devicePixelRatioF()))
        row.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        words = QVBoxLayout()
        words.setSpacing(0)
        words.addWidget(title if isinstance(title, QWidget) else _say(title, "bentoHeroTitle", "title"))
        words.addWidget(_say(line, "bentoHeroSub", "muted"))
        row.addLayout(words)
        return row

    def _hours_into(self, body: QHBoxLayout, scene: Scene, hours: HoursScroll) -> None:
        """The hours in the hero's row: on the hero itself when it is a card, or on a card of their own
        inside a hero a colourway paints."""
        hours.setMinimumHeight(scene.px(220))
        if "hero" in scene.tokens:
            card = _frame("bentoHoursCard", QVBoxLayout())
            card.layout().setContentsMargins(scene.px(8), 0, scene.px(8), 0)
            card.layout().addWidget(hours)
            body.addWidget(card, 1)
        else:
            body.addWidget(hours, 1)
        hours.show()

    def _hours(self, scene: Scene, key: str, day: int) -> HoursScroll:
        """The week's seven columns, or one day's, kept from render to render so they keep their zoom
        and where they were scrolled."""
        scroll = self._scrolls.get(key) or self._make_hours(scene, key)
        canvas = scroll.canvas
        assert isinstance(canvas, BentoCanvas)
        week = key == "week"
        canvas.set_painter(BentoPainter(scene.tokens, wide=not week))
        if week:
            canvas.set_week(scene.week.occurrences, scene.today, scene.minute)
            ink = card_ink(scene.tokens)
            for target, head in canvas.day_buttons.items():
                assert isinstance(head, DayHead)
                head.show_date(
                    scene.week.date_of(target).day, target == scene.today, ink, scene.tokens, scene.scale
                )
            assert isinstance(scroll, BentoHours)
            scroll.first = min((item.start for item in scene.week.occurrences if item.live), default=None)
            open_hours(scroll, scene.week.week_start, scene.week, scene.today, scene.minute)
        else:
            canvas.day_buttons = {}
            if day != canvas.day:
                canvas.day = day
                canvas.relayout()
            canvas.set_week(scene.week.on_day(day), scene.today, scene.minute)
            assert isinstance(scroll, BentoHours)
            scroll.first = min((item.start for item in scene.week.on_day(day) if item.live), default=None)
            open_hours(scroll, (scene.week.week_start, day), scene.week, scene.today, scene.minute, day)
        return scroll

    def _make_hours(self, scene: Scene, key: str) -> HoursScroll:
        week = key == "week"
        gutter = scene.px(GUTTER)
        canvas = BentoCanvas(self.hand, BentoPainter(scene.tokens, wide=not week), week=week, gutter=gutter)
        canvas.setObjectName("bentoWeekHours" if week else "bentoDayHours")
        canvas.setAccessibleName("The week's hours, a column for each day" if week else "The day's hours")
        canvas.day_opened.connect(self._open_day)
        scroll = BentoHours(
            canvas,
            WEEK_SCALE if week else DAY_SCALE,
            _length,
            name="bentoWeek" if week else "bentoDay",
            gutter=gutter,
        )
        self.keep_zoom(scroll)
        if week:
            header = QWidget()
            header.setObjectName("bentoWeekHeads")
            row = QHBoxLayout(header)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            for target in range(7):
                head = DayHead(target)
                head.clicked.connect(lambda _=False, chosen=target: self._open_day(chosen))
                row.addWidget(head, 1)
                canvas.day_buttons[target] = head
            scroll.set_header(header)
        self._scrolls[key] = scroll
        return scroll

    def _open_day(self, day: int) -> None:
        if self._scene is not None:
            self.day_activated.emit(self._scene.week.date_of(day).isoformat())

    # The small tiles

    def _tile_frame(self, name: str) -> QFrame:
        tile = QFrame()
        tile.setObjectName(name)
        tile.setProperty("tile", True)
        self._board.tiles.append(tile)
        return tile

    def _tile(
        self, scene: Scene, name: str, icon: str, words: str, extra: QWidget | None = None
    ) -> tuple[QFrame, QVBoxLayout]:
        """A small tile: a card with its icon and label across the top."""
        tile = self._tile_frame(name)
        box = QVBoxLayout(tile)
        px = scene.px
        box.setContentsMargins(px(16), px(16), px(16), px(16))
        box.setSpacing(px(8))
        box.addLayout(self._tile_head(scene, icon, words, name, card_ink(scene.tokens), extra))
        return tile, box

    def _tile_head(
        self, scene: Scene, icon: str, words: str, name: str, ink: Ink, extra: QWidget | None
    ) -> QHBoxLayout:
        px = scene.px
        row = QHBoxLayout()
        row.setSpacing(px(8))
        mark = QLabel()
        mark.setObjectName(f"{name}Icon")
        mark.setPixmap(icons.pixmap(icon, ink.muted, px(16), self.devicePixelRatioF()))
        row.addWidget(mark)
        row.addWidget(_say(words, f"{name}Label", "label"))
        row.addStretch(1)
        if extra is not None:
            row.addWidget(extra)
        return row

    def _tag(self, scene: Scene, category: str, ink: Ink) -> QWidget | None:
        """A category's swatch and name, as Next names what kind of thing it is."""
        name = (CATEGORIES.get(category) or {}).get("label")
        if not name:
            return None
        box = QHBoxLayout()
        box.setSpacing(scene.px(8))
        mark = QLabel()
        mark.setPixmap(swatch(category, scene.tokens, self.devicePixelRatioF(), scene.scale))
        box.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        box.addWidget(_say(name, "bentoNextTag", "muted"))
        return _frame("bentoNextTagRow", box)

    def _next_tile(self, scene: Scene) -> QFrame | None:
        """What is on now or next, the name large, when beside "in 20 min", and what follows. Only this
        week has a now."""
        said = coming(scene)
        if said is None:
            return None
        ink = card_ink(scene.tokens)
        tile, box = self._tile(scene, "bentoNext", "clock", said.label, self._tag(scene, said.category, ink))
        self._next_words(scene, box, said)
        if said.then:
            muted = html.escape(ink.muted)
            after = f' <span style="color:{muted}">·</span> '.join(
                f"{html.escape(item.title)} at {clock_label(item.start)}" for item in said.then
            )
            then = QLabel(f'<span style="color:{muted}">Then</span> {after}')
            then.setObjectName("bentoNextThen")
            then.setProperty("role", "then")
            then.setTextFormat(Qt.TextFormat.RichText)
            then.setWordWrap(True)
            box.addStretch(1)
            box.addWidget(_rule())
            box.addWidget(then)
        return tile

    def _next_words(self, scene: Scene, box: QVBoxLayout, said: Coming) -> None:
        box.addWidget(_say(said.title, "bentoNextTitle", "big", wrap=True))
        when = QHBoxLayout()
        when.setSpacing(scene.px(8))
        if said.when:
            shown = _say(said.when, "bentoNextWhen", "when")
            shown.setFont(time_font(shown.font()))
            when.addWidget(shown)
        if said.pill:
            when.addWidget(_say(said.pill, "bentoNextIn", "pill"), 0, Qt.AlignmentFlag.AlignVCenter)
        when.addStretch(1)
        box.addLayout(when)

    def _due_tile(self, scene: Scene) -> QFrame:
        """Homework still to do, soonest due first: the time left until the first is due, where each is
        placed, and how many are placed."""
        tile, box = self._tile(scene, "bentoDue", "calendar", "Due soon")
        listed = due_soon(scene.week)
        first = next((due for due in listed if due.due), None)
        if first is not None and scene.today is not None:
            value, until, past = time_left(first.due or "", scene.week.date_of(scene.today), scene.minute)
            figure = QVBoxLayout()
            figure.setSpacing(scene.px(2))
            figure.addWidget(_say(value, "bentoFigure", "danger" if past else "figure"))
            figure.addWidget(_say(until, "bentoDueUntil", "muted"))
            box.addLayout(figure)
            box.addSpacing(scene.px(4))
        if not listed:
            box.addWidget(
                _say("Nothing is due. Add homework when you get some.", "bentoDueEmpty", "muted", wrap=True)
            )
        rows = QVBoxLayout()
        rows.setSpacing(0)
        for index, due in enumerate(listed[:DUE_ROWS]):
            rows.addWidget(self._due_row(scene, index, due))
        box.addLayout(rows)
        if len(listed) > DUE_ROWS:
            box.addWidget(_say(f"{len(listed) - DUE_ROWS} more", "bentoDueMore", "muted"))
        box.addStretch(1)
        if listed:
            placed = sum(1 for due in listed if not due.waiting)
            meter = Stack("bentoDueMeter", scene.px(6))
            ink = card_ink(scene.tokens)
            meter.show_parts(
                [(paint_of(scene.tokens, HOMEWORK)[1], placed), (ink.track, len(listed) - placed)]
            )
            box.addWidget(meter)
            box.addWidget(_say(f"{placed} of {len(listed)} placed", "bentoDuePlaced", "muted"))
        return tile

    def _due_row(self, scene: Scene, index: int, due: Due) -> Row:
        px = scene.px
        where = f"placed {DAYS[due.at[0]]} {clock_label(due.at[1])}" if due.at is not None else "Not placed"
        meta = f"{short_length(due.minutes)} · {where}"
        row = Row()
        row.setObjectName(f"bentoDue{index}")
        row.setProperty("kind", "due")
        row.setProperty("block_id", due.block_id)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setAccessibleName(f"{due.title}, {meta}")
        row.setToolTip(f"Open {due.title}")
        grid = QGridLayout(row)
        grid.setContentsMargins(0, px(10), 0, px(10))
        grid.setHorizontalSpacing(px(8))
        grid.setVerticalSpacing(px(2))
        book = QLabel()
        book.setObjectName("bentoDueBook")
        book.setPixmap(
            icons.pixmap("book-open", paint_of(scene.tokens, HOMEWORK)[1], px(14), self.devicePixelRatioF())
        )
        title = _say(due.title, "bentoDueTitle", "strong")
        title.setToolTip(due.title)
        grid.addWidget(book, 0, 0, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(title, 0, 1)
        grid.addWidget(_say(meta, "bentoDueMeta", "muted"), 1, 0, 1, 2)
        grid.setColumnStretch(1, 1)
        for part in row.findChildren(QLabel):
            part.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        title.setMinimumWidth(1)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row.clicked.connect(lambda _=False, block_id=due.block_id: self.block_activated.emit(block_id))
        return row

    def _load_tile(self, scene: Scene) -> QFrame:
        """The week's homework: how much is placed and how much is still to go, and a bar for each day."""
        tile, box = self._tile(scene, "bentoLoad", "chart-column", "Homework load")
        week = scene.week
        by_day = [week.load_min(day) for day in range(7)]
        placed, to_go = sum(by_day), sum(item.minutes for item in week.waiting)
        figure = QVBoxLayout()
        figure.setSpacing(scene.px(2))
        if placed or to_go:
            figure.addWidget(_say(length_label(placed), "bentoFigure", "figure"))
            figure.addWidget(
                _say("placed" + (f", {short_length(to_go)} to go" if to_go else ""), "bentoLoadSub", "muted")
            )
        else:
            figure.addWidget(_say("No homework yet", "bentoLoadNone", "muted"))
        box.addLayout(figure)
        bars = LoadBars()
        bars.show_load(
            by_day, scene.today, card_ink(scene.tokens), paint_of(scene.tokens, HOMEWORK)[1], scene.scale
        )
        box.addWidget(bars, 1)
        return tile

    def _tray_tile(self, scene: Scene, is_day: bool) -> QFrame:
        """Homework not placed yet, as chips to drag onto the hours."""
        waiting = scene.week.waiting
        count = _say(str(len(waiting)), "bentoWaitingCount", "count") if waiting else None
        tile, box = self._tile(scene, "bentoWaiting", "list", "Not placed yet", count)
        for index, item in enumerate(waiting):
            box.addWidget(self._chip(scene, item, index))
        if not waiting:
            box.addWidget(_say("Everything you added has a time.", "bentoWaitingEmpty", "muted", wrap=True))
        box.addStretch(1)
        if waiting:
            hint = "Drag one onto your day." if is_day else "Drag one onto the week."
            box.addWidget(_say(hint, "bentoWaitingHint", "muted", wrap=True))
        return tile

    def _chip(self, scene: Scene, item: Waiting, index: int) -> Chip:
        chip = Chip(self.hand, item, scene.tokens, scene.scale)
        chip.setObjectName(f"bentoWaiting{index}")
        chip.setToolTip(item.reason)
        chip.clicked.connect(lambda _=False, block_id=item.block_id: self.block_activated.emit(block_id))
        return chip

    def _legend(self, scene: Scene, ink: Ink, *, columns: int = 0) -> Legend:
        """The week's categories, each with its swatch."""
        ratio = self.devicePixelRatioF()
        shown = [
            (swatch(category, scene.tokens, ratio, scene.scale), CATEGORIES[category]["label"])
            for category in CATEGORIES
            if any(item.category == category for item in scene.week.occurrences)
        ]
        return Legend(shown, ink.muted, scene.scale, columns)

    # A day beside its hours

    def _side(self, scene: Scene, width: int) -> tuple[QScrollArea, QVBoxLayout]:
        """The hero's side beside its hours. What does not fit its height scrolls, so the hero keeps
        the height the board gives it and the tiles under it stay on screen."""
        content = QWidget()
        content.setObjectName("bentoSideContent")
        box = QVBoxLayout(content)
        side = scrolling(content, "bentoSide")
        # setWidget fills it, and the window's page colour showed under the side.
        content.setAutoFillBackground(False)
        side.setFixedWidth(scene.px(width))
        side.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        overlay_scroll_bars(side)
        return side, box

    def _day_side(self, scene: Scene, day: int, width: int) -> QScrollArea:
        """Day's side of the hero: the day's time by category, and its free time."""
        side, box = self._side(scene, width)
        px = scene.px
        box.setContentsMargins(px(16), px(12), 0, px(12))
        box.setSpacing(px(8))
        self._summary(scene, day, box)
        box.addStretch(1)
        return side

    def _summary(self, scene: Scene, day: int, box: QVBoxLayout) -> None:
        """ "Your day": a thin bar of its time by category and a row for each, then its free time, from
        now on when it is today."""
        ink = hero_ink(scene.tokens)
        items = scene.week.on_day(day)
        head = QHBoxLayout()
        head.addWidget(_say("Your day", "bentoSumLabel", "label"))
        head.addStretch(1)
        planned = sum(item.minutes for item in items)
        head.addWidget(
            _say(
                f"{length_label(planned)} planned" if planned else "Nothing planned",
                "bentoSumPlanned",
                "muted",
            )
        )
        box.addLayout(head)
        bar = Stack("bentoSumBar", scene.px(8))
        bar.show_parts(day_parts(scene.week, day, scene.tokens, ink.track))
        box.addWidget(bar)
        rows = [
            (
                swatch(share.category, scene.tokens, self.devicePixelRatioF(), scene.scale),
                share.name,
                length_label(share.minutes),
            )
            for share in shares_of(scene.week, day)
        ]
        self._rows(scene, box, rows, "bentoSumRow")
        today = day == scene.today
        box.addSpacing(scene.px(12))
        box.addWidget(_say("Free from now" if today else "Free time", "bentoFreeLabel", "label"))
        slots = free_slots(items, scene.minute if today else None)
        free = swatch("free", scene.tokens, self.devicePixelRatioF(), scene.scale)
        self._rows(
            scene,
            box,
            [(free, range_label(*slot), length_label(slot[1] - slot[0])) for slot in slots],
            "bentoFreeRow",
        )
        if not slots:
            box.addWidget(
                _say(f"Nothing free before {clock_label(DAY_END)}", "bentoFreeNone", "muted", wrap=True)
            )

    def _rows(self, scene: Scene, box: QVBoxLayout, rows: list[tuple[QPixmap, str, str]], name: str) -> None:
        listed = QVBoxLayout()
        listed.setSpacing(0)
        box.addLayout(listed)
        for index, (mark, words, length) in enumerate(rows):
            line = QHBoxLayout()
            line.setSpacing(scene.px(8))
            dot = QLabel()
            dot.setPixmap(mark)
            line.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
            said = _say(words, f"{name}Name")
            said.setFont(time_font(said.font()))
            line.addWidget(said, 1)
            line.addWidget(_say(length, f"{name}Length", "quiet"))
            host = _frame(name, line)
            host.setProperty("rule", "bottom" if index < len(rows) - 1 else "")
            host.layout().setContentsMargins(0, scene.px(4), 0, scene.px(4))
            listed.addWidget(host)

    # Today as the hero

    def _render_today(self, scene: Scene) -> None:
        day = self.hero_day(scene)
        hero, box, body = self._hero_frame(scene)
        painted = "hero" in scene.tokens
        px = scene.px
        body.setContentsMargins(px(8), px(8), px(8 if painted else 16), px(8))
        box.addLayout(body, 1)
        self._hours_into(body, scene, self._hours(scene, "day", day))
        side, inner = self._side(scene, HERO_SIDE)
        inner.setContentsMargins(px(16), px(16), px(8) if painted else 0, px(12))
        inner.setSpacing(px(10))
        inner.addLayout(self._today_heading(scene, day))
        self._waiting_side(scene, inner)
        ink = hero_ink(scene.tokens)
        said = coming(scene) if day == scene.today else None
        if said is not None:
            card = QVBoxLayout()
            card.setSpacing(px(4))
            top = QHBoxLayout()
            top.addWidget(_say(said.label, "bentoNextLabel", "label"))
            top.addStretch(1)
            tag = self._tag(scene, said.category, ink)
            if tag is not None:
                top.addWidget(tag)
            card.addLayout(top)
            self._next_words(scene, card, said)
            inner.addLayout(card)
            inner.addWidget(_rule())
        if scene.surface == "day":
            self._summary(scene, day, inner)
            inner.addStretch(1)
        else:
            head = QHBoxLayout()
            head.addWidget(_say("Week at a glance", "bentoGlanceLabel", "label"))
            head.addStretch(1)
            head.addWidget(
                _say(
                    planned_words(sum(item.minutes for item in scene.week.occurrences)),
                    "bentoGlancePlanned",
                    "muted",
                )
            )
            inner.addLayout(head)
            glance = Glance()
            glance.show_week(scene.week, scene.today, scene.minute, scene.tokens, ink, scene.scale)
            inner.addWidget(glance, 1)
            inner.addWidget(self._legend(scene, ink, columns=3))
        body.addWidget(side)
        grid = self._grid
        others = [other for other in range(7) if other != day]
        columns = 3 if self.cramped else 6
        for column in range(columns):
            grid.setColumnStretch(column, 1)
        grid.addWidget(hero, 0, 0, 1, columns)
        grid.setRowStretch(0, 1)
        grid.setRowMinimumHeight(0, px(420))
        for index, other in enumerate(others):
            tile = DayTile(
                self._tile_day(scene, other), scene.tokens, self._radius(scene), scene.scale, self._board
            )
            tile.clicked.connect(lambda _=False, chosen=other: self._swap(chosen))
            self._board.tiles.append(tile)
            grid.addWidget(tile, 1 + index // columns, index % columns)

    def _today_heading(self, scene: Scene, day: int) -> QHBoxLayout:
        """The Today hero's day, and how much of it is still to come. On Week its name opens the day."""
        if scene.surface == "day":
            return self._heading(scene, *self._day_heading(scene, day), hero_ink(scene.tokens))
        date_of = scene.week.date_of(day)
        name = QPushButton(f"{DAY_FULL[day]} {date_of.day}")
        name.setObjectName("bentoHeroDay")
        name.setProperty("kind", "heading")
        name.setProperty("day_target", day)
        name.setCursor(Qt.CursorShape.PointingHandCursor)
        name.setToolTip(f"Open {DAY_FULL[day]}")
        name.clicked.connect(lambda _=False: self._open_day(day))
        canvas = self._scrolls["day"].canvas
        assert isinstance(canvas, BentoCanvas)
        canvas.day_buttons = {day: name}
        line = self._day_line(scene, day)
        if day == scene.today:
            line = f"Today · {line}"
        return self._heading(scene, name, line, "calendar-days", hero_ink(scene.tokens))

    def _waiting_side(self, scene: Scene, box: QVBoxLayout) -> None:
        """Not placed yet, first on the Today hero's side under the day's name, two chips to a row: the
        drag onto the hours this hero would otherwise have no way to start. Nothing when everything has
        a time. Under Next and the glance or the day's summary, which grow with their words, a short
        window or large text scrolled it out of sight."""
        waiting = scene.week.waiting
        if not waiting:
            return
        head = QHBoxLayout()
        head.addWidget(_say("Not placed yet", "bentoWaitingLabel", "label"))
        head.addWidget(_say(str(len(waiting)), "bentoWaitingCount", "count"))
        head.addStretch(1)
        box.addLayout(head)
        grid = QGridLayout()
        grid.setSpacing(scene.px(8))
        for index, item in enumerate(waiting):
            grid.addWidget(self._chip(scene, item, index), index // 2, index % 2)
        box.addLayout(grid)
        box.addWidget(_rule())

    def _tile_day(self, scene: Scene, day: int) -> TileDay:
        week = scene.week
        items = week.on_day(day)
        ink = card_ink(scene.tokens)
        return TileDay(
            day,
            week.date_of(day).day,
            items[0] if items else None,
            max(len(items) - 1, 0),
            tuple(day_parts(week, day, scene.tokens, ink.track)),
            sum(item.minutes for item in items),
            sum(1 for item in items if item.work),
            due_here(week, day),
            day == scene.today,
        )

    def _swap(self, day: int) -> None:
        """A day tile clicked: on Week it takes the hero's place; on Day it opens, which is the same."""
        scene = self._scene
        if scene is None:
            return
        if scene.surface == "day":
            self._open_day(day)
            return
        self._picked = (scene.week.week_start, day)
        self.render(scene, False)
        swapped = self._scrolls.get("day")
        if swapped is not None:
            swapped.canvas.setFocus()

    # Colours

    def _sheet(self, scene: Scene) -> str:
        tokens = scene.tokens
        card, hero = card_ink(tokens), hero_ink(tokens)
        radius = self._radius(scene)
        edge = tokens["line"] if family(tokens) == "dark" else "transparent"

        def size(role: str) -> str:
            return f"{type_pt(role, scene.scale)}pt"

        pill = f"{(QFontMetrics(at_scale(self.font(), 'caption', scene.scale)).height() + 4) // 2}px"
        on_hero = '#bentoHero[painted="true"]'
        clear = css(background="transparent")
        return base_sheet(self.objectName(), tokens) + rules(
            self.objectName(),
            {
                "#bentoScroll, #bentoBoard": css(background=tokens["bg"]),
                # Plain widgets on the tiles, which the window's stylesheet would paint its page colour.
                "#bentoWeekHeader, #bentoDayHeader, #bentoWeekZoom, #bentoDayZoom, #bentoWeekHeads": clear,
                "#bentoLegend, #bentoNextTagRow": clear,
                # Qt's holders of the scroll bars, which lie over the hours' right edge.
                "#qt_scrollarea_vcontainer, #qt_scrollarea_hcontainer": clear,
                'QFrame[tile="true"]': css(
                    background=card.ground, border=f"1px solid {edge}", border_radius=f"{radius}px"
                ),
                f"QFrame{on_hero}": css(background=hero.ground, border=f"1px solid {hero.ground}"),
                "QFrame#bentoHoursCard": css(background=card.ground, border_radius=f"{RADIUS_CARD}px"),
                '#bentoHero[painted="false"] #bentoSide': css(border_left=f"1px solid {card.line}"),
                "#bentoSide, #bentoSideContent, #bentoSide #qt_scrollarea_viewport": clear,
                "QFrame#bentoRule": css(background=card.line),
                # Styled so their rule is drawn, and clear so the window's page colour is not.
                'QFrame[rule="bottom"]': css(
                    background="transparent", border_bottom=f"1px solid {card.line}"
                ),
                "QLabel": css(color=card.text, font_size=size("body")),
                'QLabel[role="label"]': css(
                    color=card.muted, font_size=size("caption"), font_weight=WEIGHT_STRONG
                ),
                'QLabel[role="muted"]': css(color=card.muted, font_size=size("caption")),
                'QLabel[role="quiet"]': css(color=card.muted),
                'QLabel[role="strong"]': css(font_weight=WEIGHT_STRONG),
                'QLabel[role="title"]': css(font_size=size("heading"), font_weight=WEIGHT_STRONG),
                'QLabel[role="figure"], QLabel[role="danger"]': css(
                    font_size=size("title"), font_weight=WEIGHT_STRONG
                ),
                'QLabel[role="danger"]': css(color=tokens["danger"]),
                'QLabel[role="big"]': css(font_size=size("display"), font_weight=WEIGHT_STRONG),
                'QLabel[role="when"]': css(color=card.muted, font_size=size("heading")),
                'QLabel[role="then"]': css(font_size=size("caption")),
                'QLabel[role="pill"]': css(
                    background=card.tint,
                    color=card.accent,
                    font_size=size("caption"),
                    font_weight=WEIGHT_STRONG,
                    border_radius=pill,
                    padding=f"2px {scene.px(8)}px",
                ),
                'QLabel[role="count"]': css(
                    background=card.track,
                    color=card.text,
                    font_size=size("caption"),
                    font_weight=WEIGHT_STRONG,
                    border_radius=pill,
                    padding=f"2px {scene.px(8)}px",
                ),
                "QLabel#bentoHeroIcon": css(background=hero.tint, border_radius=f"{RADIUS_CARD}px"),
                'QPushButton[kind="due"]': css(
                    background="transparent",
                    border="none",
                    border_top=f"1px solid {card.line}",
                    border_radius="0px",
                    padding="0px",
                    min_height="0px",
                    text_align="left",
                ),
                'QPushButton[kind="due"]:hover': css(background=mix_oklab(card.text, card.ground, 0.04)),
                'QPushButton[kind="due"][keyfocus="true"]:focus': css(background=card.tint),
                'QPushButton[kind="heading"]': css(
                    background="transparent",
                    border="none",
                    border_radius=f"{RADIUS_CONTROL}px",
                    padding="0px",
                    min_height="0px",
                    text_align="left",
                    color=hero.text,
                    font_size=size("heading"),
                    font_weight=WEIGHT_STRONG,
                ),
                'QPushButton[kind="heading"]:hover': css(text_decoration="underline"),
                'QPushButton[kind="heading"][keyfocus="true"]:focus': css(border=f"2px solid {hero.accent}"),
                # On a hero a colourway paints, its words are in the colourway's ink.
                f"{on_hero} QLabel": css(color=hero.text),
                f'{on_hero} QLabel[role="label"], {on_hero} QLabel[role="muted"], '
                f'{on_hero} QLabel[role="when"], {on_hero} QLabel[role="quiet"]': css(color=hero.muted),
                f'{on_hero} QLabel[role="pill"]': css(background=hero.tint, color=hero.text),
                f'{on_hero} QLabel[role="count"]': css(background=hero.track, color=hero.text),
                f"{on_hero} QFrame#bentoRule": css(background=hero.line),
                f'{on_hero} QFrame[rule="bottom"]': css(border_bottom=f"1px solid {hero.line}"),
            },
        )
