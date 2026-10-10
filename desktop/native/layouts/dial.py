"""Day dial: a day screen. The whole day is a 24-hour ring, noon at the top and midnight at the bottom,
and the day's list beside it reads the ring out in words.

The face is painted, so it cannot be tabbed through. The day's list is its keyboard and screen-reader
twin: every segment of the ring is also a row that opens the same block.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QFontMetrics,
    QFontMetricsF,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from desktop.native.calendar import DAY_FULL, DAYS, day_long
from desktop.native.fonts import at_scale, time_font
from desktop.native.hours.canvas import fit_lines
from desktop.native.hours.geometry import DialTrack, Span
from desktop.native.hours.hand import Gesture, Hand, Held
from desktop.native.icons import pixmap
from desktop.native.layouts.base import (
    LayoutView,
    Scene,
    base_sheet,
    button,
    css,
    day_buttons,
    empty,
    family,
    label,
    plural,
    rules,
    scrolling,
)
from desktop.native.look import category_paint
from desktop.native.motion import OUT, Clock, duration, moves
from desktop.native.tokens import (
    RADIUS_CARD,
    RADIUS_CONTROL,
    SPACING,
    WEIGHT_NUMBER,
    WEIGHT_REGULAR,
    WEIGHT_STRONG,
    fit_lightness,
    mix_oklab,
    type_pt,
)
from desktop.native.weekmodel import (
    END_OF_DAY,
    Occurrence,
    clock_label,
    length_label,
    planned_line,
    range_label,
    short_clock,
)
from desktop.native.widgets import FittedLabel

# The mock-up's face at Normal text: 600 across, the ring from 190 to 232 about its centre, and room
# outside it for the ticks and the hour labels.
FACE_MAX, FACE_MIN = 600, 240
INNER_SHARE = 190 / 232
LABEL_ROOM = 62
GAP, MINI_GAP = 2.0, 3.0
MINI = 60
SIDE_MIN = 360
# The time on the face is the display size half again and more, and gives way to a small ring.
TIME_SCALE = 1.6
TIME_SHARE = 0.31
# How far the time sits from the hub, and its note below it, at the full size.
HUB_GAP, NOTE_GAP = 31, 34
EVENING = 22 * 60
# The words written along an arc keep this far from its ends, and need this much over their height
# in the ring's thickness; a name that does not fit is left off, and the key still explains the ring.
ARC_PAD = 6
ARC_ROOM = 4
# The key above the list names each kind of arc the ring shows, in this order.
KEY_TITLE = "Reading the ring"
KEY_WORDS = {
    "coming": "Still to come",
    "over": "Already over",
    "ahead": "Free time, still ahead",
    "gone": "Free time, already gone",
}
# The hand easing to where the time has moved it (decision 35 of 0.17), as the mock-up's does.
HAND_MS = 240
ICON = 18


@dataclass(frozen=True)
class Segment:
    """A stretch of the ring: one block, or free time when `item` is None."""

    start: int
    end: int
    item: Occurrence | None = None


def segments(blocks: Sequence[Occurrence]) -> list[Segment]:
    """The whole day, midnight to midnight, as the stretches the ring draws.

    Where blocks overlap, homework shows over a fixed block and a later start over an earlier one, as
    `day_queue` puts them: a study hall inside School is the part the student acts on, and School
    goes on either side of it."""
    cuts = sorted({0, END_OF_DAY, *(item.start for item in blocks), *(item.end for item in blocks)})
    made: list[Segment] = []
    for start, end in zip(cuts, cuts[1:], strict=False):
        over = [item for item in blocks if item.start < end and start < item.end]
        item = max(over, key=lambda entry: (entry.work, entry.start), default=None)
        if made and made[-1].item == item:
            made[-1] = Segment(made[-1].start, end, item)
        else:
            made.append(Segment(start, end, item))
    return made


def free_minutes(blocks: Sequence[Occurrence], start: int, end: int) -> int:
    """Minutes from `start` to `end` that nothing still to do takes."""
    taken = sorted(
        (max(item.start, start), min(item.end, end))
        for item in blocks
        if item.live and item.start < end and item.end > start
    )
    free, at = 0, start
    for first, last in taken:
        free += max(first - at, 0)
        at = max(at, last)
    return free + max(end - at, 0)


@dataclass(frozen=True)
class ArcLabel:
    """Words written along an arc: where they may run (degrees from the top), what they sit on and the
    ink that reads on it. `icon` is where a homework's book sits when it shares the arc."""

    words: str
    first: float
    last: float
    ground: str
    ink: str
    minutes: tuple[int, int]
    icon: float | None = None


@cache
def ink_on(ink: str, ground: str) -> str:
    """The words' colour moved the least it takes to read at 4.5 to 1 on the arc under them."""
    return fit_lightness(ink, (ground,), 4.5)


def turn(minute: float) -> float:
    """Degrees clockwise from the top of the face: midnight at the bottom, noon at the top."""
    return minute / END_OF_DAY * 360 - 180


def at(centre: QPointF, radius: float, degrees: float) -> QPointF:
    angle = math.radians(degrees)
    return QPointF(centre.x() + radius * math.sin(angle), centre.y() - radius * math.cos(angle))


def sector(centre: QPointF, inner: float, outer: float, first: float, last: float) -> QPainterPath:
    """The ring between two radii, from one turn to another."""
    big = QRectF(centre.x() - outer, centre.y() - outer, outer * 2, outer * 2)
    small = QRectF(centre.x() - inner, centre.y() - inner, inner * 2, inner * 2)
    path = QPainterPath()
    # Qt measures arcs anticlockwise from three o'clock.
    path.arcMoveTo(big, 90 - first)
    path.arcTo(big, 90 - first, first - last)
    path.arcTo(small, 90 - last, last - first)
    path.closeSubpath()
    return path


def hour_label(hour: int) -> str:
    """"14" on the 24-hour clock, "2 PM" on the 12-hour one."""
    return short_clock(hour * 60).removesuffix(":00")


def over_until(scene: Scene, day: int) -> int:
    """How much of `day` is over: all of a day gone by, none of one to come, today up to now."""
    if scene.today is None or day > scene.today:
        return 0
    return END_OF_DAY if day < scene.today else scene.minute


