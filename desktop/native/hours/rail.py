"""Today's app's rail: the slim column left of Day and Week (0.17's pick for Today's app, B).

From the top: a running focus timer, when there is one; a mini month with the week on screen banded,
today in the accent and a dot on each day homework is due; what is next, and what follows it; the
homework not placed yet, as chips to drag onto the hours; and the homework to start a focus timer
on, in time order. The month folds away from its header, and the choice is kept on this computer.
On a window too narrow for a rail it folds into one line above the hours, with the chips after it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from PySide6.QtCore import QEvent, QModelIndex, QPersistentModelIndex, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from desktop.native import icons
from desktop.native.calendar import DAYS
from desktop.native.fonts import at_scale, time_font, weighted
from desktop.native.hours.chips import TrayChip
from desktop.native.hours.hand import Hand
from desktop.native.look import category_paint, mix, text_scale
from desktop.native.tokens import RADIUS_CONTROL, SPACING, WEIGHT_STRONG
from desktop.native.weekmodel import (
    HOMEWORK,
    Occurrence,
    Waiting,
    WeekModel,
    clock_label,
    hhmm_text,
    length_label,
    minute_of,
    time_format,
)
from desktop.native.widgets import FlowLayout, overlay_scroll_bars

RAIL_PX = 280
# The most rows the focus list shows before it scrolls, so a long one never pushes the rest away.
FOCUS_ROWS = 6
LETTERS = ("M", "T", "W", "T", "F", "S", "S")
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
HIDE_MONTH = "Hide the month"
SHOW_MONTH = "Show the month"
# 8 at the sides: the window's own 9-pixel margin puts the rail's words 17 from its edge, where the
# mock-up has them at 16, and a focus row or a chip has the room to say "Chem lab report" whole.
PAD = SPACING[1]
# The gaps that keep a homework title from the book before it and the length or day after it. They are
# small so that a title as long as "Math worksheet" is not cut on a row with room for it.
BOOK_GAP = 6
TITLE_GAP = SPACING[0]
# Where a chip's title starts: past its edge, the book and the gaps between.
CHIP_TITLE_LEFT = SPACING[1] + 3 + SPACING[1] + 16 + BOOK_GAP


def label(words: str, name: str, *, kind: str = "railLabel") -> QLabel:
    made = QLabel(words)
    made.setObjectName(name)
    made.setProperty(kind, True)
    return made


def icon_button(name: str, icon: str, tip: str) -> QPushButton:
    """A small square button showing a Lucide icon, for the rail's headers."""
    made = QPushButton()
    made.setObjectName(name)
    made.setProperty("railIcon", True)
    made.setToolTip(tip)
    made.setAccessibleName(tip)
    made.setFixedSize(26, 26)
    made.setIconSize(QSize(16, 16))
    made.setProperty("icon_name", icon)
    made.setCursor(Qt.CursorShape.PointingHandCursor)
    return made


