"""Today's app's Day and Week, as Daily Scheduler draws them, beside the rail (rail.py).

Week is seven columns on a sheet that open at 48 pixels an hour and scroll, with each day's header
kept at the top: its name, its date (today's in an accent chip), and its hours of homework with the
book, so each still opens its day. Day is the day's agenda, then its hours wide at 96 pixels an hour.
Both zoom, and remember how close they were. Both are painted hours on the one `Hand`, so every
gesture works the same on each.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
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
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from desktop.native import icons
from desktop.native.calendar import CATEGORIES, DAY_FULL, DAYS
from desktop.native.fonts import at_scale, time_font
from desktop.native.hours.canvas import BlockPainter, HoursCanvas
from desktop.native.hours.geometry import FIRST, LAST, Axis, LinearTrack
from desktop.native.hours.hand import Hand
from desktop.native.hours.rail import Colours
from desktop.native.hours.zoom import HoursScroll, Scale, opening_minute
from desktop.native.layouts.base import short_length
from desktop.native.look import category_paint, mix, readable_ink, text_scale
from desktop.native.tokens import SPACING, WEIGHT_STRONG
from desktop.native.weekmodel import (
    HOMEWORK,
    Occurrence,
    WeekModel,
    clock_label,
    length_label,
)

# A Day never goes below 96 pixels an hour, where 15 minutes is 24 pixels. The Week opens at 48, where
# an hour still has edges to resize, and can go further out to see more of the day at once.
DAY_SCALE = Scale("classic.day", (96, 128, 160, 192), 96)
WEEK_SCALE = Scale("classic.week", (32, 48, 64, 96, 128), 48)
DAY_HOUR_PX = DAY_SCALE.default
WEEK_HOUR_PX = WEEK_SCALE.default
# Room above 00:00 and below 24:00, so the labels at either end of the hours are never cut.
PAD = 12
GUTTER = 60
AGENDA_PX = 288
# An empty Saturday or Sunday takes this share of a full day's width, and never less than EMPTY_MIN_PX
# (or the equal share where that is already smaller): a block dropped there still reads, with its
# icon, the first word of its name and its times.
WEEKEND = (5, 6)
EMPTY_SHARE = 0.6
EMPTY_MIN_PX = 96
# How much of the accent the time now's line across the rest of the week takes.
NOW_ACROSS = 0.45


def _hours_height(px_per_hour: int) -> int:
    return round((LAST - FIRST) / 60 * px_per_hour) + 2 * PAD


def _scaled(base: QFont, role: str, look: dict | None, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    # The look's own scale, so a custom look's text size reaches the words painted here too.
    return at_scale(base, role, text_scale(look), weight)


def open_hours(
    scroll: HoursScroll,
    key: object,
    week: WeekModel,
    today: int | None,
    now: int | None,
    day: int | None = None,
) -> None:
    """Hours open at now, in the middle of what shows, so the evening ahead is on screen with the
    day so far (decision 12 of 0.17); a day or week without now opens at its first block."""
    at_now = today is not None and now is not None and day in (None, today)
    scroll.open_at(key, opening_minute(week, today, now, day), None if at_now else 90)


def homework_minutes(week: WeekModel, day: int) -> int:
    return sum(item.minutes for item in week.on_day(day) if item.category == HOMEWORK)


class ClassicPainter(BlockPainter):
    """Today's app's hours on their sheet: the card colour, hour rules and faint day rules, today
    washed, and the time now as a line across the week, strong on today, with its time on a pill in
    the gutter where the hour labels are."""

    now_in_gutter = True

    def background(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, self.c("panel") if "panel" in self.colours else self.c("window"))

    def track(self, painter: QPainter, track: LinearTrack, today: bool) -> None:
        super().track(painter, track, today)
        if not today and self.now_minute is not None and not self.wide:
            faint = self.c("now")
            faint.setAlphaF(NOW_ACROSS)
            at = track.area.top() + track.offset(self.now_minute)
            painter.setPen(QPen(faint, 1))
            painter.drawLine(QPointF(track.area.left(), at), QPointF(track.area.right(), at))

    def now(self, painter: QPainter, track: LinearTrack, minute: int) -> None:
        """A line in the accent across today with a halo in the sheet's colour, so it parts from any
        block it crosses, and a dot at its start on the week."""
        area = track.area
        at = area.top() + track.offset(minute)
        halo = self.c("panel") if "panel" in self.colours else self.c("window")
        start, end = QPointF(area.left() - 1, at), QPointF(area.right(), at)
        painter.setPen(QPen(halo, 5))
        painter.drawLine(start, end)
        painter.setPen(QPen(self.c("now"), 2))
        painter.drawLine(start, end)
        if not self.wide:
            painter.setPen(QPen(halo, 2))
            painter.setBrush(self.c("now"))
            painter.drawEllipse(QPointF(area.left() + 1, at), 5, 5)

    def hour_labels(
        self,
        painter: QPainter,
        track: LinearTrack,
        room: float,
        every: int = 60,
        visible: QRectF | None = None,
    ) -> None:
        super().hour_labels(painter, track, room, every, visible)
        if self.now_minute is None or track.axis is not Axis.DOWN:
            return
        font = time_font(QFont(painter.font()))
        font = at_scale(font, "caption", self.scale(painter.font()), WEIGHT_STRONG)
        metrics = QFontMetricsF(font)
        words = clock_label(self.now_minute)
        width, height = metrics.horizontalAdvance(words) + 10, metrics.height() + 4
        at = track.area.top() + track.offset(self.now_minute)
        pill = QRectF(track.area.left() - 3 - width, at - height / 2, width, height)
        painter.setPen(QPen(self.c("panel") if "panel" in self.colours else self.c("window"), 2))
        painter.setBrush(self.c("now"))
        painter.drawRoundedRect(pill, height / 2, height / 2)
        painter.setPen(QColor(readable_ink(self.colours.get("now", self.colours["accent"]))))
        painter.setFont(font)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, words)


class DayName(QLabel):
    """A day's header above the week: its name and date, today's date in an accent chip, and under
    them its hours of homework with the book. Kept out of the scroll so it stays reachable; a click
    opens the day."""

    clicked = Signal(int)

    def __init__(self, day: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._day = day
        self.name, self.date, self.homework = DAYS[day], "", 0
        self.colours = Colours()
        self.look: dict | None = None
        self.setProperty("today", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText(self.name)

    def show_day(self, name: str, number: str, homework: int, today: bool) -> None:
        self.name, self.date, self.homework = name, number, homework
        self.setText(f"{name} {number}".strip())
        self.setProperty("today", today)
        words = f"{DAY_FULL[self._day]} {number}" + (
            f", {length_label(homework)} of homework" if homework else ""
        )
        self.setAccessibleName(words)
        self.setToolTip(f"Open {DAY_FULL[self._day]}")
        self.update()

    def _fonts(self) -> tuple[QFont, QFont, QFont]:
        body = _scaled(self.font(), "body", self.look)
        strong = _scaled(self.font(), "body", self.look, QFont.Weight.DemiBold)
        small = time_font(_scaled(self.font(), "caption", self.look))
        return body, strong, small

    def _top(self) -> float:
        _body, strong, _small = self._fonts()
        return max(26.0, QFontMetricsF(strong).height() + 6)

    def sizeHint(self) -> QSize:  # noqa: N802
        _body, strong, small = self._fonts()
        wide = QFontMetricsF(strong).horizontalAdvance(f"{self.name} 00") + 2 * SPACING[2] + 12
        return QSize(round(wide), round(self._top() + QFontMetricsF(small).height() + 2 * SPACING[1]))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, self.sizeHint().height())

    def _homework_left(self, icon: int) -> float:
        return SPACING[2] + icon + SPACING[0]

    def _homework_room(self, icon: int) -> float:
        return self.width() - self._homework_left(icon) - SPACING[1]

    def homework_words(self) -> str:
        """The day's homework length as hours and minutes stuck on, so "2h 15m" is never read as 2:15."""
        return short_length(self.homework)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colours = self.colours
        today = bool(self.property("today"))
        body, strong, small = self._fonts()
        top = self._top()
        y = (self.height() - top - QFontMetricsF(small).height()) / 2
        x = float(SPACING[2])
        name_font = strong if today else body
        painter.setFont(name_font)
        painter.setPen(QColor(colours.accent_text if today else colours.muted))
        name_width = QFontMetricsF(name_font).horizontalAdvance(self.name)
        painter.drawText(QRectF(x, y, name_width + 1, top), Qt.AlignmentFlag.AlignVCenter, self.name)
        x += name_width + SPACING[0]
        if self.date:
            painter.setFont(strong)
            date_width = QFontMetricsF(strong).horizontalAdvance(self.date)
            if today:
                chip = QRectF(x, y + (top - 26) / 2 + 1, max(28.0, date_width + 10), 24)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(colours.accent))
                painter.drawRoundedRect(chip, 12, 12)
                painter.setPen(QColor(colours.accent_ink))
                painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, self.date)
            else:
                painter.setPen(QColor(colours.text))
                painter.drawText(QRectF(x, y, date_width + 1, top), Qt.AlignmentFlag.AlignVCenter, self.date)
        if self.homework:
            line = QFontMetricsF(small).height()
            size = round(QFontMetricsF(small).ascent())
            below = y + top
            painter.drawPixmap(
                QPointF(SPACING[2], below + (line - size) / 2),
                icons.pixmap("book-open", colours.homework, size, self.devicePixelRatioF()),
            )
            painter.setFont(small)
            painter.setPen(QColor(colours.muted))
            painter.drawText(
                QRectF(self._homework_left(size), below, self._homework_room(size), line),
                Qt.AlignmentFlag.AlignVCenter,
                self.homework_words(),
            )
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._day)
            event.accept()
            return
        super().mousePressEvent(event)


