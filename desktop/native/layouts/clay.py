"""Clay deck: the week as a row of clay cards, one day at a time (0.17's Card carousel).

The day in front is a large card of its hours, which scroll and zoom. The days either side peek at 70 %,
laid out smaller rather than shrunk, so their words stay on the type scale, under a 60 % veil of the
page's colour so the front holds the eye. They show the stretch of the day the card in front opened
at, with its hours labelled, and stay there while it scrolls. A card is whole or out of sight, never
cut by the window's edge. The round arrows beside the card, the wheel over the row, or a sideways
drag on a neighbour or the room between the cards slide it a day at a time. Every card is live hours
on the window's hand: a block goes to a neighbour by a drop on it, and further by resting on an arrow
while it is held, which slides the row. Homework not placed yet rests in a pressed-in dish under the
row.

Day is the same row with its day's card open wider: its hours, and beside them the day's hours by
kind and, today, what is left of it.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable
from datetime import date
from typing import NamedTuple

from PySide6.QtCore import (
    QAbstractAnimation,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontInfo,
    QFontMetricsF,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from desktop.native import icons
from desktop.native.calendar import CATEGORIES, DAY_FULL, DAYS, category_icon
from desktop.native.fonts import at_scale, caption, time_font, weighted
from desktop.native.hours.canvas import (
    BOOK,
    HOMEWORK_CATEGORIES,
    INLINE_GAP,
    BlockPainter,
    Drawn,
    HoursCanvas,
    name_kept,
    word_elide,
)
from desktop.native.hours.chips import TrayChip
from desktop.native.hours.classic import open_hours
from desktop.native.hours.geometry import BETWEEN, FIRST, LAST, Axis, LinearTrack
from desktop.native.hours.hand import Hand
from desktop.native.hours.zoom import HoursScroll, Scale
from desktop.native.layouts.base import (
    LayoutView,
    Scene,
    base_sheet,
    css,
    empty,
    family,
    family_fill,
    label,
    plural,
    rules,
    scrolling,
)
from desktop.native.look import category_paint, readable_ink
from desktop.native.motion import OUT, Clock, app_level, between, duration, fade_away, hold_picture, moves
from desktop.native.tokens import (
    RADIUS_CARD,
    RADIUS_CONTROL,
    SHADOW_LARGE,
    WEIGHT_REGULAR,
    WEIGHT_STRONG,
    mix_oklab,
    type_pt,
)
from desktop.native.weekmodel import Occurrence, Waiting, WeekModel, clock_label, length_label, short_clock
from desktop.native.widgets import FlowLayout

# The card in front opens at the mock-up's 38 pixels an hour, Week and Day alike: 08:00 to 22:00 on a
# card as tall as the mock-up's.
WEEK_SCALE = Scale("clay.week", (30, 38, 48, 64, 96), 38)
DAY_SCALE = Scale("clay.day", (30, 38, 48, 64, 96), 38)
# The mock-up's measures at Normal text, in pixels: the card in front on Week and open on Day, the
# room between cards, above and below the one in front, the arrows, and each card's name row.
FRONT, OPEN = 452, 800
PEEK = 0.7
GAP = 32
# Above the card in front, and under it to the dish, where its shadow fades.
INSET, FOOT = 8, 24
ARROW = 44
FRONT_HEAD, PEEK_HEAD = 60, 48
# Inside a card, left, right and at its foot: the one in front, and a neighbour.
FRONT_PAD = (12, 16, 16)
PEEK_PAD = (8, 8, 12)
# The hour labels beside the hours in front, and room above and below them for the first and last.
LABELS = 56
# Beside a neighbour's labels: the 8 pixels hour labels keep from the hours, and 4 before them.
PEEK_LABEL_GAP = 12
END_ROOM = 20
# Day's hours by kind beside its hours, and the room between them.
SUMMARY, SUMMARY_GAP = 280, 24
# Round the page, at its sides and above and below; the dish's height; the fade at the row's ends.
AROUND = (20, 16)
DISH = 64
FADE = 80
# With less room than a card in front this wide and both neighbours whole, the one in front takes the
# row, keeping this much at its sides for the arrows.
LEAST = 340
SLIVER = 40
# A neighbour narrows to the room beside the card in front, but not below this; with less room it waits
# past the row's edge with the days further off.
PEEK_LEAST = 140
# At either end of the row, room kept clear of the cards, where the days further off slide in.
RESERVE = 24
RADIUS = 2 * RADIUS_CARD
RADIUS_BLOCK = round(1.2 * RADIUS_CARD)
SLIDE_MS = 240
# `_go` leaves the summary as it is when the caller does not pass one (the arrows).
_KEEP = object()
# Resting a held block on an arrow this long slides the row a day.
DWELL_S = 0.5
# The page's colour over the cards beside the one in front, at this strength (J10, board 5b).
VEIL = 0.6
# The slide's share between which the end picture takes over from the start picture: before it only the
# start shows, after it only the end, so two layouts overlap for a few frames and not the whole slide.
SWAP_FROM, SWAP_TO = 0.15, 0.55
# A sideways drag on the row shorter than this, at Normal text, goes back to the day it left.
DRAG_LEAST = 40
# The stretch of the day Day's summary counts, as the mock-up does.
DAY_FROM, DAY_TO = 8 * 60, 22 * 60
# A block this short on the card in front says nothing; the mock-up's one line starts here.
LINE_LEAST = 15
TOP_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop


def _paint(tokens: dict[str, str], category: str) -> tuple[str, str]:
    """A category's fill and mark in the one family, on this design's cards."""
    fill, mark = category_paint(category, {"family": family(tokens), "panel": tokens["surface"]})
    return fill or tokens["surface"], mark or tokens["line"]


def _length(px: int) -> int:
    return round((LAST - FIRST) / 60 * px) + END_ROOM


def _covered(items: Iterable[Occurrence], start: int, end: int) -> int:
    """How many minutes from `start` to `end` any of `items` takes, each minute once."""
    taken, at = 0, start
    for item in sorted(items, key=lambda entry: entry.start):
        first, last = max(item.start, at), min(item.end, end)
        if last > first:
            taken += last - first
            at = last
    return taken


def day_kinds(week: WeekModel, day: int) -> list[tuple[str, int]]:
    """A day's minutes from 08:00 to 22:00 by category, the most first."""
    kinds: dict[str, int] = {}
    for item in week.on_day(day):
        minutes = min(item.end, DAY_TO) - max(item.start, DAY_FROM)
        if minutes > 0:
            kinds[item.category] = kinds.get(item.category, 0) + minutes
    return sorted(kinds.items(), key=lambda pair: -pair[1])


def left_today(week: WeekModel, day: int, minute: int) -> tuple[int, int, Occurrence | None]:
    """What is still ahead today until 22:00: the minutes planned, the minutes free, and what is next."""
    ahead = [item for item in week.on_day(day) if item.live and item.end > minute]
    planned = _covered([item for item in ahead if item.work], minute, DAY_TO)
    busy = _covered(ahead, minute, DAY_TO)
    coming = min((item for item in ahead if item.start > minute), key=lambda item: item.start, default=None)
    return planned, max(DAY_TO - minute - busy, 0), coming


def slots(width: float, height: float, front: int, scale: float, *, wide: bool) -> dict[int, QRectF]:
    """Where each day's card lies in a row `width` by `height`: the day in front in the middle at full
    size, and each other day a step further out at 70 % of its height, the room between them kept. The
    card in front narrows so both its neighbours show whole; with too little room even for that, it
    takes the row. Open on Day, it keeps the mock-up's width while the row has it, and its neighbours
    narrow to the room beside it. A card is whole in the row or wholly past its ends, where the days
    further off wait to slide in: one cut by the window's edge read as clipped."""
    gap, sliver = GAP * scale, SLIVER * scale
    wanted = (OPEN if wide else FRONT) * scale
    whole = (width - 2 * gap - 2 * RESERVE * scale) / (1 + 2 * PEEK)
    if not wide and whole >= LEAST * scale:
        across = min(wanted, whole)
    else:
        across = min(wanted, width - 2 * (gap + sliver))
    across, tall = max(across, 1.0), max(height - (INSET + FOOT) * scale, 1.0)
    narrow, short = across * PEEK, tall * PEEK
    left, middle = (width - across) / 2, INSET * scale + tall / 2
    beside = left - gap - RESERVE * scale
    if beside >= PEEK_LEAST * scale:
        narrow = min(narrow, beside)
    found = {front: QRectF(left, middle - tall / 2, across, tall)}
    for day in range(7):
        step = day - front
        if step > 0:
            x = left + across + gap + (step - 1) * (narrow + gap)
        elif step < 0:
            x = left + step * (narrow + gap)
        else:
            continue
        found[day] = QRectF(x, middle - short / 2, narrow, short)
    # The first card each way that the edge would cut, and every card past it, move out past the edge.
    after = [day for day in range(front + 1, 7) if found[day].right() > width]
    if after:
        shift = max(width - found[after[0]].left(), 0.0)
        for day in after:
            found[day].translate(shift, 0)
    before = [day for day in range(front - 1, -1, -1) if found[day].left() < 0]
    if before:
        shift = min(-found[before[0]].right(), 0.0)
        for day in before:
            found[day].translate(shift, 0)
    return found


def _soft(
    painter: QPainter, rect: QRectF, radius: float, y: float, blur: float, spread: float, colour: QColor,
    alpha: float,
) -> None:
    """A soft shadow under a rounded rectangle, as CSS's box-shadow: layers from its inner edge to
    its outer edge, so it fades over the blur."""
    layers = 12
    shade = QColor(colour)
    shade.setAlphaF(alpha / layers)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shade)
    for layer in range(layers):
        grow = spread - blur / 2 + blur * (layer + 0.5) / layers
        if rect.width() + 2 * grow <= 0 or rect.height() + 2 * grow <= 0:
            continue
        around = rect.translated(0, y).adjusted(-grow, -grow, grow, grow)
        painter.drawRoundedRect(around, max(radius + grow, 0), max(radius + grow, 0))