def _scaled(base: QFont, role: str, look: dict | None, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    # The look's own scale, so a custom look's text size reaches the words painted here too.
    return at_scale(base, role, text_scale(look), weight)


@dataclass(frozen=True)
class Colours:
    """What the rail paints with, from the look's palette."""

    text: str = "#111827"
    muted: str = "#5b6474"
    panel: str = "#ffffff"
    window: str = "#f7f8fa"
    hairline: str = "#e4e7ec"
    accent: str = "#3d6fc4"
    accent_text: str = "#3d6fc4"
    accent_ink: str = "#ffffff"
    homework: str = "#831a1d"
    contrast: bool = False

    @classmethod
    def of(cls, palette: dict) -> Colours:
        return cls(
            text=palette["text"],
            muted=palette["muted"],
            panel=palette["panel"],
            window=palette["window"],
            hairline=palette["hairline"],
            accent=palette["accent"],
            accent_text=palette.get("accent_text", palette["accent"]),
            accent_ink=palette["accent_ink"],
            homework=category_paint(HOMEWORK, palette)[1] or palette["text"],
            contrast=palette.get("family") == "contrast",
        )


class MiniMonth(QWidget):
    """A month of dates from Monday, painted: the week on screen banded, today in the accent, a dot
    under each date homework is due, the dates of other months dimmed. A click on a date asks for it."""

    date_chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("railMonthDates")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.colours = Colours()
        self.look: dict | None = None
        self.month = date.today().replace(day=1)
        self.week_start = ""
        self.today = date.today()
        self.due: frozenset[str] = frozenset()

    def dates(self) -> list[date]:
        first = self.month - timedelta(days=self.month.weekday())
        last_day = (self.month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        end = last_day + timedelta(days=6 - last_day.weekday())
        return [first + timedelta(days=at) for at in range((end - first).days + 1)]

    def row_height(self) -> float:
        return max(28.0, QFontMetricsF(self._font()).height() + 12)

    def _font(self, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
        return time_font(_scaled(self.font(), "caption", self.look, weight))

    def sizeHint(self) -> QSize:  # noqa: N802
        rows = len(self.dates()) // 7 + 1
        return QSize(RAIL_PX - 2 * PAD, round(self.row_height() * rows))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(7 * 26, self.sizeHint().height())

    def cell(self, index: int) -> QRectF:
        """Where a date is, `index` into `dates()`, under the row of weekday letters."""
        wide = self.width() / 7
        row, column = divmod(index, 7)
        return QRectF(column * wide, (row + 1) * self.row_height(), wide, self.row_height())

    def date_point(self, iso: str) -> QPointF:
        at = [day.isoformat() for day in self.dates()].index(iso)
        return self.cell(at).center()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colours = self.colours
        tall = self.row_height()
        painter.setFont(self._font())
        painter.setPen(QColor(colours.muted))
        wide = self.width() / 7
        for column, letter in enumerate(LETTERS):
            painter.drawText(QRectF(column * wide, 0, wide, tall), Qt.AlignmentFlag.AlignCenter, letter)
        days = self.dates()
        shown_week = date.fromisoformat(self.week_start) if self.week_start else None
        for row in range(len(days) // 7):
            if shown_week is not None and days[row * 7] == shown_week:
                band = QRectF(0, (row + 1) * tall + 1, self.width(), tall - 2)
                if colours.contrast:
                    painter.setPen(QPen(QColor(colours.accent), 1))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(mix(colours.accent, colours.window, 0.12)))
                painter.drawRoundedRect(
                    band.adjusted(0.5, 0.5, -0.5, -0.5), band.height() / 2, band.height() / 2
                )
        spot = min(26.0, tall - 2)
        for index, day in enumerate(days):
            box = self.cell(index)
            circle = QRectF(box.center().x() - spot / 2, box.center().y() - spot / 2, spot, spot)
            today = day == self.today
            outside = day.month != self.month.month
            if today:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(colours.accent))
                painter.drawEllipse(circle)
                painter.setFont(self._font(QFont.Weight.DemiBold))
                painter.setPen(QColor(colours.accent_ink))
            else:
                painter.setFont(self._font())
                ink = QColor(colours.muted if outside else colours.text)
                if outside:
                    ink.setAlphaF(0.6)
                painter.setPen(ink)
            painter.drawText(circle, Qt.AlignmentFlag.AlignCenter, str(day.day))
            if day.isoformat() in self.due and not outside:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(colours.accent_ink if today else colours.homework))
                painter.drawEllipse(QPointF(circle.center().x(), circle.bottom() - 3.5), 2, 2)
        painter.end()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        for index, day in enumerate(self.dates()):
            if self.cell(index).contains(event.position()):
                self.date_chosen.emit(day.isoformat())
                return


class MonthCard(QWidget):
    """The mini month with its header: the month's name, arrows to page it, and the fold."""

    date_chosen = Signal(str)
    hide_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("railMonth")
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(0)
        self.title = label("", "railMonthTitle", kind="railMonthTitle")
        head.addWidget(self.title, 1)
        self.back = icon_button("railMonthBack", "chevron-left", "Previous month")
        self.on = icon_button("railMonthOn", "chevron-right", "Next month")
        self.fold = icon_button("railMonthHide", "chevron-up", HIDE_MONTH)
        for button in (self.back, self.on, self.fold):
            head.addWidget(button)
        box.addLayout(head)
        self.dates = MiniMonth()
        box.addWidget(self.dates)
        self.back.clicked.connect(lambda: self._page(-1))
        self.on.clicked.connect(lambda: self._page(1))
        self.fold.clicked.connect(self.hide_requested.emit)
        self.dates.date_chosen.connect(self.date_chosen.emit)
        self._anchor: tuple[str, str | None] | None = None

    def _page(self, by: int) -> None:
        month = self.dates.month
        index = month.year * 12 + month.month - 1 + by
        self.dates.month = date(index // 12, index % 12 + 1, 1)
        self._say()

    def _say(self) -> None:
        month = self.dates.month
        self.title.setText(f"{MONTHS[month.month - 1]} {month.year}")
        self.dates.updateGeometry()
        self.dates.update()

    def show_week(self, week_start: str, today: date, due: frozenset[str]) -> None:
        """The month of the week on screen, unless the student has paged it and the week is the same."""
        dates = self.dates
        first = date.fromisoformat(week_start)
        in_week = first <= today <= first + timedelta(days=6)
        key = (week_start, today.isoformat()[:7] if in_week else None)
        if key != self._anchor:
            self._anchor = key
            anchor = today if in_week else first + timedelta(days=3)
            dates.month = anchor.replace(day=1)
        dates.week_start, dates.today, dates.due = week_start, today, due
        self._say()


class EdgeCard(QFrame):
    """A card with a 3-pixel edge down its left side in a category's mark, as the week's blocks have."""

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self.edge = QColor("#000000")

    def set_edge(self, colour: str) -> None:
        self.edge = QColor(colour)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.edge)
        painter.drawRoundedRect(QRectF(0, 0, 3, self.height()), 1.5, 1.5)
        painter.end()


class NextCard(QWidget):
    """What is on now or next, when, and what follows it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("railNext")
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(SPACING[0])
        self.head = QHBoxLayout()
        self.head.setContentsMargins(0, 0, 0, 0)
        self.label = label("Next", "railNextLabel")
        self.head.addWidget(self.label, 1)
        box.addLayout(self.head)
        self.card = EdgeCard("railNextCard")
        inside = QVBoxLayout(self.card)
        inside.setContentsMargins(3 + SPACING[2], 2, 0, 2)
        inside.setSpacing(2)
        self.title = QLabel()
        self.title.setObjectName("railNextTitle")
        self.title.setWordWrap(True)
        self.when = QLabel()
        self.when.setObjectName("railNextWhen")
        self.when.setWordWrap(True)
        self.when.setFont(time_font(self.when.font()))
        self.then = QLabel()
        self.then.setObjectName("railNextThen")
        self.then.setWordWrap(True)
        for widget in (self.title, self.when, self.then):
            inside.addWidget(widget)
        box.addWidget(self.card)
        self.shown: tuple[str, str, str, str] = ("", "", "", "")

    def show_next(self, week: WeekModel | None, today: int | None, minute: int | None) -> bool:
        """Whether there is anything to say: nothing now or later today, or not this week, says nothing."""
        said = next_words(week, today, minute)
        if said != self.shown:
            self.shown = said
            heading, title, when, then = said
            self.label.setText(heading)
            self.title.setText(title)
            self.when.setText(when)
            self.then.setText(then)
            self.then.setVisible(bool(then))
        return bool(said[1])


def next_words(week: WeekModel | None, today: int | None, minute: int | None) -> tuple[str, str, str, str]:
    """The Next card's words: its label, what, when, and what follows. "Next", "Soccer practice",
    "16:00 · in 20 min", "Then Dinner at 18:30"; or "Now", "Dinner", "until 19:00 · 20 min left"."""
    if week is None or today is None or minute is None:
        return "", "", "", ""
    queue = week.day_queue(today, minute)
    if not queue.queue:
        return "", "", "", ""
    first = queue.queue[0]
    after = queue.queue[1] if len(queue.queue) > 1 else None
    then = f"Then {after.title} at {clock_label(after.start)}" if after is not None else ""
    if queue.current is first:
        return (
            "Now",
            first.title,
            f"until {clock_label(first.end)} · {length_label(first.end - minute)} left",
            then,
        )
    return "Next", first.title, f"{clock_label(first.start)} · in {length_label(first.start - minute)}", then


def next_item(week: WeekModel | None, today: int | None, minute: int | None) -> Occurrence | None:
    if week is None or today is None or minute is None:
        return None
    queue = week.day_queue(today, minute).queue
    return queue[0] if queue else None


class RailChip(TrayChip):
    """Homework not placed yet, as the rail draws it: a straight edge in homework's colour, the book,
    the title, and the length at the right. Only the title gives way when room is short."""

    def __init__(self, hand: Hand, waiting: Waiting, parent: QWidget | None = None) -> None:
        super().__init__(hand, waiting, parent)
        self.setProperty("railChip", True)
        self.length = length_label(waiting.minutes)
        self.colours = Colours()
        self.look: dict | None = None
        self.setText(waiting.title)
        self.setMouseTracking(True)
        # A long title shortens; it never widens the rail.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def _fit(self) -> None:
        # Painted whole each time, the title shortened in the paint.
        return

    def _fonts(self) -> tuple[QFont, QFont]:
        return _scaled(self.font(), "body", self.look), time_font(_scaled(self.font(), "caption", self.look))

    def sizeHint(self) -> QSize:  # noqa: N802
        body, small = self._fonts()
        tall = max(QFontMetricsF(body).height(), QFontMetricsF(small).height()) + 10
        wide = 3 + 2 * SPACING[1] + BOOK_GAP + 16 + QFontMetricsF(body).horizontalAdvance(self._title)
        return QSize(round(wide + QFontMetricsF(small).horizontalAdvance(self.length)), round(max(30, tall)))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(80, self.sizeHint().height())

    def shown_title(self) -> str:
        """The title as it fits beside the book and the length."""
        body, small = self._fonts()
        length = QFontMetricsF(small).horizontalAdvance(self.length)
        room = self.width() - CHIP_TITLE_LEFT - TITLE_GAP - length - SPACING[1]
        return QFontMetricsF(body).elidedText(self._title, Qt.TextElideMode.ElideRight, max(room, 0))

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colours = self.colours
        box = QRectF(self.rect())
        if self.underMouse() or self.hasFocus():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(mix(colours.text, colours.window, 0.06)))
            painter.drawRoundedRect(box, RADIUS_CONTROL, RADIUS_CONTROL)
        if self.hasFocus():
            painter.setPen(QPen(QColor(colours.accent), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box.adjusted(1, 1, -1, -1), RADIUS_CONTROL, RADIUS_CONTROL)
        left = SPACING[1]
        painter.fillRect(QRectF(left, 8, 3, max(0.0, box.height() - 16)), QColor(colours.homework))
        body, small = self._fonts()
        at = left + 3 + SPACING[1]
        ratio = self.devicePixelRatioF()
        painter.drawPixmap(
            QPointF(at, (box.height() - 16) / 2), icons.pixmap("book-open", colours.homework, 16, ratio)
        )
        at += 16 + BOOK_GAP
        length_room = QFontMetricsF(small).horizontalAdvance(self.length)
        painter.setFont(small)
        painter.setPen(QColor(colours.muted))
        right = box.right() - SPACING[1]
        painter.drawText(
            QRectF(right - length_room - 1, 0, length_room + 1, box.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self.length,
        )
        painter.setFont(body)
        painter.setPen(QColor(colours.text))
        painter.drawText(
            QRectF(at, 0, max(0.0, right - length_room - TITLE_GAP - at), box.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.shown_title(),
        )
        painter.end()

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        super().leaveEvent(event)
        self.update()


class FocusRows(QStyledItemDelegate):
    """A focus list row: the book, the title, and when at the right, today's in the text colour."""

    def __init__(self, rail: Rail, view: QListWidget) -> None:
        # Owned by its list, as Ctrl+K's rows are: a list does not own its delegate, and one freed
        # before its list left the list's destructor disconnecting from nothing.
        super().__init__(view)
        self.rail = rail

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        body, _small = self.rail.fonts()
        return QSize(option.rect.width(), round(max(30.0, QFontMetricsF(body).height() + 10)))

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        colours = self.rail.colours
        body, small = self.rail.fonts()
        box = QRectF(option.rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        state = option.state
        if state & QStyle.StateFlag.State_MouseOver or state & QStyle.StateFlag.State_Selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(mix(colours.text, colours.window, 0.06)))
            painter.drawRoundedRect(box, RADIUS_CONTROL, RADIUS_CONTROL)
        at = box.left() + SPACING[1]
        painter.drawPixmap(
            QPointF(at, box.top() + (box.height() - 16) / 2),
            icons.pixmap("book-open", colours.homework, 16, painter.device().devicePixelRatioF()),
        )
        at += 16 + BOOK_GAP
        when = str(index.data(Qt.ItemDataRole.ToolTipRole) or "")
        today = bool(index.data(Qt.ItemDataRole.UserRole + 1))
        timing = weighted(small, WEIGHT_STRONG) if today else QFont(small)
        width = QFontMetricsF(timing).horizontalAdvance(when)
        right = box.right() - SPACING[1]
        painter.setFont(timing)
        painter.setPen(QColor(colours.text if today else colours.muted))
        painter.drawText(
            QRectF(right - width - 1, box.top(), width + 1, box.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            when,
        )
        painter.setFont(body)
        painter.setPen(QColor(colours.text))
        room = max(0.0, right - width - TITLE_GAP - at)
        title = QFontMetricsF(body).elidedText(str(index.data()), Qt.TextElideMode.ElideRight, room)
        painter.drawText(
            QRectF(at, box.top(), room, box.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )
        painter.restore()


def focus_when(item: dict, today: int | None) -> str:
    """When a focus row's homework is: "Today 19:00", "Mon 20:00"."""
    day = item.get("day")
    start = hhmm_text(item["start"]) if item.get("start") else ""
    name = "Today" if day is not None and day == today else (DAYS[day] if isinstance(day, int) else "")
    return f"{name} {start}".strip()


class Rail(QFrame):
    """The column left of Day and Week. See the module's docstring."""

    # Homework in the focus list was chosen: its block and its day.
    focus_requested = Signal(str, object)
    # A date in the mini month was clicked.
    date_chosen = Signal(str)
    # The month was folded away (False) or shown again (True), to be kept on this computer.
    month_shown_changed = Signal(bool)

    def __init__(self, hand: Hand, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rail")
        self.hand = hand
        self.folded = False
        self.month_shown = True
        self.colours = Colours()
        self.look: dict | None = None
        self._palette: dict = {}
        self._week: WeekModel | None = None
        self._today: int | None = None
        self._minute: int | None = None
        self._tasks: tuple = ()
        self._waiting: tuple[Waiting, ...] = ()
        self._chips: list[RailChip] = []
        self._due: frozenset[str] = frozenset()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # Wide: the sections, scrolling if a short window has no room for them all, so the rail never
        # makes the window taller than the screen and cuts the hours' last label.
        self.scroll = QScrollArea()
        self.scroll.setObjectName("railScroll")
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        overlay_scroll_bars(self.scroll)
        self.body = QWidget()
        self.body.setObjectName("railBody")
        self.sections = QVBoxLayout(self.body)
        self.sections.setContentsMargins(PAD, SPACING[0], PAD, SPACING[3])
        self.sections.setSpacing(SPACING[4])
        self.timer_slot = QVBoxLayout()
        self.timer_slot.setContentsMargins(0, 0, 0, 0)
        self.sections.addLayout(self.timer_slot)
        self.month = MonthCard()
        self.month.date_chosen.connect(self.date_chosen.emit)
        self.month.hide_requested.connect(lambda: self.set_month_shown(False, said=True))
        self.sections.addWidget(self.month)
        self.show_month = icon_button("railMonthShow", "chevron-down", SHOW_MONTH)
        self.show_month.clicked.connect(lambda: self.set_month_shown(True, said=True))
        self.next = NextCard()
        self.sections.addWidget(self.next)
        self.waiting = QWidget()
        self.waiting.setObjectName("railWaiting")
        waiting_box = QVBoxLayout(self.waiting)
        waiting_box.setContentsMargins(0, 0, 0, 0)
        waiting_box.setSpacing(SPACING[0])
        self.waiting_head = QHBoxLayout()
        self.waiting_label = label("Not placed yet", "classicWaitingLabel")
        self.waiting_head.addWidget(self.waiting_label, 1)
        self.waiting_count = QLabel()
        self.waiting_count.setObjectName("railWaitingCount")
        self.waiting_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.waiting_head.addWidget(self.waiting_count)
        waiting_box.addLayout(self.waiting_head)
        self.tray = QVBoxLayout()
        self.tray.setSpacing(2)
        waiting_box.addLayout(self.tray)
        self.none_waiting = QLabel("Everything has a time.")
        self.none_waiting.setObjectName("weekNoneWaiting")
        waiting_box.addWidget(self.none_waiting)
        self.sections.addWidget(self.waiting)
        self.focus = QWidget()
        self.focus.setObjectName("railFocus")
        focus_box = QVBoxLayout(self.focus)
        focus_box.setContentsMargins(0, 0, 0, 0)
        focus_box.setSpacing(SPACING[0])
        self.focus_head = QHBoxLayout()
        self.tasks_label = label("Start a focus timer", "focusTasksLabel")
        self.focus_head.addWidget(self.tasks_label, 1)
        focus_box.addLayout(self.focus_head)
        self.tasks = QListWidget()
        self.tasks.setObjectName("focusTasks")
        self.tasks.setItemDelegate(FocusRows(self, self.tasks))
        self.tasks.setMouseTracking(True)
        self.tasks.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        overlay_scroll_bars(self.tasks)
        self.tasks.setFrameShape(QFrame.Shape.NoFrame)
        self.tasks.setToolTip("Double-click homework to start a focus timer for it.")
        self.tasks.itemActivated.connect(self._start_item)
        focus_box.addWidget(self.tasks)
        self.sections.addWidget(self.focus)
        self.sections.addStretch(1)
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll)
        # Folded: one line and the chips after it.
        self.strip = QWidget()
        self.strip.setObjectName("railStrip")
        self.flow = FlowLayout(self.strip)
        self.line = QLabel()
        self.line.setObjectName("weekSideLine")
        self.line.setFont(time_font(self.line.font()))
        self.line.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.flow.addWidget(self.line)
        outer.addWidget(self.strip)
        self.set_folded(False)

    # Look

    def set_look(self, look: dict | None, palette: dict) -> None:
        self.look = look
        self._palette = palette
        self.colours = Colours.of(palette)
        self.month.dates.look = look
        self.month.dates.colours = self.colours
        for button in self.findChildren(QPushButton):
            name = button.property("icon_name")
            if name:
                button.setIcon(icons.icon(str(name), palette["muted"]))
        for chip in self._chips:
            chip.colours, chip.look = self.colours, look
            chip.updateGeometry()
        self.next.card.set_edge(self._next_edge())
        self._fit_tasks()
        self.update()

    def fonts(self) -> tuple[QFont, QFont]:
        return _scaled(self.font(), "body", self.look), time_font(_scaled(self.font(), "caption", self.look))

    # What it shows

    def set_week(self, week: WeekModel, today: int | None, minute: int | None, assignments: dict) -> None:
        self._week, self._today, self._minute = week, today, minute
        due = frozenset(
            str(item.get("due") or "")[:10]
            for item in (assignments or {}).values()
            if item.get("due") and not item.get("completed")
        )
        self._due = due
        now = date.today() if today is None else week.date_of(today)
        self.month.show_week(week.week_start, now, due)
        self.set_waiting(week.waiting)
        self._show()

    def set_clock(self, today: int | None, minute: int | None) -> None:
        if (today, minute) != (self._today, self._minute):
            self._today, self._minute = today, minute
            self._show()

    def set_tasks(self, tasks: list[dict], today: int | None) -> None:
        # In time order, which a plan left out of order (0.17's review, section 5); and the clock, so a
        # switch to the 12-hour clock rewrites the times.
        ordered = sorted(
            tasks,
            key=lambda item: (
                item.get("day") if item.get("day") is not None else 9,
                minute_of(item["start"]) if item.get("start") else 0,
            ),
        )
        listed = tuple(
            (item.get("id"), item.get("day"), item.get("start"), item.get("title")) for item in ordered
        )
        shown = (time_format(), today, listed)
        if shown == self._tasks:
            return
        self._tasks = shown
        self.tasks.clear()
        for item in ordered:
            row = QListWidgetItem(item["title"])
            row.setData(Qt.ItemDataRole.UserRole, item)
            row.setData(
                Qt.ItemDataRole.UserRole + 1, item.get("day") is not None and item.get("day") == today
            )
            row.setData(Qt.ItemDataRole.ToolTipRole, focus_when(item, today))
            self.tasks.addItem(row)
        self._fit_tasks()
        self._show()

    def task_rows(self) -> list[tuple[str, str]]:
        """The focus list as it reads: each homework and when."""
        return [
            (self.tasks.item(row).text(), str(self.tasks.item(row).data(Qt.ItemDataRole.ToolTipRole)))
            for row in range(self.tasks.count())
        ]

    def _fit_tasks(self) -> None:
        """As tall as its rows, up to FOCUS_ROWS."""
        rows = min(self.tasks.count(), FOCUS_ROWS)
        if rows:
            self.tasks.ensurePolished()
            margins = self.tasks.contentsMargins()
            self.tasks.setFixedHeight(
                rows * self.tasks.sizeHintForRow(0) + margins.top() + margins.bottom() + 2
            )

    def set_waiting(self, waiting: tuple[Waiting, ...]) -> None:
        if self.hand.busy:
            # Rebuilding would delete the chip the pointer is holding. The release refreshes.
            return
        # Every save comes through here. Chips made again for the same homework were shown a frame
        # after the old ones went, so the tray blinked empty on each save.
        if waiting == self._waiting:
            return
        self._waiting = waiting
        for chip in self._chips:
            chip.setParent(None)
            chip.deleteLater()
        self._chips = []
        for index, item in enumerate(waiting):
            chip = RailChip(self.hand, item)
            chip.setObjectName(f"classicWaiting{index}")
            chip.colours, chip.look = self.colours, self.look
            chip.clicked.connect(lambda _=False, key=item.block_id: self.hand.open(key))
            self._chips.append(chip)
        self._place_chips()
        self._show()

    def chips(self) -> list[RailChip]:
        return list(self._chips)

    def _place_chips(self) -> None:
        home: QLayout = self.flow if self.folded else self.tray
        for chip in self._chips:
            for layout in (self.tray, self.flow):
                layout.removeWidget(chip)
            home.addWidget(chip)
            chip.show()

    def set_folded(self, folded: bool) -> None:
        """Folded on a window too narrow for a rail: one line above the hours, the chips after it."""
        self.folded = folded
        if folded:
            self.setMinimumWidth(0)
            self.setMaximumWidth(16_777_215)
        else:
            self.setFixedWidth(RAIL_PX)
        self.setProperty("folded", folded)
        self.style().unpolish(self)
        self.style().polish(self)
        self.scroll.setVisible(not folded)
        self.strip.setVisible(folded)
        self._place_chips()
        self._show()

    def set_month_shown(self, shown: bool, *, said: bool = False) -> None:
        """Show or fold away the mini month. `said` when the student did it, so it is kept."""
        if shown == self.month_shown:
            return
        self.month_shown = shown
        self._show()
        if said:
            self.month_shown_changed.emit(shown)
            (self.month.fold if shown else self.show_month).setFocus()

    def _next_edge(self) -> str:
        item = next_item(self._week, self._today, self._minute)
        mark = category_paint(item.category, self._palette)[1] if item is not None and self._palette else None
        return mark or self.colours.muted

    def _show(self) -> None:
        wide = not self.folded
        has_next = self.next.show_next(self._week, self._today, self._minute)
        self.next.card.set_edge(self._next_edge())
        self.next.setVisible(wide and has_next)
        self.month.setVisible(wide and self.month_shown)
        listed = self.tasks.count() > 0
        self.focus.setVisible(wide and listed)
        self.none_waiting.setVisible(not self._chips)
        self.waiting_count.setText(str(len(self._chips)))
        self.waiting_count.setVisible(bool(self._chips))
        # With the month folded, the way back sits on the first header the rail shows.
        for head in (self.next.head, self.waiting_head, self.focus_head):
            head.removeWidget(self.show_month)
        first = self.next.head if has_next else self.waiting_head
        first.addWidget(self.show_month)
        self.show_month.setVisible(wide and not self.month_shown)
        said = []
        if has_next:
            heading, title, when, _then = self.next.shown
            said.append(f"{heading}: {title}, {when}")
        if self._chips:
            said.append(f"Not placed yet: {len(self._chips)}")
        self.line.setText(" · ".join(said))
        self.line.setVisible(self.folded and bool(said))
        self.line.setMinimumHeight(max((chip.sizeHint().height() for chip in self._chips), default=0))
        # Folded with nothing to say, it takes no room at all.
        self.strip.setVisible(self.folded and bool(said))

    def _start_item(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.ItemDataRole.UserRole) or {}
        self.focus_requested.emit(payload.get("id") or "", payload.get("day"))
