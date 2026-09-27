"""Today's app's Day and Week, as Daily Scheduler draws them.

Day is one full-width day that opens at 96 pixels an hour and scrolls, with the homework still
waiting for a time and a summary of the day beside it. Week is seven columns that open at 48 pixels
an hour and scroll, with the days' names kept at the top so each still opens its day, and beside them
what is next, homework to focus on and what still needs a time. Both zoom, and remember how close
they were. Both are painted hours on the one `Hand`, so every gesture works the same on each.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop.native.calendar import CATEGORIES, DAYS
from desktop.native.fonts import time_font
from desktop.native.hours.canvas import BlockPainter, HoursCanvas
from desktop.native.hours.chips import TrayChip
from desktop.native.hours.geometry import FIRST, LAST, LinearTrack
from desktop.native.hours.hand import Hand
from desktop.native.hours.zoom import HoursScroll, Scale, opening_minute
from desktop.native.weekmodel import Waiting, WeekModel, hhmm_text, length_label, time_format
from desktop.native.widgets import FlowLayout

# A Day never goes below 96 pixels an hour, where 15 minutes is 24 pixels. The Week opens at 48, where
# an hour still has edges to resize, and can go further out to see more of the day at once.
DAY_SCALE = Scale("classic.day", (96, 128, 160, 192), 96)
WEEK_SCALE = Scale("classic.week", (32, 48, 64, 96, 128), 48)
DAY_HOUR_PX = DAY_SCALE.default
WEEK_HOUR_PX = WEEK_SCALE.default
PAD = 8
GUTTER = 52
SIDE_PX = 250
# The most rows the focus list shows before it scrolls, so a long one never pushes the tray away.
FOCUS_ROWS = 6


def _hours_height(px_per_hour: int) -> int:
    return round((LAST - FIRST) / 60 * px_per_hour) + 2 * PAD


class DayName(QLabel):
    """A day's name above the week. Kept out of the scroll so it stays reachable."""

    clicked = Signal(int)

    def __init__(self, day: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._day = day
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # The stylesheet underlines today's name; every name keeps room for the line.
        self.setProperty("today", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._day)
            event.accept()
            return
        super().mousePressEvent(event)


def _seven_columns(area: QRectF) -> list[LinearTrack]:
    width = area.width() / 7
    return [
        LinearTrack(day, QRectF(area.left() + day * width, area.top() + PAD, width, area.height() - 2 * PAD))
        for day in range(7)
    ]


class WeekSide(QFrame):
    """Week's side, as Day has one: the Next line, homework to start a focus timer on, and what is
    not placed yet. Folded, on a window too narrow for it, it is one line above the hours with the
    chips after it."""

    # Homework in the focus list was chosen: its block and its day.
    focus_requested = Signal(str, object)

    def __init__(self, hand: Hand, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("weekSide")
        self.hand = hand
        self.folded = False
        self._next = ""
        self._tasks: tuple = ()
        self._waiting: tuple[Waiting, ...] = ()
        self._chips: list[TrayChip] = []
        side = QVBoxLayout(self)
        # The card's padding is its margin, as on Day's side.
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(6)
        self.next = QLabel()
        self.next.setObjectName("weekNext")
        self.next.setWordWrap(True)
        self.next.setFont(time_font(self.next.font()))
        side.addWidget(self.next)
        self.tasks_label = QLabel("Start a focus timer")
        self.tasks_label.setObjectName("focusTasksLabel")
        side.addWidget(self.tasks_label)
        self.tasks = QListWidget()
        self.tasks.setObjectName("focusTasks")
        # Never a sideways scroll bar: a name too long for the side gives up its middle, never its time.
        self.tasks.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tasks.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.tasks.setToolTip("Double-click homework to start a focus timer for it.")
        self.tasks.itemActivated.connect(self._start_item)
        side.addWidget(self.tasks)
        self.waiting_label = QLabel("Not placed yet")
        self.waiting_label.setObjectName("classicWaitingLabel")
        side.addWidget(self.waiting_label)
        self.tray = QVBoxLayout()
        self.tray.setSpacing(6)
        side.addLayout(self.tray)
        self.none_waiting = QLabel("Everything has a time.")
        self.none_waiting.setObjectName("weekNoneWaiting")
        side.addWidget(self.none_waiting)
        # Folded, the line and the chips after it share one row.
        self.flow = FlowLayout()
        self.line = QLabel()
        self.line.setObjectName("weekSideLine")
        self.line.setFont(time_font(self.line.font()))
        self.line.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.flow.addWidget(self.line)
        side.addLayout(self.flow)
        side.addStretch(1)
        self.set_folded(False)

    def set_folded(self, folded: bool) -> None:
        self.folded = folded
        if folded:
            self.setMinimumWidth(0)
            self.setMaximumWidth(16_777_215)
        else:
            self.setFixedWidth(SIDE_PX)
        # The stylesheet pads a folded side less, so the line stays slim.
        self.setProperty("folded", folded)
        self.style().unpolish(self)
        self.style().polish(self)
        self._place_chips()
        self._show()

    def set_next(self, words: str) -> None:
        if words != self._next:
            self._next = words
            self._show()

    def set_tasks(self, tasks: list[dict]) -> None:
        # The clock too, so a switch to the 12-hour clock rewrites the times.
        listed = tuple((item.get("id"), item.get("start"), item.get("title")) for item in tasks)
        shown = (time_format(), listed)
        if shown == self._tasks:
            return
        self._tasks = shown
        self.tasks.clear()
        for item in tasks:
            start = hhmm_text(item["start"]) if item.get("start") else ""
            row = QListWidgetItem(f"{item['title']}  {start}".rstrip())
            row.setData(Qt.ItemDataRole.UserRole, item)
            self.tasks.addItem(row)
        self._fit_tasks()
        self._show()

    def _fit_tasks(self) -> None:
        """As tall as its rows, up to FOCUS_ROWS, whatever the look puts around them. A fixed 8 pixels
        for the padding and borders left High contrast's thicker ones a row short, behind scroll bars."""
        rows = min(self.tasks.count(), FOCUS_ROWS)
        if rows:
            self.tasks.ensurePolished()
            # The stylesheet's border and padding, which is what the margins hold once polished.
            margins = self.tasks.contentsMargins()
            chrome = margins.top() + margins.bottom() + 2
            self.tasks.setFixedHeight(rows * self.tasks.sizeHintForRow(0) + chrome)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            # After the list has taken the new look's padding and borders.
            QTimer.singleShot(0, self, self._fit_tasks)

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
            chip = TrayChip(self.hand, item)
            chip.setObjectName(f"classicWaiting{index}")
            chip.clicked.connect(lambda _=False, key=item.block_id: self.hand.open(key))
            self._chips.append(chip)
        self._place_chips()
        self._show()

    def _place_chips(self) -> None:
        home: QLayout = self.flow if self.folded else self.tray
        for chip in self._chips:
            for layout in (self.tray, self.flow):
                layout.removeWidget(chip)
            home.addWidget(chip)
            chip.show()

    def _show(self) -> None:
        wide = not self.folded
        self.next.setText(self._next)
        self.next.setVisible(wide and bool(self._next))
        listed = self.tasks.count() > 0
        self.tasks_label.setVisible(wide and listed)
        self.tasks.setVisible(wide and listed)
        self.waiting_label.setVisible(wide)
        self.none_waiting.setVisible(wide and not self._chips)
        said = [self._next] if self._next else []
        if self._chips:
            said.append(f"Not placed yet: {len(self._chips)}")
        self.line.setText(" · ".join(said))
        self.line.setVisible(self.folded and bool(said))
        # As tall as a chip, so its words sit level with the chips' words.
        self.line.setMinimumHeight(max((chip.sizeHint().height() for chip in self._chips), default=0))
        # Folded with nothing to say, it takes no room at all.
        self.setVisible(wide or bool(said))

    def _start_item(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.ItemDataRole.UserRole) or {}
        self.focus_requested.emit(payload.get("id") or "", payload.get("day"))


class ClassicWeek(QWidget):
    """The week as a scrollable overview, names fixed at the top, still drags, with its side."""

    day_opened = Signal(int)

    def __init__(self, hand: Hand, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("weekTable")
        self.week_start = ""
        self.hours = HoursCanvas(hand, BlockPainter({}), _seven_columns, gutter=GUTTER, names=self._name)
        self.hours.setObjectName("weekHours")
        self.hours.day_opened.connect(self.day_opened.emit)
        self.scroll = HoursScroll(self.hours, WEEK_SCALE, _hours_height, name="week", gutter=GUTTER)
        names = QWidget()
        names.setObjectName("weekDayNames")
        row = QHBoxLayout(names)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._name_labels: list[DayName] = []
        for day in range(7):
            name = DayName(day)
            name.setObjectName(f"weekDayName{day}")
            name.setText(DAYS[day])
            name.clicked.connect(self.day_opened.emit)
            row.addWidget(name, 1)
            self._name_labels.append(name)
        self.scroll.set_header(names)
        self.side = WeekSide(hand)
        self._box = QVBoxLayout(self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.setSpacing(0)
        self._row = QHBoxLayout()
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)
        self._row.addWidget(self.scroll, 1)
        self._row.addWidget(self.side)
        self._box.addLayout(self._row, 1)

    def set_narrow(self, narrow: bool) -> None:
        """Short of room the side folds into one line above the hours, and blocks give their names
        the room their times took."""
        if narrow != self.hours.short_words:
            self.hours.short_words = narrow
            self.hours.update()
        if narrow == self.side.folded:
            return
        for layout in (self._row, self._box):
            layout.removeWidget(self.side)
        if narrow:
            self._box.insertWidget(0, self.side)
        else:
            self._row.addWidget(self.side)
        self.side.set_folded(narrow)

    def _name(self, day: int) -> str:
        if not self.week_start:
            return DAYS[day]
        return f"{DAYS[day]} {(date.fromisoformat(self.week_start) + timedelta(days=day)).day}"

    def set_look(self, look: dict | None, palette: dict) -> None:
        self.hours.set_painter(BlockPainter(palette, look))

    def set_week(self, week: WeekModel, today: int | None, now_min: int | None) -> None:
        self.week_start = week.week_start
        self.hours.set_week(week.occurrences, today, now_min)
        self.side.set_waiting(week.waiting)
        for day, label in enumerate(self._name_labels):
            label.setText(self._name(day))
            if label.property("today") != (day == today):
                label.setProperty("today", day == today)
                label.style().unpolish(label)
                label.style().polish(label)
        self.scroll.open_at(week.week_start, opening_minute(week, today, now_min))

    def hours_surfaces(self) -> list[HoursCanvas]:
        return [self.hours]


class ClassicDay(QWidget):
    """One day, full width, with what still needs a time and what the day holds beside it."""

    def __init__(self, hand: Hand, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dayView")
        self.hand = hand
        self.day = 0
        self.hours = HoursCanvas(hand, BlockPainter({}), self._one_column, gutter=56)
        self.hours.setObjectName("dayHours")
        # The window's heading already names the day, so its header holds only the zoom.
        self.scroll = HoursScroll(self.hours, DAY_SCALE, _hours_height, name="day", gutter=56)
        self.side = QFrame()
        self.side.setObjectName("daySide")
        self.side.setFixedWidth(250)
        side = QVBoxLayout(self.side)
        # The card's padding is its margin, so the chips keep the width they had at 8 px.
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(6)
        waiting = QLabel("Not placed yet")
        waiting.setObjectName("dayWaitingLabel")
        side.addWidget(waiting)
        self.tray = QVBoxLayout()
        self.tray.setSpacing(6)
        side.addLayout(self.tray)
        self.tray_hint = QLabel(
            "Drag one onto the day to give it that time, or drag on empty time to add something."
        )
        self.tray_hint.setObjectName("dayWaitingHint")
        self.tray_hint.setWordWrap(True)
        side.addWidget(self.tray_hint)
        summary = QLabel("Summary")
        summary.setObjectName("daySummaryLabel")
        side.addWidget(summary)
        self.summary = QLabel()
        self.summary.setObjectName("daySummary")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        side.addWidget(self.summary)
        side.addStretch(1)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.scroll, 1)
        row.addWidget(self.side)

    def _one_column(self, area: QRectF) -> list[LinearTrack]:
        return [LinearTrack(self.day, area.adjusted(0, PAD, -PAD, -PAD))]

    def set_look(self, look: dict | None, palette: dict) -> None:
        self.hours.set_painter(BlockPainter(palette, look))

    def set_day(self, week: WeekModel, day: int, today: int | None, now_min: int | None) -> None:
        changed_day = day != self.day
        self.day = day
        if changed_day:
            self.hours.relayout()
        self.hours.set_week([item for item in week.occurrences if item.day == day], today, now_min)
        self._fill_tray(week)
        self._fill_summary(week, day)
        self.scroll.open_at((week.week_start, day), opening_minute(week, today, now_min, day))

    def _fill_tray(self, week: WeekModel) -> None:
        if self.hand.busy:
            # Rebuilding would delete the chip the pointer is holding. The release refreshes.
            return
        while self.tray.count():
            widget = self.tray.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for index, waiting in enumerate(week.waiting):
            chip = TrayChip(self.hand, waiting)
            chip.setObjectName(f"dayWaiting{index}")
            chip.clicked.connect(lambda _=False, key=waiting.block_id: self.hand.open(key))
            self.tray.addWidget(chip)
        self.tray_hint.setVisible(bool(week.waiting))

    def _fill_summary(self, week: WeekModel, day: int) -> None:
        totals: dict[str, int] = {}
        for item in week.on_day(day):
            name = CATEGORIES.get(item.category, {}).get("label") or ("Homework" if item.work else "Other")
            totals[name] = totals.get(name, 0) + item.minutes
        lines = [f"{name}: {length_label(minutes)}" for name, minutes in totals.items()]
        self.summary.setText("\n".join(lines) if lines else "Nothing planned.")

    def hours_surfaces(self) -> list[HoursCanvas]:
        return [self.hours]