def column_widths(total: float, empty: frozenset[int]) -> list[float]:
    """The seven days' widths over `total` pixels: equal, except that an empty weekend day is narrower
    (see EMPTY_SHARE) and the days with something in them share what that leaves, equally."""
    share = total / 7
    quiet = [day for day in WEEKEND if day in empty]
    if not quiet:
        return [share] * 7
    narrow = min(share, max(EMPTY_MIN_PX, share * EMPTY_SHARE))
    full = (total - narrow * len(quiet)) / (7 - len(quiet))
    return [narrow if day in quiet else full for day in range(7)]


def _empty_days(week: WeekModel) -> frozenset[int]:
    return frozenset(day for day in range(7) if not week.on_day(day))


class ClassicWeek(QFrame):
    """The week as a scrollable sheet, day headers fixed at the top, still drags."""

    day_opened = Signal(int)

    def __init__(self, hand: Hand, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("weekTable")
        self.week_start = ""
        self._shown: tuple[WeekModel, int | None, int | None] | None = None
        self._empty: frozenset[int] = frozenset()
        self.hours = HoursCanvas(
            hand, ClassicPainter({}), self._seven_columns, gutter=GUTTER, names=self._name
        )
        self.hours.setObjectName("weekHours")
        self.hours.day_opened.connect(self.day_opened.emit)
        self.scroll = HoursScroll(self.hours, WEEK_SCALE, _hours_height, name="week", gutter=GUTTER)
        names = QWidget()
        names.setObjectName("weekDayNames")
        row = QHBoxLayout(names)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._names_row = row
        self._name_labels: list[DayName] = []
        for day in range(7):
            name = DayName(day)
            name.setObjectName(f"weekDayName{day}")
            name.clicked.connect(self.day_opened.emit)
            row.addWidget(name, 1)
            self._name_labels.append(name)
        self.scroll.set_header(names)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        box.addWidget(self.scroll, 1)

    def _seven_columns(self, area: QRectF) -> list[LinearTrack]:
        widths = column_widths(area.width(), self._empty)
        left = area.left()
        tracks = []
        for day, width in enumerate(widths):
            tracks.append(LinearTrack(day, QRectF(left, area.top() + PAD, width, area.height() - 2 * PAD)))
            left += width
        # The names above keep to their columns: a layout's stretch is the ratio of the widths.
        for day, width in enumerate(widths):
            self._names_row.setStretch(day, max(1, round(width * 10)))
        return tracks

    def set_narrow(self, narrow: bool) -> None:
        """Short of room, blocks give their names the room their times took."""
        if narrow != self.hours.short_words:
            self.hours.short_words = narrow
            self.hours.update()

    def _name(self, day: int) -> str:
        if not self.week_start:
            return DAYS[day]
        return f"{DAYS[day]} {(date.fromisoformat(self.week_start) + timedelta(days=day)).day}"

    def set_look(self, look: dict | None, palette: dict) -> None:
        self.hours.set_painter(ClassicPainter(palette, look))
        colours = Colours.of(palette)
        for label in self._name_labels:
            label.colours, label.look = colours, look
            label.updateGeometry()
            label.update()

    def set_week(self, week: WeekModel, today: int | None, now_min: int | None) -> None:
        self.week_start = week.week_start
        empty = _empty_days(week)
        if empty != self._empty:
            # Laid out for the new widths before the blocks arrive, so none slides for a change of width.
            self._empty = empty
            self.hours.relayout()
        self.hours.set_week(week.occurrences, today, now_min)
        for day, label in enumerate(self._name_labels):
            label.show_day(DAYS[day], str(week.date_of(day).day), homework_minutes(week, day), day == today)
        self._shown = (week, today, now_min)
        open_hours(self.scroll, week.week_start, week, today, now_min)

    def open_again(self) -> None:
        """Open at now again, as on the first show: the week is on screen once more."""
        self.scroll.forget()
        if self._shown is not None:
            open_hours(self.scroll, self.week_start, *self._shown)

    def hours_surfaces(self) -> list[HoursCanvas]:
        return [self.hours]


@dataclass(frozen=True)
class Share:
    """One kind of thing in a day's summary: its name, its mark, and how long."""

    name: str
    category: str
    minutes: int


def day_shares(week: WeekModel, day: int) -> list[Share]:
    totals: dict[str, Share] = {}
    for item in week.on_day(day):
        name = CATEGORIES.get(item.category, {}).get("label") or ("Homework" if item.work else "Other")
        was = totals.get(name)
        totals[name] = Share(name, item.category, (was.minutes if was else 0) + item.minutes)
    return list(totals.values())


class DaySummary(QWidget):
    """What a day holds, as a thin stacked bar in the categories' marks and a row each, with a dot, or
    the book for homework (decision 16 of 0.17)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("daySummary")
        self.shares: list[Share] = []
        self.palette_: dict = {}
        self.look: dict | None = None

    def text(self) -> str:
        """The summary in words, a line each, as a screen reader hears it."""
        if not self.shares:
            return "Nothing planned."
        return "\n".join(f"{share.name}: {length_label(share.minutes)}" for share in self.shares)

    def set_shares(self, shares: list[Share]) -> None:
        self.shares = shares
        self.setAccessibleName("Summary")
        self.setAccessibleDescription(self.text())
        self.updateGeometry()
        self.update()

    def _row(self) -> float:
        return max(28.0, QFontMetricsF(_scaled(self.font(), "body", self.look)).height() + 8)

    def sizeHint(self) -> QSize:  # noqa: N802
        rows = max(len(self.shares), 1)
        return QSize(AGENDA_PX - 2 * SPACING[3], round(8 + SPACING[2] + rows * self._row()))

    def _mark(self, share: Share) -> QColor:
        mark = category_paint(share.category, self.palette_)[1] if self.palette_ else None
        return QColor(mark or self.palette_.get("muted", "#5b6474"))

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colours = Colours.of(self.palette_) if self.palette_ else Colours()
        body = _scaled(self.font(), "body", self.look)
        small = time_font(_scaled(self.font(), "caption", self.look))
        if not self.shares:
            painter.setFont(body)
            painter.setPen(QColor(colours.muted))
            painter.drawText(
                QRectF(self.rect()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self.text()
            )
            painter.end()
            return
        total = sum(share.minutes for share in self.shares) or 1
        x, gap = 0.0, 2.0
        room = self.width() - gap * (len(self.shares) - 1)
        for share in self.shares:
            wide = room * share.minutes / total
            painter.fillRect(QRectF(x, 0, max(wide, 1.0), 8), self._mark(share))
            x += wide + gap
        top = 8 + SPACING[2]
        row = self._row()
        ratio = self.devicePixelRatioF()
        for share in self.shares:
            middle = top + row / 2
            if share.category == HOMEWORK:
                painter.drawPixmap(
                    QPointF(0, middle - 7), icons.pixmap("book-open", colours.homework, 14, ratio)
                )
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._mark(share))
                painter.drawEllipse(QPointF(7, middle), 4, 4)
            painter.setFont(body)
            painter.setPen(QColor(colours.text))
            painter.drawText(
                QRectF(22, top, self.width() - 22, row), Qt.AlignmentFlag.AlignVCenter, share.name
            )
            painter.setFont(small)
            painter.setPen(QColor(colours.muted))
            painter.drawText(
                QRectF(0, top, self.width(), row),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                length_label(share.minutes),
            )
            top += row
        painter.end()


@dataclass(frozen=True)
class Row:
    """A block in the day's agenda and where it is drawn."""

    box: QRectF
    item: Occurrence


class AgendaList(QWidget):
    """The day in order: each thing's start and end, its name with its category's edge, how long, and
    a click opens a thing and a right-click shows its menu."""

    def __init__(self, hand: Hand, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("classicAgendaList")
        self.hand = hand
        self.setMouseTracking(True)
        self.items: tuple[Occurrence, ...] = ()
        self.now: int | None = None
        self.palette_: dict = {}
        self.look: dict | None = None
        self._hover: str | None = None
        self.rows: list[Row] = []

    def set_items(self, items: tuple[Occurrence, ...], now: int | None) -> None:
        self.items, self.now = items, now
        self._lay_out()

    def _fonts(self) -> tuple[QFont, QFont, QFont]:
        title = _scaled(self.font(), "body", self.look, QFont.Weight.DemiBold)
        small = time_font(_scaled(self.font(), "caption", self.look))
        strong = time_font(_scaled(self.font(), "caption", self.look, QFont.Weight.DemiBold))
        return title, small, strong

    def _lay_out(self) -> None:
        title, small, _strong = self._fonts()
        tall = QFontMetricsF(title).lineSpacing() + QFontMetricsF(small).lineSpacing() + 2 * SPACING[1]
        rows: list[Row] = []
        top = 0.0
        for item in self.items:
            rows.append(Row(QRectF(0, top, self.width(), tall), item))
            top += tall
        self.rows = rows
        self.setMinimumHeight(round(top))
        self.updateGeometry()
        self.update()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._lay_out()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(AGENDA_PX, self.minimumHeight())

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette_
        colours = Colours.of(palette) if palette else Colours()
        title_font, small, strong = self._fonts()
        column = max(
            [44.0, *(QFontMetricsF(font).horizontalAdvance(clock_label(minute)) + 2
              for row in self.rows
              for font, minute in ((strong, row.item.start), (small, row.item.end)))],
        )
        body_left = column + SPACING[2]
        ratio = self.devicePixelRatioF()
        for row in self.rows:
            box = row.box
            item = row.item
            past = self.now is not None and item.end <= self.now
            if item.block_id == self._hover:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(mix(colours.text, colours.panel, 0.05)))
                painter.drawRoundedRect(box, 6, 6)
            inside = box.adjusted(0, SPACING[1], 0, -SPACING[1])
            line = QFontMetricsF(small).lineSpacing()
            painter.setFont(strong)
            painter.setPen(QColor(colours.muted if past else colours.text))
            painter.drawText(
                QRectF(0, inside.top() + 2, column, line), Qt.AlignmentFlag.AlignLeft, clock_label(item.start)
            )
            painter.setFont(small)
            painter.setPen(QColor(colours.muted))
            painter.drawText(
                QRectF(0, inside.top() + 2 + line, column, line),
                Qt.AlignmentFlag.AlignLeft,
                clock_label(item.end),
            )
            mark = (
                QColor(category_paint(item.category, palette)[1] or colours.muted)
                if palette
                else QColor(colours.muted)
            )
            if past:
                mark.setAlphaF(0.45)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(mark)
            painter.drawRoundedRect(QRectF(body_left, inside.top() + 2, 3, inside.height() - 4), 1.5, 1.5)
            left = body_left + 3 + SPACING[2]
            title_line = QFontMetricsF(title_font).lineSpacing()
            if item.category == HOMEWORK:
                size = 14
                painter.drawPixmap(
                    QPointF(left, inside.top() + (title_line - size) / 2),
                    icons.pixmap("book-open", colours.homework, size, ratio),
                )
                left += size + SPACING[1]
            painter.setFont(title_font)
            painter.setPen(QColor(colours.muted if past else colours.text))
            name = QFontMetricsF(title_font).elidedText(
                item.title, Qt.TextElideMode.ElideRight, box.right() - left
            )
            painter.drawText(
                QRectF(left, inside.top(), box.right() - left, title_line), Qt.AlignmentFlag.AlignLeft, name
            )
            sub = length_label(item.minutes)
            if item.done:
                sub += " · Finished"
            elif item.missed:
                sub += " · Missed"
            painter.setFont(small)
            painter.setPen(QColor(colours.muted))
            sub_left = body_left + 3 + SPACING[2]
            painter.drawText(
                QRectF(sub_left, inside.top() + title_line, box.width(), line),
                Qt.AlignmentFlag.AlignLeft,
                sub,
            )
            if item.pinned and not item.done:
                at = sub_left + QFontMetricsF(small).horizontalAdvance(sub) + SPACING[1]
                size = round(QFontMetricsF(small).ascent())
                painter.drawPixmap(
                    QPointF(at, inside.top() + title_line + (line - size) / 2),
                    icons.pixmap("pin", colours.muted, size, ratio),
                )
                painter.drawText(
                    QRectF(at + size + 3, inside.top() + title_line, box.width(), line),
                    Qt.AlignmentFlag.AlignLeft,
                    "Pinned",
                )
        painter.end()

    def _item_at(self, point: QPointF) -> Occurrence | None:
        return next((row.item for row in self.rows if row.box.contains(point)), None)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        item = self._item_at(event.position())
        hover = item.block_id if item is not None else None
        self.setCursor(Qt.CursorShape.PointingHandCursor if item is not None else Qt.CursorShape.ArrowCursor)
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        item = self._item_at(event.position())
        if event.button() == Qt.MouseButton.LeftButton and item is not None:
            self.hand.open(item.block_id)
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        item = self._item_at(QPointF(event.pos()))
        if item is None or self.hand.busy:
            event.ignore()
            return
        event.accept()
        self.hand.ask_menu(item.block_id, item.day, event.globalPos())


class ClassicAgenda(QFrame):
    """Day's left side on the sheet: the day's name, how much it holds, the agenda, and the summary."""

    def __init__(self, hand: Hand, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("classicAgenda")
        self.setFixedWidth(AGENDA_PX)
        box = QVBoxLayout(self)
        box.setContentsMargins(SPACING[3], SPACING[3], SPACING[3], SPACING[3])
        box.setSpacing(2)
        self.heading = QLabel()
        self.heading.setObjectName("classicAgendaDay")
        self.heading.setProperty("railHeading", True)
        self.sub = QLabel()
        self.sub.setObjectName("classicAgendaSub")
        self.sub.setProperty("muted", True)
        box.addWidget(self.heading)
        box.addWidget(self.sub)
        box.addSpacing(SPACING[3])
        self.list = AgendaList(hand)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("classicAgendaScroll")
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.list)
        box.addWidget(self.scroll, 1)
        self.foot = QFrame()
        self.foot.setObjectName("classicAgendaFoot")
        foot = QVBoxLayout(self.foot)
        foot.setContentsMargins(0, SPACING[2], 0, 0)
        foot.setSpacing(SPACING[1])
        summary_label = QLabel("Summary")
        summary_label.setObjectName("daySummaryLabel")
        summary_label.setProperty("railLabel", True)
        foot.addWidget(summary_label)
        self.summary = DaySummary()
        foot.addWidget(self.summary)
        box.addWidget(self.foot)

    def set_look(self, look: dict | None, palette: dict) -> None:
        for widget in (self.list, self.summary):
            widget.palette_, widget.look = palette, look
            widget.update()
        self.list._lay_out()

    def set_day(self, week: WeekModel, day: int, today: int | None, now_min: int | None) -> None:
        items = week.on_day(day)
        self.heading.setText("Agenda")
        things = f"{len(items)} thing{'s' if len(items) != 1 else ''}"
        total = sum(item.minutes for item in items)
        self.sub.setText(f"{things} · {length_label(total)}" if items else "Nothing planned")
        self.list.set_items(items, now_min if today == day else None)
        self.summary.set_shares(day_shares(week, day))


class ClassicDay(QFrame):
    """One day: its agenda, then its hours wide, on the sheet."""

    def __init__(self, hand: Hand, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dayView")
        self.hand = hand
        self.day = 0
        self._shown: tuple[WeekModel, int | None, int | None] | None = None
        self.agenda = ClassicAgenda(hand)
        self.summary = self.agenda.summary
        self.hours = HoursCanvas(hand, ClassicPainter({}, wide=True), self._one_column, gutter=GUTTER)
        self.hours.setObjectName("dayHours")
        self.scroll = HoursScroll(self.hours, DAY_SCALE, _hours_height, name="day", gutter=GUTTER)
        names = QWidget()
        names.setObjectName("dayNames")
        row = QHBoxLayout(names)
        row.setContentsMargins(0, 0, 0, 0)
        self.name = DayName(0)
        self.name.setObjectName("dayName")
        self.name.setCursor(Qt.CursorShape.ArrowCursor)
        row.addWidget(self.name, 1)
        self.scroll.set_header(names)
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        box.addWidget(self.agenda)
        box.addWidget(self.scroll, 1)

    def _one_column(self, area: QRectF) -> list[LinearTrack]:
        return [LinearTrack(self.day, area.adjusted(0, PAD, -PAD, -PAD))]

    def set_look(self, look: dict | None, palette: dict) -> None:
        self.hours.set_painter(ClassicPainter(palette, look, wide=True))
        self.agenda.set_look(look, palette)
        self.name.colours, self.name.look = Colours.of(palette), look
        self.name.updateGeometry()

    def set_day(self, week: WeekModel, day: int, today: int | None, now_min: int | None) -> None:
        changed_day = day != self.day
        self.day = day
        if changed_day:
            self.hours.relayout()
        self.hours.set_week(week.on_day(day), today, now_min)
        self.agenda.set_day(week, day, today, now_min)
        self.name.show_day("Hours", "", homework_minutes(week, day), day == today)
        self.name.setAccessibleName("Hours")
        self.name.setToolTip("")
        self._shown = (week, today, now_min)
        open_hours(self.scroll, (week.week_start, day), week, today, now_min, day)

    def open_again(self) -> None:
        """Open at now again, as on the first show: the day is on screen once more."""
        self.scroll.forget()
        if self._shown is not None:
            week, today, now_min = self._shown
            open_hours(self.scroll, (week.week_start, self.day), week, today, now_min, self.day)

    def hours_surfaces(self) -> list[HoursCanvas]:
        return [self.hours]
