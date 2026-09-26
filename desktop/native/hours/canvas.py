"""Hours a student can drag on, drawn any way a design likes.

An `HoursCanvas` is one painted widget holding one or more tracks: a day's column, seven columns, a
lane per day, a card laid at an angle. It draws the week's blocks on them through a `BlockPainter`,
which is the only thing a design replaces to look like itself, and passes every press to the window's
`Hand`, which owns the gestures. While something is held, the canvas draws it where it would land,
with its times written on it.

The canvas also answers the rig and the tests in global coordinates: where a day and minute are,
where a block is drawn, and how to bring a stretch of hours into view.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QFontMetricsF,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QScrollArea, QWidget

from desktop.native.calendar import CATEGORIES, DAYS, create_click_range
from desktop.native.fonts import time_font
from desktop.native.hours.geometry import (
    Axis,
    LinearTrack,
    Span,
    overlap_columns,
    snap,
)
from desktop.native.hours.hand import Create, Gesture, Hand, Held, Verdict, span_words
from desktop.native.look import block_paint, readable_ink
from desktop.native.weekmodel import Occurrence, clock_label, length_label

# A press this close to a block's start or end edge resizes it, on a block long enough to have edges.
EDGE_PX = 7
FREE_HINT = "+ drag to create, or click"


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

    @property
    def detail(self) -> str:
        if self.held and self.verdict is not None:
            return self.verdict.words
        words = (
            f"{clock_label(self.span.start)}–{clock_label(self.span.end)} · {length_label(self.span.minutes)}"
        )
        for flag, word in (
            (self.done, "Finished"),
            (self.missed, "Missed"),
            (self.pinned and not self.done, "Pinned"),
        ):
            if flag:
                words += f" · {word}"
        return words


class BlockPainter:
    """How hours and blocks look. This default is Daily Scheduler's: pale category fills, a strong
    edge, a rule at each hour, a red now line carrying the time. Designs subclass it."""

    def __init__(self, colours: dict[str, str], look: dict | None = None) -> None:
        self.colours = colours
        self.look = look

    def c(self, name: str) -> QColor:
        return QColor(self.colours[name])

    def background(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, self.c("window"))

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        """A rule at each hour, in the track's upright frame, over a wash of the accent on today."""
        area = track.area
        if today:
            wash = self.c("accent")
            wash.setAlphaF(0.10)
            painter.fillRect(area, wash)
        # On a dark look the plain hairline barely shows against the page.
        rule = self.c("hairline_strong" if self.colours.get("axis") == "dark" else "hairline")
        painter.setPen(QPen(rule, 1))
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
        """Hours beside the first track: to its left down a column, above it across a lane. A label
        the edge of `visible`, the part on screen, would cut is moved inside it, as a long block's
        name is."""
        painter.setPen(self.c("muted"))
        painter.setFont(time_font(_small(painter.font())))
        metrics = QFontMetricsF(painter.font())
        for minute in range(((track.first + every - 1) // every) * every, track.last + 1, every):
            at = track.offset(minute)
            words = clock_label(minute)
            if track.axis is Axis.DOWN:
                box = QRectF(track.area.left() - room, track.area.top() + at - 9, room - 6, 18)
                align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                if visible is not None and box.bottom() > visible.top() and box.top() < visible.bottom():
                    box.moveTop(max(min(box.top(), visible.bottom() - box.height()), visible.top()))
            else:
                wide = metrics.horizontalAdvance(words) + 2
                box = QRectF(track.area.left() + at - wide / 2, track.area.top() - room, wide, room - 2)
                align = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
                if visible is not None and box.right() > visible.left() and box.left() < visible.right():
                    box.moveLeft(max(min(box.left(), visible.right() - wide), visible.left()))
            painter.drawText(box, align, words)

    def fills(self, drawn: Drawn) -> tuple[QColor, QColor, QColor | None, QColor | None]:
        """Fill, ink, outline and edge for a block: the Blocks look knob and the category."""
        category = CATEGORIES.get(drawn.category, {})
        paint = block_paint(
            self.look,
            self.colours,
            category.get("color"),
            "flexible" if drawn.work else "locked",
            category.get("mark"),
        )
        return (
            QColor(paint["fill"]),
            QColor(paint["ink"]),
            QColor(paint["outline"]) if paint["outline"] else None,
            QColor(paint["edge"]) if paint["edge"] else None,
        )

    def block(self, painter: QPainter, rect: QRectF, drawn: Drawn, visible: QRectF) -> None:
        fill, ink, outline, edge = self.fills(drawn)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 5, 5)
        if outline is not None:
            painter.setPen(QPen(outline, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 5, 5)
        if edge is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(edge)
            painter.drawRoundedRect(QRectF(rect.left(), rect.top(), 4, rect.height()), 2, 2)
        if drawn.held or drawn.chosen:
            refused = drawn.verdict is not None and not drawn.verdict.ok
            painter.setPen(QPen(self.c("error" if refused else "accent"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 5, 5)
        if drawn.columns > 1 and not drawn.held:
            # Shares its time with another block: allowed, and marked so it is not missed.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.c("error"))
            painter.drawEllipse(QPointF(rect.right() - 7, rect.top() + 7), 3.5, 3.5)
        self.words(painter, rect, drawn, ink, visible)

    def words(self, painter: QPainter, rect: QRectF, drawn: Drawn, ink: QColor, visible: QRectF) -> None:
        bold = QFont(painter.font())
        bold.setBold(True)
        plain = time_font(_small(painter.font()))
        line = QFontMetrics(bold).height()
        # The name on a bold line and its times on one line of the smaller font under it.
        two_lines = line + 1 + QFontMetricsF(plain).height()
        # The name stays in sight while the start of a long block is scrolled away, either way.
        start = QPointF(rect.left() + 8, rect.top() + 3)
        if drawn.axis is Axis.DOWN and rect.bottom() - visible.top() > 2 * line:
            start.setY(max(start.y(), visible.top() + 3))
        elif drawn.axis is Axis.ACROSS and rect.right() - visible.left() > 2 * line:
            start.setX(max(start.x(), visible.left() + 3))
        room = QRectF(start, QPointF(rect.right() - 6, rect.bottom() - 2))
        if room.height() < 6 or room.width() < 8:
            return
        detail = drawn.detail
        if drawn.held and QFontMetrics(plain).horizontalAdvance(detail) > room.width():
            detail = ""  # said in the label beside it instead
        painter.setPen(ink)
        if room.height() < two_lines:
            painter.setFont(plain)
            text = f"{drawn.title} · {detail}" if detail else drawn.title
            elided = QFontMetrics(plain).elidedText(text, Qt.TextElideMode.ElideRight, int(room.width()))
            if not elided.strip("…"):
                elided = _initial(drawn.title, QFontMetrics(plain), room.width())
            painter.drawText(room, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)
            return
        painter.setFont(bold)
        name = QFontMetrics(bold).elidedText(drawn.title, Qt.TextElideMode.ElideRight, int(room.width()))
        named = bool(name.strip("…"))
        if not named:
            name = _initial(drawn.title, QFontMetrics(bold), room.width())
        painter.drawText(
            QRectF(room.left(), room.top(), room.width(), line), Qt.AlignmentFlag.AlignLeft, name
        )
        if not named:
            # No room for any of the name, so none for its times either.
            return
        faint = QColor(ink)
        faint.setAlphaF(0.8)
        refused = drawn.verdict is not None and not drawn.verdict.ok
        painter.setPen(self.c("error") if refused else faint)
        below = QRectF(room.left(), room.top() + line + 1, room.width(), room.height() - line - 1)
        _write_lines(painter, detail, plain, below)

    def ghost(self, painter: QPainter, rect: QRectF, words: str, ok: bool) -> None:
        """Something about to be made: a tinted block where it would go, with its times."""
        colour = self.c("accent" if ok else "error")
        wash = QColor(colour)
        wash.setAlphaF(0.28)
        painter.setBrush(wash)
        painter.setPen(QPen(colour, 2))
        painter.drawRoundedRect(rect, 5, 5)
        bold = time_font(painter.font())
        bold.setBold(True)
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
        colour = self.c("error")
        font = time_font(_small(painter.font()))
        font.setBold(True)
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
        font = QFont(painter.font())
        font.setBold(today)
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


def _initial(title: str, metrics: QFontMetrics, width: float) -> str:
    """A block with no room for any of its name: its first letter if that fits, else nothing. Its
    colour already says a block is there; a lone "…" said nothing more."""
    first = title.strip()[:1]
    return first if first and metrics.horizontalAdvance(first) <= width else ""


def _small(font: QFont) -> QFont:
    made = QFont(font)
    made.setPointSizeF(max(made.pointSizeF() * 0.86, 7))
    return made


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
            " Double-click a block, or press Enter, to open it."
        )
        self.hand, self.painter = hand, painter
        self._lay_out = lay_out
        self.gutter, self.header = gutter, header
        self._names = names or (lambda day: DAYS[day])
        self.tracks: list[LinearTrack] = []
        self.occurrences: tuple[Occurrence, ...] = ()
        self.today: int | None = None
        self.now_min: int | None = None
        self._hover: tuple[LinearTrack, int] | None = None
        self._wheel = 0
        hand.preview_changed.connect(self.update)

    # What it shows

    def set_week(
        self, occurrences: Sequence[Occurrence], today: int | None = None, now_min: int | None = None
    ) -> None:
        self.occurrences = tuple(occurrences)
        self.today, self.now_min = today, now_min
        self.update()

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
        self.update()

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
        with _fresh(painter):
            self.painter.background(painter, QRectF(self.rect()))
        preview = self.hand.preview
        held = preview.held if preview is not None else None
        for index, track in enumerate(self.tracks):
            painter.save()
            painter.setTransform(track.transform, True)
            upright_visible = track.transform.inverted()[0].mapRect(visible)
            with _fresh(painter):
                self.painter.track(painter, track, track.day == self.today)
            if index == 0 and self.gutter and track.axis is Axis.DOWN:
                with _fresh(painter):
                    self.painter.hour_labels(painter, track, self.gutter, visible=upright_visible)
            if index == 0 and self.header and track.axis is Axis.ACROSS:
                with _fresh(painter):
                    self.painter.hour_labels(painter, track, self.header, every=120, visible=upright_visible)
            self._paint_hint(painter, track)
            for drawn, rect in self.drawn(track):
                with _fresh(painter):
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
            self.hand.press(self, held, at, home=(self, track))
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
        length = rect.height() if down else rect.width()
        if length < 2 * EDGE_PX + 6:
            return Gesture.MOVE
        edge = min(EDGE_PX, length / 5)
        from_start = upright.y() - rect.top() if down else upright.x() - rect.left()
        from_end = rect.bottom() - upright.y() if down else rect.right() - upright.x()
        if from_start <= edge:
            return Gesture.RESIZE_START
        if from_end <= edge:
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
        self.hand.open(hit[0].block_id)

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
