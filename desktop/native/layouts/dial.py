"""Day dial: a day screen. The day is a clock face, and a list beside it reads the arcs out in words.

The face is painted, so it cannot be tabbed through. The hour-by-hour list is its keyboard and
screen-reader twin: every arc is also a row that opens the same block.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QFontMetricsF,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from desktop.native.calendar import DAY_FULL, DAYS
from desktop.native.hours.canvas import fit_lines
from desktop.native.hours.geometry import DialTrack, Span
from desktop.native.hours.hand import Gesture, Hand, Held
from desktop.native.layouts.base import (
    LayoutView,
    Scene,
    base_sheet,
    button,
    css,
    day_buttons,
    empty,
    label,
    mark_of,
    plural,
    rules,
    scrolling,
)
from desktop.native.weekmodel import Occurrence, clock_label, length_label, planned_line

HOURS = {"day": (6 * 60, 22 * 60), "full": (0, 24 * 60)}
SWEEP = 300.0


class DialFace(QWidget):
    """One day as arcs on a ring. Fixed blocks sit on the ring, homework on a thinner ring outside it.

    The big face is a surface for the window's hand: its ring is a `DialTrack`, and an arc pressed
    there is carried round it to a new time. The small faces in the week strip only open their day."""

    block_clicked = Signal(str)
    day_clicked = Signal(int)

    def __init__(self, day: int, mini: bool, hand: Hand | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.day, self.mini, self.hand = day, mini, hand
        self.takes_blocks = hand is not None and not mini
        self._blocks: tuple[Occurrence, ...] = ()
        self._minute: int | None = None
        self._span = HOURS["day"]
        self._tokens: dict[str, str] = {}
        self._chosen = False
        self.setObjectName(f"dialMini{day}" if mini else "dialFace")
        self.setMinimumSize(64, 64) if mini else self.setMinimumSize(280, 280)
        if mini:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        if self.takes_blocks:
            self.setMouseTracking(True)
            hand.preview_changed.connect(self.update)

    def set_day(
        self,
        blocks: tuple[Occurrence, ...],
        minute: int | None,
        span: tuple[int, int],
        tokens: dict[str, str],
        chosen: bool = False,
    ) -> None:
        self._blocks, self._minute, self._span, self._tokens, self._chosen = (
            blocks,
            minute,
            span,
            tokens,
            chosen,
        )
        said = ", ".join(f"{item.title} {clock_label(item.start)}" for item in blocks) or "nothing planned"
        self.setAccessibleName(f"{DAY_FULL[self.day]}: {said}")
        self.update()

    def _geometry(self) -> tuple[QPointF, float, float]:
        side = min(self.width(), self.height())
        return QPointF(self.width() / 2, self.height() / 2), side * 0.36, side * (0.13 if self.mini else 0.10)

    @property
    def track(self) -> DialTrack:
        """The day's minutes round the face: every arc is drawn, pressed and carried on this."""
        centre, radius, width = self._geometry()
        first, last = self._span
        return DialTrack(self.day, centre, radius - width, radius + width * 1.3, first, last, SWEEP)

    def _angle(self, minute: int) -> float:
        track = self.track
        return track.turn_at(track.point_for(minute))

    def _arc(
        self,
        painter: QPainter,
        radius: float,
        width: float,
        first: int,
        last: int,
        colour: QColor,
        style: Qt.PenStyle = Qt.PenStyle.SolidLine,
    ) -> None:
        centre, _, _ = self._geometry()
        pen = QPen(colour, width, style)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        box = QRectF(centre.x() - radius, centre.y() - radius, radius * 2, radius * 2)
        begin, finish = self._angle(first), self._angle(last)
        # Qt measures arcs anticlockwise from three o'clock in sixteenths of a degree.
        painter.drawArc(box, round((90 - begin) * 16), round(-(finish - begin) * 16))

    def _ring(self, work: bool) -> tuple[float, float]:
        """The radius and width an arc is drawn at: homework on the thin outer ring."""
        _, radius, width = self._geometry()
        return (radius + width * 0.8, width * 0.5) if work else (radius, width)

    def _held(self) -> tuple[Held, Span, bool, str] | None:
        """What the hand is carrying over this face: what it is, where it would go, whether it can,
        and the words for it."""
        preview = self.hand.preview if self.takes_blocks and self.hand is not None else None
        if preview is None or preview.held.kind not in (Gesture.MOVE, Gesture.PLACE):
            return None
        if preview.span.day != self.day:
            return None
        return preview.held, preview.span, preview.verdict.ok, preview.verdict.words

    def _shown(self) -> list[Occurrence]:
        """The day's arcs, less the one the hand has lifted off this face."""
        preview = self.hand.preview if self.takes_blocks and self.hand is not None else None
        held = preview.held if preview is not None else None
        if held is None or held.kind is not Gesture.MOVE or held.from_day != self.day:
            return list(self._blocks)
        return [item for item in self._blocks if item.block_id != held.block_id]

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        if not self._tokens:
            return
        tokens = self._tokens
        centre, radius, width = self._geometry()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._arc(painter, radius, width, self._span[0], self._span[1], QColor(tokens["line"]))
        for item in self._shown():
            colour = QColor(mark_of(item.category))
            if not item.live:
                colour.setAlphaF(0.35)
            self._arc(painter, *self._ring(item.work), item.start, item.end, colour)
        if self.mini:
            if self._chosen:
                painter.setPen(QPen(QColor(tokens["accent"]), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(centre, radius * 0.55, radius * 0.55)
            painter.end()
            return
        held = self._held()
        if held is not None:
            thing, span, ok, _words = held
            work = next((item.work for item in self._blocks if item.block_id == thing.block_id), True)
            ring, thick = self._ring(work)
            # Where the carried block would go, ringed in the accent, or in red where it cannot.
            self._arc(
                painter, ring, thick + 6, span.start, span.end, QColor(tokens["accent" if ok else "danger"])
            )
            category = next((item.category for item in self._blocks if item.block_id == thing.block_id), "")
            self._arc(painter, ring, thick, span.start, span.end, QColor(mark_of(category)))
        painter.setPen(QColor(tokens["bg_muted"]))
        small = QFont(self.font())
        small.setPixelSize(max(round(radius * 0.085), 10))
        painter.setFont(small)
        step = 2 if self._span == HOURS["day"] else 3
        for hour in range(self._span[0] // 60, self._span[1] // 60 + 1, step):
            turn = math.radians(self._angle(hour * 60))
            spot = QPointF(
                centre.x() + (radius - width * 1.25) * math.sin(turn),
                centre.y() - (radius - width * 1.25) * math.cos(turn),
            )
            painter.drawText(
                QRectF(spot.x() - 16, spot.y() - 10, 32, 20), Qt.AlignmentFlag.AlignCenter, str(hour)
            )
        big = QFont(self.font())
        big.setPixelSize(max(round(radius * 0.26), 16))
        big.setBold(True)
        painter.setFont(big)
        painter.setPen(QColor(tokens["bg_ink"]))
        words = clock_label(self._minute) if self._minute is not None else DAYS[self.day]
        painter.drawText(
            QRectF(centre.x() - radius, centre.y() + radius * 0.12, radius * 2, radius * 0.4),
            Qt.AlignmentFlag.AlignCenter,
            words,
        )
        if self._minute is not None:
            turn = math.radians(self._angle(self._minute))
            hand = QPen(QColor(tokens["danger"]), 3)
            hand.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(hand)
            painter.drawLine(
                centre,
                QPointF(
                    centre.x() + (radius + width) * math.sin(turn),
                    centre.y() - (radius + width) * math.cos(turn),
                ),
            )
            painter.setBrush(QColor(tokens["danger"]))
            painter.drawEllipse(centre, 6, 6)
        if held is not None and held[3]:
            self._paint_words(painter, held[3], held[2])
        painter.end()

    def _paint_words(self, painter: QPainter, words: str, ok: bool) -> None:
        """The held block's words on a pill above the clock, as wide as the ring, so they stay on
        the face wherever the arc is carried."""
        centre, radius, _width = self._geometry()
        font = QFont(self.font())
        font.setPixelSize(max(round(radius * 0.08), 12))
        font.setBold(True)
        metrics = QFontMetricsF(font)
        room = min(2 * radius, self.width() - 16) - 20
        lines = fit_lines(words, font, room, metrics.lineSpacing() * 3)
        if not lines:
            return
        wide = max(metrics.horizontalAdvance(line) for line in lines) + 20
        tall = metrics.lineSpacing() * len(lines) + 10
        pill = QRectF(centre.x() - wide / 2, centre.y() + radius * 0.06 - tall, wide, tall)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._tokens["accent" if ok else "danger"]))
        painter.drawRoundedRect(pill, min(tall / 2, 14), min(tall / 2, 14))
        painter.setPen(QColor(self._tokens["accent_ink"]))
        painter.setFont(font)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, "\n".join(lines))

    def block_at(self, spot: QPointF) -> Occurrence | None:
        track = self.track
        if not track.contains(spot):
            return None
        centre, radius, width = self._geometry()
        minute = track.minute_at(spot)
        under = [item for item in self._blocks if item.start <= minute < item.end]
        outer = math.hypot(spot.x() - centre.x(), spot.y() - centre.y()) > radius + width * 0.5
        under.sort(key=lambda item: item.work != outer)
        return under[0] if under else None

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
        """A box as big as the arc, centred on its middle, so its centre is on the block."""
        item = next(
            (entry for entry in self._shown() if entry.block_id == block_id and entry.day == day), None
        )
        if item is None or day != self.day or not self.takes_blocks:
            return None
        centre, _, _ = self._geometry()
        ring, thick = self._ring(item.work)
        start, end = max(item.start, self._span[0]), min(item.end, self._span[1])
        if end <= start:
            return None
        points = []
        for share in (0, 0.25, 0.5, 0.75, 1):
            turn = math.radians(self._angle(round(start + (end - start) * share)))
            for reach in (ring - thick / 2, ring + thick / 2):
                points.append(
                    QPointF(centre.x() + reach * math.sin(turn), centre.y() - reach * math.cos(turn))
                )
        xs, ys = [point.x() for point in points], [point.y() for point in points]
        middle = math.radians(self._angle((start + end) // 2))
        at = QPointF(centre.x() + ring * math.sin(middle), centre.y() - ring * math.cos(middle))
        size = QRectF(0, 0, max(xs) - min(xs), max(ys) - min(ys))
        size.moveCenter(at)
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


class DayDialView(LayoutView):
    layout_id = "dial"

    def __init__(self, parent: QWidget | None = None, *, hand: Hand | None = None) -> None:
        super().__init__(parent, hand=hand)
        self._day: int | None = None
        # A view's minimum height must not become the window's: three designs pushed it past a 768 pixel
        # laptop screen. Inside a scroll area, what does not fit scrolls and the window keeps its size.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._page = QWidget()
        self._page.setObjectName("dialPage")
        self._root = QHBoxLayout(self._page)
        self._root.setContentsMargins(22, 16, 22, 16)
        self._root.setSpacing(26)
        outer.addWidget(scrolling(self._page, "dialScroll"), 1)
        # The week strip is how another day is reached, so it is pinned below the scroller rather
        # than left at the bottom of a column. At large text it used to be sliced in half, with the
        # day names off screen entirely.
        self._strip_host = QWidget()
        self._strip_host.setObjectName("dialStrip")
        self._strip = QVBoxLayout(self._strip_host)
        self._strip.setContentsMargins(22, 0, 22, 10)
        outer.addWidget(self._strip_host)

    def shown_day(self, scene: Scene) -> int:
        return self._day if self._day is not None else (scene.today if scene.today is not None else 0)

    def _show_day(self, day: int) -> None:
        scene = self._scene
        if scene is None:
            return
        self._day = None if day == scene.today else day
        self.render(scene, False)

    def render(self, scene: Scene, week_changed: bool) -> None:
        if week_changed:
            self._day = None
        tokens, name = scene.tokens, self.objectName()
        day = self.shown_day(scene)
        is_today = day == scene.today
        span = HOURS.get(scene.options.get("hours", "day"), HOURS["day"])
        small = css(font_size=f"{scene.px(13)}px", letter_spacing="1px")
        self.setStyleSheet(
            base_sheet(name, tokens)
            + rules(
                name,
                {
                    "#dialScroll, #dialPage": css(background=tokens["bg"]),
                    "#dialCard": css(
                        background=tokens["surface"],
                        border=f"1px solid {tokens['line']}",
                        border_radius=f"{scene.px(16)}px",
                    ),
                    "#dialCard QLabel": css(color=tokens["text"]),
                    "#dialCard #dialKicker, #dialCard #dialThen": css(color=tokens["muted"]) + small,
                    "#dialTitle": css(font_size=f"{scene.px(30)}px", font_weight=700),
                    "#dialHeading": css(color=tokens["bg_muted"]) + small,
                    "#dialWaiting": css(color=tokens["bg_ink"]) + small,
                    "#dialMiniName": css(color=tokens["bg_muted"], font_size=f"{scene.px(12)}px"),
                    "QPushButton": css(
                        background="transparent",
                        color=tokens["bg_ink"],
                        border=f"1px solid {tokens['line']}",
                        border_radius=f"{scene.px(22)}px",
                        padding=f"0 {scene.px(18)}px",
                        min_height=f"{scene.px(44)}px",
                        font_size=f"{scene.px(14)}px",
                        font_weight=600,
                    ),
                    "#dialCard QPushButton": css(color=tokens["text"]),
                    'QPushButton[kind="main"]': css(
                        background=tokens["accent"], color=tokens["accent_ink"], border_color=tokens["accent"]
                    ),
                    'QPushButton[kind="row"]': css(
                        background=tokens["surface"],
                        color=tokens["text"],
                        border="none",
                        border_left=f"4px solid {tokens['line']}",
                        border_radius=f"{scene.px(8)}px",
                        text_align="left",
                        padding=f"0 {scene.px(10)}px",
                        min_height=f"{scene.px(38)}px",
                        font_weight=400,
                    ),
                    'QPushButton[kind="row"][state="past"]': css(
                        color=tokens["muted"], text_decoration="line-through"
                    ),
                    'QPushButton[kind="row"][state="now"]': css(
                        border=f"1px solid {tokens['accent']}",
                        border_left=f"4px solid {tokens['accent']}",
                        font_weight=700,
                    ),
                    "QPushButton:focus": css(border=f"2px solid {tokens['accent']}"),
                },
            )
        )
        empty(self._root)
        face = DialFace(day, False, self.hand)
        face.set_day(scene.week.on_day(day), scene.minute if is_today else None, span, tokens)
        face.block_clicked.connect(self.block_activated.emit)
        self._root.addWidget(face, 6)
        side = QVBoxLayout()
        side.setSpacing(scene.px(10))
        side.addWidget(self._card(scene, day, is_today))
        blocks = scene.week.on_day(day)
        if scene.options.get("list") != "hide":
            side.addWidget(
                label(("Today" if is_today else DAY_FULL[day]).upper() + ", HOUR BY HOUR", "dialHeading")
            )
            current = scene.week.day_queue(day, scene.minute).current if is_today else None
            for index, item in enumerate(blocks):
                row = button(
                    f"{clock_label(item.start)}    {item.title}    ·  {length_label(item.minutes)}",
                    f"dialRow{index}",
                    "row",
                )
                past = not item.live or (
                    item.end <= scene.minute if is_today else (scene.today is not None and day < scene.today)
                )
                row.setProperty("state", "now" if item == current else "past" if past else "")
                row.setStyleSheet(f"border-left-color: {mark_of(item.category)};")
                row.clicked.connect(lambda _=False, key=item.block_id: self.block_activated.emit(key))
                side.addWidget(row)
            if not blocks:
                if is_today:
                    heading, title, line = scene.week.leftover_parts(day)
                    words = (
                        f"{title} · {heading}"
                        if scene.week.leftover_kind(day) == "needs_time"
                        else (line or heading)
                    )
                    side.addWidget(label(words, "dialHeading"))
                else:
                    side.addWidget(label("A free day.", "dialHeading"))
        if scene.week.waiting:
            them = "it" if len(scene.week.waiting) == 1 else "them"
            side.addWidget(
                label(
                    f"{plural(len(scene.week.waiting), 'task')} not placed yet."
                    f" Go back to planning to give {them} a time.",
                    "dialWaiting",
                    wrap=True,
                )
            )
        side.addStretch(1)
        self._root.addLayout(side, 5)
        empty(self._strip)
        wanted = scene.options.get("week") != "hide"
        self._strip_host.setVisible(wanted)
        if wanted:
            self._strip.addLayout(self._minis(scene, day, span))

    def _card(self, scene: Scene, day: int, is_today: bool) -> QFrame:
        card = QFrame()
        card.setObjectName("dialCard")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(scene.px(18), scene.px(14), scene.px(18), scene.px(16))
        actions = QHBoxLayout()
        actions.setSpacing(scene.px(8))
        if is_today:
            found = scene.week.day_queue(day, scene.minute)
            item = found.queue[0] if found.queue else None
            if item is None:
                heading, title, _line = scene.week.leftover_parts(day)
                kicker, title = heading.upper(), title
            elif item == found.current:
                kicker, title = (
                    f"NOW · UNTIL {clock_label(item.end)} · "
                    f"{length_label(item.end - scene.minute).upper()} LEFT",
                    item.title,
                )
            else:
                kicker, title = (
                    f"UP NEXT · {clock_label(item.start)} · "
                    f"IN {length_label(item.start - scene.minute).upper()}",
                    item.title,
                )
            inner.addWidget(label(kicker, "dialKicker"))
            inner.addWidget(label(title, "dialTitle", wrap=True))
            if len(found.queue) > 1:
                inner.addWidget(
                    label(
                        f"THEN {found.queue[1].title.upper()} AT {clock_label(found.queue[1].start)}",
                        "dialThen",
                    )
                )
            made = day_buttons(self, scene, item, "dial")
        else:
            work = [item for item in scene.week.on_day(day) if item.work]
            date = scene.week.date_of(day)
            inner.addWidget(
                label(f"{DAY_FULL[day].upper()}, {date.strftime('%B').upper()} {date.day}", "dialKicker")
            )
            inner.addWidget(
                label(
                    planned_line(
                        sum(item.minutes for item in work),
                        sum(item.minutes for item in work if item.done),
                    ),
                    "dialTitle",
                    wrap=True,
                )
            )
            made = []
            if scene.today is not None:
                today = button("Back to today", "dialToday", "main")
                today.clicked.connect(lambda _=False, target=scene.today: self._show_day(target))
                made.append(today)
            else:
                inner.addWidget(
                    label("THIS IS NOT THE CURRENT WEEK, SO THERE IS NO NOW TO SHOW.", "dialThen", wrap=True)
                )
            back = button("Back to planning", "dialBack")
            back.clicked.connect(self.back_requested.emit)
            made.append(back)
        for entry in made:
            actions.addWidget(entry)
        actions.addStretch()
        inner.addLayout(actions)
        return card

    def _minis(self, scene: Scene, day: int, span: tuple[int, int]) -> QHBoxLayout:
        strip = QHBoxLayout()
        strip.setSpacing(scene.px(8))
        for index, name in enumerate(DAYS):
            cell = QVBoxLayout()
            mini = DialFace(index, True)
            mini.setFixedHeight(scene.px(72))
            mini.set_day(scene.week.on_day(index), None, span, scene.tokens, chosen=index == day)
            mini.day_clicked.connect(self._show_day)
            cell.addWidget(mini)
            cell.addWidget(
                label(f"{name} {scene.week.date_of(index).day}", "dialMiniName"),
                0,
                Qt.AlignmentFlag.AlignHCenter,
            )
            strip.addLayout(cell)
        return strip
