"""Timeline: the week as a paper planner opened flat (0.17's Planner spread).

Week is two pages: Monday to Wednesday on the left, Thursday to Sunday on the right as it ships, each
day a column of hours, with the gutter between the pages and the hour rules running across both. A
handle on the fold, in the row of day names, moves days from one page to the other (J8). The seven
columns are one canvas, so a block carried from Wednesday to Thursday never leaves the surface it
started on. At the foot of the left page are the week's figures and what is next; at the foot of the
right, the homework not placed yet as sticky notes, and what is due this week.

Day opens the planner at one day: its hours on the left page; on the right its summary, what is next,
what is due this week and what is not placed yet. The mock-up's ruled space for notes is left out
until FlexWeek can keep notes: lines that look writable and keep nothing would mislead (Jonathan,
2026-09-29). Both are the shared hours, on the window's hand.
"""

from __future__ import annotations

import html
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import cached_property, partial

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFocusEvent, QFont, QFontMetricsF, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from desktop.native import icons
from desktop.native.calendar import DAY_FULL, DAYS
from desktop.native.fonts import at_scale, caption, time_font, weighted
from desktop.native.hours.canvas import (
    RADIUS_BLOCK,
    TODAY_WASH,
    BlockPainter,
    Drawn,
    HoursCanvas,
    fit_lines,
)
from desktop.native.hours.chips import TrayChip
from desktop.native.hours.classic import day_shares, open_hours
from desktop.native.hours.geometry import FIRST, LAST, LinearTrack
from desktop.native.hours.hand import Hand
from desktop.native.hours.zoom import HoursScroll, Scale
from desktop.native.layouts.base import (
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
)
from desktop.native.layouts.registry import MATCH, options_for
from desktop.native.look import FONT_FAMILIES, category_paint, look_measures, readable_ink
from desktop.native.tokens import (
    RADIUS_CARD,
    RADIUS_CONTROL,
    WEIGHT_REGULAR,
    WEIGHT_STRONG,
    mix_oklab,
    type_pt,
)
from desktop.native.weekmodel import (
    HOMEWORK,
    Occurrence,
    Waiting,
    WeekModel,
    clock_label,
    due_label,
    length_label,
    planned_line,
)
from desktop.native.widgets import FittedLabel, FlowLayout

DAY_SCALE = Scale("timeline.day", (36, 45, 60, 80, 120), 45)
# A level remembered for 0.16's lanes was an hour's width across a line; the columns keep their own.
WEEK_SCALE = Scale("timeline.spread", (28, 36, 48, 64, 96), 36)
# The days on the planner's left page as the design ships; the rest are on the right.
FOLD = int(options_for(None, "timeline")["fold"])
# Room above and below the hours for the first and last hour's label.
END_ROOM = 20
# The mock-up's measures at Normal text, in pixels: room round the spread; inside a page at its outer
# edge, by the gutter and at its top; the row of day names; the hour labels; a sticky note at the
# foot of the week and on Day.
AROUND = (16, 6, 16, 16)
OUTER, INNER, TOP = 18, 26, 14
HEADS, GUTTER = 44, 44
SQUARE_NOTE = (132, 94)
WIDE_NOTE = 216
# The least room the list of what is due takes beside the notes.
DUE_WIDE = 230
# How much of the page's room Compact keeps.
COMPACT = 0.6
# The sheet of the next pages, showing under each page's foot.
SHEET = 3