def _shadows(tokens: dict[str, str], lifted: bool) -> list[tuple[float, float, float, QColor, float]]:
    """The soft shadows under a card, as CSS's box-shadow: down, blur, spread, colour and strength.
    On a dark page the shadow is the large one."""
    if family(tokens) == "dark":
        large = SHADOW_LARGE
        return [(large.y, large.blur, 0, QColor("#000000"), large.dark_opacity)]
    ink = QColor(tokens["text"])
    if lifted:
        return [(2, 4, 0, ink, 0.06), (22, 40, -16, ink, 0.32)]
    return [(1, 2, 0, ink, 0.06), (12, 24, -14, ink, 0.24)]


def shadowed(rect: QRectF, tokens: dict[str, str], lifted: bool) -> QRectF:
    """A card with as far as its shadow reaches around it."""
    sides, top, foot = 0.0, 0.0, 0.0
    for y, blur, spread, _colour, _alpha in _shadows(tokens, lifted):
        grow = spread + blur / 2
        sides, top, foot = max(sides, grow), max(top, grow - y), max(foot, grow + y)
    return rect.adjusted(-sides, -top, sides, foot)


def paint_clay(painter: QPainter, rect: QRectF, tokens: dict[str, str], radius: float, *, lifted: bool,
               shadow: bool = True) -> None:
    """Claymorphism, tempered as the mock-up draws it: the card's surface a touch deeper at its foot,
    a highlight along its top edge, a soft shade inside its foot, a hairline ring, and a soft shadow
    under it, stronger under the one lifted in front."""
    dark = family(tokens) == "dark"
    text, surface = tokens["text"], tokens["surface"]
    painter.save()
    if shadow:
        for y, blur, spread, colour, alpha in _shadows(tokens, lifted):
            _soft(painter, rect, radius, y, blur, spread, colour, alpha)
    shape = QPainterPath()
    shape.addRoundedRect(rect, radius, radius)
    ramp = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    ramp.setColorAt(0, QColor(surface))
    ramp.setColorAt(0.55, QColor(surface))
    ramp.setColorAt(1, QColor(mix_oklab(text, surface, 0.03)))
    painter.fillPath(shape, ramp)
    painter.setClipPath(shape)
    shade = QLinearGradient(QPointF(0, rect.bottom() - 8), QPointF(0, rect.bottom()))
    low = QColor(tokens["bg"] if dark else text)
    low.setAlphaF(0.0)
    shade.setColorAt(0, low)
    low.setAlphaF(0.45 if dark else 0.04)
    shade.setColorAt(1, low)
    painter.fillRect(QRectF(rect.left(), rect.bottom() - 8, rect.width(), 8), shade)
    shine = QColor("#ffffff") if not dark else QColor(text)
    shine.setAlphaF(1.0 if not dark else 0.10)
    painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 1.5), shine)
    painter.setClipping(False)
    ring = QColor(tokens["line"])
    ring.setAlphaF(0.8 if dark else 0.7)
    painter.setPen(QPen(ring, 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius - 0.5, radius - 0.5)
    if lifted and dark:
        painter.setPen(QPen(QColor(tokens["line"]), 1))
        painter.drawRoundedRect(rect.adjusted(-0.5, -0.5, 0.5, 0.5), radius + 0.5, radius + 0.5)
    painter.restore()


class ClayPainter(BlockPainter):
    """Hours on a clay card: a faint rule at each hour, blocks as soft clay in the category family with
    the category's bar just inside their start edge, and the time now as an accent line from a dot,
    its time on a pill. The card in front says each block's times and length; a neighbour its times."""

    # The pill sits left of the hours, where their labels are: an hour label under it is left out.
    now_in_gutter = True

    def __init__(
        self, tokens: dict[str, str], *, full: bool = False, wide: bool = False, share: float = 1.0
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
        self.full = full
        # The height of these hours against the card in front's, whose blocks the least a line needs is
        # measured on: a block that reads there reads here at the same length.
        self.share = share
        self.dark = family(tokens) == "dark"

    def background(self, painter: QPainter, rect: QRectF) -> None:
        """Nothing: the clay card under the hours is the row's."""

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        painter.setPen(QPen(self.c("rule"), 1))
        area = track.area
        for minute in range(-(-track.first // 60) * 60, track.last + 1, 60):
            at = area.top() + track.offset(minute)
            painter.drawLine(QPointF(area.left(), at), QPointF(area.right(), at))

    def fills(self, drawn: Drawn) -> tuple[QColor, QColor, QColor | None, QColor | None]:
        mark = _paint(self.tokens, drawn.category)[1]
        fill = QColor(family_fill(drawn.category, self.tokens))
        if drawn.done or drawn.missed:
            fill = QColor(self.tokens["surface"])
        return fill, QColor(self.tokens["text"]), None, QColor(mark)

    def fonts(self, base: QFont) -> tuple[QFont, QFont]:
        """A block's title at 600 and its times, at the caption size on Week and the body size on Day.
        In a monospaced face, as Terminal's, letters sit 3 % closer, as the mock-up sets them, so a
        block's words still fit."""
        title, small = super().fonts(base)
        if self.wide:
            small = at_scale(time_font(base), "body", self.scale(base), WEIGHT_REGULAR)
        if QFontInfo(base).fixedPitch():
            for made in (title, small):
                made.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 97)
        return title, small

    def body(self, painter: QPainter, rect: QRectF, drawn: Drawn) -> None:
        fill, _ink, _outline, edge = self.fills(drawn)
        assert edge is not None
        radius = min(RADIUS_BLOCK, rect.height() / 2, rect.width() / 2)
        shape = QPainterPath()
        shape.addRoundedRect(rect, radius, radius)
        under = QColor(self.tokens["bg"] if self.dark else edge)
        under.setAlphaF(0.6 if self.dark else 0.22)
        painter.fillPath(shape.translated(0, 1), under)
        painter.fillPath(shape, fill)
        painter.save()
        painter.setClipPath(shape)
        surface = self.tokens["surface"]
        shine = QColor(self.tokens["text"] if self.dark else mix_oklab(surface, fill.name(), 0.6))
        shine.setAlphaF(0.09 if self.dark else 1.0)
        painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 1), shine)
        painter.restore()
        tall = rect.height()
        inset = 2 if tall < 12 else 3 if tall < 30 else (6 if self.wide else 4)
        bar = QRectF(rect.left() + (7 if self.wide else 5), rect.top() + inset, 3, max(tall - 2 * inset, 2))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(edge)
        painter.drawRoundedRect(bar, 1.5, 1.5)
        if drawn.held or drawn.chosen:
            refused = drawn.verdict is not None and not drawn.verdict.ok
            painter.setPen(QPen(self.c("error" if refused else "selection"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), max(radius - 1, 0), max(radius - 1, 0))

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
        """As the mock-up writes a block: its title, then its times and on the card in front its length,
        each on its own line while the block is tall enough; "16:00–17:30 · 1 h 30 min" under the title
        on a shorter one; on one line the title and the most that fits after it; on a block shorter
        than a line, nothing, and its colour says it is there. A long title takes two lines where the
        block has room for them."""
        if drawn.held:
            return super().words(painter, rect, drawn, ink, visible, fill, edge)
        scale = self.scale(painter.font())
        title_font, small = self.fonts(painter.font())
        if self.wide and rect.height() + 0.5 < QFontMetricsF(title_font).height():
            # Too short for a line at the body size, as Dinner's half hour is: at the caption size.
            title_font = at_scale(painter.font(), "caption", scale, WEIGHT_STRONG)
            small = at_scale(time_font(painter.font()), "caption", scale, WEIGHT_REGULAR)
        tm, sm = QFontMetricsF(title_font), QFontMetricsF(small)
        tl, sl = tm.lineSpacing(), sm.lineSpacing()
        left, top, right = (18, 6, 12) if self.wide else (14, 4, 8)
        width = rect.width() - left - right
        tall = rect.height() - top - 3
        homework = category_icon(drawn.category) is not None
        book = round(tm.ascent())
        indent = book + 4 if homework else 0
        too_short = rect.height() + BETWEEN < (LINE_LEAST * scale + BETWEEN) * self.share
        least = tm.horizontalAdvance(drawn.title.strip()[:3])
        if too_short or width < least:
            return []
        written = []
        paper = fill if fill is not None else self.c("window")
        muted = QColor(mix_oklab(ink.name(), paper.name(), 0.74))
        said = [word for flag, word in ((drawn.done, "Finished"), (drawn.missed, "Missed")) if flag]
        times = drawn.times if self.full or not said else " · ".join([drawn.times, *said])
        extra = drawn.length + (" · Pinned" if drawn.pinned and not drawn.done else "")
        under: list[str] = []
        if self.full and tall + 0.5 >= tl + 2 * sl:
            under = [times, extra]
        elif tall + 0.5 >= tl + sl:
            joined = f"{times} · {extra}"
            under = [joined if self.full and sm.horizontalAdvance(joined) <= width else times]
        most = 2 if under and tall + 0.5 >= 2 * tl + sl * len(under) else 1
        start = short_clock(drawn.span.start)
        ways = [f"{times} · {extra}", times, start] if self.full else [start]

        def after_name(indent: float) -> str:
            """What follows the name on one line: the most that fits beside it."""
            whole = tm.horizontalAdvance(drawn.title) + INLINE_GAP
            return next((way for way in ways if whole + sm.horizontalAdvance(way) <= width - indent), "")

        def said(indent: float) -> tuple[int, bool]:
            if width < indent + least:
                return 0, False
            lines = self._title_lines(drawn.title, tm, width, indent, most)
            return name_kept(lines, drawn.title), not under and bool(after_name(indent))

        if homework and said(0) > said(indent):
            # The icon gives way where it costs the name or its time, as on the shared hours.
            homework, indent = False, 0
        if under:
            names = self._title_lines(drawn.title, tm, width, indent, most)
            y = rect.top() + top
            if rect.bottom() - visible.top() > 2 * tl:
                # The name stays in sight while the start of a long block is scrolled away.
                y = max(y, visible.top() + top)
            first = y
            painter.setFont(title_font)
            painter.setPen(ink)
            for at, name in enumerate(names):
                shift = indent if at == 0 else 0
                box = QRectF(rect.left() + left + shift, y, width - shift, tl)
                painter.drawText(box, TOP_LEFT, name)
                written.append(QRectF(box.left(), y, tm.horizontalAdvance(name), tl))
                y += tl
            painter.setFont(small)
            painter.setPen(muted)
            for words in under:
                if y + sl > rect.bottom() + 1:
                    break
                shown = sm.elidedText(words, Qt.TextElideMode.ElideRight, width)
                painter.drawText(QRectF(rect.left() + left, y, width, sl), TOP_LEFT, shown)
                written.append(QRectF(rect.left() + left, y, sm.horizontalAdvance(shown), sl))
                y += sl
        else:
            room = width - indent
            after = after_name(indent)
            name = drawn.title if after else word_elide(drawn.title, tm, room)
            first = rect.top() + (rect.height() - tm.height()) / 2
            at = rect.left() + left + indent
            painter.setFont(title_font)
            painter.setPen(ink)
            painter.drawText(QRectF(at, first, room, tm.height()), TOP_LEFT, name)
            written.append(QRectF(at, first, tm.horizontalAdvance(name), tm.height()))
            if after:
                beside = QRectF(
                    at + tm.horizontalAdvance(name) + INLINE_GAP,
                    first + max(tm.ascent() - sm.ascent(), 0.0),
                    sm.horizontalAdvance(after) + 1,
                    sm.height(),
                )
                painter.setFont(small)
                painter.setPen(muted)
                painter.drawText(beside, TOP_LEFT, after)
                written.append(beside)
        if homework:
            at_book = QPointF(rect.left() + left, first + (tm.height() - book) / 2)
            colour = self._book_colour(drawn, ink, paper, edge)
            ratio = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
            picture = icons.pixmap(category_icon(drawn.category) or BOOK, colour.name(), book, ratio)
            painter.drawPixmap(at_book, picture)
            written.append(QRectF(at_book.x(), at_book.y(), book, book))
        return written

    @staticmethod
    def _title_lines(title: str, metrics: QFontMetricsF, width: float, indent: float, most: int) -> list[str]:
        """The title on one line, or on two where there is room, broken at a word; shortened with "…"
        only where it must be."""
        words = title.split()
        if most == 1 or metrics.horizontalAdvance(title) <= width - indent:
            return [word_elide(title, metrics, width - indent)]
        for count in range(len(words) - 1, 0, -1):
            if metrics.horizontalAdvance(" ".join(words[:count])) <= width - indent:
                return [" ".join(words[:count]), word_elide(" ".join(words[count:]), metrics, width)]
        return [word_elide(title, metrics, width - indent)]

    def now(self, painter: QPainter, track: LinearTrack, minute: int) -> None:
        """An accent line across the day from a dot at its start, the time on a pill near the dot."""
        colour = self.c("now")
        area = track.area
        at = area.top() + track.offset(minute)
        painter.setPen(QPen(colour, 2))
        painter.drawLine(QPointF(area.left() - 2, at), QPointF(area.right(), at))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawEllipse(QPointF(area.left(), at), 4, 4)
        font = weighted(time_font(caption(painter.font())), WEIGHT_STRONG)
        words = clock_label(minute)
        metrics = QFontMetricsF(font)
        pill = QRectF(max(0, area.left() - metrics.horizontalAdvance(words) - 15),
                      at - (metrics.height() + 2) / 2, metrics.horizontalAdvance(words) + 12,
                      metrics.height() + 2)
        painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        painter.setPen(QColor(readable_ink(colour.name())))
        painter.setFont(font)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, words)


class ClayCanvas(HoursCanvas):
    """A card's hours. The rig and the tests find days through the row, which brings a day that is
    past its edge to the front first, as the arrows would."""

    def __init__(self, hand: Hand, painter: ClayPainter, lay_out, row: Row, *, gutter: float = 0) -> None:
        super().__init__(hand, painter, lay_out, gutter=gutter)
        self.row = row

    def day_name(self, day: int) -> QPoint:
        return self.row.name_point(day)

    def reveal(self, day: int, first: int, last: int) -> None:
        self.row.reveal(day, first, last)

    def in_view(self, day: int, minute: int) -> bool:
        return self.row.in_view(self, day, minute)


class Head(QPushButton):
    """A day's name with its date at the far end, today's in an accent chip, and on the card in front
    how much it holds. A click opens the day wherever that is not the view already. The name shortens
    to "Wed" before it would be cut."""

    def __init__(self, name: str, front: bool) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setProperty("kind", "head")
        self.setProperty("front", front)
        self.day = -1
        self._note = ""
        row = QHBoxLayout(self)
        row.setContentsMargins(4 if front else 6, 0, 4, 0)
        row.setSpacing(8)
        self.title = label("", "clayDayName")
        self.title.setProperty("front", front)
        self.note = label("", "clayNote")
        # Two labels shown in turn: Qt keeps a label's padding from its first styling.
        self.date = label("", "clayDate")
        self.chip = label("", "clayToday")
        for part in (self.title, self.note, self.date, self.chip):
            part.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            part.setIndent(0)
        row.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.note, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        row.addWidget(self.date, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_day(self, day: int, number: int, today: bool, note: str, opens: bool, dated: bool = True) -> None:
        """`dated` False leaves the date to the card's corner, as Day's open card has it past the hours."""
        self.day = day
        self._note = note
        self.note.setText(note)
        self.date.setText(str(number))
        self.chip.setText(str(number))
        self.date.setVisible(dated and not today)
        self.chip.setVisible(dated and today)
        self.setProperty("opens", opens)
        self.setProperty("day_target", day if opens else None)
        self.setCursor(Qt.CursorShape.PointingHandCursor if opens else Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if opens else Qt.FocusPolicy.NoFocus)
        self.setAccessibleName(f"Show {DAY_FULL[day]}" if opens else DAY_FULL[day])
        self.setToolTip(f"Open {DAY_FULL[day]}" if opens else "")
        self.style().unpolish(self)
        self.style().polish(self)
        self._fit()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit()

    def _fit(self) -> None:
        """The whole name and the note; else the whole name alone; else "Wed", with the note if it fits."""
        if self.day < 0:
            return
        for part in (self.title, self.note, self.date, self.chip):
            part.ensurePolished()
        margins = self.layout().contentsMargins()
        tag = self.chip if self.chip.isVisibleTo(self) else self.date
        room = self.width() - margins.left() - margins.right() - 8
        if tag.isVisibleTo(self):
            room -= tag.sizeHint().width() + 8
        metrics = self.title.fontMetrics()
        note = self.note.fontMetrics().horizontalAdvance(self._note) + 8 if self._note else 0
        full, short = DAY_FULL[self.day], DAYS[self.day]
        for words, with_note in ((full, True), (full, False), (short, True), (short, False)):
            if metrics.horizontalAdvance(words) + (note if with_note else 0) <= room:
                break
        self.note.setVisible(bool(self._note) and with_note)
        self.title.setText(metrics.elidedText(words, Qt.TextElideMode.ElideRight, max(room, 0)))
        # At once, not on the next pass: a picture taken straight after, as setup's are, cut the name.
        self.layout().activate()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, super().minimumSizeHint().height())


class Card(QWidget):
    """A day beside the one in front: its name and date over its hours. The row paints its clay."""

    def __init__(self, day: int, row: Row, painter: ClayPainter) -> None:
        super().__init__(row)
        self.day = day
        box = QVBoxLayout(self)
        box.setSpacing(0)
        self.head = Head(f"clayDay{day}", front=False)
        self.head.clicked.connect(lambda _=False: row.opened.emit(self.day))
        self.hours = ClayCanvas(row.hand, painter, lambda area: row.peek_track(self.day, area), row)
        self.hours.setObjectName(f"clayPeek{day}")
        box.addWidget(self.head)
        box.addWidget(self.hours, 1)

    def dress(self, scale: float) -> None:
        """Its padding at this text size, and room left of its hours for their labels, as wide as the
        widest in the face and size they are written in and on the clock the student chose."""
        side, _right, foot = PEEK_PAD
        self.layout().setContentsMargins(round(side * scale), 0, round(side * scale), round(foot * scale))
        hours = self.hours
        hours.ensurePolished()
        base = hours.font()
        metrics = QFontMetricsF(at_scale(time_font(base), "caption", hours.painter.scale(base)))
        widest = max(metrics.horizontalAdvance(clock_label(hour * 60)) for hour in range(24))
        hours.gutter = math.ceil(widest) + PEEK_LABEL_GAP
        hours.relayout()


class Arrow(QPushButton):
    """A round clay button beside the card in front: the day before it, or the day after."""

    def __init__(self, name: str, icon: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self.icon_name = icon
        self.tokens: dict[str, str] = {}
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if not self.tokens:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        paint_clay(painter, body, self.tokens, body.height() / 2, lifted=True, shadow=False)
        if self.underMouse() and self.isEnabled():
            hover = QColor(self.tokens["text"])
            hover.setAlphaF(0.06)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hover)
            painter.drawEllipse(body)
        if self.hasFocus() and self.property("keyfocus"):
            painter.setPen(QPen(QColor(self.tokens["accent"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(body.adjusted(1, 1, -1, -1))
        faint = mix_oklab(self.tokens["muted"], self.tokens["surface"], 0.5)
        colour = self.tokens["text"] if self.isEnabled() else faint
        side = round(body.height() * 20 / ARROW)
        picture = icons.pixmap(self.icon_name, colour, side, self.devicePixelRatioF())
        painter.drawPixmap(QPointF(body.center().x() - side / 2, body.center().y() - side / 2), picture)
        painter.end()


class Fade(QWidget):
    """The row's ends fading into the page, over the days two and more away."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.page = QColor("#ffffff")
        self.reach = FADE

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        clear = QColor(self.page)
        clear.setAlphaF(0.0)
        for start, end in ((0.0, self.reach), (float(self.width()), self.width() - self.reach)):
            ramp = QLinearGradient(QPointF(start, 0), QPointF(end, 0))
            ramp.setColorAt(0, self.page)
            ramp.setColorAt(1, clear)
            painter.fillRect(QRectF(min(start, end), 0, abs(end - start), self.height()), ramp)
        painter.end()


class Shot(NamedTuple):
    """A card's picture for the slide: the card's rectangle when it was taken, where the picture's
    top-left lay (the shadow reaches past the card), and the state the card was in."""

    picture: QPixmap
    card: QRectF
    origin: QPoint
    veiled: bool
    lifted: bool


def swap(share: float) -> float:
    """How far the end picture has taken over at `share` of the slide: a smoothstep over SWAP_FROM
    to SWAP_TO."""
    x = min(max((share - SWAP_FROM) / (SWAP_TO - SWAP_FROM), 0.0), 1.0)
    return x * x * (3 - 2 * x)


def fitted(shot: Shot, card: QRectF) -> QRectF:
    """Where `shot`'s picture is drawn when its card is at `card`: one factor on both sides, the
    cards' heights, anchored at the card's top-left, so what is on it keeps its proportions."""
    factor = card.height() / shot.card.height() if shot.card.height() > 0 else 1.0
    ratio = shot.picture.devicePixelRatio() or 1.0
    left = card.x() + (shot.origin.x() - shot.card.x()) * factor
    top = card.y() + (shot.origin.y() - shot.card.y()) * factor
    return QRectF(left, top, shot.picture.width() / ratio * factor, shot.picture.height() / ratio * factor)


class Veil(QWidget):
    """The page's colour over the cards beside the one in front and their shadows, so the front holds
    the eye; never over the card in front or its shadow. Over the bare page it is the page's own
    colour, so only the cards show it. The arrows lie above it and draw their own clay."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.shape = QPainterPath()
        self.colour = QColor("#ffffff")

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if self.shape.isEmpty():
            return
        painter = QPainter(self)
        painter.fillPath(self.shape, self.colour)
        painter.end()


class Row(QWidget):
    """The days as cards in a row, one in front. It paints their clay; the cards and the hours in
    front draw what is on them. Week slides it here; Day asks the window for another day and slides
    when the window shows it."""

    # A day's name was clicked: open it on Day.
    opened = Signal(int)
    # On Day, the arrows, the wheel, a drag of the row or a rest on an arrow moved to this day of the
    # week, which may be the Sunday before it (-1) or the Monday after (7).
    turned = Signal(int)

    def __init__(self, hand: Hand, keep: Callable[[HoursScroll], HoursScroll]) -> None:
        super().__init__()
        self.setObjectName("clayRow")
        self.setAccessibleName("The week as cards, one day at a time")
        self.hand = hand
        self._keep = keep
        self.scene: Scene | None = None
        self.tokens: dict[str, str] = {}
        self.scale = 1.0
        self._open = False
        self._peeks = True
        self._front = 0
        self._week_start = ""
        self._window = (DAY_FROM, DAY_TO)
        self._cards: dict[int, Card] = {}
        self._hours: dict[str, HoursScroll] = {}
        self._heads: dict[str, Head] = {}
        self._summary: QWidget | None = None
        self._rects: dict[int, QRectF] = {}
        self._from: dict[int, QRectF] = {}
        self._to: dict[int, QRectF] = {}
        # Start and end pictures of each card for the slide, and the widgets hidden while they move.
        self._snaps: tuple[dict[int, Shot], dict[int, Shot]] | None = None
        self._share = 0.0
        self._held_back: list[QWidget] = []
        self._quiet: list[QWidget] = []
        self._wheel = 0
        # The hours the neighbours' stretch was taken for, and the hours open now: Week's week, or
        # Day's day. While they match, the neighbours stay still.
        self._held: object = None
        self._opening: object = None
        # A drag of the row: where the button went down, and whether it became one (None while it may
        # still be a click). On a neighbour, the press it held back until it knew.
        self._grip: QPointF | None = None
        self._dragging: bool | None = None
        self._held_press: tuple[QWidget, QPointF, QPointF, Qt.KeyboardModifier] | None = None
        self._replaying = False
        self._veil = Veil(self)
        self._fade = Fade(self)
        # Day's date, at the open card's far corner as the mock-up puts it: two labels shown in turn.
        self._date = label("", "clayDate")
        self._chip = label("", "clayToday")
        for stamp in (self._date, self._chip):
            stamp.setParent(self)
            stamp.hide()
        self.back = Arrow("clayBack", "chevron-left", self)
        self.ahead = Arrow("clayAhead", "chevron-right", self)
        self.back.clicked.connect(lambda _=False: self.turn(-1))
        self.ahead.clicked.connect(lambda _=False: self.turn(1))
        self._slide = Clock(self)
        self._slide.finished.connect(self._land)
        self._dwell = QTimer(self)
        self._dwell.setInterval(50)
        self._dwell.timeout.connect(self._dwelt)
        self._dwell_on: QWidget | None = None
        self._dwell_since = 0.0
        hand.active_changed.connect(self._carrying)

    # What it shows

    @property
    def front(self) -> int:
        return self._front

    @property
    def hours(self) -> HoursScroll | None:
        """The hours in front: Week's or Day's."""
        return self._hours.get("day" if self._open else "week")

    def show_scene(
        self, scene: Scene, day: int | None, peeks: bool, summary: QWidget | None = None,
    ) -> None:
        """Show `scene`: on Day, `day` in front, open; on Week, the day already in front, or today or
        Monday when the week is new. A new day in the same week slides into place. `summary` is Day's
        panel, attached before the slide's end pictures are taken so it is in them."""
        self.scene, self.tokens, self.scale = scene, scene.tokens, scene.scale
        self._build(scene)
        opened = day is not None
        mode = opened != self._open or peeks != self._peeks
        self._open, self._peeks = opened, peeks
        new_week = scene.week.week_start != self._week_start
        if new_week:
            self._week_start = scene.week.week_start
        if day is not None:
            front = day
        elif new_week:
            front = scene.today if scene.today is not None else 0
        else:
            front = self._front
        for key, scroll in self._hours.items():
            scroll.setVisible(key == ("day" if opened else "week"))
        self._fade.page = QColor(self.tokens["bg"])
        veil = QColor(self.tokens["bg"])
        veil.setAlphaF(VEIL)
        self._veil.colour = veil
        self._opening = ("day", scene.week.week_start, front) if opened else ("week", scene.week.week_start)
        for arrow in (self.back, self.ahead):
            arrow.tokens = self.tokens
            arrow.setFixedSize(round(ARROW * self.scale), round(ARROW * self.scale))
        for card in self._cards.values():
            card.dress(self.scale)
            card.hours.set_painter(ClayPainter(self.tokens, share=PEEK))
        scroll = self.hours
        assert scroll is not None
        scroll.canvas.set_painter(ClayPainter(self.tokens, full=True, wide=opened))
        week = scene.week

        def place_hours() -> None:
            if opened:
                open_hours(scroll, (week.week_start, front), week, scene.today, scene.minute, front)
            else:
                open_hours(scroll, week.week_start, week, scene.today, scene.minute)

        how = "slide" if not (mode or new_week) else "jump"
        self._go(front, how, force=True, summary=summary, arrive=place_hours)
        self._follow()
        self._fade.raise_()
        self.back.raise_()
        self.ahead.raise_()

    def set_summary(self, summary: QWidget | None) -> None:
        """What Day shows beside its hours, inside the open card. While a slide is running the new
        summary is kept hidden: a _put would show the live neighbours over the pictures."""
        if self._snaps is not None:
            self._bind_summary(summary, show=False)
            return
        self._bind_summary(summary, show=True)
        if summary is not None:
            self._put(self._rects)
            self._fade.raise_()
            self.back.raise_()
            self.ahead.raise_()

    def _bind_summary(self, summary: QWidget | None, *, show: bool) -> None:
        if self._summary is not None and self._summary is not summary:
            self._summary.setParent(None)
            self._summary.deleteLater()
        self._summary = summary
        if summary is None:
            return
        summary.setParent(self)
        summary.setVisible(show)

    def _build(self, scene: Scene) -> None:
        if self._cards:
            return
        for day in range(7):
            card = Card(day, self, ClayPainter(scene.tokens, share=PEEK))
            card.head.installEventFilter(self)
            card.hours.installEventFilter(self)
            self._cards[day] = card
        for key, scale in (("week", WEEK_SCALE), ("day", DAY_SCALE)):
            canvas = ClayCanvas(
                self.hand, ClayPainter(scene.tokens, full=True, wide=key == "day"), self.front_track, self,
                gutter=round(LABELS * scene.scale),
            )
            canvas.setObjectName("clayHours")
            canvas.setAccessibleName("The day in front, hour by hour")
            name = f"clay{key.title()}"
            gutter = round(LABELS * scene.scale)
            scroll = self._keep(HoursScroll(canvas, scale, _length, name=name, gutter=gutter))
            scroll.setParent(self)
            head = Head(f"{name}Front", front=True)
            head.clicked.connect(lambda _=False, made=head: self._front_clicked(made))
            scroll.set_header(head)
            scroll.widget().setAutoFillBackground(False)
            scroll.verticalScrollBar().valueChanged.connect(lambda _value: self._follow())
            scroll.verticalScrollBar().rangeChanged.connect(lambda _low, _high: self._follow())
            self._hours[key] = scroll
            self._heads[key] = head
        # Over the neighbours, under the hours in front.
        self._veil.raise_()
        self._veil.stackUnder(self._hours["week"])

    def _front_clicked(self, head: Head) -> None:
        if head.property("opens"):
            self.opened.emit(head.day)

    def front_track(self, area: QRectF) -> list[LinearTrack]:
        return [LinearTrack(self._front, area.adjusted(0, END_ROOM / 2, 0, -END_ROOM / 2))]

    def peek_track(self, day: int, area: QRectF) -> list[LinearTrack]:
        """A neighbour's hours are the stretch the card in front opened at, on the drag's step."""
        first, last = self._window
        return [LinearTrack(day, area.adjusted(0, 1, 0, -1), Axis.DOWN, first, last)]

    def _retarget(self) -> None:
        """Every card's words and blocks for the day now in front."""
        scene = self.scene
        if scene is None:
            return
        week, today = scene.week, scene.today
        for day, card in self._cards.items():
            card.head.set_day(day, week.date_of(day).day, day == today, "", True)
            card.hours.set_week(week.on_day(day), today, scene.minute)
            card.hours.setAccessibleName(f"{DAY_FULL[day]}'s hours, beside the day in front")
        scroll = self.hours
        assert scroll is not None
        front = self._front
        count = len(week.on_day(front))
        things = plural(count, "thing") if count else "Nothing planned"
        note = f"Today · {things}" if front == today else things
        number = week.date_of(front).day
        self._heads["day" if self._open else "week"].set_day(
            front, number, front == today, note, not self._open, dated=not self._open
        )
        self._date.setText(str(number))
        self._chip.setText(str(number))
        self._date.setVisible(self._open and front != today)
        self._chip.setVisible(self._open and front == today)
        scroll.canvas.relayout()
        scroll.canvas.set_week(week.on_day(front), today, scene.minute)
        scroll.canvas.setAccessibleName(f"{DAY_FULL[front]}, hour by hour")
        self._arrows()

    # Moving the row

    def turn(self, step: int) -> None:
        """The arrows and the wheel: Week slides a day; Day asks the window for the day, which slides
        when it is shown."""
        target = self._front + step
        if self._open:
            self.turned.emit(target)
        elif 0 <= target <= 6:
            self._go(target, "slide")

    def _go(
        self, day: int, how: str, force: bool = False, summary: object = _KEEP,
        arrive: Callable[[], None] | None = None,
    ) -> None:
        """Bring `day` to the front: sliding the row, fading to it under Reduce motion, or at once.
        `force` shows what the cards hold again when `day` is in front already. `summary` is Day's
        new panel and `arrive` places the hours; both happen before the slide's end pictures are
        taken, so those hold the day as it lands."""
        if day == self._front:
            if force:
                self._retarget()
                self._arrive(summary)
                if self._slide.state() != QAbstractAnimation.State.Running:
                    self._put(self._targets())
                    if arrive is not None:
                        arrive()
            return
        level = app_level()
        moving = how == "slide" and duration(SLIDE_MS, level) > 0 and self.isVisible() and bool(self._rects)
        moving = moving and not self.hand.busy
        slides = moving and moves(level)
        # Under Reduce motion the row changes where it is, under a picture of it that fades.
        picture = hold_picture(self, level) if moving and not slides else None
        before = dict(self._rects)
        old_front = self._front
        self._stop_slide()
        if slides:
            self._put(before)
            starts = self._pictures(before, front=old_front)
            self._front = day
            self._retarget()
            self._arrive(summary)
            self._slide_to(before, self._targets(), starts, duration(SLIDE_MS, level), arrive)
            return
        self._front = day
        self._retarget()
        self._arrive(summary)
        self._put(self._targets())
        if arrive is not None:
            arrive()
        fade_away(picture, level, ms=SLIDE_MS)

    def _arrive(self, summary: object) -> None:
        if summary is not _KEEP:
            self._bind_summary(summary if isinstance(summary, QWidget) else None, show=True)

    def _slide_to(
        self, before: dict[int, QRectF], after: dict[int, QRectF], starts: dict[int, QPixmap],
        ms: int, arrive: Callable[[], None] | None = None,
    ) -> None:
        """Slide from `before` to `after`. The end pictures are taken with the row laid out at `after`,
        and the live widgets are hidden there, not moved: they show again as the slide lands."""
        self._from, self._to = before, after
        self._put(after)
        if arrive is not None:
            arrive()
        ends = self._pictures(after, front=self._front)
        self._hold_live()
        self._snaps = (starts, ends)
        self._share = 0.0
        self._slide.start(ms, self._on_clock)
        self._on_clock(0.0)

    def _on_clock(self, ms: float) -> None:
        total = self._slide.duration()
        share = OUT.valueForProgress(ms / total) if total else 1.0
        self._slid(share)

    def _slid(self, value: object) -> None:
        share = float(value)
        rects = {day: between(self._from.get(day, rect), rect, share) for day, rect in self._to.items()}
        if self._snaps is not None:
            self._rects = rects
            self._share = share
            self._place_arrows()
            self.update()
            return
        self._put(rects)
        scroll = self.hours
        if scroll is not None:
            scroll.canvas.update()

    def _stop_slide(self) -> None:
        """Stopping does not finish the slide, so a picture still up has to give the widgets back."""
        self._slide.stop()
        self._drop_snaps()

    def _pictures(self, rects: dict[int, QRectF], *, front: int) -> dict[int, Shot]:
        """A picture of every day's card at `rects`, whole shadow included, even past the row's edge."""
        if not self.tokens or not rects:
            return {}
        # The arrows and the edge fade are not in the pictures: they stay up as the pictures move.
        apart = [w for w in (self.back, self.ahead, self._fade) if w.isVisible()]
        for widget in apart:
            widget.hide()
        whole = self.grab()
        for widget in apart:
            widget.show()
        ratio = self.devicePixelRatioF() if whole.isNull() else whole.devicePixelRatio()
        snaps: dict[int, Shot] = {}
        for day, rect in rects.items():
            if day != front and not self._peeks:
                continue
            shot = self._picture_of(day, rect, front, whole, ratio)
            if shot is not None and not shot.picture.isNull():
                snaps[day] = shot
        return snaps

    def _picture_of(
        self, day: int, rect: QRectF, front: int, whole: QPixmap, ratio: float,
    ) -> Shot | None:
        area = shadowed(rect, self.tokens, day == front).toRect()
        if area.width() <= 0 or area.height() <= 0:
            return None
        picture = self._pixmap_of(day, rect, front, area, whole, ratio)
        if picture is None:
            return None
        return Shot(picture, QRectF(rect), area.topLeft(), day != front, day == front)

    def _pixmap_of(
        self, day: int, rect: QRectF, front: int, area: QRect, whole: QPixmap, ratio: float,
    ) -> QPixmap | None:
        if not whole.isNull() and self.rect().contains(area):
            kept = whole.copy(
                QRect(
                    round(area.x() * ratio),
                    round(area.y() * ratio),
                    round(area.width() * ratio),
                    round(area.height() * ratio),
                )
            )
            if not kept.isNull():
                kept.setDevicePixelRatio(ratio)
                return kept
        return self._draw_day_picture(day, rect, front, area, ratio)

    def _draw_day_picture(
        self, day: int, rect: QRectF, front: int, area: QRect, ratio: float,
    ) -> QPixmap:
        pixmap = QPixmap(max(1, round(area.width() * ratio)), max(1, round(area.height() * ratio)))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(-area.x(), -area.y())
        paint_clay(painter, rect, self.tokens, RADIUS * self.scale, lifted=day == front)
        if day != front:
            card = self._cards.get(day)
            if card is not None:
                shown = card.isVisible()
                if not shown:
                    card.show()
                card.render(painter, card.pos())
                if not shown:
                    card.hide()
            colour = QColor(self.tokens["bg"])
            colour.setAlphaF(VEIL)
            painter.fillRect(QRectF(area), colour)
        else:
            for widget in (self.hours, self._date, self._chip, self._summary):
                if widget is not None and widget.isVisible():
                    widget.render(painter, widget.pos())
        painter.end()
        return pixmap

    def _hold_live(self) -> None:
        """Hide the live cards, the date and Day's summary until the slide lands, and quiet the hours
        in front: they stay up, where tests and a drop read them, but are not painted. None of them
        is moved while it is held, so nothing stale is left on screen."""
        held: list[QWidget] = []
        for widget in (*self._cards.values(), self._veil, self._date, self._chip, self._summary):
            if widget is not None and not widget.isHidden():
                widget.hide()
                held.append(widget)
        self._held_back = held
        scroll = self.hours
        if scroll is not None and scroll.updatesEnabled():
            scroll.setUpdatesEnabled(False)
            self._quiet = [scroll]

    def _drop_snaps(self) -> None:
        self._snaps = None
        self._share = 1.0
        held = self._held_back
        self._held_back = []
        for widget in held:
            if isValid(widget):
                widget.show()
        quiet = self._quiet
        self._quiet = []
        for widget in quiet:
            if isValid(widget):
                widget.setUpdatesEnabled(True)

    def _land(self) -> None:
        self._drop_snaps()
        self._put(self._to)

    def _paint_snaps(self) -> None:
        """Each card as the clay of its current rectangle with its start picture and its end picture
        over it. A picture is scaled by one factor, the card's height over its own, and clipped to the
        card, so words keep their proportions; where it falls short the card's own surface shows."""
        snaps = self._snaps
        if not snaps or not self.tokens:
            return
        starts, ends = snaps
        mix = swap(self._share)
        radius = RADIUS * self.scale
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        order = sorted(
            (day for day in self._rects if day != self._front and self._peeks),
            key=lambda day: -abs(day - self._front),
        )
        for day in (*order, self._front):
            rect = self._rects.get(day)
            if rect is None:
                continue
            if rect.right() < -FADE or rect.left() > self.width() + FADE:
                continue
            start, end = starts.get(day), ends.get(day)
            if start is None or end is None:
                layers = [(shot, 1.0) for shot in (start, end) if shot is not None]
            else:
                layers = [(shot, weight) for shot, weight in ((start, 1.0 - mix), (end, mix)) if weight > 0]
            if not layers:
                continue
            self._paint_ground(painter, rect, layers, radius)
            shape = QPainterPath()
            shape.addRoundedRect(rect, radius, radius)
            painter.setClipPath(shape)
            for shot, weight in layers:
                painter.setOpacity(weight)
                self._blit(painter, shot.picture, fitted(shot, rect))
            painter.setClipping(False)
            painter.setOpacity(1.0)
        self._paint_arrow_clay(painter)
        painter.end()

    def _paint_ground(
        self, painter: QPainter, rect: QRectF, layers: list[tuple[Shot, float]], radius: float,
    ) -> None:
        """The card's clay at `rect`, which shows where a picture does not reach: the shadow of each
        picture's state at its share, one surface, and the veil as far as the pictures are veiled."""
        for shot, weight in layers:
            for y, blur, spread, colour, alpha in _shadows(self.tokens, shot.lifted):
                _soft(painter, rect, radius, y, blur, spread, colour, alpha * weight)
        lifted = max(layers, key=lambda layer: layer[1])[0].lifted
        paint_clay(painter, rect, self.tokens, radius, lifted=lifted, shadow=False)
        veiled = sum(weight for shot, weight in layers if shot.veiled)
        if veiled > 0:
            colour = QColor(self.tokens["bg"])
            colour.setAlphaF(VEIL * min(veiled, 1.0))
            painter.fillRect(shadowed(rect, self.tokens, False), colour)

    def _paint_arrow_clay(self, painter: QPainter) -> None:
        for arrow in (self.back, self.ahead):
            if arrow.isVisible():
                body = QRectF(arrow.geometry())
                paint_clay(painter, body, self.tokens, body.height() / 2, lifted=False)

    def _blit(self, painter: QPainter, picture: QPixmap, target: QRectF) -> None:
        """Draw `picture` in `target`, which has its proportions. At its own size it is copied."""
        ratio = picture.devicePixelRatio() or 1.0
        wide, tall = picture.width() / ratio, picture.height() / ratio
        if abs(target.width() - wide) < 1e-3 and abs(target.height() - tall) < 1e-3:
            painter.drawPixmap(QPoint(round(target.x()), round(target.y())), picture)
            return
        painter.drawPixmap(target, picture, QRectF(picture.rect()))

    def _targets(self) -> dict[int, QRectF]:
        return slots(self.width(), self.height(), self._front, self.scale, wide=self._open)

    def _put(self, rects: dict[int, QRectF]) -> None:
        """Every card where `rects` puts it: the one in front as its hours, and Day's summary in it."""
        if not rects or not self._cards:
            return
        self._rects = dict(rects)
        for day, card in self._cards.items():
            shown = day != self._front and self._peeks
            if shown:
                card.setGeometry(rects[day].toRect())
            card.setVisible(shown)
        self._place_front(rects[self._front])
        self._fade.setGeometry(self.rect())
        self._place_arrows()
        self._veil_cards()
        self.update()

    def _place_front(self, front: QRectF) -> None:
        """The hours, the date and Day's summary on the card in front, which `front` is."""
        scale = self.scale
        side, right, foot = (size * scale for size in FRONT_PAD)
        beside = (SUMMARY + SUMMARY_GAP) * scale if self._open and self._summary is not None else 0
        scroll = self.hours
        if scroll is not None:
            scroll.setGeometry(front.adjusted(side, 0, -right - beside, -foot).toRect())
        for stamp in (self._date, self._chip):
            stamp.adjustSize()
            stamp.move(
                round(front.right() - right - stamp.width()),
                round(front.top() + (FRONT_HEAD * scale - stamp.height()) / 2),
            )
        if self._summary is not None:
            top = front.top() + FRONT_HEAD * scale
            wide = SUMMARY * scale
            box = QRectF(front.right() - right - wide, top, wide, front.bottom() - foot - top)
            self._summary.setGeometry(box.toRect())

    def _veil_cards(self) -> None:
        """The veil over every neighbour and its shadow, short of the card in front's shadow."""
        veil = self._veil
        veil.setGeometry(self.rect())
        shape = QPainterPath()
        if self.tokens and self._peeks:
            for day, rect in self._rects.items():
                if day != self._front:
                    shape.addRect(shadowed(rect, self.tokens, False))
            kept = QPainterPath()
            kept.addRect(shadowed(self._rects[self._front], self.tokens, True))
            shape = shape.subtracted(kept)
        veil.shape = shape
        veil.update()

    def _place_arrows(self) -> None:
        """The arrows in the gaps either side of the card in front, halfway down; and the fade at the
        row's ends, over the room outside the cards in view, where the days further off slide in."""
        targets = self._targets()
        front = targets.get(self._front)
        if front is None:
            return
        gap, side = GAP * self.scale, self.back.width()
        middle = round(front.center().y() - side / 2)
        self.back.move(round(front.left() - gap / 2 - side / 2), middle)
        self.ahead.move(round(front.right() + gap / 2 - side / 2), middle)
        width = self.width()
        seen = [
            min(rect.left(), width - rect.right())
            for day, rect in targets.items()
            if day != self._front and self._peeks and rect.left() >= 0 and rect.right() <= width
        ]
        reach = min(seen) if seen else FADE * self.scale
        self._fade.reach = min(max(reach, RESERVE * self.scale), FADE * self.scale)

    def _arrows(self) -> None:
        scene = self.scene
        if scene is None:
            return
        first = self._open or self._front > 0
        last = self._open or self._front < 6
        self.back.setEnabled(first)
        self.ahead.setEnabled(last)
        for arrow, step in ((self.back, -1), (self.ahead, 1)):
            day = scene.week.date_of(self._front + step)
            name = DAY_FULL[day.weekday()]
            arrow.setToolTip(name)
            arrow.setAccessibleName(f"Show {name}")

    def _follow(self) -> None:
        """Neighbours take the stretch of the day the card in front shows, on the drag's step, so a
        block dropped at their top or foot still lands on it: when its hours open afresh, another week
        or another day on Day, and each time they put themselves where they opened while the page
        settles. Then they stay still while the student scrolls it (J10)."""
        scroll = self.hours
        if scroll is None or not scroll.canvas.tracks:
            return
        if self._held == self._opening and not scroll.placing():
            return
        self._held = self._opening
        track = scroll.canvas.tracks[0]
        top = scroll.verticalScrollBar().value()
        middle = track.area.center().x()
        first = track.minute_at(QPointF(middle, top))
        last = track.minute_at(QPointF(middle, top + scroll.viewport().height()))
        step = self.hand.step
        window = (
            max(FIRST, math.floor(first / step) * step),
            min(LAST, max(math.ceil(last / step) * step, math.floor(first / step) * step + step)),
        )
        if window != self._window:
            self._window = window
            for card in self._cards.values():
                card.hours.relayout()
                card.hours.update()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._stop_slide()
        self._put(self._targets())

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if self._snaps is not None:
            self._paint_snaps()
            return
        if not self.tokens or not self._rects:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = RADIUS * self.scale
        order = sorted((day for day in self._rects if day != self._front and self._peeks),
                       key=lambda day: -abs(day - self._front))
        for day in order:
            rect = self._rects[day]
            if rect.right() >= -FADE and rect.left() <= self.width() + FADE:
                paint_clay(painter, rect, self.tokens, radius, lifted=False)
        paint_clay(painter, self._rects[self._front], self.tokens, radius, lifted=True)
        self._paint_arrow_clay(painter)
        painter.end()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """The wheel over the row slides it a day a notch. Over the card in front it is the hours'."""
        event.accept()
        front = self._rects.get(self._front)
        running = self._slide.state() == QAbstractAnimation.State.Running
        if front is not None and front.contains(event.position()) or running:
            self._wheel = 0
            return
        delta = event.angleDelta()
        self._wheel += delta.x() if abs(delta.x()) > abs(delta.y()) else delta.y()
        if abs(self._wheel) >= 120:
            step = -1 if self._wheel > 0 else 1
            self._wheel = 0
            self.turn(step)

    # Dragging the row

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """A press in the room between the cards, or on a neighbour's edge, may start a drag of the row.
        The card in front is its hours' own: a drag there never moves the row."""
        front = self._rects.get(self._front)
        if event.button() != Qt.MouseButton.LeftButton or front is None or front.contains(event.position()):
            super().mousePressEvent(event)
            return
        self._grip, self._dragging = event.globalPosition(), None
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._grip is None or self._held_press is not None:
            super().mouseMoveEvent(event)
            return
        self._drag_to(event.globalPosition())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._grip is None or self._held_press is not None or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        self._let_go(event.globalPosition())

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """On a neighbour's name or hours, a press is held back until the pointer shows what it is: a
        sideways drag moves the row; anything else is handed on as it came, so a click still opens the
        day or a block and a drag up or down still carries a block."""
        if self._replaying or not isinstance(event, QMouseEvent):
            return False
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress:
            left = event.button() == Qt.MouseButton.LeftButton
            if not left or self.hand.busy or not isinstance(watched, QWidget):
                return False
            self._grip, self._dragging = event.globalPosition(), None
            self._held_press = (watched, event.position(), event.globalPosition(), event.modifiers())
            return True
        if self._held_press is None or self._held_press[0] is not watched:
            return False
        if kind == QEvent.Type.MouseMove:
            if self._drag_to(event.globalPosition()) is False:
                self._hand_on(event)
            return True
        if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                self._held_press = None
                self._let_go(event.globalPosition())
            else:
                self._hand_on(event)
            return True
        return False

    def _hand_on(self, event: QMouseEvent) -> None:
        """Give the neighbour the press the row held back, then `event`, as if the row never looked."""
        held = self._held_press
        assert held is not None
        watched, local, at, modifiers = held
        self._held_press, self._grip, self._dragging = None, None, None
        left = Qt.MouseButton.LeftButton
        self._replaying = True
        try:
            QApplication.sendEvent(
                watched, QMouseEvent(QEvent.Type.MouseButtonPress, local, at, left, left, modifiers)
            )
            QApplication.sendEvent(
                watched,
                QMouseEvent(
                    event.type(), event.position(), event.globalPosition(), event.button(), event.buttons(),
                    event.modifiers(),
                ),
            )
        finally:
            self._replaying = False

    def _drag_to(self, at: QPointF) -> bool | None:
        """The row follows the pointer once it has gone sideways further than a click strays, and more
        across than up or down. None while that is not known yet; False when it went up or down."""
        grip = self._grip
        if grip is None:
            return None
        across, down = at.x() - grip.x(), at.y() - grip.y()
        if self._dragging is None:
            if max(abs(across), abs(down)) < QApplication.startDragDistance():
                return None
            self._dragging = abs(across) > abs(down)
            if self._dragging:
                self._stop_slide()
        if self._dragging:
            self._put({day: rect.translated(across, 0) for day, rect in self._targets().items()})
        return self._dragging

    def _let_go(self, at: QPointF) -> None:
        """Settle on the day nearest the middle, as the arrows do; a drag shorter than DRAG_LEAST goes
        back. On Day the window is asked for the day, as the arrows ask it."""
        grip, dragging = self._grip, self._dragging
        self._grip = self._dragging = None
        if grip is None or not dragging:
            return
        across = at.x() - grip.x()
        if abs(across) < DRAG_LEAST * self.scale:
            self._go_back()
            return
        towards = 1 if across < 0 else -1
        targets = self._targets()
        here = targets[self._front]
        beside = targets.get(self._front + towards, targets.get(self._front - towards))
        pitch = abs(beside.center().x() - here.center().x()) if beside is not None else here.width()
        target = self._front + towards * max(1, round(abs(across) / max(pitch, 1.0)))
        target = min(max(target, -1 if self._open else 0), 7 if self._open else 6)
        if target == self._front:
            self._go_back()
        elif not self._open:
            self._go(target, "slide")
        else:
            left = self._front
            self.turned.emit(target)
            if self._front == left:
                # The window shows the day later, or not at all: the row goes back meanwhile, and slides
                # from wherever it is when the day arrives.
                self._go_back()

    def _go_back(self) -> None:
        """The row back to the day in front, sliding as the arrows slide it, at once without motion."""
        motion_level, rects = app_level(), self._targets()
        length = duration(SLIDE_MS, motion_level)
        if length > 0 and moves(motion_level) and self.isVisible() and self._rects:
            before = dict(self._rects)
            self._stop_slide()
            self._put(before)
            self._slide_to(before, rects, self._pictures(before, front=self._front), length)
            return
        self._put(rects)

    # While a block is held

    def _carrying(self, active: bool) -> None:
        if active and self.isVisible():
            self._dwell_on = None
            self._dwell.start()
            return
        self._dwell.stop()
        shown = self.scene
        if not active and self._open and shown is not None and self.isVisible():
            day = next((at for at in range(7) if shown.week.date_of(at).isoformat() == shown.iso_day), None)
            if day is not None and day != self._front:
                # Carried to another day on Day: the window follows it there once it is let go.
                self.turned.emit(self._front)

    def _dwelt(self) -> None:
        """A held block resting on an arrow slides the row a day, and again after as long."""
        at = QCursor.pos()
        over = next(
            (arrow for arrow in (self.back, self.ahead)
             if arrow.isVisible() and arrow.rect().contains(arrow.mapFromGlobal(at))),
            None,
        )
        now = time.monotonic()
        if over is not self._dwell_on:
            self._dwell_on, self._dwell_since = over, now
            return
        if over is None or now - self._dwell_since < DWELL_S:
            return
        self._dwell_since = now
        target = self._front + (-1 if over is self.back else 1)
        if 0 <= target <= 6:
            self._go(target, "jump")

    # For the rig and the tests

    def surfaces(self) -> list[QWidget]:
        """The hours in front first, then every other day's, left to right: past the row's edge too,
        where `reveal` brings them to the front."""
        scroll = self.hours
        found: list[QWidget] = [scroll.canvas] if scroll is not None and scroll.isVisible() else []
        found += [card.hours for _day, card in sorted(self._cards.items()) if card.isVisible()]
        return found

    def name_point(self, day: int) -> QPoint:
        """Where a day's name is on screen. A day whose name is past the row's edge comes to the front."""
        if day != self._front and day in self._cards:
            head = self._cards[day].head
            centre = head.mapTo(self, head.rect().center())
            if head.isVisible() and self.rect().contains(centre):
                return head.mapToGlobal(head.rect().center())
            self._go(day, "jump")
        head = self._heads["day" if self._open else "week"]
        return head.mapToGlobal(head.rect().center())

    def reveal(self, day: int, first: int, last: int) -> None:
        """Bring `day` to the front, at once, and this stretch of it into view."""
        if day != self._front and 0 <= day <= 6:
            self._go(day, "jump")
        scroll = self.hours
        if scroll is None:
            return
        canvas = scroll.canvas
        HoursCanvas.reveal(canvas, day, first, last)
        page = _page_of(self)
        track = canvas.track_for(day, first) or canvas.track_for(day)
        if page is None or track is None:
            return
        for minute in (last, first):
            local = track.point_for(min(max(minute, track.first), track.last)).toPoint()
            inside = canvas.mapTo(page.widget(), local)
            page.ensureVisible(inside.x(), inside.y(), 20, 60)

    def in_view(self, canvas: HoursCanvas, day: int, minute: int) -> bool:
        if not HoursCanvas.in_view(canvas, day, minute):
            return False
        track = canvas.track_for(day, minute)
        if track is None:
            return False
        local = track.point_for(minute).toPoint()
        if not self.rect().adjusted(-2, -2, 2, 2).contains(canvas.mapTo(self, local)):
            return False
        page = _page_of(self)
        if page is None:
            return True
        return page.viewport().rect().adjusted(-2, -2, 2, 2).contains(canvas.mapTo(page.viewport(), local))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, round(340 * self.scale))

    def sizeHint(self) -> QSize:  # noqa: N802
        # The dish's chips wrap, so the page is laid out at its preferred height: the row asks for its
        # least and takes what is left.
        return self.minimumSizeHint()


def _page_of(widget: QWidget | None) -> QScrollArea | None:
    """The page's scroll area holding the row."""
    found = widget.parentWidget() if widget is not None else None
    while found is not None and not isinstance(found, QScrollArea):
        found = found.parentWidget()
    return found


class Dish(QFrame):
    """A pressed-in tray: a shade inside its top edge and a highlight along its foot."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("clayDish")
        self.tokens: dict[str, str] = {}
        self.radius = float(RADIUS)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        if not self.tokens:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        dark = family(self.tokens) == "dark"
        page, text, surface = self.tokens["bg"], self.tokens["text"], self.tokens["surface"]
        shape = QPainterPath()
        shape.addRoundedRect(body, self.radius, self.radius)
        tray = mix_oklab(page, surface, 0.55) if dark else mix_oklab(text, page, 0.04)
        painter.fillPath(shape, QColor(tray))
        painter.setClipPath(shape)
        shade = QLinearGradient(QPointF(0, body.top()), QPointF(0, body.top() + 8))
        low = QColor("#000000" if dark else text)
        low.setAlphaF(0.35 if dark else 0.09)
        shade.setColorAt(0, low)
        low.setAlphaF(0.0)
        shade.setColorAt(1, low)
        painter.fillRect(QRectF(body.left(), body.top(), body.width(), 8), shade)
        painter.fillRect(QRectF(body.left(), body.bottom() - 1, body.width(), 1), QColor(surface))
        painter.setClipping(False)
        if dark:
            ring = QColor(self.tokens["line"])
            ring.setAlphaF(0.7)
            painter.setPen(QPen(ring, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(body, self.radius, self.radius)
        painter.end()


class ClayChip(TrayChip):
    """Homework not placed yet as a clay chip: the book in its category's colour, its name, how long
    it takes, and a grip. Drag it onto a day to give it a time; a click opens it."""

    def __init__(self, hand: Hand, waiting: Waiting, tokens: dict[str, str], scale: float) -> None:
        super().__init__(hand, waiting)
        self.tokens, self.scale = tokens, scale
        self.length = length_label(waiting.minutes)
        self.fill, self.mark = _paint(tokens, waiting.category or "assignments")

    def _fit(self) -> None:
        # Painted whole each time: the title shortens in the paint.
        return

    def _fonts(self) -> tuple[QFont, QFont]:
        # Both weights named: the window's stylesheet sets a button's font at 600.
        return (
            at_scale(self.font(), "body", self.scale, WEIGHT_STRONG),
            at_scale(self.font(), "body", self.scale, WEIGHT_REGULAR),
        )

    def _measures(self) -> tuple[float, float, float, float]:
        """Its height, the book's circle, the grip, and the room between parts."""
        return 40 * self.scale, 28 * self.scale, 16 * self.scale, 8 * self.scale

    def sizeHint(self) -> QSize:  # noqa: N802
        title, small = self._fonts()
        tall, circle, grip, gap = self._measures()
        wide = 6 * self.scale + circle + gap + QFontMetricsF(title).horizontalAdvance(self._title) + gap
        wide += QFontMetricsF(small).horizontalAdvance(self.length) + gap + grip + gap
        return QSize(math.ceil(wide) + 2, math.ceil(tall) + 4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        hint = self.sizeHint()
        return QSize(min(hint.width(), round(160 * self.scale)), hint.height())

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tall, circle, grip, gap = self._measures()
        body = QRectF(1, 1, self.width() - 2, tall)
        dark = family(self.tokens) == "dark"
        shadow = QColor("#000000" if dark else self.tokens["text"])
        _soft(painter, body, tall / 2, 2, 4, -1, shadow, 0.4 if dark else 0.14)
        paint_clay(painter, body, self.tokens, tall / 2, lifted=False, shadow=False)
        if self.hasFocus() and self.property("keyfocus"):
            painter.setPen(QPen(QColor(self.tokens["accent"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(body.adjusted(1, 1, -1, -1), tall / 2 - 1, tall / 2 - 1)
        ring = QRectF(body.left() + 6 * self.scale, body.center().y() - circle / 2, circle, circle)
        painter.setPen(QPen(QColor(self.mark), 1.5))
        painter.setBrush(QColor(self.fill))
        painter.drawEllipse(ring.adjusted(0.75, 0.75, -0.75, -0.75))
        side = round(14 * self.scale)
        ratio = self.devicePixelRatioF()
        painter.drawPixmap(QPointF(ring.center().x() - side / 2, ring.center().y() - side / 2),
                           icons.pixmap(BOOK, self.tokens["text"], side, ratio))
        title, small = self._fonts()
        tm, sm = QFontMetricsF(title), QFontMetricsF(small)
        end = body.right() - gap - grip
        room = end - gap - (ring.right() + gap) - sm.horizontalAdvance(self.length) - gap
        name = tm.elidedText(self._title, Qt.TextElideMode.ElideRight, max(room, 0))
        left = ring.right() + gap
        line = QRectF(left, body.center().y() - tm.height() / 2, tm.horizontalAdvance(name) + 1, tm.height())
        painter.setFont(title)
        painter.setPen(QColor(self.tokens["text"]))
        painter.drawText(line, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        painter.setFont(small)
        painter.setPen(QColor(self.tokens["muted"]))
        after = QRectF(line.right() + gap - 1, line.top(), sm.horizontalAdvance(self.length) + 1, tm.height())
        painter.drawText(after, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.length)
        painter.drawPixmap(QPointF(end, body.center().y() - grip / 2),
                           icons.pixmap("grip-vertical", self.tokens["muted"], round(grip), ratio))
        painter.end()


class Bar(QWidget):
    """A day's hours by kind as one thin bar, each kind in its mark, free time last."""

    def __init__(self, parts: list[tuple[str, int]], scale: float) -> None:
        super().__init__()
        self.parts = parts
        self.setFixedHeight(round(8 * scale))

    def paintEvent(self, event: object) -> None:  # noqa: N802
        total = sum(minutes for _colour, minutes in self.parts)
        if total <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.rect())
        shape = QPainterPath()
        shape.addRoundedRect(body, body.height() / 2, body.height() / 2)
        painter.setClipPath(shape)
        room = body.width() - 2 * (len(self.parts) - 1)
        at = body.left()
        for colour, minutes in self.parts:
            wide = room * minutes / total
            painter.fillRect(QRectF(at, body.top(), wide, body.height()), QColor(colour))
            at += wide + 2
        painter.end()


class Dot(QWidget):
    """A category's dot, or free time's hollow ring."""

    def __init__(self, colour: str, hollow: bool, scale: float) -> None:
        super().__init__()
        self.colour, self.hollow = colour, hollow
        self.setFixedSize(round(10 * scale), round(10 * scale))

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        if self.hollow:
            painter.setPen(QPen(QColor(self.colour), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.colour))
        painter.drawEllipse(body)
        painter.end()


class ClayDeckView(LayoutView):
    layout_id = "clay"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        # A view's minimum height must not become the window's: inside a scroll area, what does not fit
        # scrolls and the window keeps its size.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._page = QWidget()
        self._page.setObjectName("clayPage")
        self._root = QVBoxLayout(self._page)
        outer.addWidget(scrolling(self._page, "clayScroll"))
        self.row = Row(self.hand, self.keep_zoom)
        self.row.opened.connect(self._open_day)
        self.row.turned.connect(self._open_day)
        self._root.setSpacing(0)
        self._root.addWidget(self.row, 1)
        self._dish = Dish()
        self._tray = QHBoxLayout(self._dish)
        # The row runs to the window's edges, where its ends fade; the dish keeps the page's margins.
        self._foot = QHBoxLayout()
        self._foot.addWidget(self._dish)
        self._root.addLayout(self._foot)

    def shown_day(self, scene: Scene) -> int:
        if scene.surface == "day" and scene.iso_day:
            for day in range(7):
                if scene.week.date_of(day).isoformat() == scene.iso_day:
                    return day
        return scene.today if scene.today is not None else 0

    def hours_surfaces(self) -> list[QWidget]:
        """The hours in front first: the one the zoom is on and the rig reads first."""
        return [widget for widget in self.row.surfaces() if widget.isVisible()]

    def render(self, scene: Scene, week_changed: bool) -> None:
        px = scene.px
        self.setStyleSheet(self._sheet(scene))
        self._root.setContentsMargins(0, px(AROUND[1]), 0, px(AROUND[1]))
        self._foot.setContentsMargins(px(AROUND[0]), 0, px(AROUND[0]), 0)
        is_day = scene.surface == "day"
        day = self.shown_day(scene) if is_day else None
        summary = self._summary(scene, day) if day is not None else None
        self.row.show_scene(scene, day, scene.options.get("peek") != "hide", summary)
        self._fill_dish(scene)

    def _open_day(self, day: int) -> None:
        if self._scene is not None:
            self.day_activated.emit(self._scene.week.date_of(day).isoformat())

    # The dish

    def _fill_dish(self, scene: Scene) -> None:
        px = scene.px
        self._dish.tokens = scene.tokens
        self._dish.radius = RADIUS * scene.scale
        self._dish.setMinimumHeight(px(DISH))
        empty(self._tray)
        self._tray.setContentsMargins(px(24), px(10), px(24), px(10))
        self._tray.setSpacing(px(24))
        head = QVBoxLayout()
        head.setSpacing(px(2))
        head.addWidget(label("Not placed yet", "clayTrayLabel"))
        waiting = scene.week.waiting
        due = _due_words(waiting)
        if due:
            head.addWidget(label(due, "clayDue"))
        self._tray.addLayout(head)
        if not waiting:
            self._tray.addWidget(label("Nothing is waiting for a time.", "clayEmpty"), 1)
            self.update()
            return
        chips = FlowLayout(gap=px(12))
        chips.setContentsMargins(0, 0, 0, 0)
        for index, item in enumerate(waiting):
            chip = ClayChip(self.hand, item, scene.tokens, scene.scale)
            chip.setObjectName(f"clayWaiting{index}")
            chip.clicked.connect(lambda _=False, block_id=item.block_id: self.block_activated.emit(block_id))
            chips.addWidget(chip)
        holder = QFrame()
        holder.setObjectName("clayChips")
        holder.setLayout(chips)
        self._tray.addWidget(holder, 1)
        self._tray.addWidget(label("Drag a chip onto a day.", "clayHint"), 0, Qt.AlignmentFlag.AlignVCenter)

    # Day's summary

    def _summary(self, scene: Scene, day: int) -> QFrame:
        """The day's hours by kind from 08:00 to 22:00 with its free time, as a bar and a row each;
        and today, what is left of it."""
        px, tokens, week = scene.px, scene.tokens, scene.week
        frame = QFrame()
        frame.setObjectName("claySummary")
        box = QVBoxLayout(frame)
        box.setContentsMargins(px(24), 0, 0, 0)
        box.setSpacing(px(12))
        title = f"{DAY_FULL[day]}, {clock_label(DAY_FROM)} to {clock_label(DAY_TO)}"
        box.addWidget(label(title, "claySumTitle"))
        kinds = day_kinds(week, day)
        free = DAY_TO - DAY_FROM - _covered(week.on_day(day), DAY_FROM, DAY_TO)
        free_bar = mix_oklab(tokens["text"], tokens["surface"], 0.14)
        parts = [(_paint(tokens, kind)[1], minutes) for kind, minutes in kinds]
        box.addWidget(Bar([*parts, (free_bar, free)], scene.scale))
        rows = QVBoxLayout()
        rows.setSpacing(0)
        for at, (kind, minutes) in enumerate(kinds):
            name = (CATEGORIES.get(kind) or {}).get("label") or "Other"
            dot = Dot(_paint(tokens, kind)[1], False, scene.scale)
            book = kind in HOMEWORK_CATEGORIES
            rows.addWidget(self._row(scene, dot, name, length_label(minutes), at == 0, book))
        rows.addWidget(self._row(scene, Dot(tokens["line"], True, scene.scale), "Free", length_label(free),
                                 not kinds))
        box.addLayout(rows)
        if day == scene.today and scene.minute < DAY_TO:
            planned, open_min, coming = left_today(week, day, scene.minute)
            box.addSpacing(px(12))
            box.addWidget(label("Left today", "clayLeftTitle"))
            left = QVBoxLayout()
            left.setSpacing(0)
            lines = [("clock", "Planned", length_label(planned)),
                     ("sun", f"Free until {clock_label(DAY_TO)}", length_label(open_min))]
            if coming is not None:
                lines.append(("skip-forward", f"Next at {clock_label(coming.start)}",
                              f"in {length_label(coming.start - scene.minute)}"))
            for at, (icon, words, value) in enumerate(lines):
                mark = QLabel()
                mark.setObjectName("clayLeftIcon")
                mark.setPixmap(icons.pixmap(icon, tokens["muted"], px(14), self.devicePixelRatioF()))
                left.addWidget(self._row(scene, mark, words, value, at == 0))
            box.addLayout(left)
        box.addStretch(1)
        return frame

    def _row(
        self, scene: Scene, mark: QWidget, words: str, value: str, first: bool, book: bool = False
    ) -> QFrame:
        row = QFrame()
        row.setObjectName("claySumRow")
        row.setProperty("first", first)
        row.setFixedHeight(scene.px(30))
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(scene.px(8))
        line.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        line.addWidget(label(words, "claySumName"), 0, Qt.AlignmentFlag.AlignVCenter)
        if book:
            icon = QLabel()
            icon.setObjectName("claySumBook")
            icon.setPixmap(icons.pixmap(BOOK, scene.tokens["muted"], scene.px(12), self.devicePixelRatioF()))
            line.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        line.addStretch(1)
        line.addWidget(label(value, "claySumLength"), 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _sheet(self, scene: Scene) -> str:
        tokens = scene.tokens
        text, muted, accent, surface = tokens["text"], tokens["muted"], tokens["accent"], tokens["surface"]

        def size(role: str) -> str:
            return f"{type_pt(role, scene.scale)}pt"

        chip = round(24 * scene.scale)
        clear = css(background="transparent")
        caption_words = css(color=muted, font_size=size("caption"))
        return base_sheet(self.objectName(), tokens) + rules(
            self.objectName(),
            {
                "#clayScroll, #clayPage": css(background=tokens["bg"]),
                # Plain widgets on the cards, which the window's stylesheet would paint its page colour.
                "#clayWeekHeader, #clayDayHeader, #clayWeekZoom, #clayDayZoom, #clayChips": clear,
                "#qt_scrollarea_vcontainer, #qt_scrollarea_hcontainer": clear,
                "QLabel": css(color=text, font_size=size("body")),
                # A stylesheet's height beats setFixedHeight, so a name row's is set here.
                'QPushButton[kind="head"]': css(
                    background="transparent",
                    border="none",
                    border_radius=f"{RADIUS_CONTROL}px",
                    padding="0",
                    min_height=f"{scene.px(PEEK_HEAD)}px",
                    max_height=f"{scene.px(PEEK_HEAD)}px",
                ),
                'QPushButton[kind="head"][front="true"]': css(
                    min_height=f"{scene.px(FRONT_HEAD)}px", max_height=f"{scene.px(FRONT_HEAD)}px"
                ),
                'QPushButton[kind="head"][opens="true"]:hover': css(
                    background=mix_oklab(text, surface, 0.05)
                ),
                'QPushButton[kind="head"][keyfocus="true"]:focus': css(border=f"2px solid {accent}"),
                "QLabel#clayDayName": css(font_size=size("heading"), font_weight=WEIGHT_STRONG),
                'QLabel#clayDayName[front="true"]': css(font_size=size("title")),
                "QLabel#clayNote, QLabel#clayDate": css(color=muted),
                "QLabel#clayToday": css(
                    background=accent,
                    color=tokens["accent_ink"],
                    font_weight=WEIGHT_STRONG,
                    border_radius=f"{chip // 2}px",
                    padding=f"0 {round(8 * scene.scale)}px",
                    min_height=f"{chip}px",
                    max_height=f"{chip}px",
                ),
                "QLabel#clayTrayLabel, QLabel#claySumTitle, QLabel#clayLeftTitle": css(
                    font_weight=WEIGHT_STRONG
                ),
                "QLabel#clayDue, QLabel#clayHint, QLabel#clayEmpty": caption_words,
                "QLabel#claySumLength": css(color=muted),
                "QFrame#claySummary": css(border_left=f"1px solid {tokens['line']}"),
                'QFrame#claySumRow[first="false"]': css(border_top=f"1px solid {tokens['line']}"),
            },
        )


def _due_words(waiting: Iterable[Waiting]) -> str:
    """When what is not placed yet is due, as the dish says it: "Due Sun 27", or the soonest first."""
    dues = sorted({item.due[:10] for item in waiting if item.due})
    if not dues:
        return ""
    soonest = date.fromisoformat(dues[0])
    words = f"{DAYS[soonest.weekday()]} {soonest.day}"
    return f"Due {words}" if len(dues) == 1 else f"First due {words}"
