"""Hours a student can drag on, drawn any way a design likes.

An `HoursCanvas` is one painted widget holding one or more tracks: a day's column, seven columns, a
lane per day, a card laid at an angle. It draws the week's blocks on them through a `BlockPainter`,
which is the only thing a design replaces to look like itself, and passes every press to the window's
`Hand`, which owns the gestures. While something is held, the canvas draws it where it would land,
with its times written on it. When a new week arrives with blocks somewhere else, such as after Plan,
they slide from where they were to where they are, and blocks that were not there fade in.

The canvas also answers the rig and the tests in global coordinates: where a day and minute are,
where a block is drawn, and how to bring a stretch of hours into view.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QRect, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QFontMetrics,
    QFontMetricsF,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QScrollArea, QWidget

from desktop.native import icons
from desktop.native.calendar import DAYS, create_click_range
from desktop.native.fonts import at_scale, caption, time_font, weighted
from desktop.native.hours.geometry import (
    BETWEEN,
    Axis,
    LinearTrack,
    Span,
    overlap_columns,
    snap,
)
from desktop.native.hours.hand import Create, Gesture, Hand, Held, Verdict, span_words
from desktop.native.look import (
    block_paint,
    category_paint,
    contrast,
    look_measures,
    mix,
    readable_ink,
    text_scale,
)
from desktop.native.motion import DURATION_MS, app_level
from desktop.native.tokens import RADIUS_CONTROL, TYPE_PT, WEIGHT_REGULAR, WEIGHT_STRONG
from desktop.native.weekmodel import Occurrence, clock_label, length_label, range_label, short_clock

# A press this close to a block's start or end edge resizes it, on a block long enough to have edges.
EDGE_PX = 7
# Decision 14 of 0.17: a 3-pixel category edge, and the words kept this far inside a block.
EDGE_WIDTH = 3
RADIUS_BLOCK = RADIUS_CONTROL
TEXT_LEFT, TEXT_RIGHT, TEXT_TOP = 8, 5, 3
# A block's times and length, in its ink laid this much over its fill.
MUTED_INK = 0.72
# Homework: a block of it carries a book as well as its colour, for a student who cannot tell the colours.
HOMEWORK_CATEGORIES = ("assignments", "homework")
BOOK = "book-open"
FREE_HINT = "+ drag to create, or click"
# How much of the text colour washes today's column when a week is shown (decision 13 of 0.17).
TODAY_WASH = 0.03

# A block as the canvas knows it between renders: its id and the day it is drawn on.
Key = tuple[str, int]


@dataclass(frozen=True)
class Drawn:
    """A block as it is drawn right now: where, beside how many, and whether it is the one held."""

    block_id: str
    title: str
    category: str
    work: bool
    span: Span
    column: int
    columns: int
    held: bool = False
    verdict: Verdict | None = None
    chosen: bool = False
    done: bool = False
    missed: bool = False
    pinned: bool = False
    axis: Axis = Axis.DOWN
    # Its name only, on hours too narrow for the name and its times.
    short: bool = False

    @property
    def times(self) -> str:
        return range_label(self.span.start, self.span.end)

    @property
    def length(self) -> str:
        """Its length, then what became of it: "1 h", "1 h · Missed"."""
        words = length_label(self.span.minutes)
        for flag, word in ((self.done, "Finished"), (self.missed, "Missed")):
            if flag:
                words += f" · {word}"
        return words

    @property
    def detail(self) -> str:
        """Everything a block says under its name, on one line, for a screen reader and the tests."""
        if self.held and self.verdict is not None:
            return self.verdict.words
        words = f"{self.times} · {self.length}"
        return words + " · Pinned" if self.pinned and not self.done else words


class BlockPainter:
    """How hours and blocks look. This default is Daily Scheduler's: pale category fills, a strong
    edge, a rule at each hour, a now line in the accent carrying the time. Designs subclass it."""

    # Where the time now is written: on a pill at the start of its line, or in the gutter beside it,
    # where it takes the place of the hour labels near it.
    now_in_gutter = False
    # A title with no room for its first word says nothing, and its colour says it is there, rather
    # than cutting inside the word ("Robot…"). Retro desktop's; the others keep decision 14's cut.
    whole_words = False

    def __init__(self, colours: dict[str, str], look: dict | None = None, *, wide: bool = False) -> None:
        self.colours = colours
        self.look = look
        # One wide day, whose blocks put their length beside the title and write it larger.
        self.wide = wide
        # The minute now on these hours, set by the canvas before it paints, or None.
        self.now_minute: int | None = None

    @cached_property
    def measures(self) -> dict:
        """The look's block and grid settings: a custom look may hide today's wash, a block's times or
        length, and set the edge's width."""
        return look_measures(self.look)

    def c(self, name: str) -> QColor:
        return QColor(self.colours[name])

    def background(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, self.c("window"))

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        """A rule at each hour, in the track's upright frame, over a faint wash of the text colour on
        today. The accent is never spread over a column: picked as Gold, it turned today khaki."""
        area = track.area
        if today and self.measures["today_highlight"]:
            wash = self.c("text")
            wash.setAlphaF(TODAY_WASH)
            painter.fillRect(area, wash)
        painter.setPen(QPen(QColor(self.colours.get("rule") or self.colours["hairline"]), 1))
        for minute in range(-(-track.first // 60) * 60, track.last + 1, 60):
            offset = track.offset(minute)
            if track.axis is Axis.DOWN:
                painter.drawLine(
                    QPointF(area.left(), area.top() + offset), QPointF(area.right(), area.top() + offset)
                )
            else:
                painter.drawLine(
                    QPointF(area.left() + offset, area.top()), QPointF(area.left() + offset, area.bottom())
                )
        if track.axis is Axis.DOWN:
            painter.drawLine(area.topLeft(), area.bottomLeft())
        else:
            painter.drawLine(area.topLeft(), area.topRight())

    def hour_labels(
        self,
        painter: QPainter,
        track: LinearTrack,
        room: float,
        every: int = 60,
        visible: QRectF | None = None,
    ) -> None:
        """Hours beside the first track, in caption: to its left down a column, above it across a
        lane. Down a column, a label the edge of `visible`, the part on screen, would cut is left
        out, as is one the time now takes the place of; moved inside, it named the wrong rule.
        Across a lane it is moved inside, where it still sits over its own hour."""
        font = at_scale(time_font(painter.font()), "caption", self.scale(painter.font()))
        painter.setFont(font)
        painter.setPen(self.c("muted"))
        metrics = QFontMetricsF(font)
        tall = metrics.height() + 2
        for minute in range(((track.first + every - 1) // every) * every, track.last + 1, every):
            at = track.offset(minute)
            words = clock_label(minute)
            if track.axis is Axis.DOWN:
                box = QRectF(track.area.left() - room, track.area.top() + at - tall / 2, room - 8, tall)
                align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                if visible is not None and (box.top() < visible.top() or box.bottom() > visible.bottom()):
                    continue
                near_now = self.now_minute is not None and abs(at - track.offset(self.now_minute)) < tall
                if self.now_in_gutter and near_now:
                    continue
            else:
                wide = metrics.horizontalAdvance(words) + 2
                box = QRectF(track.area.left() + at - wide / 2, track.area.top() - room, wide, room - 2)
                align = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
                if visible is not None and box.right() > visible.left() and box.left() < visible.right():
                    box.moveLeft(max(min(box.left(), visible.right() - wide), visible.left()))
            painter.drawText(box, align, words)

    def fills(self, drawn: Drawn) -> tuple[QColor, QColor, QColor | None, QColor | None]:
        """Fill, ink, outline and edge for a block: the Blocks look knob and the category."""
        fill, mark = category_paint(drawn.category, self.colours)
        paint = block_paint(self.look, self.colours, fill, "flexible" if drawn.work else "locked", mark)
        return (
            QColor(paint["fill"]),
            QColor(paint["ink"]),
            QColor(paint["outline"]) if paint["outline"] else None,
            QColor(paint["edge"]) if paint["edge"] else None,
        )

    def block(self, painter: QPainter, rect: QRectF, drawn: Drawn, visible: QRectF) -> None:
        fill, ink, outline, edge = self.fills(drawn)
        shape = QPainterPath()
        shape.addRoundedRect(rect, RADIUS_BLOCK, RADIUS_BLOCK)
        painter.fillPath(shape, fill)
        if outline is not None:
            painter.setPen(QPen(outline, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), RADIUS_BLOCK - 1, RADIUS_BLOCK - 1)
        if edge is not None:
            # A straight edge inside the block's own corners, as the category's mark.
            painter.save()
            painter.setClipPath(shape)
            # A custom look may set its own width.
            width = self.measures["edge_width"] or EDGE_WIDTH
            painter.fillRect(QRectF(rect.left(), rect.top(), width, rect.height()), edge)
            painter.restore()
        if drawn.held or drawn.chosen:
            refused = drawn.verdict is not None and not drawn.verdict.ok
            painter.setPen(QPen(self.c("error" if refused else "accent"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), RADIUS_BLOCK - 1, RADIUS_BLOCK - 1)
        if drawn.columns > 1 and not drawn.held:
            # Shares its time with another block: allowed, and marked so it is not missed. In its own
            # ink, since red is for what cannot be.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ink)
            painter.drawEllipse(QPointF(rect.right() - 7, rect.top() + 7), 3.5, 3.5)
        self.words(painter, rect, drawn, ink, visible, fill, edge)

    def scale(self, font: QFont) -> float:
        """The Text knob as a factor: the look's when the painter has one, else what the window's
        own font says, for a design that paints without the look."""
        if self.look is not None:
            return text_scale(self.look)
        return font.pointSizeF() / TYPE_PT["body"] if font.pointSizeF() > 0 else 1.0

    def fonts(self, base: QFont) -> tuple[QFont, QFont]:
        """A block's title and its small print: the title at 600, both at caption size on a week and
        the title at body size on a wide day (decision 14 of 0.17)."""
        scale = self.scale(base)
        title = at_scale(base, "body" if self.wide else "caption", scale, WEIGHT_STRONG)
        small = at_scale(time_font(base), "caption", scale, WEIGHT_REGULAR)
        return title, small

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
        """The most a block can say without cutting a word: its title on up to two lines, its times,
        its length; then the title and its start on one line; with no room for three letters,
        nothing, and its colour says it is there."""
        title_font, small = self.fonts(painter.font())
        title_line = QFontMetricsF(title_font).lineSpacing()
        # The name stays in sight while the start of a long block is scrolled away, either way.
        start = QPointF(rect.left() + TEXT_LEFT, rect.top() + TEXT_TOP)
        if drawn.axis is Axis.DOWN and rect.bottom() - visible.top() > 2 * title_line:
            start.setY(max(start.y(), visible.top() + TEXT_TOP))
        elif drawn.axis is Axis.ACROSS and rect.right() - visible.left() > 2 * title_line:
            start.setX(max(start.x(), visible.left() + TEXT_TOP))
        room = QRectF(start, QPointF(rect.right() - TEXT_RIGHT, rect.bottom() - 1))
        paper = fill if fill is not None else self.c("window")
        muted = QColor(mix(ink.name(), paper.name(), MUTED_INK))
        book = self._book_colour(drawn, ink, paper, edge)
        if drawn.held:
            refused = drawn.verdict is not None and not drawn.verdict.ok
            fits = QFontMetricsF(small).horizontalAdvance(drawn.detail) <= room.width()
            words = drawn.detail if fits else ""
            lay = held_layout(drawn.title, words, title_font, small, room, book is not None)
            _paint_layout(painter, lay, title_font, small, ink, self.c("error") if refused else muted, book)
            return
        # One line may take the block's whole height: at Large text a half-hour on the week is one
        # caption line exactly, and High contrast's outlined Dinner said nothing, an empty box.
        tight = QRectF(room.left(), max(rect.top(), room.top() - TEXT_TOP), room.width(), 0)
        tight.setBottom(rect.bottom())
        shown = (self.measures["show_times"], self.measures["show_lengths"])
        lay = block_layout(
            drawn, title_font, small, room, tight=tight, wide=self.wide, book=book is not None, shown=shown
        )
        if self.whole_words and cuts_a_word(lay, drawn.title):
            return
        _paint_layout(painter, lay, title_font, small, ink, muted, book, muted)

    def _book_colour(self, drawn: Drawn, ink: QColor, paper: QColor, edge: QColor | None) -> QColor | None:
        """Homework carries a book as well as its colour. In its mark where the mark reads on the
        block, else in the block's ink."""
        if drawn.category not in HOMEWORK_CATEGORIES:
            return None
        if edge is not None and contrast(edge.name(), paper.name()) >= 3.0:
            return edge
        return ink

    def ghost(self, painter: QPainter, rect: QRectF, words: str, ok: bool) -> None:
        """Something about to be made: a tinted block where it would go, with its times."""
        colour = self.c("accent" if ok else "error")
        wash = QColor(colour)
        wash.setAlphaF(0.28)
        painter.setBrush(wash)
        painter.setPen(QPen(colour, 2))
        painter.drawRoundedRect(rect, 5, 5)
        bold = weighted(time_font(painter.font()), WEIGHT_STRONG)
        painter.setPen(self.c("text"))
        _write_lines(painter, words, bold, rect.adjusted(8, 3, -6, -3))

    def hint(self, painter: QPainter, rect: QRectF, big: bool) -> None:
        """The free time under the pointer, lit, with how to use it."""
        accent = self.c("accent")
        wash = QColor(accent)
        wash.setAlphaF(0.07)
        line = QColor(accent)
        line.setAlphaF(0.4)
        painter.setBrush(wash)
        painter.setPen(QPen(line, 1, Qt.PenStyle.DashLine))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
        if big:
            words = QColor(accent)
            words.setAlphaF(0.75)
            painter.setPen(words)
            painter.setFont(_small(painter.font()))
            painter.drawText(
                rect.adjusted(8, 2, -4, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, FREE_HINT
            )

    def now(self, painter: QPainter, track: LinearTrack, minute: int) -> None:
        """A line across the track at `minute`, starting from a pill with the time on it."""
        colour = QColor(self.colours.get("now", self.colours["accent"]))
        font = weighted(time_font(_small(painter.font())), WEIGHT_STRONG)
        metrics = QFontMetricsF(font)
        words = clock_label(minute)
        width, height = metrics.horizontalAdvance(words) + 10, metrics.height() + 2
        at = track.offset(minute)
        area = track.area
        if track.axis is Axis.DOWN:
            pill = QRectF(area.left(), area.top() + at - height / 2, width, height)
            ends = (QPointF(pill.right(), area.top() + at), QPointF(area.right(), area.top() + at))
        else:
            pill = QRectF(area.left() + at - width / 2, area.top(), width, height)
            ends = (QPointF(area.left() + at, pill.bottom()), QPointF(area.left() + at, area.bottom()))
        painter.setPen(QPen(colour, 2))
        painter.drawLine(*ends)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawRoundedRect(pill, height / 2, height / 2)
        painter.setPen(QColor(readable_ink(colour.name())))
        painter.setFont(font)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, words)

    def label(self, painter: QPainter, beside: QRectF, words: str, ok: bool, room: QRectF) -> None:
        """The held block's words on a pill beside it, when the block is too small to say them, kept
        in `room`, the part of the hours on screen."""
        plain = time_font(_small(painter.font()))
        metrics = QFontMetrics(plain)
        width, height = metrics.horizontalAdvance(words) + 20, metrics.height() + 10
        left = beside.right() + 6 if beside.right() + 6 + width <= room.right() else beside.left() - 6 - width
        top = max(min(beside.top(), room.bottom() - height), room.top())
        pill = QRectF(max(left, room.left()), top, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.c("accent" if ok else "error"))
        painter.drawRoundedRect(pill, height / 2, height / 2)
        painter.setPen(self.c("accent_ink"))
        painter.setFont(plain)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, words)

    def day_name(self, painter: QPainter, box: QRectF, words: str, today: bool) -> None:
        font = weighted(painter.font(), WEIGHT_STRONG if today else WEIGHT_REGULAR)
        painter.setFont(font)
        painter.setPen(self.c("accent" if today else "muted"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, words)
        if today:
            ink = QFontMetricsF(font).boundingRect(box, int(Qt.AlignmentFlag.AlignCenter), words)
            painter.fillRect(QRectF(ink.left(), ink.bottom() + 1, ink.width(), 2), self.c("accent"))


@contextmanager
def _fresh(painter: QPainter) -> Iterator[None]:
    """Whatever a painter method sets on the painter, its font above all, is undone after it, so
    what is drawn next starts from the canvas's own font and not from the small one before it."""
    painter.save()
    try:
        yield
    finally:
        painter.restore()


def _write_lines(painter: QPainter, text: str, font: QFont, room: QRectF) -> None:
    """`text` in the whole lines that fit `room`, from its top left."""
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    for index, line in enumerate(fit_lines(text, font, room.width(), room.height())):
        box = QRectF(room.left(), room.top() + index * metrics.lineSpacing(), room.width(), metrics.height())
        painter.drawText(box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, line)


def _between(start: QRectF, end: QRectF, share: float) -> QRectF:
    """The rectangle `share` of the way from `start` to `end`."""
    return QRectF(
        start.x() + (end.x() - start.x()) * share,
        start.y() + (end.y() - start.y()) * share,
        start.width() + (end.width() - start.width()) * share,
        start.height() + (end.height() - start.height()) * share,
    )


def _small(font: QFont) -> QFont:
    return caption(font)


# Words that belong to the number before them.
UNITS = ("h", "min")


def _words(text: str) -> list[str]:
    """The words a line may break between. A number keeps the unit after it, so a length never
    reads "6" at the end of one line and "h 30 min" at the start of the next."""
    words: list[str] = []
    for word in text.split():
        if words and word in UNITS and words[-1].isdigit():
            words[-1] += " " + word
        else:
            words.append(word)
    return words


def fit_lines(text: str, font: QFont, width: float, height: float) -> list[str]:
    """`text` broken at its spaces into the whole lines that fit a box, so none is cut in half by its
    edge. When some is left over, the last line ends in "…"; so does a word wider than the box. A
    line with room for nothing but "…" is left out, and so is everything after it."""
    metrics = QFontMetricsF(font)
    room = int((height + metrics.leading()) // metrics.lineSpacing())
    if room < 1:
        return []
    wrapped: list[list[str]] = []
    for word in _words(text):
        if wrapped and metrics.horizontalAdvance(" ".join([*wrapped[-1], word])) <= width:
            wrapped[-1].append(word)
        else:
            wrapped.append([word])
    shown = wrapped[:room]
    if len(wrapped) > room:
        shown[-1] = [word for line in wrapped[room - 1 :] for word in line]
    lines = []
    for line in shown:
        fitted = metrics.elidedText(" ".join(line), Qt.TextElideMode.ElideRight, width)
        if not fitted.strip("…"):
            # Not one letter of it fits: a line of "…" says nothing, and what follows even less.
            break
        lines.append(fitted)
    return lines


@dataclass(frozen=True)
class Written:
    """One line of a block's words: what it says, in the title's font or the small one, and where.
    `book` puts the homework book before it; `pin` puts a pin before a line aligned right."""

    text: str
    title: bool
    box: QRectF
    right: bool = False
    book: bool = False
    pin: bool = False


# Between a title and the time or length on its line.
INLINE_GAP = 6


def _book_room(metrics: QFontMetricsF) -> float:
    """The book's size at a font, and the room it takes before the title."""
    return round(metrics.ascent()) + 3


def _wrap(text: str, metrics: QFontMetricsF, width: float, indent: float) -> tuple[list[str], bool]:
    """`text` broken at its spaces into lines of `width`, the first `indent` shorter; and whether
    every word fits its line whole."""
    lines: list[str] = []
    whole = True
    for word in _words(text):
        if lines:
            room = width - (indent if len(lines) == 1 else 0)
            if metrics.horizontalAdvance(f"{lines[-1]} {word}") <= room:
                lines[-1] += f" {word}"
                continue
        lines.append(word)
        if metrics.horizontalAdvance(word) > width - (indent if len(lines) == 1 else 0):
            whole = False
    return lines, whole


def word_elide(text: str, metrics: QFontMetricsF, width: float) -> str:
    """`text` in `width`, given way at a space where it must, "Math…" rather than "Math works…". Only
    a first word wider than the room is cut inside it."""
    if metrics.horizontalAdvance(text) <= width:
        return text
    words = _words(text)
    kept = ""
    for word in words:
        longer = f"{kept} {word}".strip()
        if metrics.horizontalAdvance(longer + "…") > width:
            break
        kept = longer
    if kept:
        return kept + "…"
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)


def cuts_a_word(lay: list[Written], title: str) -> bool:
    """Whether a block's words cut its title inside a word: "Robot…" for "Robotics club"."""
    whole = set(_words(title))
    for line in lay:
        if line.title and line.text.endswith("…"):
            kept = line.text[:-1].split()
            if not kept or kept[-1] not in whole:
                return True
    return False


def _clamp(lines: list[str], most: int, metrics: QFontMetricsF, width: float, indent: float) -> list[str]:
    """At most `most` lines, the last one ending in "…" if there was more, each within its width."""
    shown = lines[:most]
    if len(lines) > most:
        shown[-1] = " ".join(lines[most - 1 :])
    return [word_elide(line, metrics, width - (indent if at == 0 else 0)) for at, line in enumerate(shown)]


def _beside(title: QFontMetricsF, small: QFontMetricsF) -> float:
    """How far below a title line's top small print on the same line starts, so the two share a baseline."""
    return max(title.ascent() - small.ascent(), 0.0)


def block_layout(
    drawn: Drawn,
    title_font: QFont,
    small: QFont,
    room: QRectF,
    *,
    tight: QRectF | None = None,
    wide: bool = False,
    book: bool = False,
    shown: tuple[bool, bool] = (True, True),
) -> list[Written]:
    """What a block says in `room`, and where (decision 14 of 0.17). The first way that fits with no
    word cut: the title on up to two lines, its times, its length; then without the length; the
    title on one line and its times; "Dinner 18:30" on one line; the title alone. Only if none fits
    whole does the title give way with "…". With no room for three of its letters, nothing: the
    block's colour says it is there. A wide day puts the length at the right of the title. `shown`
    is whether the look shows times and lengths; a flag such as Finished stays either way.

    `tight` is the block's room with less kept from its top and bottom, for one line on a block too
    short for the usual margins, as a half-hour Dinner is on the week."""
    tight = tight if tight is not None else room
    tm, sm = QFontMetricsF(title_font), QFontMetricsF(small)
    indent = _book_room(tm) if book else 0.0
    width, height = room.width(), room.height()
    tl, sl = tm.lineSpacing(), sm.lineSpacing()
    if width < indent + tm.horizontalAdvance(drawn.title.strip()[:3]) or tight.height() + 0.5 < tl:
        return []
    # One line starts where the usual margin puts it, or higher on a block too short for that.
    line_top = room.top() if height + 0.5 >= tl else tight.top()
    lines, whole = _wrap(drawn.title, tm, width, indent)
    if wide:
        return _wide_layout(drawn, tm, sm, room, line_top, indent, book)

    def stack(most: int, extras: tuple[str, ...], cut: bool) -> list[Written] | None:
        if any(sm.horizontalAdvance(extra) > width for extra in extras):
            return None
        count = min(len(lines), most)
        if count > 1 or extras:
            if tl * count + sl * len(extras) > height + 0.5:
                return None
            top = room.top()
        else:
            top = line_top
        if not cut and (not whole or len(lines) > most):
            return None
        out = []
        for at, text in enumerate(_clamp(lines, most, tm, width, indent)):
            left = room.left() + (indent if at == 0 else 0)
            out.append(Written(text, True, QRectF(left, top, room.right() - left, tl), book=book and at == 0))
            top += tl
        for extra in extras:
            out.append(Written(extra, False, QRectF(room.left(), top, width, sl)))
            top += sl
        return out

    def one_line(after: str, cut: bool) -> list[Written] | None:
        """The title and `after` on one line, as "Dinner 18:30"."""
        after_width = sm.horizontalAdvance(after)
        title_room = width - indent - INLINE_GAP - after_width
        if title_room < tm.horizontalAdvance(drawn.title.strip()[:3]):
            return None
        fits = tm.horizontalAdvance(drawn.title) <= title_room
        if not fits and not cut:
            return None
        text = drawn.title if fits else word_elide(drawn.title, tm, title_room)
        left = room.left() + indent
        written = [Written(text, True, QRectF(left, line_top, title_room, tl), book=book)]
        at = left + tm.horizontalAdvance(text) + INLINE_GAP
        written.append(Written(after, False, QRectF(at, line_top + _beside(tm, sm), after_width + 1, sl)))
        return written

    if drawn.short:
        # Short of room the window asked for names only: "Soccer practice" whole over two lines
        # says more than "Soccer …" and its times.
        ways = [lambda cut: stack(3, (), cut), lambda cut: stack(1, (), cut)]
    else:
        said = ((drawn.done, "Finished"), (drawn.missed, "Missed"))
        flags = " · ".join(word for flag, word in said if flag)
        times = drawn.times if shown[0] else ""
        length = drawn.length if shown[1] else flags
        ways = [
            lambda cut: stack(2, tuple(part for part in (times, length) if part), cut),
            lambda cut: stack(2, tuple(part for part in (times,) if part), cut),
            lambda cut: stack(1, tuple(part for part in (times,) if part), cut),
            lambda cut: one_line(short_clock(drawn.span.start) if shown[0] else "", cut),
            lambda cut: stack(2, (), cut),
            lambda cut: stack(1, (), cut),
        ]
    for way in ways:
        found = way(False)
        if found is not None:
            return found
    # Nothing says the title whole: it gives way, and the name comes before its start on one line,
    # "Math works…" rather than "Mat… 19:00".
    for way in ways[:3] + ways[4:] + ways[3:4]:
        found = way(True)
        if found is not None:
            return found
    return []


def _wide_layout(
    drawn: Drawn,
    tm: QFontMetricsF,
    sm: QFontMetricsF,
    room: QRectF,
    line_top: float,
    indent: float,
    book: bool,
) -> list[Written]:
    """One wide day's block: the title with the length at its right, the times under them; or all
    three on one line."""
    width, height = room.width(), room.height()
    tl, sl = tm.lineSpacing(), sm.lineSpacing()
    pinned = drawn.pinned and not drawn.done
    length_width = sm.horizontalAdvance(drawn.length) + (_book_room(sm) if pinned else 0)
    title_room = width - length_width - INLINE_GAP
    shifted = _beside(tm, sm)

    def length_at(top: float) -> Written:
        box = QRectF(room.left(), top + shifted, width, sl)
        return Written(drawn.length, False, box, right=True, pin=pinned)

    def stacked(cut: bool) -> list[Written] | None:
        narrowed, fits = _wrap(drawn.title, tm, title_room, indent)
        count = min(len(narrowed), 2)
        if tl * count + sl > height + 0.5 or sm.horizontalAdvance(drawn.times) > width:
            return None
        if not cut and (not fits or len(narrowed) > 2):
            return None
        out = []
        top = room.top()
        for at, text in enumerate(_clamp(narrowed, 2, tm, title_room, indent)):
            left = room.left() + (indent if at == 0 else 0)
            box = QRectF(left, top, title_room - (left - room.left()), tl)
            out.append(Written(text, True, box, book=book and at == 0))
            top += tl
        out.append(length_at(room.top()))
        out.append(Written(drawn.times, False, QRectF(room.left(), top, width, sl)))
        return out

    def inline(cut: bool) -> list[Written] | None:
        times_width = sm.horizontalAdvance(drawn.times)
        name_room = title_room - indent - INLINE_GAP - times_width
        if name_room < tm.horizontalAdvance(drawn.title.strip()[:3]):
            return None
        fits = tm.horizontalAdvance(drawn.title) <= name_room
        if not fits and not cut:
            return None
        text = drawn.title if fits else word_elide(drawn.title, tm, name_room)
        left = room.left() + indent
        at = left + tm.horizontalAdvance(text) + INLINE_GAP
        return [
            Written(text, True, QRectF(left, line_top, name_room, tl), book=book),
            Written(drawn.times, False, QRectF(at, line_top + shifted, times_width + 1, sl)),
            length_at(line_top),
        ]

    for cut in (False, True):
        for way in (stacked, inline):
            found = way(cut)
            if found is not None:
                return found
    return []


def held_layout(
    title: str, words: str, title_font: QFont, small: QFont, room: QRectF, book: bool
) -> list[Written]:
    """A held block: its name, and under it where it would land, in whole lines."""
    tm, sm = QFontMetricsF(title_font), QFontMetricsF(small)
    indent = _book_room(tm) if book else 0.0
    if room.height() + 0.5 < tm.height() or room.width() < indent + 8:
        return []
    name = tm.elidedText(title, Qt.TextElideMode.ElideRight, room.width() - indent)
    tl, sl = tm.lineSpacing(), sm.lineSpacing()
    box = QRectF(room.left() + indent, room.top(), room.width() - indent, tl)
    out = [Written(name, True, box, book=book)]
    below = room.height() - tl
    for at, line in enumerate(fit_lines(words, small, room.width(), below)):
        out.append(Written(line, False, QRectF(room.left(), room.top() + tl + at * sl, room.width(), sl)))
    return out


def _paint_layout(
    painter: QPainter,
    lay: list[Written],
    title_font: QFont,
    small: QFont,
    ink: QColor,
    muted: QColor,
    book: QColor | None,
    pin: QColor | None = None,
) -> None:
    ratio = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
    for line in lay:
        font = title_font if line.title else small
        metrics = QFontMetricsF(font)
        painter.setFont(font)
        painter.setPen(ink if line.title else muted)
        align = Qt.AlignmentFlag.AlignRight if line.right else Qt.AlignmentFlag.AlignLeft
        painter.drawText(line.box, align | Qt.AlignmentFlag.AlignTop, line.text)
        size = round(metrics.ascent())
        top = line.box.top() + (metrics.height() - size) / 2
        if line.book and book is not None:
            left = line.box.left() - _book_room(metrics)
            painter.drawPixmap(QPointF(left, top), icons.pixmap(BOOK, book.name(), size, ratio))
        if line.pin and pin is not None:
            left = line.box.right() - metrics.horizontalAdvance(line.text) - _book_room(metrics)
            painter.drawPixmap(QPointF(left, top), icons.pixmap("pin", pin.name(), size, ratio))


class HoursCanvas(QWidget):
    """One painted widget of hours. `lay_out` says where each day's track lies in it.

    Days whose time runs down are named in the `header` above them; days whose time runs across are
    named in the `gutter` to their left. Either name, clicked, opens that day."""

    # A surface the hand can drop blocks on (see hand.py).
    takes_blocks = True

    # A day's name was clicked: open it on Day.
    day_opened = Signal(int)
    # Zoom by this many steps (0 goes back to the surface's own level), about this point in the
    # canvas, or about the middle of what is on screen when there is none.
    zoom_asked = Signal(int, object)

    def __init__(
        self,
        hand: Hand,
        painter: BlockPainter,
        lay_out: Callable[[QRectF], list[LinearTrack]] | None = None,
        *,
        gutter: float = 0,
        header: float = 0,
        names: Callable[[int], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("hoursCanvas")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Hours")
        self.setAccessibleDescription(
            "Drag a block to move it, its top or bottom edge to resize it, or empty time to add something."
            " Click a block, or press Enter, to open it. Right-click it for more."
        )
        self.hand, self.painter = hand, painter
        self._lay_out = lay_out
        self.gutter, self.header = gutter, header
        self._names = names or (lambda day: DAYS[day])
        self.tracks: list[LinearTrack] = []
        self.occurrences: tuple[Occurrence, ...] = ()
        self.today: int | None = None
        self.now_min: int | None = None
        # Blocks say their names only; the window sets it when the hours are narrow.
        self.short_words = False
        self._hover: tuple[LinearTrack, int] | None = None
        self._wheel = 0
        # Where each block was drawn at the last render, in the canvas's own coordinates, and, while
        # they settle, where the moved ones started and which are new.
        self._last_rects: dict[Key, QRectF] = {}
        self._slides: dict[Key, QRectF] = {}
        self._fresh: set[Key] = set()
        self._progress = 1.0
        # A child, so it goes with the canvas and never paints one that is gone.
        self._settling = QVariantAnimation(self)
        self._settling.setStartValue(0.0)
        self._settling.setEndValue(1.0)
        self._settling.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._settling.valueChanged.connect(self._settle_step)
        self._settling.finished.connect(self._settled)
        hand.preview_changed.connect(self.update)

    # What it shows

    def set_week(
        self, occurrences: Sequence[Occurrence], today: int | None = None, now_min: int | None = None
    ) -> None:
        previous = self._last_rects
        self.occurrences = tuple(occurrences)
        self.today, self.now_min = today, now_min
        self._last_rects = self._rects()
        if self._last_rects != previous:
            # From where each block is drawn now, which is partway along if it is still sliding.
            self._settle_from({key: self._shown_rect(key, rect) for key, rect in previous.items()})
        self.update()

    def _rects(self) -> dict[Key, QRectF]:
        return {
            (drawn.block_id, drawn.span.day): track.transform.mapRect(rect)
            for track in self.tracks
            for drawn, rect in self.drawn(track)
            if not drawn.held
        }

    def _settle_from(self, before: dict[Key, QRectF]) -> None:
        """Slide each block that moved from where it was drawn, and fade in each that is new. A week
        with nothing in common with the last, such as another week or the first, simply shows."""
        self._settling.stop()
        self._slides, self._fresh, self._progress = {}, set(), 1.0
        level = app_level()
        now = self._last_rects
        shared = {key[0] for key in before} & {key[0] for key in now}
        if DURATION_MS.get(level, 0) == 0 or not self.isVisible() or not shared:
            return
        gone = {key[0]: rect for key, rect in before.items() if key not in now}
        for key, rect in now.items():
            if key[0] == self.hand.dropped:
                continue
            start = before.get(key)
            if start is None:
                # Carried to another day by a change that was not a drag, such as Plan.
                start = gone.get(key[0])
            if start is None:
                self._fresh.add(key)
            elif start != rect:
                self._slides[key] = start
        if self._slides or self._fresh:
            self._progress = 0.0
            self._settling.setDuration(DURATION_MS[level])
            self._settling.start()

    def _settle_step(self, value: object) -> None:
        self._progress = float(value)
        self.update()

    def _settled(self) -> None:
        self._slides, self._fresh, self._progress = {}, set(), 1.0
        self.update()

    def _shown_rect(self, key: Key, rect: QRectF) -> QRectF:
        """Where a block is drawn at this moment of its slide, in the canvas's coordinates."""
        start = self._slides.get(key)
        return rect if start is None else _between(start, rect, self._progress)

    def set_clock(self, today: int | None, now_min: int | None) -> None:
        if (today, now_min) != (self.today, self.now_min):
            self.today, self.now_min = today, now_min
            self.update()

    def set_painter(self, painter: BlockPainter) -> None:
        self.painter = painter
        self.update()

    def lay_out(self, area: QRectF) -> list[LinearTrack]:
        if self._lay_out is not None:
            return self._lay_out(area)
        return [LinearTrack(0, area)]

    def relayout(self) -> None:
        area = QRectF(self.rect()).adjusted(self.gutter, self.header, 0, 0)
        self.tracks = self.lay_out(area) if area.width() > 0 and area.height() > 0 else []
        # A zoom or a resize moves every block, and none of them should slide for it.
        self._settling.stop()
        self._settled()
        self._last_rects = self._rects()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.relayout()

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)
        self.relayout()

    def track_at(self, point: QPointF) -> LinearTrack | None:
        for track in self.tracks:
            if track.contains(point):
                return track
        return None

    def track_for(self, day: int, minute: int | None = None) -> LinearTrack | None:
        for track in self.tracks:
            if track.day == day and (minute is None or track.first <= minute <= track.last):
                return track
        return None

    # Where blocks are drawn

    def drawn(self, track: LinearTrack) -> list[tuple[Drawn, QRectF]]:
        """Every block on a track, the held one where it would land, with its rectangle in the track's
        upright frame. Painting and pressing both read this, so they always agree."""
        preview = self.hand.preview
        held = preview.held if preview is not None else None
        chosen = self.hand.selection
        items: list[Drawn] = []
        moving = held is not None and held.kind in (Gesture.MOVE, Gesture.RESIZE_START, Gesture.RESIZE_END)
        for item in self.occurrences:
            if item.day != track.day or item.end <= track.first or item.start >= track.last:
                continue
            if moving and held is not None and item.block_id == held.block_id and item.day == held.from_day:
                continue
            items.append(
                Drawn(
                    item.block_id,
                    item.title,
                    item.category,
                    item.work,
                    Span(item.day, item.start, item.end),
                    0,
                    1,
                    chosen=chosen == (item.block_id, item.day),
                    done=item.done,
                    missed=item.missed,
                    pinned=item.pinned,
                    axis=track.axis,
                    short=self.short_words,
                )
            )
        if (
            preview is not None
            and held is not None
            and held.kind in (Gesture.MOVE, Gesture.RESIZE_START, Gesture.RESIZE_END, Gesture.PLACE)
        ):
            span = preview.span
            if span.day == track.day and span.end > track.first and span.start < track.last:
                category = next((o.category for o in self.occurrences if o.block_id == held.block_id), "")
                work = next(
                    (o.work for o in self.occurrences if o.block_id == held.block_id),
                    held.kind is Gesture.PLACE,
                )
                items.append(
                    Drawn(
                        held.block_id or "",
                        held.title,
                        category or ("homework" if work else ""),
                        work,
                        span,
                        0,
                        1,
                        held=True,
                        verdict=preview.verdict,
                        axis=track.axis,
                    )
                )
        columns = overlap_columns([(d.span.start, d.span.end) for d in items])
        out = []
        for drawn, (column, count) in zip(items, columns, strict=True):
            placed = Drawn(**{**drawn.__dict__, "column": column, "columns": count})
            out.append((placed, track.rect_for(drawn.span.start, drawn.span.end, column, count)))
        return out

    def _block_at(self, point: QPointF) -> tuple[Drawn, QRectF, LinearTrack] | None:
        track = self.track_at(point)
        if track is None:
            return None
        upright = track.upright(point)
        hit = None
        for drawn, rect in self.drawn(track):
            if not drawn.held and rect.contains(upright):
                hit = (drawn, rect, track)
        return hit

    # Painting

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        visible = self._visible()
        shown_today = self.today is not None and any(track.day == self.today for track in self.tracks)
        self.painter.now_minute = self.now_min if shown_today else None
        with _fresh(painter):
            self.painter.background(painter, QRectF(self.rect()))
        preview = self.hand.preview
        held = preview.held if preview is not None else None
        # On hours of one day, washing today washes everything and marks nothing.
        week = len({track.day for track in self.tracks}) > 1
        for index, track in enumerate(self.tracks):
            painter.save()
            painter.setTransform(track.transform, True)
            upright_visible = track.transform.inverted()[0].mapRect(visible)
            with _fresh(painter):
                self.painter.track(painter, track, week and track.day == self.today)
            if index == 0 and self.gutter and track.axis is Axis.DOWN:
                with _fresh(painter):
                    self.painter.hour_labels(painter, track, self.gutter, visible=upright_visible)
            if index == 0 and self.header and track.axis is Axis.ACROSS:
                with _fresh(painter):
                    self.painter.hour_labels(painter, track, self.header, every=120, visible=upright_visible)
            self._paint_hint(painter, track)
            for drawn, rect in self.drawn(track):
                with _fresh(painter):
                    key = (drawn.block_id, drawn.span.day)
                    if not drawn.held and key in self._slides:
                        start = track.transform.inverted()[0].mapRect(self._slides[key])
                        rect = _between(start, rect, self._progress)
                    elif not drawn.held and key in self._fresh:
                        painter.setOpacity(self._progress)
                    self.painter.block(painter, rect, drawn, upright_visible)
            if (
                preview is not None
                and held is not None
                and held.kind is Gesture.CREATE
                and preview.span.day == track.day
            ):
                rect = track.rect_for(preview.span.start, preview.span.end)
                with _fresh(painter):
                    self.painter.ghost(painter, rect, span_words(preview.span), True)
            if (
                self.today == track.day
                and self.now_min is not None
                and track.first <= self.now_min <= track.last
            ):
                with _fresh(painter):
                    self.painter.now(painter, track, self.now_min)
            painter.restore()
        for track in self.tracks:
            box = self._name_box(track)
            if box is not None:
                with _fresh(painter):
                    self.painter.day_name(painter, box, self._names(track.day), track.day == self.today)
        self._paint_label(painter)
        painter.end()

    def _visible(self) -> QRectF:
        """The part of the hours on screen. Not the part being repainted: a long block's name is kept
        in sight at the start of what shows, and a small repaint must not draw it a second time."""
        area = self._scroll_area()
        if area is None:
            return QRectF(self.rect())
        port = area.viewport()
        return QRectF(QRect(self.mapFrom(port, QPoint(0, 0)), port.size())).intersected(QRectF(self.rect()))

    def _name_box(self, track: LinearTrack) -> QRectF | None:
        """Where a day's name is drawn: over a column, or left of a lane. None when there is no room
        for one, or the day already has a name box from another of its tracks."""
        first = next(item for item in self.tracks if item.day == track.day)
        if first is not track or track.turn:
            return None
        if track.axis is Axis.DOWN and self.header:
            return QRectF(track.area.left(), 0, track.area.width(), self.header)
        if track.axis is Axis.ACROSS and self.gutter:
            return QRectF(0, track.area.top(), self.gutter, track.area.height())
        return None

    def _paint_label(self, painter: QPainter) -> None:
        preview = self.hand.preview
        if preview is None or preview.held.kind is Gesture.CREATE:
            return
        for track in self.tracks:
            for drawn, rect in self.drawn(track):
                if not drawn.held:
                    continue
                words = preview.verdict.words
                metrics = QFontMetrics(time_font(_small(painter.font())))
                small = metrics.horizontalAdvance(words) > rect.width() - 14
                if small or rect.height() < 30:
                    self.painter.label(
                        painter, track.transform.mapRect(rect), words, preview.verdict.ok, self._visible()
                    )
                return

    def _paint_hint(self, painter: QPainter, track: LinearTrack) -> None:
        if self._hover is None or self.hand.busy or self._hover[0] is not track:
            return
        minute = self._hover[1]
        low, high = track.first, track.last
        for item in self.occurrences:
            if item.day != track.day:
                continue
            if item.start <= minute < item.end:
                return
            if item.end <= minute:
                low = max(low, item.end)
            elif item.start > minute:
                high = min(high, item.start)
        if high - low < self.hand.step:
            return
        rect = track.rect_for(low, high)
        big = (rect.height() if track.axis is Axis.DOWN else rect.width()) >= 26
        with _fresh(painter):
            self.painter.hint(painter, rect, big)

    # Pointer

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        point = event.position()
        name = self._name_at(point)
        if name is not None:
            self.day_opened.emit(name)
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        at = event.globalPosition().toPoint()
        hit = self._block_at(point)
        if hit is not None:
            drawn, rect, track = hit
            minute = track.minute_at(point)
            upright = track.upright(point)
            kind = self._edge_kind(rect, upright, track)
            # How far the pointer is from the edge it moves, so nothing jumps on the first move.
            edge = drawn.span.end if kind is Gesture.RESIZE_END else drawn.span.start
            held = Held(
                kind,
                drawn.title,
                drawn.span.minutes,
                drawn.block_id,
                drawn.span.day,
                drawn.span,
                round(minute - edge),
            )
            self.hand.select(drawn.block_id, drawn.span.day)
            # A click opens it; a drag moves or resizes it.
            self.hand.press(self, held, at, tap=lambda: self.hand.open(drawn.block_id), home=(self, track))
            return
        track = self.track_at(point)
        if track is None:
            return
        # Less half a step, so rounding floors: the block starts in the step the pointer went down in.
        step = self.hand.step
        anchor = min(max(snap(track.minute_at(point) - step / 2, step), track.first), track.last - step)
        held = Held(Gesture.CREATE, "", step, None, track.day, Span(track.day, anchor, anchor + step))
        self.hand.selection = None
        self.hand.press(self, held, at, tap=lambda: self._quick_create(track, anchor), home=(self, track))

    def _edge_kind(self, rect: QRectF, upright: QPointF, track: LinearTrack) -> Gesture:
        """Resize from within a few pixels of the start or end edge of a block long enough to have
        edges; move from anywhere else. As in Daily Scheduler, except that an edge is never more than
        a fifth of the block, so a short block still moves when pressed a quarter of the way in."""
        down = track.axis is Axis.DOWN
        # The drawing stops a pixel short of the block's start and two of its end, so blocks back to
        # back stand apart. An edge is pressed on the drawing, but it is at most a fifth of the block's
        # own time less those pixels: a fifth of the drawing let a 15-minute block on Day resize when
        # pressed three quarters of the way into its time.
        lead, trail = 1.0, BETWEEN - 1.0
        length = (rect.height() if down else rect.width()) + lead + trail
        if length < 2 * EDGE_PX + 6:
            return Gesture.MOVE
        from_start = upright.y() - rect.top() if down else upright.x() - rect.left()
        from_end = rect.bottom() - upright.y() if down else rect.right() - upright.x()
        if from_start <= min(EDGE_PX, length / 5 - lead):
            return Gesture.RESIZE_START
        if from_end <= min(EDGE_PX, length / 5 - trail):
            return Gesture.RESIZE_END
        return Gesture.MOVE

    def _quick_create(self, track: LinearTrack, anchor: int) -> None:
        """A click on free time makes up to an hour there, stopping at the next block or at the end
        of the track."""
        taken = sorted((item.start, item.end) for item in self.occurrences if item.day == track.day)
        if any(start <= anchor < end for start, end in taken):
            return
        made = create_click_range(anchor, taken)
        if made is not None and min(made[1], track.last) - made[0] >= self.hand.step:
            self.hand.commit(Create(Span(track.day, made[0], min(made[1], track.last))))

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        hit = self._block_at(event.position())
        if event.button() != Qt.MouseButton.LeftButton or hit is None:
            super().mouseDoubleClickEvent(event)
            return
        self.hand.open(hit[0].block_id, second_click=True)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        """A right-click on a block asks for its menu. It picks nothing up, and on free time or while
        something is carried it does nothing."""
        hit = self._block_at(QPointF(event.pos()))
        if hit is None or self.hand.busy:
            event.ignore()
            return
        event.accept()
        self.hand.ask_menu(hit[0].block_id, hit[0].span.day, event.globalPos())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self.hand.busy:
            return
        point = event.position()
        hit = self._block_at(point)
        track = self.track_at(point)
        if hit is not None:
            kind = self._edge_kind(hit[1], hit[2].upright(point), hit[2])
            self.setCursor(
                Qt.CursorShape.OpenHandCursor if kind is Gesture.MOVE else self._resize_cursor(hit[2])
            )
            hover = None
        elif self._name_at(point) is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            hover = None
        else:
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if track is not None else Qt.CursorShape.ArrowCursor
            )
            hover = (track, snap(track.minute_at(point), self.hand.step)) if track is not None else None
        if hover != self._hover:
            self._hover = hover
            self.update()

    def _resize_cursor(self, track: LinearTrack) -> Qt.CursorShape:
        return Qt.CursorShape.SizeVerCursor if track.axis is Axis.DOWN else Qt.CursorShape.SizeHorCursor

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        if self._hover is not None:
            self._hover = None
            self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Ctrl and the wheel zoom about the pointer. Without Ctrl the hours scroll as usual."""
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._wheel = 0
            event.ignore()
            return
        event.accept()
        # A touchpad sends small turns; a step is a whole notch of a wheel.
        self._wheel += event.angleDelta().y()
        steps = int(self._wheel / 120)
        if steps:
            self._wheel -= steps * 120
            self.zoom_asked.emit(steps, event.position())

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Enter opens the chosen block. Everything else goes to the window's shortcuts, zoom
        included."""
        chosen = self.hand.selection
        mine = chosen is not None and any(item.block_id == chosen[0] for item in self.occurrences)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and chosen is not None and mine:
            self.hand.open(chosen[0])
            event.accept()
            return
        event.ignore()

    def _name_at(self, point: QPointF) -> int | None:
        for track in self.tracks:
            box = self._name_box(track)
            if box is not None and box.contains(point):
                return track.day
        return None

    # For the rig and the tests, in global coordinates

    def point_for(self, day: int, minute: int) -> QPoint:
        track = self.track_for(day, minute)
        if track is None:
            raise LookupError(f"no track for day {day} at minute {minute}")
        return self.mapToGlobal(track.point_for(minute).toPoint())

    def block_rect(self, block_id: str, day: int) -> QRect | None:
        for track in self.tracks:
            if track.day != day:
                continue
            for drawn, rect in self.drawn(track):
                if drawn.block_id == block_id and not drawn.held:
                    box = track.transform.mapRect(rect).toRect()
                    return QRect(self.mapToGlobal(box.topLeft()), box.size())
        return None

    def day_name(self, day: int) -> QPoint:
        track = self.track_for(day)
        box = self._name_box(track) if track is not None else None
        if box is None:
            raise LookupError(f"no name drawn for day {day}")
        return self.mapToGlobal(box.center().toPoint())

    def _scroll_area(self) -> QScrollArea | None:
        area = self.parentWidget()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        return area

    def in_view(self, day: int, minute: int) -> bool:
        """Whether this minute sits in the nearest scroll viewport."""
        track = self.track_for(day, minute)
        if track is None:
            return False
        local = track.point_for(minute).toPoint()
        area = self._scroll_area()
        if area is None:
            return self.rect().adjusted(-2, -2, 2, 2).contains(local)
        viewport = area.viewport()
        return viewport.rect().adjusted(-2, -2, 2, 2).contains(self.mapTo(viewport, local))

    def reveal(self, day: int, first: int, last: int) -> None:
        """Scroll the nearest scroll area so this stretch of the day is on screen."""
        area = self._scroll_area()
        track = self.track_for(day, first) or self.track_for(day)
        if area is None or track is None:
            return
        for minute in (last, first):
            local = track.point_for(min(max(minute, track.first), track.last)).toPoint()
            inside = self.mapTo(area.widget(), local) if area.widget() is not self else local
            area.ensureVisible(inside.x(), inside.y(), 20, 40)

    def held_words(self) -> str:
        preview = self.hand.preview
        return preview.verdict.words if preview is not None else ""