def pages_of(left: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """The days on each page, with the first `left` of the week on the left one."""
    return tuple(range(left)), tuple(range(left, 7))


def fold_at(left: int, width: float) -> float:
    """Where the fold runs across hours `width` wide with `left` days on the left page: after `left`
    + 1 of eight equal shares, the hour labels' column counting as one. At 3 | 4 that is the middle,
    where the fold always was, and each day across moves it about a column."""
    return width * (left + 1) / 8


def landing(tracks: list[LinearTrack], at: float) -> int:
    """The days on the left page if the fold were let go at `at`: each day whose middle is left of it,
    so the fold snaps to the nearest day edge. Never fewer than one on either page."""
    return min(max(sum(track.area.center().x() < at for track in tracks), 1), 6)


def _run(days: tuple[int, ...]) -> str:
    """A page's days as "Mon–Tue", or one day's short name."""
    first, last = DAYS[days[0]], DAYS[days[-1]]
    return first if first == last else f"{first}–{last}"


def _spread(inner: float, left: int, area: QRectF) -> list[LinearTrack]:
    """The first `left` days on the left page, right of the hour labels, and the rest on the right,
    `inner` clear of the fold on either side. Each page's days share its width equally."""
    fold = fold_at(left, area.right())
    top, tall = area.top() + END_ROOM / 2, area.height() - END_ROOM
    tracks = []
    for days, (start, end) in zip(
        pages_of(left), ((area.left(), fold - inner), (fold + inner, area.right())), strict=True
    ):
        wide = (end - start) / len(days)
        tracks += [
            LinearTrack(day, QRectF(start + at * wide, top, wide, tall)) for at, day in enumerate(days)
        ]
    return tracks


def _column(day: int, area: QRectF) -> list[LinearTrack]:
    return [LinearTrack(day, area.adjusted(0, END_ROOM / 2, 0, -END_ROOM / 2))]


def _length(px: int) -> int:
    return round((LAST - FIRST) / 60 * px) + END_ROOM


@dataclass(frozen=True)
class Due:
    """Homework due this week, as the notes list it: where its first session is, or None while one
    of its sessions waits for a time."""

    title: str
    at: tuple[int, int] | None
    due: str | None = None


def due_this_week(week: WeekModel) -> list[Due]:
    """What is not placed yet first, by when it is due; then the rest by where they are placed."""
    first, last = week.date_of(0).isoformat(), week.date_of(6).isoformat()

    def this_week(due: str | None) -> bool:
        return bool(due) and first <= (due or "")[:10] <= last

    waiting: dict[str, Due] = {}
    for item in week.waiting:
        if this_week(item.due):
            waiting.setdefault(item.assignment_id or item.block_id, Due(item.title, None, item.due))
    placed: dict[str, Due] = {}
    for entry in week.occurrences:
        key = entry.assignment_id or entry.block_id
        if entry.work and this_week(entry.due) and key not in waiting:
            placed.setdefault(key, Due(entry.title, (entry.day, entry.start), entry.due))
    return [*waiting.values(), *sorted(placed.values(), key=lambda due: due.at or (0, 0))]


def week_figures(week: WeekModel) -> tuple[tuple[str, str], ...]:
    """The foot of the left page: the minutes of homework planned, how many homework are done (each
    with every one of its sessions finished), and how many sessions wait for a time."""
    homework: dict[str, list[bool]] = {}
    for entry in week.occurrences:
        if entry.work:
            homework.setdefault(entry.assignment_id or entry.block_id, []).append(entry.done)
    for item in week.waiting:
        homework.setdefault(item.assignment_id or item.block_id, []).append(False)
    done = sum(all(finished) for finished in homework.values())
    planned = sum(entry.minutes for entry in week.occurrences if entry.work)
    return (
        (length_label(planned), "homework planned"),
        (f"{done} of {len(homework)}" if homework else "0", "done"),
        (str(len(week.waiting)), "not placed yet"),
    )


def next_up(scene: Scene) -> Occurrence | None:
    """The next thing to start today, on this week."""
    if scene.today is None:
        return None
    return next(
        (entry for entry in scene.week.on_day(scene.today) if entry.live and entry.start > scene.minute), None
    )


def _when(entry: Occurrence, minute: int) -> str:
    return f"at {clock_label(entry.start)}, in {length_label(entry.start - minute)}"


def _due_words(due: str | None) -> str:
    """When homework is due: "due Sun 4 Oct", without a clock so it is not read as a placed time."""
    if not due:
        return ""
    words = due_label(due, "")
    return f"due {words.split(',')[0]}" if words else ""


def _placed_words(at: tuple[int, int] | None) -> str:
    """Where a session sits, in those words, so the time is not read as its deadline."""
    if at is None:
        return "Not placed yet"
    return f"placed {DAYS[at[0]]} {clock_label(at[1])}"


def _paint(tokens: dict[str, str], category: str) -> tuple[str, str]:
    """A category's fill and mark in the one family, on this design's pages."""
    fill, mark = category_paint(category, {"family": family(tokens), "panel": tokens["surface"]})
    return fill or tokens["surface"], mark or tokens["line"]


class TimelinePainter(BlockPainter):
    """Ruled paper. The hours are ruled at each hour on the spread's pages, with a hairline between
    days; blocks are cards in their category's colour outlined in ink, with its tab down the start
    edge."""

    def __init__(
        self,
        tokens: dict[str, str],
        *,
        edged: frozenset[int] = frozenset(),
        wide: bool = False,
        spine: float = 0,
        pages: tuple[tuple[int, ...], ...] = pages_of(FOLD),
    ) -> None:
        soft = mix_oklab(tokens["line"], tokens["surface"], 0.5)
        super().__init__(
            {
                "window": tokens["surface"],
                "hairline": soft,
                "rule": soft,
                "accent": tokens["accent"],
                "accent_ink": tokens["accent_ink"],
                "accent_text": tokens.get("accent_text", tokens["accent"]),
                "now": tokens.get("now", tokens["accent"]),
                "selection": tokens.get("selection", tokens["accent"]),
                "error": tokens["danger"],
                "text": tokens["text"],
                "muted": tokens["muted"],
                "block_edge": tokens["block_edge"],
            },
            wide=wide,
        )
        self.tokens = tokens
        # The days with a hairline down their start edge: every column but the first on the right page.
        self.edged = edged
        # While today is on the right page, which has no hour labels, the room between the pages at
        # the fold, where the time now goes if it fits; otherwise 0. Beside the labels it takes the
        # place of the one nearest it, as in Today's app.
        self.spine = spine
        self.pages = pages
        self._ink = QColor(mix_oklab(tokens["text"], tokens["surface"], 0.78))
        # Set as each block is drawn, for `fonts`: one on Day too short for a line at the body size,
        # whose title is then in the caption size, as the mock-up writes "Dinner 18:30–19:00 · 30 min".
        self._tiny = False

    @cached_property
    def measures(self) -> dict:
        # The week's narrow columns say a block's name and times; Day says its length too.
        return {**look_measures(self.look), "show_lengths": self.wide}

    def background(self, painter: QPainter, rect: QRectF) -> None:
        """Nothing: the pages under the hours are the spread's."""

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        area = track.area
        if today:
            wash = self.c("text")
            wash.setAlphaF(TODAY_WASH)
            painter.fillRect(area, wash)
        painter.setPen(QPen(self.c("rule"), 1))
        for minute in range(-(-track.first // 60) * 60, track.last + 1, 60):
            at = area.top() + track.offset(minute)
            painter.drawLine(QPointF(area.left(), at), QPointF(area.right(), at))
        if track.day in self.edged:
            painter.drawLine(area.topLeft(), area.bottomLeft())

    def fills(self, drawn: Drawn) -> tuple[QColor, QColor, QColor | None, QColor | None]:
        fill, mark = _paint(self.tokens, drawn.category)
        paper = self.tokens["surface"]
        if drawn.done or drawn.missed:
            return QColor(paper), QColor(self.tokens["muted"]), None, QColor(mark)
        return QColor(fill), QColor(self.tokens["text"]), None, QColor(mark)

    def fonts(self, base: QFont) -> tuple[QFont, QFont]:
        title, small = super().fonts(base)
        if self._tiny:
            title = at_scale(base, "caption", self.scale(base), WEIGHT_STRONG)
        return title, small

    def block(self, painter: QPainter, rect: QRectF, drawn: Drawn, visible: QRectF) -> None:
        self._tiny = False
        body = QFontMetricsF(self.fonts(painter.font())[0]).lineSpacing()
        self._tiny = self.wide and rect.height() + 0.5 < body
        super().block(painter, rect, drawn, visible)
        if not (drawn.held or drawn.chosen):
            painter.setPen(QPen(self._ink, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                rect.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS_BLOCK - 0.5, RADIUS_BLOCK - 0.5
            )

    def hour_labels(
        self,
        painter: QPainter,
        track: LinearTrack,
        room: float,
        every: int = 60,
        visible: QRectF | None = None,
    ) -> None:
        font = QFont(painter.font())
        self.now_in_gutter = self._beside_labels(font)
        super().hour_labels(painter, track, room, every, visible)
        if self.now_in_gutter and self.now_minute is not None:
            painter.setFont(font)
            at = track.area.top() + track.offset(self.now_minute)
            pill = self._pill_width(font, self.now_minute)
            self._now_pill(painter, track.area.left() - 3 - pill, at, self.now_minute)

    def now(self, painter: QPainter, track: LinearTrack, minute: int) -> None:
        """A line across the day at `minute`. Its time is on a pill beside the hour labels
        (`hour_labels`), or for a day on the right page in the middle of the fold: beside today's own
        column the pill lay on the day before and covered its blocks."""
        area = track.area
        at = area.top() + track.offset(minute)
        painter.setPen(QPen(self.c("now"), 2))
        painter.drawLine(QPointF(area.left(), at), QPointF(area.right(), at))
        if not self._beside_labels(painter.font()):
            page = next(days for days in self.pages if track.day in days)
            fold = area.left() - page.index(track.day) * area.width() - self.spine / 2
            self._now_pill(painter, fold - self._pill_width(painter.font(), minute) / 2, at, minute)

    def _beside_labels(self, base: QFont) -> bool:
        """Whether the pill goes beside the hour labels: unless today is on the right page and the
        pill fits the fold with a pixel to spare on either side. In Compact it does not."""
        return self.now_minute is None or self._pill_width(base, self.now_minute) + 2 > self.spine

    @staticmethod
    def _pill_font(base: QFont) -> QFont:
        return weighted(time_font(caption(base)), WEIGHT_STRONG)

    def _pill_width(self, base: QFont, minute: int) -> float:
        return QFontMetricsF(self._pill_font(base)).horizontalAdvance(clock_label(minute)) + 6

    def _now_pill(self, painter: QPainter, left: float, at: float, minute: int) -> None:
        """The time now on a pill from `left`, in the canvas's font `painter` has."""
        colour = self.c("now")
        font = self._pill_font(painter.font())
        words = clock_label(minute)
        width, height = self._pill_width(painter.font(), minute), QFontMetricsF(font).height() + 2
        pill = QRectF(max(0, left), at - height / 2, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawRoundedRect(pill, height / 2, height / 2)
        painter.setPen(QColor(readable_ink(colour.name())))
        painter.setFont(font)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, words)


class Spread(QWidget):
    """A planner opened flat: two pages joined at a fold line down the middle, and the next sheet
    showing under their foot. What is laid on it is clear, so its paper shows."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.setObjectName(name)
        self.tokens: dict[str, str] = {}
        # Where the fold runs across it, asked as it paints; the middle when not set, as on Day.
        self.fold: Callable[[], float] | None = None

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if not self.tokens:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paper, edge = QColor(self.tokens["surface"]), QColor(self.tokens["line"])
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5 - SHEET)
        painter.setPen(QPen(edge, 1))
        painter.setBrush(paper)
        for sheet in (box.translated(0, SHEET).adjusted(1, 0, -1, 0), box):
            painter.drawRoundedRect(sheet, RADIUS_CARD, RADIUS_CARD)
        fold = self.fold() if self.fold is not None else self.width() / 2
        painter.setPen(QPen(edge, 1))
        painter.drawLine(QPointF(fold, box.top()), QPointF(fold, box.bottom()))
        painter.end()


class DayHeading(QPushButton):
    """A day's name over its column, with its date right after it, today's in an accent chip. The
    name shortens to "Wed" before it would be cut. On Week a click opens the day."""

    opened = Signal(int)
    PAD, GAP = 8, 6

    def __init__(self, day: int, name: str, opens: bool) -> None:
        super().__init__()
        self.day = day
        self.setObjectName(name)
        self.setProperty("kind", "heading")
        self.setAccessibleName(f"Show {DAY_FULL[day]}" if opens else DAY_FULL[day])
        if opens:
            self.setProperty("day_target", day)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(f"Open {DAY_FULL[day]}")
            self.clicked.connect(lambda _=False: self.opened.emit(self.day))
        else:
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row = QHBoxLayout(self)
        row.setContentsMargins(self.PAD, 0, 0, 0)
        row.setSpacing(self.GAP)
        self.title = label(DAY_FULL[day], "timelineDayName")
        # Two labels shown in turn: Qt keeps a label's padding from its first styling, so a date
        # restyled as today's chip later lost the chip's padding.
        self.date = label("", "timelineDate")
        self.chip = label("", "timelineChip")
        for part in (self.title, self.date, self.chip):
            part.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            # A styled label counts as framed and is indented by half a letter; the chip's own padding
            # is all the room it needs.
            part.setIndent(0)
            row.addWidget(part, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)

    def set_date(self, number: int, today: bool) -> None:
        self.date.setText(str(number))
        self.chip.setText(str(number))
        self.date.setVisible(not today)
        self.chip.setVisible(today)
        self._fit()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit()

    def _fit(self) -> None:
        """The whole name if it fits beside the date, else its short form, closer to its edge and its
        date in a narrow column; shortened further only if even that does not fit. Measured in the
        name's own styled face."""
        tag = self.chip if self.chip.isVisibleTo(self) else self.date
        for part in (self.title, tag):
            part.ensurePolished()
        metrics = self.title.fontMetrics()
        full, short = DAY_FULL[self.day], DAYS[self.day]
        room = self.width() - self.PAD - self.GAP - tag.sizeHint().width()
        pad, gap = (self.PAD, self.GAP) if metrics.horizontalAdvance(short) <= room else (2, 3)
        self.layout().setContentsMargins(pad, 0, 0, 0)
        self.layout().setSpacing(gap)
        room = self.width() - pad - gap - tag.sizeHint().width()
        words = full if metrics.horizontalAdvance(full) <= room else short
        self.title.setText(metrics.elidedText(words, Qt.TextElideMode.ElideRight, max(room, 0)))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, super().minimumSizeHint().height())


class FoldHandle(QWidget):
    """The fold's handle in the row of day names, "‹ 3 | 4 ›": the days on each page. Dragged sideways
    it carries the fold to the day edge nearest the pointer, a day changing page once the pointer
    passes its middle; ‹ and ›, or Left and Right with focus on it, move one day across. It takes its
    own presses, so a drag started here never picks up a block from the hours."""

    moved = Signal(int)
    # Room either side of the words, and the share of its width at each end that is ‹ or ›.
    PAD, ENDS = 6, 0.3

    def __init__(self, heads: Heads) -> None:
        super().__init__(heads)
        self.heads = heads
        self.setObjectName("timelineFold")
        self.setToolTip("Drag to move days between the pages")
        self.setAccessibleName("Fold between the pages")
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.left = FOLD
        self.tokens: dict[str, str] = {}
        self.scale = 1.0
        # Where it was pressed, and once that became a drag, the days the left page would hold if
        # let go now.
        self._pressed: QPointF | None = None
        self._landing: int | None = None

    def text(self) -> str:
        return "".join(self._parts())

    def _parts(self) -> tuple[str, str, str]:
        """‹, the days on each page as it would be let go now, and ›."""
        shown = self.left if self._landing is None else self._landing
        return "‹", f" {shown} | {7 - shown} ", "›"

    def carrying(self) -> bool:
        return self._landing is not None

    def show_fold(self, left: int, tokens: dict[str, str], scale: float) -> None:
        self.left, self.tokens, self.scale = left, tokens, scale
        self.setAccessibleDescription(
            f"{plural(left, 'day')} on the left page, {7 - left} on the right. Left and Right move one "
            "day across."
        )
        self.resize(self.sizeHint())
        self.update()

    def _font(self) -> QFont:
        return at_scale(self.font(), "caption", self.scale, WEIGHT_STRONG)

    def sizeHint(self) -> QSize:  # noqa: N802
        metrics = QFontMetricsF(self._font())
        # As wide as its widest counts, so it keeps its size while they change under a drag.
        wide = max(metrics.horizontalAdvance(f"‹ {left} | {7 - left} ›") for left in range(1, 7))
        return QSize(round(wide + 2 * self.PAD * self.scale), round(metrics.height() + 6 * self.scale))

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if not self.tokens:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        held = self.carrying()
        accent = QColor(self.tokens["accent"])
        box = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        edge = accent if held or self.hasFocus() else QColor(self.tokens["line"])
        painter.setPen(QPen(edge, 2 if self.hasFocus() else 1))
        painter.setBrush(accent if held else QColor(self.tokens["surface"]))
        painter.drawRoundedRect(box, box.height() / 2, box.height() / 2)
        font = self._font()
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        back, counts, forward = self._parts()
        ink = QColor(self.tokens["accent_ink"] if held else self.tokens["text"])
        arrows = ink if held else QColor(self.tokens.get("accent_text", self.tokens["accent"]))
        at = box.center().x() - metrics.horizontalAdvance(self.text()) / 2
        for words, colour in ((back, arrows), (counts, ink), (forward, arrows)):
            wide = metrics.horizontalAdvance(words)
            painter.setPen(colour)
            painter.drawText(QRectF(at, box.top(), wide, box.height()), Qt.AlignmentFlag.AlignCenter, words)
            at += wide
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._pressed = event.position()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._pressed is None:
            return
        travelled = abs(event.position().x() - self._pressed.x())
        if not self.carrying() and travelled < QApplication.startDragDistance():
            return
        canvas = self.heads.canvas
        self._landing = landing(canvas.tracks, canvas.mapFromGlobal(event.globalPosition()).x())
        canvas.show_landing((self.left, self._landing))
        # Under the pointer while it is carried, as the mock-up draws it.
        across = self.heads.mapFromGlobal(event.globalPosition()).x()
        self.move(round(across - self.width() / 2), self.y())
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pressed, landed = self._pressed, self._landing
        if pressed is None:
            super().mouseReleaseEvent(event)
            return
        self._let_go()
        if landed is not None:
            self._go(landed)
        elif pressed.x() < self.width() * self.ENDS:
            self._go(self.left - 1)
        elif pressed.x() > self.width() * (1 - self.ENDS):
            self._go(self.left + 1)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Left:
            self._go(self.left - 1)
        elif event.key() == Qt.Key.Key_Right:
            self._go(self.left + 1)
        elif event.key() == Qt.Key.Key_Escape and self._pressed is not None:
            self._let_go()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self.update()

    def _let_go(self) -> None:
        self._pressed = self._landing = None
        self.heads.canvas.show_landing(None)
        self.heads.place()
        self.update()

    def _go(self, left: int) -> None:
        left = min(max(left, 1), 6)
        if left != self.left:
            self.moved.emit(left)


class Heads(QFrame):
    """The days' names over their columns, kept above the hours as they scroll, and on Week the
    fold's handle between the pages."""

    opened = Signal(int)

    def __init__(self, canvas: TimelineCanvas, days: tuple[int, ...], opens: bool) -> None:
        super().__init__()
        self.setObjectName("timelineHeads")
        self.canvas = canvas
        self.opens = opens
        self.headings: dict[int, DayHeading] = {}
        # Day is one page of hours beside its notes, with no fold to move.
        self.handle = FoldHandle(self) if opens else None
        self.show_days(days)
        canvas.heads = self

    def show_days(self, days: tuple[int, ...]) -> None:
        if tuple(self.headings) == days:
            return
        for heading in self.headings.values():
            heading.setParent(None)
            heading.deleteLater()
        name = "timelineWeekDay{}" if self.opens else "timelineDayHead"
        self.headings = {day: DayHeading(day, name.format(day), self.opens) for day in days}
        for heading in self.headings.values():
            heading.setParent(self)
            heading.opened.connect(self.opened)
            heading.show()
        self.place()

    def place(self) -> None:
        """Each name over its column: the canvas's hours start after the hour labels, and this row
        after the zoom above them."""
        for track in self.canvas.tracks:
            heading = self.headings.get(track.day)
            if heading is not None:
                left = round(track.area.left() - self.canvas.gutter)
                heading.setGeometry(
                    QRect(left, 0, round(track.area.right() - self.canvas.gutter) - left, self.height())
                )
        handle, split = self.handle, self.canvas.split
        if handle is not None and split is not None and not handle.carrying():
            across = fold_at(split[0], self.canvas.width()) - self.canvas.gutter
            handle.move(round(across - handle.width() / 2), round((self.height() - handle.height()) / 2))
            # Over the day names, which are made again when the days shown change.
            handle.raise_()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.place()


def _page_of(widget: QWidget | None) -> QScrollArea | None:
    """The scroll area holding this one: the page, where the hours' own scroll is inside it."""
    found = widget.parentWidget() if widget is not None else None
    while found is not None and not isinstance(found, QScrollArea):
        found = found.parentWidget()
    return found


class TimelineCanvas(HoursCanvas):
    """Hours on a page that scrolls too, in a short window: a time is brought on screen in the hours
    and then in the page. The week's day names are the headings over its columns."""

    def __init__(self, hand: Hand, painter: TimelinePainter, lay_out) -> None:
        super().__init__(hand, painter, lay_out)
        self.heads: Heads | None = None
        # On Week: the days on the left page and the room either side of the fold. None on Day.
        self.split: tuple[int, int] | None = None
        # The pages' feet side by side, as wide as the pages over them.
        self.feet: QBoxLayout | None = None
        # While the fold's handle is carried: the days the left page has, and would have if let go.
        self.landing: tuple[int, int] | None = None

    def relayout(self) -> None:
        super().relayout()
        if self.feet is not None and self.split is not None:
            left, inner = self.split
            fold = fold_at(left, self.width())
            # The feet run under the hours' scroll bar too, so the right one reaches past the canvas.
            scroll = self._scroll_area()
            reach = scroll.width() if scroll is not None else self.width()
            for at, wide in enumerate((fold - inner, reach - fold - inner)):
                if self.feet.stretch(at) != max(round(wide), 1):
                    self.feet.setStretch(at, max(round(wide), 1))
        if self.heads is not None:
            self.heads.place()

    def fold_x(self) -> float:
        """Where the fold runs across the hours."""
        return fold_at(self.split[0], self.width()) if self.split is not None else self.width() / 2

    def show_landing(self, landing: tuple[int, int] | None) -> None:
        self.landing = landing
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        super().paintEvent(event)
        if self.landing is None or len(self.tracks) != 7:
            return
        painter = QPainter(self)
        try:
            self._paint_landing(painter, *self.landing)
        finally:
            painter.end()

    def _paint_landing(self, painter: QPainter, now: int, then: int) -> None:
        """Where the fold lands if let go: the days that change page tinted, a dashed line at the day
        edge it snaps to, and the pages that makes named at the top of the line."""
        tokens = self.painter.tokens
        areas = {track.day: track.area for track in self.tracks}
        if then < now:
            moving, at = range(then, now), areas[then].left()
        elif then > now:
            moving, at = range(now, then), areas[then - 1].right()
        else:
            moving, at = range(0), self.fold_x()
        accent = QColor(tokens["accent"])
        wash = QColor(accent)
        wash.setAlphaF(0.12)
        for day in moving:
            painter.fillRect(areas[day], wash)
        # On a whole pixel, so the dashes are the accent and not a blend of it.
        at = round(at)
        painter.setPen(QPen(accent, 2, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(at, 0), QPointF(at, self.height()))
        visible = self._visible()
        left, right = pages_of(then)
        words = f"{_run(left)} | {_run(right)}"
        font = weighted(caption(self.font()), WEIGHT_STRONG)
        metrics = QFontMetricsF(font)
        box = QRectF(0, 0, metrics.horizontalAdvance(words) + 16, metrics.height() + 6)
        box.moveCenter(QPointF(at, visible.top() + 6 + box.height() / 2))
        box.moveLeft(min(max(box.left(), 0), self.width() - box.width()))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens["text"]))
        painter.drawRoundedRect(box, box.height() / 2, box.height() / 2)
        painter.setPen(QColor(tokens["surface"]))
        painter.setFont(font)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, words)

    def day_name(self, day: int) -> QPoint:
        heading = self.heads.headings.get(day) if self.heads is not None else None
        if heading is None or heading.property("day_target") is None:
            return super().day_name(day)
        return heading.mapToGlobal(heading.rect().center())

    def reveal(self, day: int, first: int, last: int) -> None:
        super().reveal(day, first, last)
        track = self.track_for(day, first) or self.track_for(day)
        page = _page_of(self._scroll_area())
        if page is None or track is None:
            return
        for minute in (last, first):
            local = track.point_for(min(max(minute, track.first), track.last)).toPoint()
            inside = self.mapTo(page.widget(), local)
            page.ensureVisible(inside.x(), inside.y(), 20, 60)

    def in_view(self, day: int, minute: int) -> bool:
        if not super().in_view(day, minute):
            return False
        page = _page_of(self._scroll_area())
        track = self.track_for(day, minute)
        if page is None or track is None:
            return True
        port = page.viewport()
        return (
            port.rect().adjusted(-2, -2, 2, 2).contains(self.mapTo(port, track.point_for(minute).toPoint()))
        )


class Note(TrayChip):
    """Homework not placed yet as a sticky note, set a little askew: its colour with a deeper strip
    along the top, the book and its name, how long it takes and when it is due. Square at the foot
    of the week, wide on Day. Drag it onto a day to give it a time; a click opens it."""

    def __init__(
        self, hand: Hand, waiting: Waiting, tokens: dict[str, str], *, tilt: float, square: bool, scale: float
    ) -> None:
        super().__init__(hand, waiting)
        self.setText(waiting.title)
        self.setProperty("note", True)
        self.tokens, self.tilt, self.square, self.scale = tokens, tilt, square, scale
        self.length = length_label(waiting.minutes)
        self.due = _due_words(waiting.due)
        self.fill, self.mark = _paint(tokens, waiting.category or HOMEWORK)

    def _fit(self) -> None:
        # Painted whole each time: the title wraps and shortens in the paint.
        return

    def _fonts(self) -> tuple[QFont, QFont]:
        # Both weights named: the window's stylesheet sets a button's font at 600.
        title = at_scale(self.font(), "caption" if self.square else "body", self.scale, WEIGHT_STRONG)
        return title, time_font(at_scale(self.font(), "caption", self.scale, WEIGHT_REGULAR))

    def _pad(self) -> tuple[float, float, float]:
        """Its padding at the top, the sides and the foot."""
        return tuple(size * self.scale for size in ((12, 10, 8) if self.square else (13, 12, 10)))

    def _meta(self) -> list[str]:
        parts = [self.length, *([self.due] if self.due else [])]
        return parts if self.square else [" · ".join(parts)]

    def sizeHint(self) -> QSize:  # noqa: N802
        if self.square:
            return QSize(round(SQUARE_NOTE[0] * self.scale), round(SQUARE_NOTE[1] * self.scale))
        title, small = self._fonts()
        top, side, foot = self._pad()
        book = QFontMetricsF(title).ascent() + 5
        words = max(
            QFontMetricsF(title).horizontalAdvance(self._title) + book,
            QFontMetricsF(small).horizontalAdvance(self._meta()[0]),
        )
        tall = top + QFontMetricsF(title).lineSpacing() + 2 + QFontMetricsF(small).lineSpacing() + foot
        return QSize(round(max(WIDE_NOTE * self.scale, words + 2 * side) + 4), round(tall + 4))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        hint = self.sizeHint()
        return QSize(min(hint.width(), round(WIDE_NOTE * self.scale * 0.6)), hint.height())

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        centre = QRectF(self.rect()).center()
        painter.translate(centre)
        painter.rotate(self.tilt)
        painter.translate(-centre)
        # Clear of the widget's edge, so its turned corners are not cut.
        body = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        fill = QColor(self.fill)
        painter.fillRect(body, fill)
        painter.fillRect(
            QRectF(body.left(), body.top(), body.width(), 5 * self.scale),
            QColor(mix_oklab(self.mark, self.fill, 0.30)),
        )
        if self.hasFocus():
            painter.setPen(QPen(QColor(self.tokens["accent"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(body.adjusted(1, 1, -1, -1))
        ink = self.tokens["text"]
        title, small = self._fonts()
        top, side, foot = self._pad()
        metrics = QFontMetricsF(title)
        icon = round(metrics.ascent())
        book = icon + 5
        room = QRectF(body.left() + side + book, body.top() + top, body.width() - 2 * side - book, 0)
        lines = fit_lines(self._title, title, room.width(), metrics.lineSpacing() * (2 if self.square else 1))
        painter.drawPixmap(
            QPointF(room.left() - book, room.top() + (metrics.height() - icon) / 2),
            icons.pixmap("book-open", ink, icon, self.devicePixelRatioF()),
        )
        painter.setPen(QColor(ink))
        painter.setFont(title)
        for at, line in enumerate(lines):
            box = QRectF(room.left(), room.top() + at * metrics.lineSpacing(), room.width(), metrics.height())
            painter.drawText(box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, line)
        meta = self._meta()
        line = QFontMetricsF(small).lineSpacing()
        below = (
            body.bottom() - foot - line * len(meta) if self.square else room.top() + metrics.lineSpacing() + 2
        )
        painter.setPen(QColor(mix_oklab(ink, self.fill, 0.72)))
        painter.setFont(small)
        for at, words in enumerate(meta):
            box = QRectF(body.left() + side, below + at * line, body.width() - 2 * side, line)
            painter.drawText(box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, words)
        painter.end()


class Split(QFrame):
    """Two parts side by side while it is `wide` enough for both, and one over the other when not,
    as the foot of the right page is in a narrow window or at large text."""

    def __init__(self, name: str, wide: int, gap: int) -> None:
        super().__init__()
        self.setObjectName(name)
        self.wide = wide
        self.box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(gap)
        # Its page's half of the spread, whatever its parts would like: the direction follows that.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        side = self.width() >= self.wide
        direction = QBoxLayout.Direction.LeftToRight if side else QBoxLayout.Direction.TopToBottom
        if self.box.direction() != direction:
            self.box.setDirection(direction)


@dataclass
class Pages:
    """A spread kept between renders: its hours, which keep their zoom and place, and the parts laid
    out again each time."""

    spread: Spread
    hours: HoursScroll
    # The two pages' parts side by side, the gutter between them.
    row: QBoxLayout
    feet: tuple[QVBoxLayout, ...]


def _frame(name: str, box: QBoxLayout | None = None) -> QFrame:
    made = QFrame()
    made.setObjectName(name)
    if box is not None:
        made.setLayout(box)
        box.setContentsMargins(0, 0, 0, 0)
    return made


def _clear(area: QScrollArea) -> QScrollArea:
    """A scroll area on the spread whose content lets the paper show. setWidget fills it, and a
    picture of the design drawn outside the window, as setup's are, showed grey under the hours."""
    area.widget().setAutoFillBackground(False)
    return area


class TimelineView(LayoutView):
    layout_id = "timeline"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._page = QWidget()
        self._page.setObjectName("timelinePage")
        self._root = QVBoxLayout(self._page)
        outer.addWidget(scrolling(self._page, "timelineScroll"))
        self._pages: dict[str, Pages] = {}
        # The text size they were made at: their gutter and the pages' measures are fixed when made.
        self._made_at: float | None = None

    def render(self, scene: Scene, week_changed: bool) -> None:
        tight = COMPACT if scene.options.get("density") == "compact" else 1.0
        if self._made_at != scene.scale:
            for kept in self._pages.values():
                kept.spread.setParent(None)
                kept.spread.deleteLater()
            self._pages, self._made_at = {}, scene.scale
        self.setStyleSheet(self._sheet(scene))
        px = scene.px
        self._root.setContentsMargins(*(px(size * tight) for size in AROUND))
        key = "day" if scene.surface == "day" else "week"
        pages = self._pages.get(key) or self._make(key, scene)
        for kept in self._pages.values():
            kept.spread.setVisible(kept is pages)
        pages.spread.tokens = scene.tokens
        pages.spread.update()
        outer, top, inner = px(OUTER * tight), px(TOP * tight), px(INNER * tight)
        pages.spread.layout().setContentsMargins(outer, top, outer, top + SHEET)
        pages.row.setSpacing(2 * inner)
        if key == "day":
            self._render_day(scene, pages, tight)
        else:
            self._render_week(scene, pages, inner, tight)

    def _make(self, key: str, scene: Scene) -> Pages:
        px = scene.px
        spread = Spread(f"timeline{key.title()}Spread")
        day = key == "day"
        layout = QHBoxLayout(spread) if day else QVBoxLayout(spread)
        layout.setSpacing(0)
        # Laid out and painted as each render says.
        canvas = TimelineCanvas(self.hand, TimelinePainter(scene.tokens), None)
        heads = Heads(canvas, () if day else tuple(range(7)), not day)
        heads.opened.connect(self._open_day)
        if heads.handle is not None:
            heads.handle.moved.connect(self._fold_moved)
        heads.setFixedHeight(px(HEADS))
        if day:
            canvas.setObjectName("timelineHours")
            canvas.setAccessibleName("The day's page of hours")
            hours = HoursScroll(canvas, DAY_SCALE, _length, name="timelineDay", gutter=px(GUTTER))
        else:
            canvas.setObjectName("timelineSpread")
            canvas.setAccessibleName("The week on two pages, a column of hours for each day")
            canvas.setAccessibleDescription(
                "Drag a block up or down to change its time, or onto another day's column. Pull its top "
                "or bottom edge to resize it, or drag empty time to add something. Click a block to open it."
            )
            hours = HoursScroll(canvas, WEEK_SCALE, _length, name="timelineWeek", gutter=px(GUTTER))
        self.keep_zoom(hours)
        hours.zoomed.connect(lambda _key, _px, kept=hours: self._fit_hours(kept, self._scene))
        hours.set_header(heads)
        _clear(hours)
        feet: list[QVBoxLayout] = []
        # Capped at the length of the hours, which then sit at the top of their page.
        layout.addWidget(hours, 1)
        if day:
            notes = QVBoxLayout()
            notes_page = _frame("timelineNotesPage", notes)
            layout.addWidget(_clear(scrolling(notes_page, "timelineNotesScroll")), 1)
            feet.append(notes)
            row: QBoxLayout = layout
        else:
            row = QHBoxLayout()
            for name in ("timelineWeekFoot", "timelineNotesFoot"):
                foot = QVBoxLayout()
                page_foot = _frame(name, foot)
                # As wide as its page, whatever its parts would like: the canvas sets the stretches.
                page_foot.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                row.addWidget(page_foot, 1)
                feet.append(foot)
            layout.addWidget(_frame("timelineFeet", row))
            canvas.feet = row
            spread.fold = lambda: canvas.mapTo(spread, QPoint(0, 0)).x() + canvas.fold_x()
        self._root.addWidget(spread, 1)
        made = Pages(spread, hours, row, tuple(feet))
        self._pages[key] = made
        return made

    def _fit_hours(self, hours: HoursScroll, scene: Scene | None) -> None:
        """No taller than the hours and their names: past that the foot of the page takes the room."""
        if scene is None:
            return
        hours.setMinimumHeight(min(scene.px(220), _length(hours.px)))
        hours.setMaximumHeight(max(30, hours.header.sizeHint().height()) + _length(hours.px))

    # Week

    def _render_week(self, scene: Scene, pages: Pages, inner: int, tight: float) -> None:
        hours = pages.hours
        canvas = hours.canvas
        left = int(scene.options.get("fold", FOLD))
        pages_now = pages_of(left)
        canvas.split = (left, inner)
        canvas._lay_out = partial(_spread, inner, left)
        spine = 2 * inner if scene.today in pages_now[1] else 0
        # A hairline down each day's start edge, but the first on the right page, which is the fold's.
        edged = frozenset(range(7)) - {left}
        canvas.set_painter(TimelinePainter(scene.tokens, edged=edged, spine=spine, pages=pages_now))
        if canvas.heads is not None and canvas.heads.handle is not None:
            canvas.heads.handle.show_fold(left, scene.tokens, scene.scale)
        canvas.relayout()
        self._date_heads(scene, canvas.heads)
        canvas.set_week(_shown(scene, scene.week.occurrences), scene.today, scene.minute)
        open_hours(hours, scene.week.week_start, scene.week, scene.today, scene.minute)
        self._fit_hours(hours, scene)
        left, right = pages.feet
        for foot in (left, right):
            empty(foot)
            foot.parentWidget().setContentsMargins(0, scene.px(12 * tight), 0, 0)
        self._figures(scene, left)
        self._notes_foot(scene, right)

    def _figures(self, scene: Scene, foot: QVBoxLayout) -> None:
        """This week in figures, and what is next."""
        px = scene.px
        foot.setSpacing(px(8))
        foot.addWidget(label("This week", "timelineLabel"))
        row = QHBoxLayout()
        row.setSpacing(px(32))
        for value, words in week_figures(scene.week):
            pair = QVBoxLayout()
            pair.setSpacing(px(2))
            pair.addWidget(label(value, "timelineStat"))
            pair.addWidget(label(words, "timelineStatWord"))
            row.addLayout(pair)
        row.addStretch(1)
        foot.addLayout(row)
        coming = next_up(scene)
        if coming is not None:
            muted = scene.tokens["muted"]
            line = QLabel(
                f'<span style="color:{muted}">Next</span> {html.escape(coming.title)} '
                f'<span style="color:{muted}">{_when(coming, scene.minute)}</span>'
            )
            line.setObjectName("timelineNext")
            line.setTextFormat(Qt.TextFormat.RichText)
            line.setWordWrap(True)
            foot.addSpacing(px(4))
            foot.addWidget(line)
        foot.addStretch(1)

    def _notes_foot(self, scene: Scene, foot: QVBoxLayout) -> None:
        """Not placed yet as sticky notes, and what is due this week beside them."""
        px = scene.px
        # Two square notes side by side, as the mock-up's 276 pixels hold, at any text size.
        wide = 2 * round(SQUARE_NOTE[0] * scene.scale) + px(12)
        split = Split("timelineNotesSplit", wide + px(24) + px(DUE_WIDE), px(24))
        notes = _frame("timelineNotes", QVBoxLayout())
        notes.setFixedWidth(wide)
        self._waiting(scene, notes.layout(), square=True)
        split.box.addWidget(notes, 0, Qt.AlignmentFlag.AlignTop)
        due = _frame("timelineDue", QVBoxLayout())
        self._due(scene, due.layout(), big=False)
        split.box.addWidget(due, 1, Qt.AlignmentFlag.AlignTop)
        foot.addWidget(split)
        foot.addStretch(1)

    # Day

    def _render_day(self, scene: Scene, pages: Pages, tight: float) -> None:
        day = self.shown_day(scene)
        hours = pages.hours
        canvas = hours.canvas
        canvas._lay_out = partial(_column, day)
        canvas.set_painter(TimelinePainter(scene.tokens, wide=True))
        if canvas.heads is not None:
            canvas.heads.show_days((day,))
        canvas.relayout()
        self._date_heads(scene, canvas.heads)
        canvas.set_week(_shown(scene, scene.week.on_day(day)), scene.today, scene.minute)
        open_hours(hours, (scene.week.week_start, day), scene.week, scene.today, scene.minute, day)
        self._fit_hours(hours, scene)
        (notes,) = pages.feet
        empty(notes)
        px = scene.px
        notes.parentWidget().setContentsMargins(px(4), px(12 * tight), px(4), 0)
        notes.setSpacing(px(24 * tight))
        is_today = day == scene.today
        notes.addLayout(self._summary(scene, day, is_today))
        coming = next_up(scene) if is_today else None
        if coming is not None:
            section = self._section(scene, "Next")
            line = QLabel(
                f'<span style="font-weight:{WEIGHT_STRONG}">{html.escape(coming.title)}</span> '
                f'<span style="color:{scene.tokens["muted"]}">{_when(coming, scene.minute)}</span>'
            )
            line.setObjectName("timelineNext")
            line.setTextFormat(Qt.TextFormat.RichText)
            line.setWordWrap(True)
            section.addWidget(line)
            notes.addLayout(section)
        section = QVBoxLayout()
        section.setSpacing(0)
        self._due(scene, section, big=True)
        notes.addLayout(section)
        section = QVBoxLayout()
        section.setSpacing(px(6))
        self._waiting(scene, section, square=False)
        notes.addLayout(section)
        notes.addStretch(1)

    def shown_day(self, scene: Scene) -> int:
        if scene.surface == "day" and scene.iso_day:
            for day in range(7):
                if scene.week.date_of(day).isoformat() == scene.iso_day:
                    return day
        return scene.today if scene.today is not None else 0

    def _summary(self, scene: Scene, day: int, is_today: bool) -> QVBoxLayout:
        """The day's homework planned and done, and its time by category, each with its dot."""
        px = scene.px
        section = self._section(scene, "Today" if is_today else DAY_FULL[day])
        work = [entry for entry in scene.week.on_day(day) if entry.work]
        planned = planned_line(
            sum(entry.minutes for entry in work), sum(entry.minutes for entry in work if entry.done)
        )
        section.addWidget(label(planned, "timelineSum"))
        grid = QGridLayout()
        grid.setContentsMargins(0, px(4), 0, 0)
        grid.setHorizontalSpacing(px(24))
        grid.setVerticalSpacing(px(6))
        for at, share in enumerate(day_shares(scene.week, day)):
            row = QHBoxLayout()
            row.setSpacing(px(8))
            dot = QFrame()
            dot.setObjectName("timelineDot")
            dot.setFixedSize(px(8), px(8))
            dot.setStyleSheet(
                f"background: {_paint(scene.tokens, share.category)[1]}; border-radius: {px(8) // 2}px;"
            )
            row.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(label(share.name, "timelineShare"))
            row.addStretch(1)
            row.addWidget(label(length_label(share.minutes), "timelineShareLength"))
            grid.addLayout(row, at // 2, at % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        section.addLayout(grid)
        return section

    # Shared

    def _section(self, scene: Scene, words: str) -> QVBoxLayout:
        section = QVBoxLayout()
        section.setSpacing(scene.px(6))
        section.addWidget(label(words, "timelineLabel"))
        return section

    def _date_heads(self, scene: Scene, heads: Heads | None) -> None:
        for day, heading in (heads.headings if heads is not None else {}).items():
            heading.set_date(scene.week.date_of(day).day, day == scene.today)

    def _waiting(self, scene: Scene, box: QVBoxLayout, *, square: bool) -> None:
        """Not placed yet, as sticky notes set a little askew each way in turn."""
        waiting = scene.week.waiting
        if not waiting:
            return
        box.setSpacing(scene.px(8))
        box.addWidget(label("Not placed yet", "timelineTrayLabel"))
        notes = FlowLayout(gap=scene.px(12))
        tilts = (-1.4, 1.0) if square else (-1.2, 0.9)
        for index, item in enumerate(waiting):
            note = Note(
                self.hand, item, scene.tokens, tilt=tilts[index % 2], square=square, scale=scene.scale
            )
            note.setObjectName(f"timelineWaiting{index}")
            note.clicked.connect(lambda _=False, block_id=item.block_id: self.block_activated.emit(block_id))
            notes.addWidget(note)
        host = QFrame()
        host.setObjectName("timelineNoteRow")
        host.setLayout(notes)
        notes.setContentsMargins(0, 0, 0, 0)
        box.addWidget(host)

    def _due(self, scene: Scene, box: QVBoxLayout, *, big: bool) -> None:
        """Homework due this week: when each is due, and where it is placed."""
        px = scene.px
        box.addWidget(label("Due this week", "timelineLabel"))
        box.addSpacing(px(6))
        listed = due_this_week(scene.week)
        if not listed:
            box.addWidget(label("Nothing is due this week.", "timelineHint", wrap=True))
            return
        icon = px(13)
        book = icons.pixmap("book-open", scene.tokens["text"], icon, self.devicePixelRatioF())
        for due in listed:
            row = QHBoxLayout()
            row.setSpacing(px(6))
            line = _frame("timelineDueRow", row)
            line.setProperty("ruled", big)
            line.setFixedHeight(px(40 if big else 34))
            mark = QLabel()
            mark.setObjectName("timelineDueBook")
            mark.setPixmap(book)
            column = QVBoxLayout()
            column.setSpacing(0)
            column.setContentsMargins(0, 0, 0, 0)
            title = FittedLabel(minimum=px(40))
            title.setObjectName("timelineDueTitle")
            title.setProperty("big", big)
            title.set_full_text(due.title)
            deadline, placed = _due_words(due.due), _placed_words(due.at)
            where = label(" · ".join(part for part in (deadline, placed) if part), "timelineDueWhen")
            if due.at is None:
                where.setProperty("open", True)
            column.addWidget(title)
            column.addWidget(where)
            row.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
            row.addLayout(column, 1)
            box.addWidget(line)

    def _fold_moved(self, left: int) -> None:
        """The fold let go somewhere new: the pages are laid out again now, and the window keeps it
        with the look."""
        if self._scene is None:
            return
        self.show_week(replace(self._scene, options={**self._scene.options, "fold": str(left)}))
        self.option_set.emit("fold", str(left))

    def _open_day(self, day: int) -> None:
        if self._scene is not None:
            self.day_activated.emit(self._scene.week.date_of(day).isoformat())

    def _sheet(self, scene: Scene) -> str:
        tokens = scene.tokens
        text, muted, accent = tokens["text"], tokens["muted"], tokens["accent"]
        soft = mix_oklab(tokens["line"], tokens["surface"], 0.5)

        def size(role: str) -> str:
            return f"{type_pt(role, scene.scale)}pt"

        # The design's own colourways are its catalogue's pairing, Newsreader over Inter; in Match my
        # look its headings take the look's heading face (look.HEADING_NAMES).
        serif = css(font_family=FONT_FAMILIES["serif"]) if scene.options.get("colour", MATCH) != MATCH else ""
        chip = round(20 * scene.scale)
        clear = css(background="transparent")
        return base_sheet(self.objectName(), tokens) + rules(
            self.objectName(),
            {
                "#timelineScroll, #timelinePage": css(background=tokens["bg"]),
                # Plain widgets on the pages, which the window's stylesheet would paint its page colour.
                "#timelineWeekHeader, #timelineDayHeader, #timelineWeekZoom, #timelineDayZoom": clear,
                # Qt's holders of the scroll bars, which lie over the pages' right edge.
                "#qt_scrollarea_vcontainer, #qt_scrollarea_hcontainer": clear,
                "QLabel": css(color=text),
                'QPushButton[kind="heading"]': css(
                    background="transparent",
                    border="none",
                    border_radius=f"{RADIUS_CONTROL}px",
                    padding="0",
                    min_height="0",
                ),
                'QPushButton[kind="heading"]:hover': css(background=mix_oklab(text, tokens["surface"], 0.04)),
                'QPushButton[kind="heading"][keyfocus="true"]:focus': css(border=f"2px solid {accent}"),
                "QLabel#timelineDayName": css(font_size=size("heading"), font_weight=WEIGHT_STRONG) + serif,
                "QLabel#timelineDate": css(color=muted, font_size=size("caption")),
                "QLabel#timelineChip": css(
                    background=accent,
                    color=tokens["accent_ink"],
                    font_weight=WEIGHT_STRONG,
                    border_radius=f"{chip // 2}px",
                    padding=f"0 {round(8 * scene.scale)}px",
                    min_height=f"{chip}px",
                    max_height=f"{chip}px",
                ),
                "QFrame#timelineWeekFoot, QFrame#timelineNotesFoot": css(
                    border_top=f"1px solid {tokens['line']}"
                ),
                "QLabel#timelineLabel, QLabel#timelineTrayLabel": css(
                    color=muted, font_size=size("caption"), font_weight=WEIGHT_STRONG
                ),
                "QLabel#timelineStat": css(font_size=size("title"), font_weight=WEIGHT_STRONG) + serif,
                "QLabel#timelineStatWord, QLabel#timelineHint, QLabel#timelineShareLength": css(
                    color=muted, font_size=size("caption")
                ),
                "QLabel#timelineShare": css(font_size=size("caption")),
                "QLabel#timelineNext, QLabel#timelineSum": css(font_size=size("body")),
                'QFrame#timelineDueRow[ruled="true"]': css(border_bottom=f"1px solid {soft}"),
                "QLabel#timelineDueTitle": css(font_size=size("caption")),
                'QLabel#timelineDueTitle[big="true"]': css(font_size=size("body")),
                "QLabel#timelineDueWhen": css(color=muted, font_size=size("caption")),
                'QLabel#timelineDueWhen[open="true"]': css(color=accent, font_weight=WEIGHT_STRONG),
            },
        )


def _shown(scene: Scene, items: tuple[Occurrence, ...]) -> list[Occurrence]:
    """What the hours draw: everything, or with Finished and past items hidden, what is still ahead."""
    if scene.options.get("finished") != "hide":
        return list(items)
    today = scene.today

    def over(item: Occurrence) -> bool:
        if today is None:
            return False
        return item.day < today or (item.day == today and item.end <= scene.minute)

    return [item for item in items if item.live and not over(item)]
