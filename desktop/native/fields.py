"""The fields every sheet, setup page and Settings page shares (5.2 A of 0.17.2): days picked as a row of
pills, dates picked on a month drawn in the look, numbers stepped with a − and a + big enough to hit,
and clock times typed with no arrows. One module, so the block editor, Routines, alarms, work hours and
setup draw each the same way; it imports nothing of the app's own widgets, so each of those can use
it."""

from __future__ import annotations

import re

from PySide6.QtCore import QDate, QDateTime, QEvent, QObject, QRect, QRectF, Qt, QTime, Signal
from PySide6.QtGui import (
    QColor,
    QFocusEvent,
    QKeyEvent,
    QPainter,
    QPalette,
    QPen,
    QTextCharFormat,
    QValidator,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QCalendarWidget,
    QDateEdit,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from backend.slots import SLOT_MIN
from desktop.native import icons
from desktop.native.calendar import DAY_FULL, DAYS
from desktop.native.tokens import WEIGHT_STRONG
from desktop.native.weekmodel import clock_text, time_format

# A day of another month, and the letters over the days, as shares of the text colour on the card.
FAINT = 0.45
HEADER = 0.7
# Room between the month and the popup's rounded edge.
POPUP_PAD = 8
# The popup's corners, and its edge as a share of the text colour on the card.
CORNER = 10
EDGE = 0.22
# The quick lengths under a homework's time, in minutes (5.2 A of 0.17.2).
QUICK_LENGTHS = (15, 30, 45, 60, 90)
ARROWS = (("qt_calendar_prevmonth", "chevron-left"), ("qt_calendar_nextmonth", "chevron-right"))
END_OF_DAY = 24 * 60
# "15:15", "1515", "3:15 pm", "3:15pm", "315p": an hour, minutes with or without the colon, and a
# half of the day. Minutes are optional only where `whole` is not asked for.
WRITTEN_TIME = re.compile(r"(\d{1,2})(?::?(\d{2}))?\s*(?:([ap])\.?(?:m\.?)?)?")


class DayPicker(QWidget):
    """The seven days as pills on one line, each a checkable button named `name` and its index.
    `changed` says any of them was ticked or unticked."""

    changed = Signal()

    def __init__(self, days: list[int] | tuple[int, ...] = (), name: str = "day") -> None:
        super().__init__()
        self.setObjectName("setupRow")
        # Its height is the pills'; a form short of room squeezed the row to a sliver without this.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        self.buttons: list[QPushButton] = []
        for index, short in enumerate(DAYS):
            button = QPushButton(short)
            button.setObjectName(f"{name}{index}")
            button.setProperty("pill", True)
            button.setCheckable(True)
            button.setChecked(index in days)
            button.setAccessibleName(DAY_FULL[index])
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAutoDefault(False)
            button.toggled.connect(self.changed)
            line.addWidget(button)
            self.buttons.append(button)
        line.addStretch(1)

    def days(self) -> list[int]:
        return [index for index, button in enumerate(self.buttons) if button.isChecked()]

    def set_days(self, days: list[int]) -> None:
        for index, button in enumerate(self.buttons):
            button.setChecked(index in days)


def _toward(colour: QColor, ground: QColor, share: float) -> QColor:
    """`colour` at `share` of the way from `ground`."""
    return QColor.fromRgbF(
        ground.redF() + (colour.redF() - ground.redF()) * share,
        ground.greenF() + (colour.greenF() - ground.greenF()) * share,
        ground.blueF() + (colour.blueF() - ground.blueF()) * share,
    )


class LookCalendar(QCalendarWidget):
    """A month drawn in the look: Monday first, weekends in the text colour like any other day, the
    picked day a round dot in the accent, today ringed in it, and other months' days faint. Qt's own
    drew Saturday and Sunday red and the picked day as a square (T19 of the 0.17.0 audit)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("lookCalendar")
        self.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.SingleLetterDayNames)
        for day in (Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday):
            self.setWeekdayTextFormat(day, QTextCharFormat())
        self._view = self.findChild(QAbstractItemView, "qt_calendar_calendarview")

    def colours(self) -> tuple[QColor, QColor, QColor, QColor]:
        """The words, the card under them, the accent and the words on the accent, as the look's style
        sheet gives them to the month's grid."""
        colours = self._view.palette()
        return (
            colours.color(QPalette.ColorRole.Text),
            colours.color(QPalette.ColorRole.Base),
            colours.color(QPalette.ColorRole.Highlight),
            colours.color(QPalette.ColorRole.HighlightedText),
        )

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.Type.StyleChange, QEvent.Type.PaletteChange):
            self._dress()

    def showEvent(self, event: object) -> None:  # noqa: N802
        self._dress()
        super().showEvent(event)

    def _dress(self) -> None:
        """What the style sheet cannot colour: the day letters, and the arrows as Lucide's chevrons."""
        text, ground, _accent, _ink = self.colours()
        letters = QTextCharFormat()
        letters.setForeground(_toward(text, ground, HEADER))
        letters.setFontWeight(WEIGHT_STRONG)
        self.setHeaderTextFormat(letters)
        for name, icon in ARROWS:
            arrow = self.findChild(QToolButton, name)
            if arrow is not None:
                arrow.setIcon(icons.icon(icon, text.name()))

    def paintCell(self, painter: QPainter, rect: QRect, day: QDate) -> None:  # noqa: N802
        text, ground, accent, ink = self.colours()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, ground)
        side = min(rect.width(), rect.height()) - 4
        dot = QRectF(0, 0, side, side)
        dot.moveCenter(QRectF(rect).center())
        usable = self.minimumDate() <= day <= self.maximumDate()
        words = text if day.month() == self.monthShown() and usable else _toward(text, ground, FAINT)
        if day == self.selectedDate():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawEllipse(dot)
            words = ink
        elif day == QDate.currentDate():
            painter.setPen(QPen(accent, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(dot.adjusted(0.75, 0.75, -0.75, -0.75))
        painter.setPen(words)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(day.day()))
        painter.restore()


class PopupCard(QObject):
    """Paints a date's popup as a card in the month's own colours before the month is drawn on it."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Paint and isinstance(watched, QWidget):
            month = watched.findChild(LookCalendar)
            if month is not None:
                text, ground, _accent, _ink = month.colours()
                painter = QPainter(watched)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(QPen(_toward(text, ground, EDGE), 1))
                painter.setBrush(ground)
                painter.drawRoundedRect(QRectF(watched.rect()).adjusted(0.5, 0.5, -0.5, -0.5), CORNER, CORNER)
                painter.end()
        return False


class DateField(QDateEdit):
    """A date typed, or picked on a LookCalendar that drops under the field on the card's colour, with
    an edge and rounded corners so it reads apart from the sheet under it."""

    def __init__(self, day: QDate | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCalendarPopup(True)
        # Made with this field as its parent, so Qt owns it, not Python's garbage collector.
        self.setCalendarWidget(LookCalendar(self))
        popup = self.calendarWidget().parentWidget()
        # A rounded card with an edge, on nothing at its corners. The style sheet cannot draw it: Qt
        # left the popup's background unpainted whatever its rule said.
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup.layout().setContentsMargins(POPUP_PAD, POPUP_PAD, POPUP_PAD, POPUP_PAD)
        popup.installEventFilter(PopupCard(self))
        if day is not None:
            self.setDate(day)


def read_clock(text: str, *, end: bool = False, whole: bool = True) -> int | None:
    """The minute of the day `text` writes, or None when it writes no time. The same on either clock:
    "3:15 pm" is 15:15 on the 24-hour one too. An end of the day, 24:00 or 00:00, is 1440, and only an
    end box takes it. `whole` asks for the minutes to be written; an hour alone is "3 pm" or "15"."""
    found = WRITTEN_TIME.fullmatch(text.strip().lower())
    if found is None or (whole and found[2] is None):
        return None
    hour, minute, half = int(found[1]), int(found[2] or 0), found[3]
    if minute > 59:
        return None
    if half:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if half == "p" else 0)
    minutes = hour * 60 + minute
    if minutes == END_OF_DAY:
        return END_OF_DAY if end else None
    if hour > 23:
        return None
    return END_OF_DAY if end and minutes == 0 else minutes


class ClockField(QTimeEdit):
    """A clock time typed as it is written, "16:00", in the student's clock. Qt's arrows inside the box
    were too small to hit and took a quarter of it (T20 of the 0.17.0 audit); the arrow keys and the
    wheel still step it, a quarter hour at a time.

    It is a text box: typing replaces what is selected, Backspace clears, and "1515", "3:15 pm" and
    "315p" all say 15:15. Qt's own time box edits one section at a time, and typed over a selection it
    kept the old hour. A time is taken as soon as the text says one; what does not is put back as the
    last good time when the student leaves the box. An `end` box reads 00:00 as 24:00, the end of the
    day, which a QTime cannot hold."""

    # Set again in __init__; Qt asks for the text while the base class is still being made.
    _end = False
    _typing = False
    _before: int | None = None

    def __init__(
        self, time: QTime | None = None, parent: QWidget | None = None, *, end: bool = False
    ) -> None:
        super().__init__(parent)
        self._end = end
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setProperty("typed", True)
        self.setDisplayFormat(time_format())
        line = self.lineEdit()
        # Qt re-selects a section every time the cursor moves, and rewrites the text on every edit.
        line.cursorPositionChanged.disconnect()
        line.textChanged.disconnect()
        line.textEdited.connect(self._edited)
        line.installEventFilter(self)
        if time is not None:
            self.setTime(time)

    def minutes(self) -> int:
        """The minute of the day, 1440 for the end of the day in an end box."""
        return self._minutes_of(self.time())

    def _minutes_of(self, time: QTime) -> int:
        minutes = time.hour() * 60 + time.minute()
        return END_OF_DAY if self._end and minutes == 0 else minutes

    def _limits(self) -> tuple[int, int]:
        low, high = self._minutes_of(self.minimumTime()), self._minutes_of(self.maximumTime())
        if self._end and self.maximumTime() >= QTime(23, 59):
            high = END_OF_DAY
        return low if low != END_OF_DAY else 0, high

    def _take(self, minutes: int, *, as_typed: bool = False) -> bool:
        """Make `minutes` the time; `as_typed` leaves the text as the student wrote it."""
        low, high = self._limits()
        if not low <= minutes <= high:
            return False
        self._typing = as_typed
        try:
            self.setTime(QTime(minutes // 60 % 24, minutes % 60))
        finally:
            self._typing = False
        return True

    def _edited(self, text: str) -> None:
        if self._before is None:
            self._before = self.minutes()
        minutes = read_clock(text, end=self._end)
        if minutes is not None:
            self._take(minutes, as_typed=True)

    def _settle(self) -> None:
        """The student is done typing: an hour alone counts, and a text that says no time puts back the
        time from before they began, not a half-typed one."""
        line = self.lineEdit()
        minutes = read_clock(line.text(), end=self._end, whole=False)
        if minutes is None and self._before is not None:
            minutes = self._before
        if minutes is not None:
            self._take(minutes)
        self._before = None
        line.blockSignals(True)
        line.setText(clock_text(self.minutes()))
        line.blockSignals(False)

    def textFromDateTime(self, dateTime: QDateTime) -> str:  # noqa: N802, N803
        return self.lineEdit().text() if self._typing else clock_text(self._minutes_of(dateTime.time()))

    def dateTimeFromText(self, text: str) -> QDateTime:  # noqa: N802
        minutes = read_clock(text, end=self._end, whole=False)
        if minutes is None:
            return self.dateTime()
        return QDateTime(self.date(), QTime(minutes // 60 % 24, minutes % 60))

    def validate(self, input: str, pos: int) -> tuple[QValidator.State, str, int]:  # noqa: A002
        written = read_clock(input, end=self._end, whole=False) is not None
        return (QValidator.State.Acceptable if written else QValidator.State.Intermediate, input, pos)

    def fixup(self, input: str) -> str:  # noqa: A002
        return clock_text(self.minutes())

    def stepBy(self, steps: int) -> None:  # noqa: N802
        self._settle()
        now = self.minutes()
        # Up from 08:07 is 08:15 and down is 08:00: the quarter hour on each side.
        if steps < 0 and now % SLOT_MIN:
            steps += 1
        low, high = self._limits()
        self._take(max(low, min(now - now % SLOT_MIN + steps * SLOT_MIN, high)))
        self.lineEdit().selectAll()

    def stepEnabled(self) -> QAbstractSpinBox.StepEnabledFlag:  # noqa: N802
        low, high = self._limits()
        flags = QAbstractSpinBox.StepEnabledFlag.StepNone
        if self.minutes() > low:
            flags |= QAbstractSpinBox.StepEnabledFlag.StepDownEnabled
        if self.minutes() < high:
            flags |= QAbstractSpinBox.StepEnabledFlag.StepUpEnabled
        return flags

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._settle()
        # The spin box's own handling, not the time box's, which moves between sections.
        QAbstractSpinBox.keyPressEvent(self, event)

    def focusInEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        super().focusInEvent(event)
        if event.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        ):
            self.lineEdit().selectAll()

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        self._settle()
        super().focusOutEvent(event)

    def focusNextPrevChild(self, next: bool) -> bool:  # noqa: A002
        # One box, not one section per stop.
        return QWidget.focusNextPrevChild(self, next)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.lineEdit() and event.type() == QEvent.Type.MouseButtonDblClick:
            # A time is one thing: Qt's word selection took only the hour or the minutes.
            self.lineEdit().selectAll()
            return True
        return super().eventFilter(watched, event)


class Stepper(QWidget):
    """A number as − value +. The box keeps its typing, its range and its steps; the two buttons step
    it and stop at its ends. `quick` adds a row of pills under it that set a length in one click, the
    one matching the value lit. Qt's arrows inside the box were too small to hit (T20)."""

    def __init__(self, box: QSpinBox, quick: tuple[int, ...] = ()) -> None:
        super().__init__()
        self.setObjectName("stepper")
        # As wide as its parts: stretched across a form, its + stood apart from where a box ends.
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.box = box
        box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setProperty("stepped", True)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(0)
        self.less = self._button("stepLess", "minus", "One step less", -1)
        self.more = self._button("stepMore", "plus", "One step more", 1)
        line.addWidget(self.less)
        line.addWidget(box)
        line.addWidget(self.more)
        line.addStretch(1)
        column.addLayout(line)
        self.chips: list[QPushButton] = []
        if quick:
            chips = QHBoxLayout()
            chips.setContentsMargins(0, 0, 0, 0)
            chips.setSpacing(4)
            for minutes in quick:
                chip = QPushButton(str(minutes))
                chip.setObjectName("quickLength")
                chip.setProperty("pill", True)
                chip.setProperty("minutes", minutes)
                chip.setCheckable(True)
                chip.setAutoDefault(False)
                chip.setAccessibleName(f"{minutes} minutes")
                chip.setCursor(Qt.CursorShape.PointingHandCursor)
                chip.clicked.connect(self._pick)
                chips.addWidget(chip)
                self.chips.append(chip)
            chips.addStretch(1)
            column.addLayout(chips)
        box.installEventFilter(self)
        box.valueChanged.connect(self._follow)
        self._follow()

    def first_line(self) -> QWidget:
        """What a label beside it lines up with: the box, not the pills under it."""
        return self.box

    def _button(self, name: str, icon: str, words: str, by: int) -> QPushButton:
        button = QPushButton()
        button.setObjectName(name)
        button.setProperty("step", True)
        button.setProperty("by", by)
        button.setAccessibleName(words)
        # The box is where the keys go; its arrow keys step it as these do.
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setAutoDefault(False)
        button.setAutoRepeat(True)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        icons.tint(button, icon)
        button.clicked.connect(self._step)
        return button

    def _step(self) -> None:
        self.box.stepBy(int(self.sender().property("by")))

    def _pick(self) -> None:
        self.box.setValue(int(self.sender().property("minutes")))
        self._follow()

    def _follow(self, *_value: object) -> None:
        steps = self.box.stepEnabled()
        live = self.box.isEnabled()
        self.less.setEnabled(live and bool(steps & QAbstractSpinBox.StepEnabledFlag.StepDownEnabled))
        self.more.setEnabled(live and bool(steps & QAbstractSpinBox.StepEnabledFlag.StepUpEnabled))
        for chip in self.chips:
            chip.setChecked(chip.property("minutes") == self.box.value())
            chip.setEnabled(live)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.box and event.type() == QEvent.Type.EnabledChange:
            self._follow()
        return False