class DialFace(QWidget):
    """One day as a ring of segments. The big face also has ticks, hour labels, the hand and the time;
    the small ones in the week strip are the ring alone, with the hand on today's.

    The big face is a surface for the window's hand: its ring is a `DialTrack`, and a segment pressed
    there is carried round it to a new time. A small face only opens its day."""

    block_clicked = Signal(str)
    day_clicked = Signal(int)

    def __init__(self, day: int, mini: bool, hand: Hand | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.day, self.mini, self.hand = day, mini, hand
        self.takes_blocks = hand is not None and not mini
        self._blocks: tuple[Occurrence, ...] = ()
        self._over = 0
        self._now: int | None = None
        # The minute the hand points at while it eases to `_now`.
        self._hand_at: float | None = None
        self._hand_goal: int | None = None
        self._easing = Clock(self)
        self._tokens: dict[str, str] = {}
        self._scale = 1.0
        self.setObjectName(f"dialMini{day}" if mini else "dialFace")
        if mini:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        if self.takes_blocks:
            self.setMouseTracking(True)
            hand.preview_changed.connect(self.update)

    def set_day(
        self,
        blocks: tuple[Occurrence, ...],
        over: int,
        tokens: dict[str, str],
        now: int | None = None,
        scale: float = 1.0,
    ) -> None:
        """`over` is the minute before which the day is over, drawn paler; `now` draws the hand."""
        self._blocks, self._over, self._tokens, self._now, self._scale = blocks, over, tokens, now, scale
        said = ", ".join(f"{item.title} {clock_label(item.start)}" for item in blocks) or "nothing planned"
        self.setAccessibleName(f"{DAY_FULL[self.day]}: {said}")
        # The time and its note are painted, so they are said here too.
        time = clock_label(now) if now is not None else ""
        self.setAccessibleDescription(". ".join(part for part in (time, self._note()) if part))
        self.update()

    def ease_hand(self, since: int) -> None:
        """Move the hand from `since` to now, easing, where things may travel; else it is simply there."""
        length = duration(HAND_MS)
        if self._now is None or since == self._now or not moves() or not length:
            return
        self._easing.stop()
        self._hand_at = float(since)
        goal = self._now
        self._hand_goal = goal
        self._easing.start(
            length, lambda at: self._eased(since + (goal - since) * OUT.valueForProgress(at / length))
        )

    def _eased(self, minute: object) -> None:
        self._hand_at = None if minute == self._hand_goal else float(minute)
        self.update()

    def _radii(self) -> tuple[QPointF, float, float]:
        """The centre and the ring's inner and outer edge."""
        side = min(self.width(), self.height())
        centre = QPointF(self.width() / 2, self.height() / 2)
        if self.mini:
            outer = side / 2 - 2
            return centre, outer - side * 8 / MINI, outer
        outer = max(side / 2 - LABEL_ROOM * self._scale, 20)
        return centre, outer * INNER_SHARE, outer

    @property
    def track(self) -> DialTrack:
        """The day's minutes round the face: every segment is drawn, pressed and carried on this."""
        centre, inner, outer = self._radii()
        return DialTrack(self.day, centre, inner, outer, 0, END_OF_DAY, 360.0)

    def _paint_of(self, category: str) -> tuple[str, str]:
        """A category's fill, for what is over, and its mark, for what is still to come."""
        tokens = self._tokens
        fill, mark = category_paint(category, {"family": family(tokens), "panel": tokens["surface"]})
        return fill or mix_oklab(tokens["bg_muted"], tokens["bg"], 0.35), mark or tokens["bg_muted"]

    def _free(self, past: bool) -> QColor:
        dark = family(self._tokens) == "dark"
        share = (0.06 if dark else 0.04) if past else (0.11 if dark else 0.08)
        return QColor(mix_oklab(self._tokens["bg_ink"], self._tokens["bg"], share))

    def _shown(self) -> list[Occurrence]:
        """The day's blocks, less the one the hand has lifted off this face."""
        preview = self.hand.preview if self.takes_blocks and self.hand is not None else None
        held = preview.held if preview is not None else None
        if held is None or held.kind is not Gesture.MOVE or held.from_day != self.day:
            return list(self._blocks)
        return [item for item in self._blocks if item.block_id != held.block_id]

    def _held(self) -> tuple[Held, Span, bool, str] | None:
        """What the hand is carrying over this face: what it is, where it would go, whether it can,
        and the words for it."""
        preview = self.hand.preview if self.takes_blocks and self.hand is not None else None
        if preview is None or preview.held.kind not in (Gesture.MOVE, Gesture.PLACE):
            return None
        if preview.span.day != self.day:
            return None
        return preview.held, preview.span, preview.verdict.ok, preview.verdict.words

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        if not self._tokens:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        centre, inner, outer = self._radii()
        words = self.arc_labels()
        icons = {label.minutes: label.icon for label in words if label.icon is not None}
        for piece in segments(self._shown()):
            self._paint_segment(painter, piece, centre, inner, outer, icons.get((piece.start, piece.end)))
        self._paint_arc_labels(painter, centre, inner, outer, words)
        held = None if self.mini else self._held()
        if held is not None:
            thing, span, ok, _words = held
            category = next((item.category for item in self._blocks if item.block_id == thing.block_id), "")
            path = sector(centre, inner, outer, turn(span.start), turn(span.end))
            # Where the carried block would go, edged in the accent, or in red where it cannot.
            painter.setPen(QPen(QColor(self._tokens["accent" if ok else "danger"]), 3))
            painter.setBrush(QColor(self._paint_of(category)[1]))
            painter.drawPath(path)
        if not self.mini:
            self._paint_ticks(painter, centre, outer)
        if self._now is not None:
            self._paint_hand(painter, centre, inner)
        if not self.mini:
            box, lines = self._time_lines()
            for words, font, colour, baseline in lines:
                painter.setFont(font)
                painter.setPen(QColor(self._tokens[colour]))
                width = QFontMetricsF(font).horizontalAdvance(words)
                painter.drawText(QPointF(centre.x() - width / 2, baseline), words)
            if held is not None and held[3]:
                self._paint_words(painter, held[3], held[2], box)
        painter.end()

    def _fill(self, painter: QPainter, path: QPainterPath, colour: QColor) -> None:
        # Stroked in its own colour, as the mock-up draws them, which rounds the corners a little.
        pen = QPen(colour, 2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(colour)
        painter.drawPath(path)

    def _paint_segment(
        self,
        painter: QPainter,
        piece: Segment,
        centre: QPointF,
        inner: float,
        outer: float,
        icon_at: float | None = None,
    ) -> None:
        gap = MINI_GAP if self.mini else GAP
        first, last = turn(piece.start) + gap / 2, turn(piece.end) - gap / 2
        if last <= first:
            return
        item, over = piece.item, self._over
        if item is None:
            # The free time holding now is split there with no gap, its elapsed part fainter.
            parts = [(first, last, piece.end <= over)]
            if piece.start < over < piece.end:
                parts = [(first, turn(over), True), (turn(over), last, False)]
            for begin, finish, past in parts:
                if finish > begin:
                    self._fill(painter, sector(centre, inner, outer, begin, finish), self._free(past))
            return
        past = piece.end <= over or not item.live
        fill, mark = self._paint_of(item.category)
        self._fill(painter, sector(centre, inner, outer, first, last), QColor(fill if past else mark))
        size = round(ICON * self._scale)
        middle = (inner + outer) / 2
        if self.mini or not item.work or math.radians(last - first) * middle < size + 6:
            return
        spot = at(centre, middle, (first + last) / 2 if icon_at is None else icon_at)
        icon = pixmap("book-open", self._tokens["bg_ink" if past else "bg"], size, self.devicePixelRatioF())
        painter.drawPixmap(QPointF(spot.x() - size / 2, spot.y() - size / 2), icon)

    def _arc_font(self) -> QFont:
        return at_scale(self.font(), "caption", self._scale, WEIGHT_STRONG)

    def arc_labels(self) -> list[ArcLabel]:
        """The words that fit along their arcs: each block's name, "Earlier today" on the widest free
        time already gone, and "Free until 22:00" on the free time still ahead (today only). Words that
        would run past their arc, or a ring too thin to hold them, are left off."""
        if self.mini or not self._tokens:
            return []
        _centre, inner, outer = self._radii()
        metrics = QFontMetricsF(self._arc_font())
        if outer - inner < metrics.capHeight() + ARC_ROOM:
            return []
        middle, size = (inner + outer) / 2, round(ICON * self._scale)

        def room(first: float, last: float) -> float:
            return math.radians(last - first) * middle - 2 * ARC_PAD

        plan: list[ArcLabel] = []
        gone: list[ArcLabel] = []
        for piece in segments(self._shown()):
            first, last = turn(piece.start) + GAP / 2, turn(piece.end) - GAP / 2
            item = piece.item
            if last <= first:
                continue
            if item is not None:
                past = piece.end <= self._over or not item.live
                fill, mark = self._paint_of(item.category)
                ground = fill if past else mark
                begin, icon = first, None
                if item.work and math.radians(last - first) * middle >= size + 6:
                    # The book keeps the start of the arc and the name follows it.
                    begin = first + math.degrees((size + 8) / middle)
                    icon = first + math.degrees((size / 2 + 4) / middle)
                if metrics.horizontalAdvance(item.title) <= room(begin, last):
                    ink = ink_on(self._tokens["bg_ink"], ground)
                    minutes = (piece.start, piece.end)
                    plan.append(ArcLabel(item.title, begin, last, ground, ink, minutes, icon))
                continue
            if self._now is None:
                continue
            cut = piece.start < self._over < piece.end
            parts = (
                [(piece.start, self._over, True), (self._over, piece.end, False)]
                if cut
                else [(piece.start, piece.end, piece.end <= self._over)]
            )
            for begin, end, past in parts:
                words = "Earlier today" if past else f"Free until {clock_label(min(end, EVENING))}"
                if not past and begin >= EVENING:
                    continue
                ground = self._free(past).name()
                arc = ArcLabel(
                    words,
                    turn(begin) + (GAP / 2 if begin == piece.start else 0),
                    turn(end) - (GAP / 2 if end == piece.end else 0),
                    ground,
                    ink_on(self._tokens["bg_muted"], ground),
                    (piece.start, piece.end),
                )
                if metrics.horizontalAdvance(words) <= room(arc.first, arc.last):
                    (gone if past else plan).append(arc)
        if gone:
            plan.append(max(gone, key=lambda arc: arc.last - arc.first))
        return plan

    def _paint_arc_labels(
        self, painter: QPainter, centre: QPointF, inner: float, outer: float, labels: list[ArcLabel]
    ) -> None:
        """Each word written along its arc, a letter at a time, turned to the ring. On the bottom half
        the words run the other way round, so they still read left to right."""
        font = self._arc_font()
        metrics = QFontMetricsF(font)
        middle, cap = (inner + outer) / 2, metrics.capHeight()
        painter.setFont(font)
        for arc in labels:
            wide = metrics.horizontalAdvance(arc.words)
            mid = (arc.first + arc.last) / 2
            below = abs(mid) > 90
            painter.setPen(QColor(arc.ink))
            for index, char in enumerate(arc.words):
                before = metrics.horizontalAdvance(arc.words[:index])
                along = before + metrics.horizontalAdvance(char) / 2 - wide / 2
                degrees = math.degrees(along / middle)
                angle = mid - degrees if below else mid + degrees
                spot = at(centre, middle + cap / 2 if below else middle - cap / 2, angle)
                painter.save()
                painter.translate(spot)
                painter.rotate(angle + 180 if below else angle)
                painter.drawText(QPointF(-metrics.horizontalAdvance(char) / 2, 0), char)
                painter.restore()

    def key_rows(self) -> list[tuple[str, list[str]]]:
        """The kinds of arc this ring shows, each with its words and up to three colours: the key under
        the day's list."""
        seen: dict[str, list[str]] = {}
        for piece in segments(self._shown()):
            item = piece.item
            if item is None:
                if piece.end > self._over:
                    seen.setdefault("ahead", [self._free(False).name()])
                if piece.start < self._over:
                    seen.setdefault("gone", [self._free(True).name()])
                continue
            fill, mark = self._paint_of(item.category)
            kind, colour = ("over", fill) if piece.end <= self._over or not item.live else ("coming", mark)
            colours = seen.setdefault(kind, [])
            if colour not in colours and len(colours) < 3:
                colours.append(colour)
        return [(KEY_WORDS[kind], seen[kind]) for kind in KEY_WORDS if kind in seen]

    def _paint_ticks(self, painter: QPainter, centre: QPointF, outer: float) -> None:
        """Labels every two hours, with ticks only between them so no tick reads as a minus sign."""
        scale, tokens = self._scale, self._tokens
        font = at_scale(self.font(), "caption", scale)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        for hour in range(24):
            degrees = turn(hour * 60)
            long = hour % 6 == 0
            pen = QPen(QColor(tokens["bg_muted" if long else "line"]), 1.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            reach = (17 if long else 12) * scale
            if hour % 2:
                painter.drawLine(at(centre, outer + 7 * scale, degrees), at(centre, outer + reach, degrees))
            if hour % 2 == 0:
                words = hour_label(hour)
                # A wider label needs more space from the ring.
                wider = metrics.horizontalAdvance(words) - metrics.horizontalAdvance("06")
                across = abs(math.sin(math.radians(degrees))) * wider / 2
                spot = at(centre, outer + 32 * scale + across, degrees)
                painter.setPen(QColor(tokens["bg_muted"]))
                room = QRectF(spot.x() - 40, spot.y() - 12, 80, 24)
                painter.drawText(room, Qt.AlignmentFlag.AlignCenter, words)

    def _hand_tip(self, centre: QPointF, inner: float, minute: float | None = None) -> QPointF:
        """The hand reaches the ring's inner edge and no further. It points at `minute`, or at now."""
        pointing = minute if minute is not None else self._now or 0
        return at(centre, inner - (4 if self.mini else 8), turn(pointing))

    def _paint_hand(self, painter: QPainter, centre: QPointF, inner: float) -> None:
        accent = QColor(self._tokens["accent"])
        pen = QPen(accent, 1.75 if self.mini else 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(centre, self._hand_tip(centre, inner, self._hand_at))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawEllipse(centre, 3 if self.mini else 8, 3 if self.mini else 8)
        if not self.mini:
            painter.setBrush(QColor(self._tokens["bg"]))
            painter.drawEllipse(centre, 3, 3)

    def _note(self) -> str:
        if self._now is None or self._now >= EVENING:
            return ""
        free = free_minutes(self._blocks, self._now, EVENING)
        until = clock_label(EVENING)
        return f"{length_label(free)} free until {until}" if free else f"No free time until {until}"

    def _time_lines(self) -> tuple[QRectF, list[tuple[str, QFont, str, float]]]:
        """The time and its note as one block of words, and each line's font, colour and baseline.

        The block sits under the hub, or above it when the hand would cross it there, as it does when
        it points down around midnight. Another day shows its name in the middle, with no hand."""
        centre, inner, _outer = self._radii()
        full = type_pt("display", self._scale) * TIME_SCALE
        big = time_font(at_scale(self.font(), "display", self._scale, WEIGHT_NUMBER))
        big.setPointSizeF(min(full, inner * TIME_SHARE * 72 / max(self.logicalDpiY(), 1)))
        big.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98)
        shrink = big.pointSizeF() / full
        words = clock_label(self._now) if self._now is not None else DAYS[self.day]
        metrics = QFontMetricsF(big)
        lines = [(words, big, "bg_ink", metrics.capHeight())]
        width, height = metrics.horizontalAdvance(words), metrics.capHeight() + metrics.descent()
        note = self._note()
        small = at_scale(self.font(), "body", self._scale)
        quiet = QFontMetricsF(small)
        baseline = metrics.capHeight() + NOTE_GAP * shrink
        # The note only where it fits inside the ring.
        reach = math.hypot(quiet.horizontalAdvance(note) / 2, HUB_GAP * shrink + baseline + quiet.descent())
        if note and reach < inner - 6:
            lines.append((note, small, "bg_muted", baseline))
            width = max(width, quiet.horizontalAdvance(note))
            height = baseline + quiet.descent()
        if self._now is None:
            top = centre.y() - metrics.capHeight() / 2
        else:
            top = centre.y() + HUB_GAP * shrink
            below = QRectF(centre.x() - width / 2, top, width, height)
            tip = self._hand_tip(centre, inner)
            if any(below.contains(centre + (tip - centre) * (step / 40)) for step in range(41)):
                top = centre.y() - HUB_GAP * shrink - height
        return (
            QRectF(centre.x() - width / 2, top, width, height),
            [(text, font, colour, top + offset) for text, font, colour, offset in lines],
        )

    def time_box(self) -> QRectF:
        """Where the time and its note are drawn, for the tests."""
        return self._time_lines()[0]

    def _paint_words(self, painter: QPainter, words: str, ok: bool, time: QRectF) -> None:
        """The held block's words on a pill across the hub from the time, as wide as the ring allows,
        so they stay on the face wherever the segment is carried."""
        centre, inner, _outer = self._radii()
        font = at_scale(self.font(), "body", self._scale, WEIGHT_STRONG)
        metrics = QFontMetricsF(font)
        lines = fit_lines(words, font, 2 * inner - 40, metrics.lineSpacing() * 3)
        if not lines:
            return
        wide = max(metrics.horizontalAdvance(line) for line in lines) + 20
        tall = metrics.lineSpacing() * len(lines) + 10
        top = centre.y() - 14 - tall if time.top() >= centre.y() - 1 else centre.y() + 14
        pill = QRectF(centre.x() - wide / 2, top, wide, tall)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._tokens["accent" if ok else "danger"]))
        painter.drawRoundedRect(pill, RADIUS_CONTROL, RADIUS_CONTROL)
        painter.setPen(QColor(self._tokens["accent_ink" if ok else "danger_ink"]))
        painter.setFont(font)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, "\n".join(lines))

    def _runs_of(self, block_id: str) -> list[Segment]:
        return [piece for piece in segments(self._shown()) if piece.item and piece.item.block_id == block_id]

    def block_at(self, spot: QPointF) -> Occurrence | None:
        track = self.track
        if not track.contains(spot):
            return None
        minute = track.minute_at(spot)
        return next(
            (piece.item for piece in segments(self._blocks) if piece.start <= minute < piece.end), None
        )

    # The hand's surface

    def track_at(self, point: QPointF) -> DialTrack | None:
        track = self.track
        return track if self.takes_blocks and track.contains(point) else None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self.mini:
            self.day_clicked.emit(self.day)
            return
        item = self.block_at(event.position()) if event.button() == Qt.MouseButton.LeftButton else None
        if item is None or not self.takes_blocks:
            return
        track = self.track
        # How far into the block it was held, so it does not jump on the first move.
        grab = round(track.minute_at(event.position()) - item.start)
        held = Held(
            Gesture.MOVE,
            item.title,
            item.minutes,
            item.block_id,
            item.day,
            Span(item.day, item.start, item.end),
            grab,
        )
        self.hand.press(
            self,
            held,
            event.globalPosition().toPoint(),
            tap=lambda: self.block_clicked.emit(item.block_id),
            home=(self, track),
        )

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        item = self.block_at(QPointF(event.pos())) if self.takes_blocks and not self.mini else None
        if item is None or self.hand.busy:
            event.ignore()
            return
        event.accept()
        self.hand.ask_menu(item.block_id, item.day, event.globalPos())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self.takes_blocks and not self.hand.busy:
            over = self.block_at(event.position()) is not None
            self.setCursor(Qt.CursorShape.OpenHandCursor if over else Qt.CursorShape.ArrowCursor)

    # For the rig and the tests, in global coordinates

    def take_focus(self, ring: bool, placed: tuple | None = None) -> None:
        """The keyboard lands on the ring. The other designs land on their hours; Dial has none."""
        del ring
        if not self.takes_blocks:
            return
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        if placed is not None and self.hand is not None and placed[1] == self.day:
            self.hand.select(placed[0], placed[1])

    def track_for(self, day: int, minute: int | None = None) -> DialTrack | None:
        track = self.track
        if not self.takes_blocks or day != self.day:
            return None
        if minute is not None and not track.first <= minute <= track.last:
            return None
        return track

    def point_for(self, day: int, minute: int) -> QPoint:
        track = self.track_for(day, minute)
        if track is None:
            raise LookupError(f"no ring for day {day} at minute {minute}")
        return self.mapToGlobal(track.point_for(minute).toPoint())

    def block_rect(self, block_id: str, day: int) -> QRect | None:
        """A box as big as the block's longest segment, centred on its middle, so its centre is on
        the block."""
        runs = self._runs_of(block_id)
        if day != self.day or not self.takes_blocks or not runs:
            return None
        longest = max(runs, key=lambda piece: piece.end - piece.start)
        centre, inner, outer = self._radii()
        points = [
            at(centre, reach, turn(longest.start + (longest.end - longest.start) * share))
            for share in (0, 0.25, 0.5, 0.75, 1)
            for reach in (inner, outer)
        ]
        xs, ys = [point.x() for point in points], [point.y() for point in points]
        size = QRectF(0, 0, max(xs) - min(xs), max(ys) - min(ys))
        size.moveCenter(at(centre, (inner + outer) / 2, turn((longest.start + longest.end) / 2)))
        box = size.toRect()
        return QRect(self.mapToGlobal(box.topLeft()), box.size())

    def day_name(self, day: int) -> QPoint:
        raise LookupError("the dial names no day on its face")

    def _scroll_area(self) -> QScrollArea | None:
        area = self.parentWidget()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        return area

    def in_view(self, day: int, minute: int) -> bool:
        track = self.track_for(day, minute)
        if track is None:
            return False
        local = track.point_for(minute).toPoint()
        area = self._scroll_area()
        if area is None:
            return self.rect().contains(local)
        viewport = area.viewport()
        return viewport.rect().adjusted(-2, -2, 2, 2).contains(self.mapTo(viewport, local))

    def reveal(self, day: int, first: int, last: int) -> None:
        area = self._scroll_area()
        track = self.track_for(day)
        if area is None or track is None:
            return
        for minute in (last, first):
            local = track.point_for(min(max(minute, track.first), track.last)).toPoint()
            inside = self.mapTo(area.widget(), local)
            area.ensureVisible(inside.x(), inside.y(), 20, 40)

    def held_words(self) -> str:
        preview = self.hand.preview if self.hand is not None else None
        return preview.verdict.words if preview is not None else ""


