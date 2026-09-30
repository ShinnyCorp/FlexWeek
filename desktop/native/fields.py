"""The fields every sheet, setup page and Settings page shares (5.2 A of 0.17.2): days picked as a row of
pills, and dates picked on a month drawn in the look. One module, so the block editor, Routines, alarms,
work hours and setup draw a day the same way; it imports nothing of the app's own widgets, so each of
those can use it."""

from __future__ import annotations

from PySide6.QtCore import QDate, QEvent, QObject, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QDateEdit,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from desktop.native import icons
from desktop.native.calendar import DAY_FULL, DAYS
from desktop.native.tokens import WEIGHT_STRONG

# A day of another month, and the letters over the days, as shares of the text colour on the card.
FAINT = 0.45
HEADER = 0.7
# Room between the month and the popup's rounded edge.
POPUP_PAD = 8
# The popup's corners, and its edge as a share of the text colour on the card.
CORNER = 10
EDGE = 0.22
ARROWS = (("qt_calendar_prevmonth", "chevron-left"), ("qt_calendar_nextmonth", "chevron-right"))


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