def _quiet(widget: QWidget) -> QWidget:
    """A part of a row that lets the pointer through to the row, which opens the block."""
    widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    return widget


class _Swatch(QWidget):
    """A small rounded chip of an arc's colours, side by side, in the key."""

    def __init__(self, colours: list[str], edge: str, width: int, height: int) -> None:
        super().__init__()
        self.colours, self._edge = colours, edge
        self.setObjectName("dialKeySwatch")
        self.setFixedSize(width, height)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        shape = QPainterPath()
        shape.addRoundedRect(box, 3, 3)
        painter.setClipPath(shape)
        share = box.width() / max(len(self.colours), 1)
        for index, colour in enumerate(self.colours):
            stripe = QRectF(box.left() + index * share, box.top(), share + 1, box.height())
            painter.fillRect(stripe, QColor(colour))
        painter.setClipping(False)
        painter.setPen(QPen(QColor(self._edge), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(shape)
        painter.end()


class DayDialView(LayoutView):
    """The day as a dial (0.17's Dial): the ring on the left, the Next card and the day's list beside
    it, and the week's small dials along the bottom."""

    layout_id = "dial"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        self._day: int | None = None
        self._face: DialFace | None = None
        # The day and minute the hand last pointed at, for it to ease on from there.
        self._hand_was: tuple[int, int] | None = None
        self._side: QWidget | None = None
        # A view's minimum height must not become the window's: three designs pushed it past a 768 pixel
        # laptop screen. Inside a scroll area, what does not fit scrolls and the window keeps its size.
        outer = self._outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._page = QWidget()
        self._page.setObjectName("dialPage")
        self._root = QHBoxLayout(self._page)
        self._scroll = scrolling(self._page, "dialScroll")
        outer.addWidget(self._scroll, 1)
        # The week strip is how another day is reached, so it is pinned below the scroller rather
        # than left at the bottom of a column. At large text it used to be sliced in half, with the
        # day names off screen entirely.
        self._strip_host = QWidget()
        self._strip_host.setObjectName("dialStrip")
        self._strip = QVBoxLayout(self._strip_host)
        outer.addWidget(self._strip_host)

    def shown_day(self, scene: Scene) -> int:
        return self._day if self._day is not None else (scene.today if scene.today is not None else 0)

    def watched_date(self) -> str | None:
        scene = self._scene
        return scene.week.date_of(self.shown_day(scene)).isoformat() if scene is not None else None

    def _show_day(self, day: int) -> None:
        scene = self._scene
        if scene is None:
            return
        self._day = None if day == scene.today else day
        self.render(scene, False)
        self.watched_day_changed.emit(scene.week.date_of(day).isoformat())

    def render(self, scene: Scene, week_changed: bool) -> None:
        if week_changed:
            self._day = None
        day = self.shown_day(scene)
        is_today = day == scene.today
        px = scene.px
        self.setStyleSheet(self._sheet(scene))
        self._root.setContentsMargins(px(SPACING[3]), px(SPACING[3]), px(SPACING[4]), 0)
        self._root.setSpacing(px(SPACING[4]))
        self._strip.setContentsMargins(px(SPACING[3]), px(SPACING[3]), px(SPACING[4]), px(SPACING[4]))
        empty(self._root)
        self._face = DialFace(day, False, self.hand)
        now = scene.minute if is_today else None
        self._face.set_day(scene.week.on_day(day), over_until(scene, day), scene.tokens, now, scene.scale)
        was, self._hand_was = self._hand_was, (day, now) if now is not None else None
        if was is not None and was[0] == day and now is not None:
            self._face.ease_hand(was[1])
        self._face.block_clicked.connect(self.block_activated.emit)
        self._root.addWidget(self._face, 0, Qt.AlignmentFlag.AlignTop)
        self._side = QWidget()
        self._side.setObjectName("dialSide")
        side = QVBoxLayout(self._side)
        side.setContentsMargins(0, px(SPACING[4]), 0, 0)
        side.setSpacing(px(SPACING[3]))
        side.addWidget(self._card(scene, day, is_today))
        # Above the list, which can run long: under it the key sat below the fold at 1300 by 720.
        side.addWidget(self._key(scene, self._face.key_rows()))
        if scene.options.get("list") != "hide":
            side.addWidget(self._list(scene, day, is_today))
        side.addStretch(1)
        self._root.addWidget(self._side, 1)
        empty(self._strip)
        wanted = scene.options.get("week") != "hide"
        self._strip_host.setVisible(wanted)
        if wanted:
            self._strip.addWidget(self._week(scene, day))
        # Shown now rather than on the event loop's next pass, so _fit measures them.
        for part in (self._face, self._side, *self._strip_host.findChildren(QFrame, "dialWeek")):
            part.show()
        self._fit()

    def _sheet(self, scene: Scene) -> str:
        tokens = scene.tokens

        def size(role: str) -> str:
            return f"{type_pt(role, scene.scale)}pt"

        def pill(role: str, padding: int) -> str:
            # Qt draws a radius over half the height as square corners, so it is measured.
            return f"{(QFontMetrics(at_scale(self.font(), role, scene.scale)).height() + 2 * padding) // 2}px"

        ink, muted, text, card = tokens["bg_ink"], tokens["muted"], tokens["text"], tokens["surface"]
        edge = f"1px solid {tokens['line']}"
        tint = mix_oklab(tokens["accent"], card, 0.10)
        # Words on the cards are the colourway's card text. Each label's own rule names its type, so it
        # ties with the card's rule and wins by coming after it.
        return base_sheet(self.objectName(), tokens) + rules(
            self.objectName(),
            {
                "#dialScroll, #dialPage, #dialSide, #dialStrip": css(background=tokens["bg"]),
                "#dialCard, #dialList, #dialKey, #dialWeek": css(
                    background=card, border=edge, border_radius=f"{round(RADIUS_CARD * 1.4)}px"
                ),
                "#dialCard QLabel, #dialList QLabel, #dialKey QLabel, #dialWeek QLabel": css(
                    color=text, font_size=size("body")
                ),
                "QLabel#dialKicker, QLabel#dialListLabel": css(color=muted, font_weight=WEIGHT_STRONG),
                "QLabel#dialIn": css(
                    color=fit_lightness(tokens["accent"], (tint,), 4.5),
                    background=tint,
                    font_weight=WEIGHT_STRONG,
                    border_radius=pill("body", 2),
                    padding="2px 10px",
                ),
                "QLabel#dialTitle": css(font_size=size("title"), font_weight=WEIGHT_STRONG),
                # Nothing else planned: a sentence of words, not the screen's headline (#25).
                'QLabel#dialTitle[quiet="true"]': css(font_size=size("heading"), font_weight=WEIGHT_STRONG),
                "QLabel#dialKeyWord": css(color=muted, font_size=size("caption")),
                "QLabel#dialThen, QLabel#dialCount, QLabel#dialRowLength, QLabel#dialWaitingList": css(
                    color=muted
                ),
                "QLabel#dialRowName, QLabel#dialWaiting": css(font_weight=WEIGHT_STRONG),
                'QPushButton[state="past"] #dialRowTime, QPushButton[state="past"] #dialRowName': css(
                    color=muted
                ),
                "#dialRowTag": css(
                    background=mix_oklab(text, card, 0.06), border_radius=f"{RADIUS_CONTROL}px"
                ),
                "QLabel#dialRowTagText": css(
                    color=muted, font_size=size("caption"), font_weight=WEIGHT_REGULAR
                ),
                # Styled so their rule is drawn, and clear so the window's page colour is not.
                "#dialNone, #dialUnplaced": css(background="transparent", border_top=edge),
                "#dialNone QLabel": css(color=muted),
                "QLabel#dialMiniName": css(color=muted, font_size=size("caption")),
                "QLabel#dialMiniDate": css(font_size=size("caption"), font_weight=WEIGHT_STRONG),
                'QLabel#dialMiniName[chosen="true"]': css(color=text, font_weight=WEIGHT_STRONG),
                'QLabel#dialMiniDate[today="true"]': css(
                    background=tokens["accent"],
                    color=tokens["accent_ink"],
                    border_radius=pill("caption", 0),
                    padding="0 6px",
                ),
                "QPushButton": css(
                    background=card,
                    color=text,
                    border=edge,
                    border_radius=f"{RADIUS_CONTROL}px",
                    padding=f"0 {scene.px(14)}px 0 {scene.px(SPACING[2])}px",
                    min_height=f"{scene.px(36)}px",
                    font_size=size("body"),
                    font_weight=WEIGHT_STRONG,
                ),
                "QPushButton:hover": css(background=mix_oklab(text, card, 0.06)),
                'QPushButton[kind="main"]': css(
                    background=tokens["accent"], color=tokens["accent_ink"], border_color=tokens["accent"]
                ),
                'QPushButton[kind="row"]': css(
                    background="transparent",
                    border="none",
                    border_top=edge,
                    border_radius="0px",
                    padding="0px",
                    min_height=f"{scene.px(40)}px",
                ),
                'QPushButton[kind="row"]:hover': css(background=mix_oklab(text, card, 0.04)),
                # Rung only when reached with the keyboard, as every button in the app is.
                'QPushButton[keyfocus="true"]:focus': css(border_color=tokens["accent"]),
                'QPushButton[kind="main"][keyfocus="true"]:focus': css(border_color=ink),
                'QPushButton[kind="row"][keyfocus="true"]:focus': css(background=tint),
            },
        )

    def _card(self, scene: Scene, day: int, is_today: bool) -> QFrame:
        """What is on now or next, with the day's buttons; or, for another day, what it holds."""
        card = QFrame()
        card.setObjectName("dialCard")
        px = scene.px
        inner = QVBoxLayout(card)
        inner.setContentsMargins(px(SPACING[4]), px(SPACING[3]), px(SPACING[4]), px(SPACING[4]))
        inner.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(px(SPACING[2]))
        heading = QHBoxLayout()
        heading.setSpacing(px(10))
        item, pill, line, quiet = None, "", "", False
        if is_today:
            found = scene.week.day_queue(day, scene.minute)
            item = found.queue[0] if found.queue else None
            if item is None:
                kicker, title, line = scene.week.leftover_parts(day)
                quiet = kicker == title
                if quiet and scene.minute < EVENING:
                    line = f"Your evening is free until {clock_label(EVENING)}."
            elif item == found.current:
                kicker, title, pill = "Now", item.title, f"{length_label(item.end - scene.minute)} left"
            else:
                kicker, title, pill = "Up next", item.title, f"in {length_label(item.start - scene.minute)}"
            if item is not None:
                line = f"{range_label(item.start, item.end)} · {length_label(item.minutes)}"
                if len(found.queue) > 1:
                    after = found.queue[1]
                    line += f" · then {after.title} at {clock_label(after.start)}"
            made = day_buttons(self, scene, item, "dial")
        else:
            work = [entry for entry in scene.week.on_day(day) if entry.work]
            date = scene.week.date_of(day)
            kicker = day_long(date)
            title = planned_line(
                sum(entry.minutes for entry in work), sum(entry.minutes for entry in work if entry.done)
            )
            made = []
            if scene.today is not None:
                today = button("Back to today", "dialToday", "main")
                today.clicked.connect(lambda _=False, target=scene.today: self._show_day(target))
                made.append(today)
            else:
                line = "This is not the current week, so there is no now to show."
            back = button("Back to planning", "dialBack")
            back.clicked.connect(self.back_requested.emit)
            made.append(back)
        said = label(kicker, "dialKicker")
        # Said once: a heading that only repeats the title goes. Only ever hidden here: the row has no
        # parent yet, and shown now the label would open as a window of its own for a moment.
        if kicker == title:
            said.hide()
        top.addWidget(said)
        top.addStretch()
        if pill:
            top.addWidget(label(pill, "dialIn"))
        inner.addLayout(top)
        inner.addSpacing(px(SPACING[1]))
        if item is not None:
            dot = QFrame()
            dot.setObjectName("dialDot")
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(
                f"background: {self._mark(scene, item.category)}; border-radius: 5px; border: none;"
            )
            heading.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        words = label(title, "dialTitle", wrap=True)
        words.setProperty("quiet", quiet)
        heading.addWidget(words, 1)
        inner.addLayout(heading)
        if line:
            inner.addSpacing(px(SPACING[0]))
            inner.addWidget(label(line, "dialThen", wrap=True))
        inner.addSpacing(px(SPACING[3]))
        # Two to a row, so the card stays narrow enough to leave the dial its room.
        actions = QGridLayout()
        actions.setHorizontalSpacing(px(SPACING[1]))
        actions.setVerticalSpacing(px(SPACING[1]))
        for index, entry in enumerate(made):
            actions.addWidget(entry, index // 2, index % 2)
        actions.setColumnStretch(2, 1)
        inner.addLayout(actions)
        return card

    def _mark(self, scene: Scene, category: str) -> str:
        tokens = scene.tokens
        mark = category_paint(category, {"family": family(tokens), "panel": tokens["surface"]})[1]
        return mark or tokens["muted"]

    def _list(self, scene: Scene, day: int, is_today: bool) -> QFrame:
        """The day in rows: start time, category mark, title and length, in columns. What is over is
        marked Done rather than struck through, and every row opens its block."""
        box = QFrame()
        box.setObjectName("dialList")
        px = scene.px
        column = QVBoxLayout(box)
        column.setContentsMargins(px(SPACING[4]), px(SPACING[3]), px(SPACING[4]), px(SPACING[2]))
        column.setSpacing(0)
        blocks = scene.week.on_day(day)
        header = QHBoxLayout()
        header.addWidget(label("Today" if is_today else DAY_FULL[day], "dialListLabel"))
        header.addStretch()
        header.addWidget(label(plural(len(blocks), "thing"), "dialCount"))
        column.addLayout(header)
        column.addSpacing(px(SPACING[0]))
        found = scene.week.day_queue(day, scene.minute) if is_today else None
        closing = found is not None and bool(found.queue)
        times = QFontMetrics(at_scale(self.font(), "body", scene.scale))
        shown = [item.start for item in blocks] + ([max(item.end for item in blocks)] if closing else [])
        time_width = max((times.horizontalAdvance(clock_label(minute)) for minute in shown), default=0) + 2
        over = over_until(scene, day)
        for index, item in enumerate(blocks):
            current = found.current if found is not None else None
            column.addWidget(self._row(scene, index, item, item == current, over, time_width))
        if closing:
            # Said once, where the day ends: the card is still about what comes next.
            column.addWidget(self._closing(scene, max(item.end for item in blocks), time_width))
        if scene.week.waiting:
            column.addWidget(self._unplaced(scene))
        return box

    def _key(self, scene: Scene, rows: list[tuple[str, list[str]]]) -> QFrame:
        """"Reading the ring": what each kind of arc on the face means, for the kinds it shows."""
        box = QFrame()
        box.setObjectName("dialKey")
        px = scene.px
        column = QVBoxLayout(box)
        column.setContentsMargins(px(SPACING[4]), px(SPACING[3]), px(SPACING[4]), px(SPACING[3]))
        column.setSpacing(px(SPACING[1]))
        column.addWidget(label(KEY_TITLE, "dialListLabel"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(px(SPACING[4]))
        grid.setVerticalSpacing(px(SPACING[1]))
        for index, (words, colours) in enumerate(rows):
            cell = QHBoxLayout()
            cell.setSpacing(px(SPACING[1]))
            cell.addWidget(_Swatch(colours, scene.tokens["line"], px(22), px(10)))
            cell.addWidget(label(words, "dialKeyWord"), 1)
            grid.addLayout(cell, index // 2, index % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        column.addLayout(grid)
        return box

    def _row(
        self, scene: Scene, index: int, item: Occurrence, is_now: bool, over: int, time_width: int
    ) -> QPushButton:
        px, tokens = scene.px, scene.tokens
        past = not item.live or item.end <= over
        state = "now" if is_now else "past" if past else ""
        row = button("", f"dialRow{index}", "row")
        row.setProperty("state", state)
        tag = "Missed" if item.missed else "Done" if past else ""
        pinned = "Pinned" if item.pinned else ""
        said = [clock_label(item.start), item.title, length_label(item.minutes), tag, pinned]
        row.setAccessibleName(", ".join(part for part in said if part))
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(px(SPACING[2]))
        when = label(clock_label(item.start), "dialRowTime")
        when.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        when.setFixedWidth(time_width)
        line.addWidget(_quiet(when))
        fill, mark = category_paint(item.category, {"family": family(tokens), "panel": tokens["surface"]})
        mark = mark or tokens["muted"]
        edge = QFrame()
        edge.setObjectName("dialRowMark")
        edge.setFixedSize(4, px(20))
        edge.setStyleSheet(
            f"background: {fill or mark}; border: 1px solid {mark}; border-radius: 2px;"
            if past
            else f"background: {mark}; border: none; border-radius: 2px;"
        )
        line.addWidget(_quiet(edge))
        name = QHBoxLayout()
        name.setSpacing(px(6))
        if item.work:
            book = QLabel()
            book.setPixmap(pixmap("book-open", tokens["muted"], 14, self.devicePixelRatioF()))
            name.addWidget(_quiet(book))
        title = FittedLabel(minimum=40)
        title.setObjectName("dialRowName")
        title.set_full_text(item.title)
        name.addWidget(_quiet(title))
        if tag:
            name.addWidget(_quiet(self._tag(scene, tag, "check" if tag == "Done" else "")))
        if item.pinned:
            name.addWidget(_quiet(self._tag(scene, "Pinned", "")))
        name.addStretch(1)
        line.addLayout(name, 1)
        length = label(length_label(item.minutes), "dialRowLength")
        length.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        length.setMinimumWidth(px(80))
        line.addWidget(_quiet(length))
        row.clicked.connect(lambda _=False, key=item.block_id: self.block_activated.emit(key))
        return row

    def _tag(self, scene: Scene, word: str, icon: str) -> QFrame:
        tag = QFrame()
        tag.setObjectName("dialRowTag")
        line = QHBoxLayout(tag)
        line.setContentsMargins(scene.px(6), 0, scene.px(6), 0)
        line.setSpacing(scene.px(3))
        if icon:
            mark = QLabel()
            mark.setPixmap(pixmap(icon, scene.tokens["muted"], 12, self.devicePixelRatioF()))
            line.addWidget(mark)
        line.addWidget(label(word, "dialRowTagText"))
        tag.setFixedHeight(scene.px(20))
        return tag

    def _closing(self, scene: Scene, minute: int, time_width: int) -> QWidget:
        row = QWidget()
        row.setObjectName("dialNone")
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row.setMinimumHeight(scene.px(40))
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(scene.px(SPACING[2]))
        when = label(clock_label(minute), "dialNoneTime")
        when.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        when.setFixedWidth(time_width)
        line.addWidget(when)
        line.addSpacing(4)
        line.addWidget(label("Nothing else today", "dialNoneName"), 1)
        return row

    def _unplaced(self, scene: Scene) -> QWidget:
        """Homework with no time yet, counted, and named after it as far as there is room."""
        waiting = scene.week.waiting
        row = QWidget()
        row.setObjectName("dialUnplaced")
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        line = QHBoxLayout(row)
        line.setContentsMargins(0, scene.px(SPACING[2]), 0, scene.px(SPACING[1]))
        line.setSpacing(scene.px(SPACING[1]))
        book = QLabel()
        book.setPixmap(
            pixmap("book-open", self._mark(scene, "assignments"), 16, self.devicePixelRatioF())
        )
        line.addWidget(book)
        line.addWidget(label(f"{len(waiting)} homework not placed yet", "dialWaiting"))
        names = FittedLabel(minimum=40)
        names.setObjectName("dialWaitingList")
        names.set_full_text("· " + ", ".join(item.title for item in waiting))
        line.addWidget(names, 1)
        return row

    def _week(self, scene: Scene, day: int) -> QFrame:
        """The week's small dials, labelled, today's with its hand and the days gone by paler."""
        card = QFrame()
        card.setObjectName("dialWeek")
        px = scene.px
        strip = QHBoxLayout(card)
        strip.setContentsMargins(px(SPACING[3]), px(SPACING[1]), px(SPACING[3]), px(SPACING[1]))
        strip.setSpacing(px(SPACING[1]))
        for index, name in enumerate(DAYS):
            cell = QVBoxLayout()
            cell.setSpacing(px(SPACING[0]))
            mini = DialFace(index, True)
            mini.setFixedSize(px(MINI), px(MINI))
            mini.set_day(
                scene.week.on_day(index),
                over_until(scene, index),
                scene.tokens,
                scene.minute if index == scene.today else None,
                scene.scale,
            )
            mini.day_clicked.connect(self._show_day)
            cell.addWidget(mini, 0, Qt.AlignmentFlag.AlignHCenter)
            said = QHBoxLayout()
            said.setSpacing(px(SPACING[0]))
            said.addStretch()
            short = label(name, "dialMiniName")
            short.setProperty("chosen", index in (day, scene.today))
            said.addWidget(short)
            date = label(str(scene.week.date_of(index).day), "dialMiniDate")
            date.setProperty("today", index == scene.today)
            said.addWidget(date)
            said.addStretch()
            cell.addLayout(said)
            strip.addLayout(cell, 1)
        return card

    def _fit(self) -> None:
        """The dial as large as the room allows, up to its size in the mock-up, and never so large
        that the day's list beside it loses its columns."""
        face, side, scene = self._face, self._side, self._scene
        if face is None or side is None or scene is None:
            return
        for child in self.findChildren(QWidget):
            child.ensurePolished()
        # The strip below takes its height first; the dial has what is left of the scroller.
        self._outer.activate()
        margins = self._root.contentsMargins()
        # Room is kept for the scroller's bar, which a long list brings, so it never pushes the page
        # sideways.
        bar = self._scroll.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        across = self._scroll.width() - bar - margins.left() - margins.right() - self._root.spacing()
        across -= max(side.minimumSizeHint().width(), scene.px(SIDE_MIN))
        down = self._scroll.height() - margins.top() - margins.bottom()
        size = max(min(scene.px(FACE_MAX), across, down), scene.px(FACE_MIN))
        face.setFixedSize(size, size)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit()
