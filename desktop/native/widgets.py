"""Native calendar and editors using the scheduler's existing data models."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from PySide6.QtCore import (
    Property,
    QDate,
    QEvent,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSize,
    QStandardPaths,
    Qt,
    QTime,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFontMetrics,
    QHideEvent,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProxyStyle,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QStyle,
    QStyleOptionButton,
    QStyleOptionSlider,
    QStylePainter,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from backend.explain import REASON_COPY
from backend.models import ESTIMATE_MAX_MIN, Assignment, TimeBlock, WeekRequest, due_is_timed, parse_due
from backend.slots import (
    DAY_END_MIN,
    DAY_START_MIN,
    SLOT_MIN,
    hhmm_to_minutes,
    minutes_to_hhmm,
)
from desktop.native import icons
from desktop.native.calendar import (
    CATEGORIES,
    SETUP_SCHOOL_ID,
    is_series,
    local_stamp,
    monday_of,
    span_clash,
    span_problem,
)
from desktop.native.elevation import lift
from desktop.native.fonts import time_font, weighted
from desktop.native.icons import pixmap as icon_pixmap
from desktop.native.menus import Menu
from desktop.native.motion import OUT, SEGMENT_MS, app_level, appear, between, duration, moves, settle, vanish
from desktop.native.reuse import (
    AVAILABILITY_LIMIT,
    LATE_MINUTES,
    PROTECTED_KINDS,
    preview_conflict_message,
    routine_source_blocks,
    row_conflict,
)
from desktop.native.tokens import SHADOW_LARGE, SPACING, WEIGHT_REGULAR, WEIGHT_STRONG, Shadow
from desktop.native.weekmodel import due_label, hhmm_text, length_label, time_format
from desktop.native.work_windows import WorkWindowsEditor

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SWATCH_PX = 12
DETAIL_BOX_HEIGHT = 84
# A scroll area reports its own modest size hint rather than its content's, which is what keeps the
# homework editor on a laptop screen. It does not claim the content's width either, so that is set.
HOMEWORK_MIN_WIDTH = 520
DIALOG_USABLE_HEIGHT = 480
# Dates as a student reads them. "2026-09-27 23:59" made them work out which day that was.
DUE_DATE_FORMAT = "ddd d MMM yyyy"
DATE_FORMAT = "ddd d MMM yyyy"
DIALOG_MAX_HEIGHT = 700
SLOT_HINT = "Use a multiple of 15 minutes, such as 15, 30, or 45."
ESTIMATE_ERROR = "That time is not a multiple of 15 minutes."
ESTIMATE_SHORT = "Give it at least 15 minutes."
ESTIMATE_LONG = "That is more than 24 hours. Split it into parts and add each part as its own homework."
HOMEWORK_PROBLEMS = {
    "due": "Choose a valid due date.",
    "course": "Keep the course name under 40 characters.",
    "spotify_url": "Paste a Spotify share link from open.spotify.com.",
    "notes": "Keep notes under 4,000 characters.",
    "priority": "Choose a priority from the list.",
    "energy": "Choose a time of day from the list.",
    "completed_at": "Set a valid time for finished homework.",
}
HOMEWORK_REFUSED = "Check the homework details and try again."
PLAN_REVIEW_MAX = 132
UNFINISHED_MAX = 132
REPEAT_NOTE = "Tick more days to repeat it this week."
SCHOOL_HOURS_NOTE = "The days and times you are at school, so nothing is planned then."
ROUTINE_LIST_MIN_HEIGHT = 130
REPLAN_TIP = (
    "Find new times for all of this week's homework, as if none had a time yet. Homework you placed "
    "yourself stays put. Use it when your week has changed a lot."
)
DAY_FULL = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


# What the block editor says when the server's rules refuse a block, by the field they name. Their own
# words ("Value error, spotify_url must be ...") are for a developer, not a student.
BLOCK_PROBLEMS = {
    "title": "Give it a title.",
    "days": "Tick at least one day.",
    "spotify_url": "That is not a Spotify share link. Paste one that starts with https://open.spotify.com, "
    "or leave it empty.",
}
BLOCK_REFUSED = "FlexWeek cannot keep this block as it is. Check its title, days and times."


def _block_problem(error: ValidationError) -> str:
    fields = [str(part) for item in error.errors() for part in item.get("loc") or ()]
    return next((BLOCK_PROBLEMS[field] for field in fields if field in BLOCK_PROBLEMS), BLOCK_REFUSED)


class WheelGuard(QObject):
    """A number box, time box or dropdown takes the mouse wheel only once it has been clicked into;
    otherwise the wheel scrolls whatever it is on. Scrolling down Settings changed every box the
    pointer passed over on the way."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        kind = event.type()
        if not isinstance(watched, (QAbstractSpinBox, QComboBox)):
            return False
        if kind == QEvent.Type.Polish:
            # Qt gives a wheel-focus box the keyboard before the wheel arrives, so it would always
            # look clicked into by the time this filter sees the wheel.
            watched.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        elif kind == QEvent.Type.Wheel and not watched.hasFocus():
            # Ignored and stopped here, Qt offers it to the parent, which is the page's scroll area.
            event.ignore()
            return True
        return False


def steady_wheel(app: QApplication) -> None:
    if app.findChild(WheelGuard) is None:
        app.installEventFilter(WheelGuard(app))


# The focus reasons that mean the student moved with the keyboard.
KEYED = (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason, Qt.FocusReason.ShortcutFocusReason)


class KeyFocus(QObject):
    """Marks a button reached with the keyboard, so its focus ring shows, and clears the mark when a click
    focuses it: Qt's `:focus` also holds after a click, which would ring every button pressed. Other
    reasons, such as the window coming back to the front, leave the mark as it was."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.FocusIn and isinstance(watched, QAbstractButton):
            reason = event.reason()
            if reason in KEYED or reason == Qt.FocusReason.MouseFocusReason:
                keyed = reason in KEYED
                if bool(watched.property("keyfocus")) != keyed:
                    watched.setProperty("keyfocus", keyed)
                    watched.style().unpolish(watched)
                    watched.style().polish(watched)
        return False


def keyboard_focus_rings(app: QApplication) -> None:
    if app.findChild(KeyFocus) is None:
        app.installEventFilter(KeyFocus(app))


class OverlayBar(QObject):
    """Draws a scroll bar marked `overlay` as a thin rounded handle that widens under the pointer. The
    bar lies over the edge of what scrolls (AppStyle makes it transient), so the content keeps its
    whole width, as a phone's or a Mac's does."""

    REST, WIDE, EDGE = 4, 8, 2

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if not isinstance(watched, QScrollBar):
            return False
        kind = event.type()
        if kind in (QEvent.Type.Enter, QEvent.Type.Leave):
            watched.setProperty("hovered", kind == QEvent.Type.Enter)
            watched.update()
        elif kind == QEvent.Type.Paint:
            self._paint(watched)
            return True
        return False

    def _paint(self, bar: QScrollBar) -> None:
        if bar.maximum() <= bar.minimum():
            return
        option = QStyleOptionSlider()
        bar.initStyleOption(option)
        handle = QRectF(
            bar.style().subControlRect(
                QStyle.ComplexControl.CC_ScrollBar, option, QStyle.SubControl.SC_ScrollBarSlider, bar
            )
        )
        wide = bool(bar.property("hovered")) or bar.isSliderDown()
        thick = self.WIDE if wide else self.REST
        down = bar.orientation() == Qt.Orientation.Vertical
        across = (bar.width() if down else bar.height()) - thick - self.EDGE
        if down:
            pill = QRectF(
                across, handle.top() + self.EDGE, thick, max(handle.height() - 2 * self.EDGE, thick)
            )
        else:
            pill = QRectF(
                handle.left() + self.EDGE, across, max(handle.width() - 2 * self.EDGE, thick), thick
            )
        ink = bar.palette().color(QPalette.ColorRole.WindowText)
        painter = QPainter(bar)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if wide:
            track = QColor(ink)
            track.setAlphaF(0.06)
            painter.setBrush(track)
            groove = QRectF(bar.rect()).adjusted(1, 1, -1, -1)
            painter.drawRoundedRect(
                groove, min(groove.width(), groove.height()) / 2, min(groove.width(), groove.height()) / 2
            )
        ink.setAlphaF(0.65 if bar.isSliderDown() else 0.5 if wide else 0.3)
        painter.setBrush(ink)
        painter.drawRoundedRect(pill, thick / 2, thick / 2)
        painter.end()


def overlay_scroll_bars(area: QAbstractScrollArea) -> None:
    """Decision 12's scroll bars on `area`: thin, laid over its content's edge, wider under the pointer.
    Called before the area is first shown, which is when it lays its bars out."""
    global _OVERLAY
    if _OVERLAY is None:
        _OVERLAY = OverlayBar()
    for bar in (area.verticalScrollBar(), area.horizontalScrollBar()):
        bar.setProperty("overlay", True)
        bar.installEventFilter(_OVERLAY)


_OVERLAY: OverlayBar | None = None


def overlaid(widget: object) -> bool:
    return isinstance(widget, QScrollBar) and bool(widget.property("overlay"))


class SegmentTrack(QFrame):
    """A segmented control's track, a pill, with the chosen segment raised on it as a pill of its own
    and lifted with the small shadow. Painted, since a stylesheet's corner cannot follow a height
    that the text size sets, and so the chosen pill can slide to the segment chosen next (decision
    32 of 0.17), or cross-fade to it where things may not travel. The stylesheet gives the colours:
    `alternate-background-color` is the track, `selection-background-color` the chosen segment and
    `color` an outline, drawn when it differs from the track; `qproperty-shade` is the shadow's
    opacity out of 255, or 0 for none."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._shade = 0
        # Where the chosen pill was last drawn, and where it leaves from for the segment just chosen.
        self._drawn: QRectF | None = None
        self._from = QRectF()
        self._slide = QVariantAnimation(self)
        self._slide.setStartValue(0.0)
        self._slide.setEndValue(1.0)
        self._slide.valueChanged.connect(lambda _share: self.update())

    def _get_shade(self) -> int:
        return self._shade

    def _set_shade(self, value: int) -> None:
        self._shade = value
        self.update()

    shade = Property(int, _get_shade, _set_shade)

    def add(self, button: QAbstractButton) -> None:
        self.layout().addWidget(button)
        button.toggled.connect(self._chosen)

    def _chosen(self, on: bool) -> None:
        length = duration(SEGMENT_MS)
        if on and self._drawn is not None and self.isVisible() and length:
            self._from = QRectF(self._drawn)
            self._slide.stop()
            self._slide.setDuration(length)
            self._slide.start()
        self.update()

    def _pills(self, target: QRectF) -> list[tuple[QRectF, float]]:
        """The chosen pill as drawn now, with its opacity: sliding from where it was, or where things
        may not travel, fading from there to here."""
        if self._slide.state() == QVariantAnimation.State.Stopped:
            return [(target, 1.0)]
        share = OUT.valueForProgress(self._slide.currentTime() / max(self._slide.duration(), 1))
        start = self._from
        if not moves():
            return [(start, 1 - share), (target, share)]
        return [(between(start, target, share), 1.0)]

    def paintEvent(self, event: object) -> None:  # noqa: N802
        colours = self.palette()
        track = colours.color(QPalette.ColorRole.AlternateBase)
        outline = colours.color(QPalette.ColorRole.WindowText)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(outline, 1) if outline != track else Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(box, box.height() / 2, box.height() / 2)
        chosen = next(
            (b for b in self.findChildren(QAbstractButton) if b.isChecked() and b.isVisible()), None
        )
        self._drawn = None
        if chosen is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            shade = self._shade
            for pill, opacity in self._pills(QRectF(chosen.geometry())):
                self._drawn = pill
                radius = pill.height() / 2
                painter.setOpacity(opacity)
                # The small shadow (decision 6), 0 1 3: three widening rings, each a third of its opacity.
                for spread in (1.5, 1.0, 0.5) if shade else ():
                    painter.setBrush(QColor(0, 0, 0, round(shade / 3)))
                    painter.drawRoundedRect(
                        pill.adjusted(-spread, 1 - spread, spread, 1 + spread), radius, radius
                    )
                painter.setBrush(colours.color(QPalette.ColorRole.Highlight))
                painter.drawRoundedRect(pill, radius, radius)
        painter.end()


class Segment(QPushButton):
    """One choice on a SegmentTrack, always as wide as its words at the chosen weight, so choosing it
    moves nothing and cuts nothing."""

    def sizeHint(self) -> QSize:  # noqa: N802
        hint = super().sizeHint()
        words = self.text()
        extra = QFontMetrics(weighted(self.font(), WEIGHT_STRONG)).horizontalAdvance(words)
        return QSize(
            hint.width() + max(0, extra - self.fontMetrics().horizontalAdvance(words)), hint.height()
        )

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()


# How far a dialog's content sits in from its edges. Qt's styles give about 11 px.
DIALOG_MARGIN = 24
LAYOUT_MARGINS = (
    QStyle.PixelMetric.PM_LayoutLeftMargin,
    QStyle.PixelMetric.PM_LayoutTopMargin,
    QStyle.PixelMetric.PM_LayoutRightMargin,
    QStyle.PixelMetric.PM_LayoutBottomMargin,
)


class AppStyle(QProxyStyle):
    """The platform's own style, with what a stylesheet cannot say: a dialog's content sits
    DIALOG_MARGIN in from its edges, and a time box writes its figures at one width, so 11:11 and
    20:00 line up. A layout given margins of its own keeps them."""

    def pixelMetric(self, metric, option=None, widget=None):  # noqa: N802
        if metric in LAYOUT_MARGINS and isinstance(widget, QDialog):
            return DIALOG_MARGIN
        if metric == QStyle.PixelMetric.PM_ScrollView_ScrollBarOverlap and overlaid(widget):
            # The whole bar lies over the content, which keeps its width.
            return super().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent, option, widget)
        return super().pixelMetric(metric, option, widget)

    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: N802
        if hint == QStyle.StyleHint.SH_ScrollBar_Transient and overlaid(widget):
            return 1
        return super().styleHint(hint, option, widget, returnData)

    def polish(self, target):  # Qt names one method for a widget, a palette and the application.
        if isinstance(target, QTimeEdit):
            target.setFont(time_font(target.font()))
        return super().polish(target)


def use_app_style(app: QApplication) -> None:
    if not isinstance(app.style(), AppStyle):
        app.setStyle(AppStyle())


def _validation_text(error: Exception) -> str:
    loc: tuple[object, ...] = ()
    message = str(error)
    if isinstance(error, ValidationError) and error.errors():
        first = error.errors()[0]
        loc = tuple(first.get("loc") or ())
        message = str(first.get("msg") or error)
    names = {str(part) for part in loc}
    if names & {"estimate_min", "duration_min"} or "multiple of 15" in message:
        return ESTIMATE_ERROR
    return message


def _homework_problem(error: ValueError) -> str:
    if not isinstance(error, ValidationError):
        return HOMEWORK_REFUSED
    first = error.errors()[0]
    path = tuple(str(part) for part in first.get("loc") or ())
    field = path[0] if path else ""
    if field == "title":
        return (
            "Keep the homework title under 80 characters."
            if first["type"] == "string_too_long"
            else "Give the homework a title."
        )
    if field == "estimate_min":
        return ESTIMATE_ERROR
    if field == "links":
        if "url" in path:
            return "A link needs an http:// or https:// address."
        if "label" in path:
            return "Give each link a name under 80 characters."
        return "Keep no more than 20 links."
    if field == "checklist":
        if "text" in path:
            return "Keep each checklist step under 80 characters."
        return "Keep no more than 40 checklist steps."
    return HOMEWORK_PROBLEMS.get(field, HOMEWORK_REFUSED)


def fit_scroll_dialog(dialog: QDialog, *, min_height: int = DIALOG_USABLE_HEIGHT) -> None:
    """A QScrollArea reports a short size hint, so a dialog that only sets a minimum width
    opened as a strip too short to read the fields or the Save button."""
    screen = dialog.screen().availableGeometry() if dialog.screen() else None
    max_h = min(DIALOG_MAX_HEIGHT, screen.height() - 48) if screen else DIALOG_MAX_HEIGHT
    max_w = (screen.width() - 48) if screen else 1280
    min_h = min(max(min_height, 240), max_h)
    dialog.setMinimumHeight(min_h)
    width = min(max(dialog.minimumWidth(), dialog.sizeHint().width()), max_w)
    height = min(max(min_h, dialog.sizeHint().height()), max_h)
    dialog.resize(width, height)


TOAST_MS = 6000
TOAST_MARGIN = 24
TOAST_MIN_WIDTH = 280
TOAST_MAX_WIDTH = 420
# Room round the toast's card for its shadow.
TOAST_SHADOW = 4
# Between the toast's bottom edge and the foot of the hours, and between its words and its button.
TOAST_FOOT = 16
TOAST_GAP = 12


class FittedLabel(QLabel):
    """A heading that asks for the room its whole text needs and shortens with an ellipsis only when
    the row has none left. Given a fixed 96 pixels instead, the week title read "21 – 27 S" at every
    width, and Qt laid the buttons after it out as if it had no width at all, on top of it."""

    def __init__(self, parent: QWidget | None = None, minimum: int = 96) -> None:
        super().__init__(parent)
        self._full = ""
        self._short = ""
        self._minimum = minimum

    def set_full_text(self, text: str, short: str = "") -> None:
        """`short` is shown before any ellipsis: "28 Sep – 4 Oct" says the whole week where
        "28 Septemb…" lost its end."""
        self._full = text
        self._short = short
        self.setAccessibleName(text)
        self.updateGeometry()
        self._fit()

    def full_text(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:  # noqa: N802
        margins = self.contentsMargins()
        width = self.fontMetrics().horizontalAdvance(self._full) + margins.left() + margins.right() + 2
        return QSize(width, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # A short form is kept whole: "21 – 2…" said less than either form.
        margins = self.contentsMargins()
        short = self.fontMetrics().horizontalAdvance(self._short) + margins.left() + margins.right() + 2
        return QSize(max(self._minimum, short if self._short else 0), super().minimumSizeHint().height())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        # The stylesheet's larger font arrives after construction, and it changes the width needed.
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.updateGeometry()
            self._fit()

    def _fit(self) -> None:
        room = max(0, self.contentsRect().width())
        metrics = self.fontMetrics()
        text = self._full
        if self._short and metrics.horizontalAdvance(text) > room:
            text = self._short
        super().setText(metrics.elidedText(text, Qt.TextElideMode.ElideRight, room))


class FittedButton(QPushButton):
    """A button with a short form of its words, shown when its row has no room for the whole of
    them, so it is never cut mid-word. It asks for the room the whole words need."""

    def __init__(self, text: str, short: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full, self._short = text, short
        self.setAccessibleName(text)
        # A plain button never goes below the room for its whole words; this one may, to its short form.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set_texts(self, text: str, short: str) -> None:
        self._full, self._short = text, short
        self.setAccessibleName(text)
        self.setText(text)
        self.updateGeometry()
        self._fit()

    def _wide(self, words: str) -> int:
        fonts = self.fontMetrics()
        chrome = super().sizeHint().width() - fonts.horizontalAdvance(self.text())
        return chrome + fonts.horizontalAdvance(words)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._wide(self._full), super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._wide(self._short), super().minimumSizeHint().height())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.updateGeometry()
            self._fit()

    def _fit(self) -> None:
        words = self._full if self.width() >= self._wide(self._full) else self._short
        if words != self.text():
            self.setText(words)


class EndsLayout(QLayout):
    """Two groups on one row, the first at its left and the second at its right, each as wide as it
    asks while there is room. Short of room, the first gives way first, down to its smallest, then
    the second; with no room for both at their smallest, the second goes under the first, still at
    the right. So the top bar is never squeezed until its words are cut."""

    def __init__(self, parent: QWidget | None = None, gap: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._gap = gap

    def add_group(self, group: QLayout) -> None:
        # A layout, not a widget holding one: a change inside it reaches the window's layout at once.
        self.addChildLayout(group)
        self._items.append(group)

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 - Qt virtual
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - Qt virtual
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - Qt virtual
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802 - Qt virtual
        return Qt.Orientation.Horizontal

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt virtual
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt virtual
        return self._arrange(QRect(0, 0, width, 0), place=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt virtual
        super().setGeometry(rect)
        self._arrange(rect, place=True)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt virtual
        hints = [item.sizeHint() for item in self._items]
        return self._framed(
            sum(hint.width() for hint in hints) + self._gap * (len(hints) - 1),
            max((hint.height() for hint in hints), default=0),
        )

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt virtual
        smallest = [item.minimumSize() for item in self._items]
        return self._framed(
            max((size.width() for size in smallest), default=0),
            max((size.height() for size in smallest), default=0),
        )

    def _framed(self, width: int, height: int) -> QSize:
        margins = self.contentsMargins()
        return QSize(width + margins.left() + margins.right(), height + margins.top() + margins.bottom())

    def _arrange(self, rect: QRect, place: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        shown = [item for item in self._items if not item.isEmpty()]
        if len(shown) != 2:
            tall = max((item.sizeHint().height() for item in shown), default=0)
            for item in shown if place else ():
                item.setGeometry(QRect(area.x(), area.y(), area.width(), tall))
            return tall + margins.top() + margins.bottom()
        first, second = shown
        least = first.minimumSize().width()
        if least + self._gap + second.minimumSize().width() <= area.width():
            right = min(second.sizeHint().width(), area.width() - self._gap - least)
            left = min(first.sizeHint().width(), area.width() - self._gap - right)
            tall = max(first.sizeHint().height(), second.sizeHint().height())
            if place:
                first.setGeometry(QRect(area.x(), area.y(), left, tall))
                second.setGeometry(QRect(area.x() + area.width() - right, area.y(), right, tall))
            return tall + margins.top() + margins.bottom()
        top, below = first.sizeHint().height(), second.sizeHint().height()
        if place:
            first.setGeometry(QRect(area.x(), area.y(), min(first.sizeHint().width(), area.width()), top))
            wide = min(second.sizeHint().width(), area.width())
            second.setGeometry(QRect(area.x() + area.width() - wide, area.y() + top + self._gap, wide, below))
        return top + self._gap + below + margins.top() + margins.bottom()


class Toast(QWidget):
    """One notice at a time, bottom right of the page it was said on, with at most one button.

    Dark with light words, the 16 corners of a sheet and the small shadow (decision 20 of 0.17). The
    toast itself is the part that moves and fades; the painted card inside it carries the shadow, as a
    widget holds one effect. The toast and its words let the pointer through to what is under them.
    The button is laid over the card as the window's own child, since Qt passes a widget's clicks on
    only with its children's. `over` is the page area it sits in; while that is hidden, the window.
    """

    def __init__(self, parent: QWidget, over: QWidget) -> None:
        super().__init__(parent)
        self._over = over
        self.setObjectName("toastHost")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        around = QHBoxLayout(self)
        around.setContentsMargins(TOAST_SHADOW, TOAST_SHADOW, TOAST_SHADOW, TOAST_SHADOW)
        self.card = QFrame()
        self.card.setObjectName("toast")
        self.card.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        around.addWidget(self.card)
        row = QHBoxLayout(self.card)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(TOAST_GAP)
        self.label = QLabel()
        self.label.setObjectName("toastText")
        self.label.setWordWrap(True)
        row.addWidget(self.label, 1)
        # Room for the button, which is not in this layout.
        self._slot = QSpacerItem(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row.addItem(self._slot)
        self.button = QPushButton(parent)
        self.button.setObjectName("toastButton")
        self.button.hide()
        self.button.clicked.connect(self._pressed)
        self._callback: Callable[[], None] | None = None
        self._action_colour = "#a1bbe4"
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(TOAST_MS)
        self._timer.timeout.connect(self._go)
        # The window's Animations level. A notice rises into place and fades when it goes.
        self.motion = "normal"
        self.hide()

    def set_look(self, action_colour: str, shadow: Shadow | None, dark: bool = False) -> None:
        """The colour of the toast's button, for its icon, and the shadow, or none in a look without."""
        self._action_colour = action_colour
        if shadow is None:
            self.card.setGraphicsEffect(None)
        else:
            lift(self.card, shadow, dark)
        self._dress_button()

    def text(self) -> str:
        return self.label.text()

    def show_message(self, text: str, button: str = "", callback: Callable[[], None] | None = None) -> None:
        self.label.setText(text)
        self.setAccessibleName(text)
        self.setAccessibleDescription(text)
        self.button.setText(button)
        self._dress_button()
        self._callback = callback if button else None
        size = self.button.sizeHint() if button else QSize(0, 0)
        self._slot.changeSize(size.width(), size.height(), QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.card.layout().invalidate()
        # The last notice's rise ends where it was going, and its fade-out ends it, so this one
        # comes in on its own.
        settle(self)
        settle(self.button)
        was_shown = self.isVisible()
        self.show()
        self.reposition()
        self.raise_()
        self.button.setVisible(bool(button))
        self.button.raise_()
        if not was_shown:
            # The button is the window's own child, so it rises beside the card rather than with it.
            appear(self, self.motion, rise=True)
            appear(self.button, self.motion, rise=True)
        # One with something to press stays long enough to reach for it.
        self._timer.start(TOAST_MS * 2 if button else TOAST_MS)

    def _dress_button(self) -> None:
        # Undo is the one button with a picture: the arrow back, in the button's own colour.
        undo = self.button.text() == "Undo"
        self.button.setIcon(icons.icon("undo-2", self._action_colour) if undo else QIcon())
        self.button.setIconSize(QSize(14, 14))

    def reposition(self) -> None:
        host = self.parentWidget()
        if host is None:
            return
        over = self._over
        area = QRect(over.mapTo(host, QPoint(0, 0)), over.size()) if over.isVisible() else host.rect()
        # A wrapped label asks for a narrow width, which broke short notices after their
        # second-last word. Measured unwrapped, a notice keeps one line until the room runs out.
        self.label.setWordWrap(False)
        natural = self.sizeHint().width()
        self.label.setWordWrap(True)
        room = max(120, min(TOAST_MAX_WIDTH, area.width() - 2 * TOAST_FOOT) + 2 * TOAST_SHADOW)
        width = min(max(natural, TOAST_MIN_WIDTH), room)
        height = max(self.heightForWidth(width), self.minimumSizeHint().height())
        # Bottom right of the page, 16 pixels in from its corner, and never past the window's foot.
        right = area.left() + area.width() - TOAST_FOOT + TOAST_SHADOW
        bottom = min(area.top() + area.height(), host.height()) - TOAST_FOOT + TOAST_SHADOW
        self.setGeometry(max(0, right - width), max(0, bottom - height), width, height)

    def moveEvent(self, event: QMoveEvent) -> None:  # noqa: N802
        super().moveEvent(event)
        self._place_button()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_button()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802
        super().hideEvent(event)
        # Not when the window is: this notice comes back with it.
        if self.isHidden():
            self._timer.stop()
            self.button.hide()

    def _place_button(self) -> None:
        inside = self.card.contentsRect().translated(self.card.pos())
        size = self.button.sizeHint()
        self.button.setGeometry(
            self.x() + inside.right() + 1 - size.width(),
            self.y() + inside.top() + (inside.height() - size.height()) // 2,
            size.width(),
            size.height(),
        )

    def _pressed(self) -> None:
        callback = self._callback
        self.hide()
        if callback is not None:
            callback()

    def _go(self) -> None:
        vanish(self, self.motion)
        vanish(self.button, self.motion)


class FlowLayout(QLayout):
    """Left to right, wrapping onto new rows.

    The week page has about twenty actions. In a plain row their combined width became the window's
    minimum, over 2,300 pixels, which no laptop screen holds. Here the minimum is one button wide.
    """

    def __init__(self, parent: QWidget | None = None, gap: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._gap = gap

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 - Qt virtual
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - Qt virtual
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - Qt virtual
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802 - Qt virtual
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt virtual
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt virtual
        return self._arrange(QRect(0, 0, width, 0), place=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt virtual
        super().setGeometry(rect)
        self._arrange(rect, place=True)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt virtual
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt virtual
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _arrange(self, rect: QRect, place: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, row_height = area.x(), area.y(), 0
        for item in self._items:
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            if item.hasHeightForWidth():
                # A card whose words wrap is taller than its plain hint says; given only the hint,
                # the second line was drawn over whatever came next.
                hint.setHeight(item.heightForWidth(hint.width()))
            if row_height and x + hint.width() > area.right() + 1:
                x = area.x()
                y += row_height + self._gap
                row_height = 0
            if place:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._gap
            row_height = max(row_height, hint.height())
        return y + row_height - rect.y() + margins.bottom()


class AddMenu(Menu):
    """Everything that adds something to the week, in one menu.

    This was a strip of eight chips above the calendar, which armed a type for dragging, plus two Add
    buttons beside it. Ten controls, always on screen, for something a student does a few times a
    week. The types live here now, with their colours, and the button that opens this menu says which
    one a drag will make.
    """

    category_chosen = Signal(str)
    homework_requested = Signal()
    fixed_requested = Signal()
    school_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("addMenu")
        for name, words, icon, asked in (
            ("addMenuHomework", "Add homework…", "book-open", self.homework_requested),
            ("addMenuFixed", "Add fixed time…", "clock", self.fixed_requested),
            ("addMenuSchool", "School hours…", "school", self.school_requested),
        ):
            self.add(words, icon, name=name).triggered.connect(asked.emit)
        self.addSeparator()
        add_heading(self, "Then drag on the calendar")
        self._actions: dict[str, QAction] = {}
        for key, info in CATEGORIES.items():
            action = self.addAction(info["label"])
            action.setObjectName(f"addMenu-{key}")
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, value=key: self.category_chosen.emit(value))
            self._actions[key] = action

    def set_armed(self, category: str | None) -> None:
        for key, action in self._actions.items():
            action.setChecked(key == category)

    def set_palette(self, palette: dict, accent_chips: bool) -> None:
        """A colour beside each type, so the menu says what a block of it will look like. "Colour
        chips with my accent" paints them all in the accent, as it did the chips."""
        for key, action in self._actions.items():
            face = palette["accent"] if accent_chips else CATEGORIES[key]["mark"]
            action.setIcon(QIcon(swatch(face)))


def swatch(colour: str, size: int = SWATCH_PX) -> QPixmap:
    """A rounded square of one colour, for a menu row or a button."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor(colour))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, size, size, size // 4, size // 4)
    painter.end()
    return pixmap


_ART_STROKES = {
    "tick": ((QPoint(7, 17), QPoint(13, 23), QPoint(25, 9)), 4.0),
    "down": ((QPoint(9, 13), QPoint(16, 20), QPoint(23, 13)), 3.2),
    "up": ((QPoint(9, 19), QPoint(16, 12), QPoint(23, 19)), 3.2),
}


def _art_file(shape: str, colour: str) -> str:
    """One stroke in one colour as an image file, for a style sheet's `image:`. Drawn here rather than
    shipped, so the packaged app needs no extra file; twice its drawn size so it stays sharp."""
    folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
    path = folder / f"flexweek-{shape}-{QColor(colour).name()[1:]}.png"
    if not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        points, width = _ART_STROKES[shape]
        image = QPixmap(32, 32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(colour), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline(list(points))
        painter.end()
        image.save(str(path))
    return path.as_posix()


def _switch_file(on: bool, track: str, knob: str) -> str:
    """A switch's pill and knob as one image, the knob at the right when on. Drawn at twice the
    34 by 20 the style sheet shows it."""
    folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
    names = (QColor(track).name()[1:], QColor(knob).name()[1:], "on" if on else "off")
    path = folder / f"flexweek-switch-{'-'.join(names)}.png"
    if not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        image = QPixmap(68, 40)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(track))
        painter.drawRoundedRect(0, 0, 68, 40, 20, 20)
        painter.setBrush(QColor(knob))
        painter.drawEllipse(32 if on else 4, 4, 32, 32)
        painter.end()
        image.save(str(path))
    return path.as_posix()


def _icon_file(name: str, colour: str) -> str:
    """Lucide's `name` in `colour` as an image file, for a style sheet's `image:`, at twice 16 pixels."""
    folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
    path = folder / f"flexweek-icon-{name}-{QColor(colour).name()[1:]}.png"
    if not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        icons.pixmap(name, colour, 32).save(str(path))
    return path.as_posix()


def control_art(palette: dict) -> dict[str, str]:
    """The images the control rules in `pack_stylesheet` draw with: a tick in the accent's ink,
    chevrons for dropdowns and steppers in the muted ink, a switch on, off and greyed, and the
    chevron after More in the text colour."""
    return {
        "more": _icon_file("chevron-down", palette["text"]),
        "tick": _art_file("tick", palette["accent_ink"]),
        "down": _art_file("down", palette["muted"]),
        "up": _art_file("up", palette["muted"]),
        "switch_on": _switch_file(True, palette["accent"], palette["accent_ink"]),
        "switch_off": _switch_file(False, palette["hairline_strong"], "#ffffff"),
        "switch_on_off": _switch_file(True, palette["hairline_strong"], palette["hairline"]),
        "switch_off_off": _switch_file(False, palette["hairline"], palette["hairline_strong"]),
    }


def rounded_picture(picture: QPixmap, radius: int) -> QPixmap:
    """The picture with its corners rounded to match the card it sits in."""
    ratio = picture.devicePixelRatio()
    out = QPixmap(picture.size())
    out.setDevicePixelRatio(ratio)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, picture.width() / ratio, picture.height() / ratio), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, picture)
    painter.end()
    return out


class ChoiceCard(QFrame):
    """A picture and a name the student picks by clicking, or by Space or Enter."""

    chosen = Signal()

    def __init__(self, name: str, note: str, width: int) -> None:
        super().__init__()
        self.setObjectName("setupChoice")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(name)
        self.setAccessibleDescription(note)
        self._width = width
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 10, 10, 12)
        box.setSpacing(6)
        self.picture = QLabel()
        self.picture.setObjectName("setupChoicePicture")
        self.picture.setFixedSize(width, round(width * 0.625))
        box.addWidget(self.picture)
        name_label = QLabel(name)
        name_label.setObjectName("setupChoiceName")
        name_label.setWordWrap(True)
        box.addWidget(name_label)
        self.note = QLabel(note)
        self.note.setObjectName("setupChoiceNote")
        self.note.setWordWrap(True)
        box.addWidget(self.note)
        box.addStretch(1)
        self.setFixedWidth(width + 22)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.select(False)

    def set_picture(self, picture: QPixmap) -> None:
        self.picture.setPixmap(rounded_picture(picture, 6))

    def select(self, on: bool) -> None:
        self.setProperty("selected", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def is_selected(self) -> bool:
        return bool(self.property("selected"))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.chosen.emit()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.chosen.emit()
            return
        super().keyPressEvent(event)


def plain_card() -> tuple[QFrame, QVBoxLayout]:
    """A dialog's body as one card on its page, with no heading of its own: the window names it."""
    card = QFrame()
    card.setObjectName("dialogCard")
    box = QVBoxLayout(card)
    box.setContentsMargins(16, 16, 16, 16)
    box.setSpacing(8)
    return card, box


def info_card(title: str, note: str) -> tuple[QFrame, QVBoxLayout]:
    """A card in a dialog: what it is for, as a heading and a sentence, then its controls."""
    card = QFrame()
    card.setObjectName("dialogCard")
    box = QVBoxLayout(card)
    # 12 above and below, a step under the sides: Account's three cards at the 13-point body stood 778
    # pixels tall, more than a 1366 by 768 laptop has.
    box.setContentsMargins(SPACING[3], SPACING[2], SPACING[3], SPACING[2])
    box.setSpacing(SPACING[1])
    heading = QLabel(title)
    heading.setObjectName("cardTitle")
    # One line, not wrapped: a dialog's height is fixed before its words wrap, so a sentence that
    # took two lines squeezed the card and drew its list over its button.
    words = QLabel(note)
    words.setObjectName("cardNote")
    box.addWidget(heading)
    box.addWidget(words)
    return card, box


class Switch(QCheckBox):
    """On or off, drawn as a toggle by the style sheet. Still a check box, so it is read, set and
    announced as one.

    Its words wrap under their own first line, as a label's do: a check box's words are one line, so
    at Large text "Split long homework into focus sessions" made Settings wider than an 800 pixel
    window. The style draws the toggle; the words are drawn here."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("switch", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # A check box's own policy makes its one line the least it may be given.
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def _toggle(self) -> tuple[QStyleOptionButton, QRect, int]:
        """The style's option with no words, where it draws the toggle, and the room after it."""
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        mark = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        gap = self.style().pixelMetric(QStyle.PixelMetric.PM_CheckBoxLabelSpacing, option, self)
        return option, mark, mark.right() + 1 + gap

    def _words(self, width: int) -> QRect:
        return self.fontMetrics().boundingRect(
            QRect(0, 0, max(width, 1), 100_000), int(Qt.TextFlag.TextWordWrap), self.text()
        )

    def sizeHint(self) -> QSize:  # noqa: N802
        _option, mark, start = self._toggle()
        words = self.fontMetrics().size(0, self.text())
        return QSize(start + words.width() + 2, max(mark.height(), words.height()) + 2)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        _option, mark, start = self._toggle()
        longest = max((self.fontMetrics().horizontalAdvance(word) for word in self.text().split()), default=0)
        return QSize(start + longest + 2, mark.height())

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        _option, mark, start = self._toggle()
        return max(mark.height(), self._words(width - start - 2).height()) + 2

    def hitButton(self, pos: QPoint) -> bool:  # noqa: N802
        return self.rect().contains(pos)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        option, mark, start = self._toggle()
        painter = QStylePainter(self)
        painter.drawControl(QStyle.ControlElement.CE_CheckBox, option)
        group = QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        painter.setPen(self.palette().color(group, QPalette.ColorRole.WindowText))
        words = self._words(self.width() - start - 2)
        # The first line sits level with the toggle; the rest run under it.
        top = max(0, (mark.height() - self.fontMetrics().height()) // 2) + mark.top()
        painter.drawText(
            QRect(start, top, self.width() - start - 2, words.height()),
            int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
            self.text(),
        )


class Choices(QFrame):
    """One of a few values, answering the calls a dropdown answers, so the code that reads and sets a
    setting does not care which control shows it."""

    currentIndexChanged = Signal(int)  # noqa: N815

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._texts: list[str] = []
        self._data: list[object] = []
        self._index = -1

    def count(self) -> int:
        return len(self._data)

    def itemText(self, index: int) -> str:  # noqa: N802
        return self._texts[index]

    def itemData(self, index: int) -> object:  # noqa: N802
        return self._data[index]

    def findData(self, value: object) -> int:  # noqa: N802
        return self._data.index(value) if value in self._data else -1

    def currentIndex(self) -> int:  # noqa: N802
        return self._index

    def currentData(self) -> object:  # noqa: N802
        return self._data[self._index] if 0 <= self._index < len(self._data) else None

    def currentText(self) -> str:  # noqa: N802
        return self._texts[self._index] if 0 <= self._index < len(self._texts) else ""

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if not -1 <= index < len(self._data) or index == self._index:
            self._show(self._index)
            return
        self._index = index
        self._show(index)
        self.currentIndexChanged.emit(index)

    def _remember(self, text: str, data: object) -> int:
        self._texts.append(text)
        self._data.append(data)
        return len(self._data) - 1

    def _show(self, index: int) -> None:
        raise NotImplementedError


class Segmented(Choices):
    """Two or three choices side by side in one track, the chosen one raised."""

    def __init__(self, choices: tuple[tuple[str, object], ...] = (), name: str = "") -> None:
        super().__init__()
        self.setProperty("segmented", True)
        if name:
            self.setObjectName(name)
        self._line = QHBoxLayout(self)
        self._line.setContentsMargins(2, 2, 2, 2)
        self._line.setSpacing(2)
        self._buttons: list[QPushButton] = []
        # Ids, not a lambda per button: a lambda naming the control kept it from being freed.
        self._group = QButtonGroup(self)
        self._group.setExclusive(False)
        self._group.idClicked.connect(self.setCurrentIndex)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        for text, data in choices:
            self.addItem(text, data)

    def addItem(self, text: str, data: object = None) -> None:  # noqa: N802
        index = self._remember(text, data)
        button = QPushButton(text)
        button.setObjectName(f"{self.objectName()}-{data}" if self.objectName() else "")
        button.setProperty("segment", True)
        # A choice shown, never what Enter presses in a dialog.
        button.setAutoDefault(False)
        button.setCheckable(True)
        button.setAccessibleName(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._group.addButton(button, index)
        self._line.addWidget(button)
        self._buttons.append(button)
        # A segment ticked from code chooses it too, as a radio button's tick does.
        button.toggled.connect(self._follow)
        if self._index < 0:
            self.setCurrentIndex(index)

    def buttons(self) -> list[QPushButton]:
        return list(self._buttons)

    def _follow(self, on: bool) -> None:
        index = self._buttons.index(self.sender()) if self.sender() in self._buttons else -1
        if on and index != self._index:
            self.setCurrentIndex(index)

    def _show(self, index: int) -> None:
        for at, button in enumerate(self._buttons):
            button.setChecked(at == index)


class SwatchButton(QAbstractButton):
    """One colour to pick: a round swatch with its name under it. The chosen one is ringed and ticked,
    so it is told by more than its colour."""

    SIZE = 28
    DISABLED = 0.4

    def __init__(self, text: str) -> None:
        super().__init__()
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(text)
        self.fill = "#808080"
        self.ink = "#ffffff"

    def sizeHint(self) -> QSize:  # noqa: N802
        words = self.fontMetrics()
        ring = self.SIZE + 2 * SPACING[0]
        return QSize(max(ring, words.horizontalAdvance(self.text()) + SPACING[1]), ring + words.height() + 2)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.isEnabled() and not self.isChecked():
            # As a segment that cannot be chosen: faint, with the chosen one still clear.
            painter.setOpacity(self.DISABLED)
        ring = self.SIZE + 2 * SPACING[0]
        left = (self.width() - ring) / 2
        colour = QColor(self.fill)
        if self.isChecked() or self.hasFocus():
            # A ring clear of the swatch: the accent's own colour when chosen, half of it on focus.
            edge = QColor(colour)
            if not self.isChecked():
                edge.setAlphaF(0.4)
            painter.setPen(QPen(edge, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(left + 1, 1, ring - 2, ring - 2))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        inset = SPACING[0]
        painter.drawEllipse(QRectF(left + inset, inset, self.SIZE, self.SIZE))
        if self.isChecked():
            tick = 16
            ratio = self.devicePixelRatioF()
            mark = icon_pixmap("check", self.ink, tick, ratio)
            painter.drawPixmap(round(left + (ring - tick) / 2), round((ring - tick) / 2), mark)
        words = self.palette().color(QPalette.ColorRole.WindowText)
        painter.setPen(words)
        painter.setFont(weighted(self.font(), WEIGHT_STRONG if self.isChecked() else WEIGHT_REGULAR))
        below = QRectF(0, ring + 2, self.width(), self.height() - ring - 2)
        painter.drawText(below, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), self.text())
        painter.end()


class Swatches(Choices):
    """A few colours side by side, as swatches, answering the calls a dropdown answers."""

    def __init__(self, choices: tuple[tuple[str, object], ...] = (), name: str = "") -> None:
        super().__init__()
        bare(self)
        if name:
            self.setObjectName(name)
        self._line = QHBoxLayout(self)
        self._line.setContentsMargins(0, 0, 0, 0)
        self._line.setSpacing(SPACING[2])
        self._buttons: list[SwatchButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(False)
        self._group.idClicked.connect(self.setCurrentIndex)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        for text, data in choices:
            self.addItem(text, data)

    def addItem(self, text: str, data: object = None) -> None:  # noqa: N802
        index = self._remember(text, data)
        button = SwatchButton(text)
        button.setObjectName(f"{self.objectName()}-{data}" if self.objectName() else "")
        self._group.addButton(button, index)
        self._line.addWidget(button)
        self._buttons.append(button)
        if self._index < 0:
            self.setCurrentIndex(index)

    def buttons(self) -> list[SwatchButton]:
        return list(self._buttons)

    def set_colours(self, colours: dict[object, tuple[str, str]]) -> None:
        """Each swatch's (colour, tick colour), by its value."""
        for data, button in zip(self._data, self._buttons, strict=True):
            button.fill, button.ink = colours.get(data, (button.fill, button.ink))
            button.update()

    def _show(self, index: int) -> None:
        for at, button in enumerate(self._buttons):
            button.setChecked(at == index)


def confirm_box(
    parent: QWidget | None, title: str, question: str, yes: str, *, danger: bool = True
) -> QMessageBox:
    """A question before something that cannot be taken back lightly. The answer buttons say what
    they do, and Cancel is the default, so Enter pressed out of habit changes nothing. The answer is
    red only when it destroys something; logging out keeps everything, so it is not."""
    box = QMessageBox(parent)
    box.setObjectName("confirmBox")
    box.setIcon(QMessageBox.Icon.NoIcon)
    box.setWindowTitle(title)
    box.setText(question)
    # Looks set before the box adds them: it styles a button as it adds it, so Delete set red afterwards
    # was drawn in the accent colour. Given the box as parent, since PySide does not hand a button added
    # this way to the box, and it was freed with the last Python name for it.
    go = QPushButton(yes, box)
    go.setObjectName("confirmYes")
    go.setProperty("danger", danger)
    stay = QPushButton("Cancel", box)
    stay.setObjectName("confirmCancel")
    stay.setProperty("quiet", True)
    box.addButton(go, QMessageBox.ButtonRole.DestructiveRole)
    box.addButton(stay, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(stay)
    box.setEscapeButton(stay)
    return box


def confirm(parent: QWidget | None, title: str, question: str, yes: str, *, danger: bool = True) -> bool:
    box = confirm_box(parent, title, question, yes, danger=danger)
    box.exec()
    chosen = box.clickedButton()
    return chosen is not None and chosen.objectName() == "confirmYes"


def add_heading(menu: QMenu, text: str) -> QWidgetAction:
    """A heading row. Fusion draws `QMenu.addSection` as a bare separator, so the More menu's Adding
    and Planning were never shown in any design."""
    label = QLabel(text)
    label.setObjectName("menuHeading")
    action = QWidgetAction(menu)
    action.setDefaultWidget(label)
    action.setEnabled(False)
    menu.addAction(action)
    return action


class DayAgenda(QWidget):
    item_activated = Signal(str)
    homework_activated = Signal(str)
    plan_requested = Signal()
    add_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dayAgenda")
        layout = QVBoxLayout(self)
        self.heading = QLabel()
        self.heading.setObjectName("dayTitle")
        layout.addWidget(self.heading)
        self.next_action = QPushButton()
        self.next_action.setObjectName("dayNextAction")
        self.next_action.clicked.connect(self._on_next)
        action_row = QHBoxLayout()
        action_row.addWidget(self.next_action)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        self.list = QListWidget()
        self.list.setObjectName("dayList")
        self.list.itemDoubleClicked.connect(self._on_item)
        layout.addWidget(self.list)
        self._next_kind = "add"
        self._next_id: str | None = None

    def set_agenda(self, iso_day: str, agenda: dict, day_data: dict | None) -> None:
        day_index = agenda["day_index"]
        name = DAY_FULL[day_index] if 0 <= day_index <= 6 else iso_day
        self.heading.setText(date.fromisoformat(iso_day).strftime("%A, %b %d"))
        nxt = agenda["next_action"]
        self._next_kind = nxt["kind"]
        self._next_id = nxt.get("id")
        labels = {
            "add": "Add homework",
            "plan": "Plan my homework",
            "start": "Open the next session",
        }
        self.next_action.setText(labels[nxt["kind"]])
        self.list.clear()
        if not agenda["due_soon"] and not agenda["sessions"] and not agenda["fixed"]:
            empty = QListWidgetItem(f"Nothing is due soon and nothing is planned for {name}.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)
            return
        week_start = monday_of(iso_day)
        load = (day_data or {}).get("workload") or {}
        if load:
            work = QListWidgetItem(
                f"{length_label(load.get('scheduled_min', 0))} planned"
                f" · {length_label(load.get('available_min', 0))} free"
            )
            work.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(work)
        unplaced = [row for row in agenda["sessions"] if not row["start"]]
        timeline = [("session", row) for row in agenda["sessions"] if row["start"]]
        timeline.extend(("fixed", row) for row in agenda["fixed"])
        timeline.sort(key=lambda pair: str(pair[1]["start"]))
        for row in unplaced:
            block = row["block"]
            item = self._row(
                f"not placed yet · {block['title']} · {length_label(block.get('duration_min') or 0)}",
                block.get("category") or "assignments",
            )
            item.setData(Qt.ItemDataRole.UserRole, {"kind": "block", "id": block["id"]})
            self.list.addItem(item)
        for _kind, row in timeline:
            block = row["block"]
            duration = int(block.get("duration_min") or 0)
            item = self._row(
                f"{hhmm_text(row['start'])} · {block['title']} · {length_label(duration)}",
                block.get("category") or "",
            )
            item.setData(Qt.ItemDataRole.UserRole, {"kind": "block", "id": block["id"]})
            item.setSizeHint(QSize(0, max(28, min(160, duration // 3))))
            self.list.addItem(item)
        for item in agenda["due_soon"]:
            # A student reads "Thu 17 Sep", not "2026-09-17T23:59". due_label is what every other
            # surface in the app already uses.
            row = self._row(
                f"{item['title']} · due {due_label(item.get('due'), week_start)}",
                item.get("category") or "assignments",
            )
            row.setData(Qt.ItemDataRole.UserRole, {"kind": "homework", "id": item["id"]})
            self.list.addItem(row)

    def _section(self, title: str, rows: list) -> None:
        if not rows:
            return
        head = QListWidgetItem(title.upper())
        head.setFlags(Qt.ItemFlag.NoItemFlags)
        self.list.addItem(head)

    @staticmethod
    def _row(words: str, category: str) -> QListWidgetItem:
        """One agenda row, with the category's own colour beside it, as every other surface paints it."""
        item = QListWidgetItem(words)
        mark = (CATEGORIES.get(category) or {}).get("mark")
        if mark:
            item.setData(Qt.ItemDataRole.DecorationRole, QColor(mark))
        return item

    def _on_next(self) -> None:
        if self._next_kind == "plan":
            self.plan_requested.emit()
        elif self._next_kind == "add":
            self.add_requested.emit()
        elif self._next_id:
            self.item_activated.emit(self._next_id)
        else:
            for index in range(self.list.count()):
                candidate = self.list.item(index)
                data = candidate.data(Qt.ItemDataRole.UserRole) if candidate else None
                if data and data.get("kind") == "block":
                    self.item_activated.emit(data["id"])
                    return

    def _on_item(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        if data.get("kind") == "homework":
            self.homework_activated.emit(data["id"])
        elif data.get("kind") == "block":
            self.item_activated.emit(data["id"])


def _line(name: str, text: str = "", limit: int = 80) -> QLineEdit:
    field = QLineEdit(text)
    field.setObjectName(name)
    field.setMaxLength(limit)
    return field


class LengthBox(QSpinBox):
    """A homework's length in minutes. The arrows stop at 15 minutes and at a day. A length typed past
    either end is kept as typed, so the editor says what is wrong with it: a box that stopped at 15
    turned a typed 0 back into the last length without a word."""

    def __init__(self, name: str, value: int) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setRange(0, 9999)
        self.setSingleStep(SLOT_MIN)
        self.setSuffix(" min")
        self.setValue(value)

    def stepBy(self, steps: int) -> None:  # noqa: N802 - Qt virtual
        self.setValue(min(max(self.value() + steps * self.singleStep(), SLOT_MIN), ESTIMATE_MAX_MIN))

    def stepEnabled(self) -> QAbstractSpinBox.StepEnabledFlag:  # noqa: N802 - Qt virtual
        flags = QAbstractSpinBox.StepEnabledFlag.StepNone
        if self.value() < ESTIMATE_MAX_MIN:
            flags |= QAbstractSpinBox.StepEnabledFlag.StepUpEnabled
        if self.value() > SLOT_MIN:
            flags |= QAbstractSpinBox.StepEnabledFlag.StepDownEnabled
        return flags


def _error_label() -> QLabel:
    label = QLabel()
    label.setObjectName("validationError")
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setAccessibleName("Validation error")
    return label


def _buttons(dialog: QDialog) -> QDialogButtonBox:
    """Save and Cancel, in the order the platform puts them. Made inside `dialog`, so Save is the
    dialog's own default: made outside it, Enter pressed the first button after the title instead,
    More details in the homework editor."""
    choices = QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    buttons = QDialogButtonBox(choices, dialog)
    buttons.setObjectName("dialogButtons")
    for button in buttons.buttons():
        # KDE's style puts a floppy disk on Save and a red X on Cancel.
        button.setIcon(QIcon())
    buttons.button(QDialogButtonBox.StandardButton.Save).setDefault(True)
    cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    cancel.setProperty("quiet", True)
    # Already under the style sheet, so it is drawn again as the plain button it now is.
    cancel.style().unpolish(cancel)
    cancel.style().polish(cancel)
    return buttons


def _preset_locked(category: str | None, day: int, start: str, duration_min: int) -> dict:
    info = CATEGORIES.get(category or "")
    days = [day]
    title = ""
    chosen_start = start
    chosen_duration = duration_min
    if info is not None:
        title = info["label"]
        preset = info["preset"]
        if duration_min == 60 and start == "16:00" and "start" in preset:
            chosen_start = preset["start"]
            chosen_duration = hhmm_to_minutes(preset["end"]) - hhmm_to_minutes(preset["start"])
            days = list(preset.get("days") or [day])
        elif "start" not in preset:
            chosen_duration = preset.get("duration_min", duration_min)
    return {
        "id": str(uuid4()),
        "kind": "locked",
        "title": title,
        "days": days,
        "start": chosen_start,
        "duration_min": chosen_duration,
        "category": category,
    }


def bare(widget: QWidget) -> QWidget:
    """A box that only holds other widgets: it paints nothing, so a dialog's body is its card and not
    a pale box inside it."""
    widget.setProperty("bare", True)
    return widget


def _first_line(field: QWidget | QLayout | None) -> QWidget | None:
    """The control on a field's first line: the field itself, or the first control in a box of them."""
    if isinstance(field, QLayout):
        for index in range(field.count()):
            item = field.itemAt(index)
            found = _first_line(item.widget() or item.layout())
            if found is not None:
                return found
        return None
    lead = getattr(field, "first_line", None)
    if callable(lead):
        return lead()
    holder = (QFrame, QAbstractSpinBox, QComboBox, QLineEdit, QAbstractButton, QLabel)
    if field is not None and not isinstance(field, holder) and field.layout() is not None:
        return _first_line(field.layout())
    return field


class FieldLabel(QLabel):
    """A form's label, as tall as its field's first line and centred in it, so its words sit on the
    same line as the words in the field. QFormLayout set a label level with the field's top edge,
    a few pixels above them (decision 23 of 0.17)."""

    def __init__(self, words: str, line: QWidget | None) -> None:
        super().__init__(words)
        self._line = line
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # Fixed, so the form gives it exactly its height and does not stretch it down a tall field.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _tall(self, size: QSize) -> QSize:
        if self._line is None:
            return size
        return QSize(size.width(), max(size.height(), self._line.sizeHint().height()))

    def sizeHint(self) -> QSize:  # noqa: N802
        return self._tall(super().sizeHint())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self._tall(super().minimumSizeHint())


class Form(QFormLayout):
    """A form whose labels sit on their fields' line of words. A text label given with its field is
    made a FieldLabel for that field."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def addRow(self, *row: object) -> None:  # noqa: N802
        if len(row) == 2 and isinstance(row[0], str):
            words, field = row
            super().addRow(FieldLabel(words, _first_line(field)), field)
            return
        super().addRow(*row)


def field_kind(widget: QWidget) -> str | None:
    """What a field holds, which decides its width. A text field is none of these: it takes the row."""
    if isinstance(widget, QTimeEdit):
        return "time"
    if isinstance(widget, QDateEdit):
        return "date"
    if isinstance(widget, QSpinBox):
        return "number"
    if isinstance(widget, QComboBox) and not widget.isEditable():
        return "choice"
    return None


def even_fields(root: QWidget) -> None:
    """One width per kind of field (decision 23 of 0.17): every time box as wide as the widest time box
    in `root`, and so for dates, numbers and dropdowns. Each was as wide as its text or its row: a
    200-pixel date in a 340-pixel column, and Start and End 420 pixels for five characters."""
    kinds: dict[str, list[QWidget]] = {}
    for widget in root.findChildren(QWidget):
        kind = field_kind(widget)
        # A popup's own boxes, such as a date's calendar, are in a window of their own.
        if kind is not None and widget.window() is root.window():
            kinds.setdefault(kind, []).append(widget)
    for fields in kinds.values():
        width = max(field.sizeHint().width() for field in fields)
        for field in fields:
            if field.width() != width or field.minimumWidth() != width:
                field.setFixedWidth(width)


class FitScroll(QScrollArea):
    """A dialog's body that scrolls only past the room it is given. A plain scroll area asks for a
    modest fixed height, so a dialog opened short of its content, or tall with nothing in it."""

    def __init__(self, body: QWidget, name: str) -> None:
        super().__init__()
        self.setObjectName(name)
        bare(self)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # The keyboard starts on the first field in it, not on the box around them.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWidget(bare(body))

    def _extra(self) -> QSize:
        margins = self.contentsMargins()
        return QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def sizeHint(self) -> QSize:  # noqa: N802
        wanted = self.widget().sizeHint() + self._extra()
        return QSize(max(super().sizeHint().width(), wanted.width()), wanted.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # As wide as its widest row, since it never scrolls sideways; as short as a few lines.
        least = super().minimumSizeHint()
        return QSize(max(least.width(), self.widget().minimumSizeHint().width() + self._extra().width()),
                     least.height())

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return self.widget().hasHeightForWidth()

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        extra = self._extra()
        return self.widget().heightForWidth(width - extra.width()) + extra.height()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        # A scroll area hears its content change size but keeps asking its dialog for the old one.
        if watched is self.widget() and event.type() == QEvent.Type.LayoutRequest:
            self.updateGeometry()
        return super().eventFilter(watched, event)


# A sheet's card is lifted off the dimmed window by the large shadow (decision 6 of 0.17), which needs
# this much room around the card to be drawn; the card keeps SHEET_GAP from the window's edges, and the
# window behind it is dimmed by SHEET_DIM of black.
SHEET_ROOM = SHADOW_LARGE.y + SHADOW_LARGE.blur
SHEET_GAP = SPACING[4]
SHEET_PAD = SPACING[4]
SHEET_DIM = 0.4


class SheetShade(QWidget):
    """The window under a sheet, dimmed, so the sheet reads as the one thing to answer. It only paints:
    the sheet is modal, so the window takes no clicks while it is up."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setObjectName("sheetShade")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, round(255 * SHEET_DIM)))
        painter.end()


class Dialog(QDialog):
    """A dialog that eases in the first time it shows, at the app's motion level, with one width for
    each kind of field in it.

    A sheet (decision 23 of 0.17) is drawn inside its window rather than as a window of its own: its
    card, with the large shadow, over the window dimmed. To Qt it is still a modal dialog, so the
    window's keys wait for it and `activeModalWidget` finds it. Made without a parent it is a window."""

    _appeared = False
    _shade: SheetShade | None = None

    def __init__(self, parent: QWidget | None = None, *, sheet: bool = False) -> None:
        super().__init__(parent)
        self.sheet = sheet and parent is not None
        self.card: QFrame | None = None
        # The sheet's card and the room for its shadow, which fade in as one: the card's own effect
        # is its shadow, and a widget holds one effect.
        self._face: QWidget | None = None
        if self.sheet:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setProperty("sheet", True)

    def card_body(self) -> QVBoxLayout:
        """The layout the dialog's content goes in, on its one card: the sheet itself, or the card on a
        window's page. The body is the card, not a box drawn inside it."""
        outer = QVBoxLayout(self)
        self.card = QFrame()
        self.card.setObjectName("sheetCard")
        inner = QVBoxLayout(self.card)
        inner.setContentsMargins(SHEET_PAD, SHEET_PAD, SHEET_PAD, SHEET_PAD)
        inner.setSpacing(SPACING[2])
        if self.sheet:
            self._face = bare(QWidget())
            self._face.setObjectName("sheetFace")
            around = QVBoxLayout(self._face)
            around.setContentsMargins(SHEET_ROOM, SHEET_ROOM, SHEET_ROOM, SHEET_ROOM)
            around.addWidget(self.card)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(self._face)
        else:
            outer.addWidget(self.card)
        return inner

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        even_fields(self)
        if self.sheet:
            self._over_window()
        self.refit()
        if not self._appeared:
            self._appeared = True
            level = app_level()
            for part in self._content():
                appear(part, level, rise=True)
            if self._shade is not None:
                appear(self._shade, level)

    def _content(self) -> list[QWidget]:
        """What fades in and rises the first time the dialog shows (decision 31 of 0.17): a window's
        own opacity is ignored on Wayland, and an effect on a window draws its insides over nothing,
        so the fade goes on what the window holds."""
        if self._face is not None:
            return [self._face]
        if self.card is not None:
            return [self.card]
        direct = Qt.FindChildOption.FindDirectChildrenOnly
        return [
            child
            for child in self.findChildren(QWidget, options=direct)
            if not child.isWindow() and child.graphicsEffect() is None
        ]

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802
        super().hideEvent(event)
        if self._shade is not None:
            self._shade.deleteLater()
            self._shade = None
            self.parentWidget().window().removeEventFilter(self)

    def refit(self, *_changed: object) -> None:
        """Size the dialog to what it holds again, once what changed has been laid out: its fonts
        and padding arrive with the style sheet after it shows, and More details makes it taller."""
        QTimer.singleShot(0, self._refit_now)

    def _refit_now(self) -> None:
        if not self.isVisible():
            return
        # A card keeps telling its dialog the size it had before the style sheet reached it, so
        # fields were squeezed over each other; each part is asked again.
        for child in self.findChildren(QWidget):
            child.updateGeometry()
        layout = self.layout()
        if layout is None:
            return
        layout.activate()
        if self.sheet:
            self._over_window()
            return
        wanted = self.sizeHint()
        width = max(self.width(), wanted.width())
        tall = layout.totalHeightForWidth(width) if layout.hasHeightForWidth() else wanted.height()
        height = max(self.height(), wanted.height(), tall)
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            width, height = min(width, screen.width() - 48), min(height, screen.height() - 48)
        if (width, height) != (self.width(), self.height()):
            self.resize(width, height)

    def _over_window(self) -> None:
        """The sheet at its content's size, as much as its window has room for, centred over it, and
        the window dimmed behind it."""
        host = self.parentWidget().window()
        room = host.geometry()
        most_w = room.width() - 2 * SHEET_GAP + 2 * SHEET_ROOM
        most_h = room.height() - 2 * SHEET_GAP + 2 * SHEET_ROOM
        # Measured from the card itself: the dialog's layout keeps the card's size from before its fonts
        # arrived.
        card = self.card
        shadow = 2 * SHEET_ROOM
        hint = card.sizeHint().expandedTo(card.minimumSizeHint()).expandedTo(card.minimumSize())
        inner = min(hint.width(), most_w - shadow)
        # Words that wrap need the height they take at this width, not at the width they would like.
        tall = card.heightForWidth(inner) if card.hasHeightForWidth() else hint.height()
        width = inner + shadow
        height = min(max(hint.height(), tall) + shadow, most_h)
        self.setFixedSize(width, height)
        self.move(room.x() + (room.width() - width) // 2, room.y() + (room.height() - height) // 2)
        if self.card is not None and self.card.graphicsEffect() is None:
            dark = self.palette().color(QPalette.ColorRole.WindowText).lightness() > 128
            lift(self.card, SHADOW_LARGE, dark)
        if self._shade is None:
            self._shade = SheetShade(host)
            # Gone with the sheet however it goes, even if it is freed while still on screen.
            self.destroyed.connect(self._shade.deleteLater)
            host.installEventFilter(self)
        self._shade.setGeometry(host.rect())
        self._shade.show()
        self._shade.raise_()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if (
            self._shade is not None
            and watched is self.parentWidget().window()
            and event.type() in (QEvent.Type.Resize, QEvent.Type.Move)
        ):
            self._over_window()
        return super().eventFilter(watched, event)


class BlockDialog(Dialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        block: dict | None = None,
        day: int = 0,
        start: str = "16:00",
        duration_min: int = 60,
        category: str | None = None,
        occurrence_day: int | None = None,
        from_range: bool = False,
    ) -> None:
        super().__init__(parent, sheet=True)
        if block is not None:
            self._original = deepcopy(block)
        elif from_range:
            info = CATEGORIES.get(category or "")
            self._original = {
                "id": str(uuid4()),
                "kind": "locked",
                "title": info["label"] if info else "",
                "days": [day],
                "start": start,
                "duration_min": duration_min,
                "category": category,
            }
        else:
            self._original = _preset_locked(category, day, start, duration_min)
        self._result: dict | None = None
        self._deleted = False
        self._occurrence_day = occurrence_day
        self._series_days: list[bool] | None = None
        existing = block is not None
        series = existing and is_series(self._original)
        self.setWindowTitle("Edit event" if existing else "New event")
        self.setObjectName("blockDialog")
        layout = self.card_body()
        body = QWidget()
        form = Form(body)
        form.setContentsMargins(0, 0, 0, 0)
        self.title = _line("blockTitle", self._original["title"])
        form.addRow("Title", self.title)
        self.days = []
        choices = QHBoxLayout()
        for index, name in enumerate(DAYS):
            check = QCheckBox(name)
            check.setObjectName(f"blockDay{index}")
            check.setChecked(index in self._original["days"])
            choices.addWidget(check)
            self.days.append(check)
        # A week's blocks are its own, so ticking more days repeats a block within this week only.
        # One line, never wrapped, under the boxes it is about. Wrapped, the form gave it two lines'
        # height for one line of words, or one line's height for two.
        self.repeat_note = QLabel(REPEAT_NOTE)
        self.repeat_note.setObjectName("blockRepeatNote")
        days_field = QVBoxLayout()
        days_field.addLayout(choices)
        days_field.addWidget(self.repeat_note)
        # The label sits on the boxes' line, not halfway down to the note.
        form.addRow("Days", days_field)
        # Which days a change reaches matters only for a block that repeats, opened on one of its days:
        # a choice of two, under the days it is about (decision 23 of 0.17).
        scopes = (("This day only", "occurrence"), ("Every selected day", "series"))
        self.scope_choice = Segmented(scopes, "editScope")
        self.scope_occurrence, self.scope_series = self.scope_choice.buttons()
        self.scope_occurrence.setObjectName("scopeOccurrence")
        self.scope_series.setObjectName("scopeSeries")
        self.scope_choice.setCurrentIndex(1)
        scope_box = self.scope_choice
        form.addRow("Apply to", scope_box)
        form.setRowVisible(scope_box, bool(series and occurrence_day is not None))
        note = QLabel("Changes apply to every selected day in this series.")
        note.setObjectName("seriesScope")
        # isHidden, not isVisible: nothing is visible before the dialog is shown, so the note stood over
        # "This day only" and "Every selected day" and contradicted the first.
        form.addRow("", note)
        repeating = existing and len(self._original.get("days") or []) > 1
        form.setRowVisible(note, repeating and scope_box.isHidden())
        self.scope_choice.currentIndexChanged.connect(self._sync_scope)
        self.start = QTimeEdit(QTime.fromString(self._original.get("start") or start, "HH:mm"))
        self.start.setDisplayFormat(time_format())
        self.start.setObjectName("blockStart")
        form.addRow("Start", self.start)
        # Start and End are what a student knows ("08:00 to 14:30"); the length is worked out from
        # them. A Duration box beside End was a second way to say the same thing, and could disagree.
        self._length = int(self._original["duration_min"])
        self.end = QTimeEdit(self._minutes_clock(self._clock_minutes(self.start.time()) + self._length))
        self.end.setDisplayFormat(time_format())
        self.end.setObjectName("blockEnd")
        form.addRow("End", self.end)
        self.duration_line = QLabel()
        self.duration_line.setObjectName("blockDurationLine")
        form.addRow("", self.duration_line)
        self.start.timeChanged.connect(self._keep_length)
        self.end.timeChanged.connect(self._show_length)
        self._show_length()
        self.category = QComboBox()
        self.category.setObjectName("blockCategory")
        self.category.addItem("None", None)
        for key, info in CATEGORIES.items():
            self.category.addItem(info["label"], key)
        chosen = self._original.get("category") or category
        if chosen and self.category.findData(chosen) < 0:
            self.category.addItem(chosen, chosen)
        self.category.setCurrentIndex(max(0, self.category.findData(chosen)))
        form.addRow("Category", self.category)
        # A block could carry a Spotify link from the web, and the Spotify button already opens it,
        # but there was no way to set one here. The link is validated with the rest of the block.
        self.spotify = _line("blockSpotify", self._original.get("spotify_url") or "", 500)
        self.spotify.setPlaceholderText("https://open.spotify.com/…")
        form.addRow("Spotify link", self.spotify)
        self.missed = QCheckBox(
            "I missed it" if occurrence_day is None else f"I missed it on {DAY_FULL[occurrence_day]}"
        )
        self.missed.setObjectName("blockMissed")
        already = occurrence_day in (self._original.get("missed_days") or [])
        self.missed.setChecked(already)
        form.addRow("", self.missed)
        form.setRowVisible(self.missed, bool(existing and occurrence_day is not None))
        layout.addWidget(FitScroll(body, "blockScroll"), 1)
        self.error = _error_label()
        layout.addWidget(self.error)
        # Delete is not one of the dialog's answers: quiet words at the left, away from Save.
        row = QHBoxLayout()
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("deleteBlock")
        self.delete_button.setAutoDefault(False)
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.setVisible(existing)
        self.delete_button.clicked.connect(self._delete)
        row.addWidget(self.delete_button)
        row.addStretch(1)
        buttons = _buttons(self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        layout.addLayout(row)
        self._sync_scope()

    def _sync_scope(self, *_index: object) -> None:
        occurrence = self.scope_occurrence.isChecked() and self._occurrence_day is not None
        # "This day only" ticks one day. Going back used to leave it that way, so Save took the block
        # off every other day. The series' ticks are kept while the one-day view is showing.
        if occurrence and self._series_days is None:
            self._series_days = [check.isChecked() for check in self.days]
        for index, check in enumerate(self.days):
            if occurrence:
                check.setChecked(index == self._occurrence_day)
                check.setEnabled(False)
            else:
                if self._series_days is not None:
                    check.setChecked(self._series_days[index])
                check.setEnabled(True)
        if not occurrence:
            self._series_days = None
        self.repeat_note.setVisible(not occurrence)

    def _clock_minutes(self, clock: QTime) -> int:
        return clock.hour() * 60 + clock.minute()

    def _minutes_clock(self, minutes: int) -> QTime:
        minutes %= 24 * 60
        return QTime(minutes // 60, minutes % 60)

    def _span(self) -> int:
        return self._clock_minutes(self.end.time()) - self._clock_minutes(self.start.time())

    def _span_problem(self) -> str:
        return "End must be after Start." if self._span() <= 0 else ""

    def _keep_length(self, *_args: object) -> None:
        """Moving the start moves the end with it, as a calendar does, so the length stays."""
        self.end.setTime(self._minutes_clock(self._clock_minutes(self.start.time()) + self._length))

    def _show_length(self, *_args: object) -> None:
        problem = self._span_problem()
        if not problem:
            self._length = self._span()
        # The problem is said here, beside the times, in the error colour; nowhere else, so it is
        # not the same sentence twice.
        self.duration_line.setText(problem or length_label(self._span()))
        self.duration_line.setProperty("problem", bool(problem))
        self.duration_line.style().unpolish(self.duration_line)
        self.duration_line.style().polish(self.duration_line)

    def scope(self) -> str:
        if self.scope_occurrence.isChecked() and self._occurrence_day is not None:
            return "occurrence"
        return "series"

    def occurrence_day(self) -> int | None:
        return self._occurrence_day

    def deleted(self) -> bool:
        return self._deleted

    def recover_missed(self) -> bool:
        # The window asks after exec() returns. isVisible() is false for every child of a closed dialog,
        # so it made this box do nothing; isHidden() only says whether the box was ever offered.
        return (
            not self.missed.isHidden()
            and self.missed.isChecked()
            and self._occurrence_day is not None
            and self._occurrence_day not in (self._original.get("missed_days") or [])
        )

    def _delete(self) -> None:
        name = self.title.text().strip() or self._original.get("title") or "this event"
        if self.scope() == "occurrence" and self._occurrence_day is not None:
            name += " on " + DAY_FULL[self._occurrence_day]
        if not confirm(self, "Delete event", f"Delete {name}? You can undo this.", "Delete"):
            return
        self._deleted = True
        super().accept()

    def accept(self) -> None:
        if self._deleted:
            super().accept()
            return
        if self._span_problem():
            self.end.setFocus()
            return
        candidate = deepcopy(self._original)
        chosen_days = [index for index, check in enumerate(self.days) if check.isChecked()]
        candidate.update(
            title=self.title.text().strip(),
            days=chosen_days,
            start=self.start.time().toString("HH:mm"),
            duration_min=self._span(),
            category=self.category.currentData(),
            spotify_url=self.spotify.text().strip() or None,
        )
        # Unticking a day that was missed restores it, as the web's "Restore Wed" button does.
        unticked = not self.missed.isHidden() and not self.missed.isChecked()
        restored = self._occurrence_day if unticked else None
        candidate["missed_days"] = [
            day for day in candidate.get("missed_days", []) if day in candidate["days"] and day != restored
        ]
        if candidate["kind"] != "locked":
            self.error.setText("Use the homework editor for flexible work.")
            return
        try:
            WeekRequest(blocks=[TimeBlock.model_validate(candidate)])
        except ValidationError as error:
            self.error.setText(_block_problem(error))
            return
        self._result = candidate
        super().accept()

    def block(self) -> dict:
        return deepcopy(self._result if self._result is not None else self._original)


class SchoolHoursDialog(Dialog):
    """School's days and times, asked as setup's Your week page asks them. `block()` is the School to
    save, or None when no day is ticked: no school on the calendar."""

    def __init__(self, parent: QWidget | None, school: dict | None = None) -> None:
        super().__init__(parent)
        # Setup's own controls, imported here: setup imports this module.
        from desktop.native.setup import DayPicker, TimeRange

        self._original = deepcopy(school) if school is not None else None
        self._result: dict | None = None
        self.setObjectName("schoolHoursDialog")
        self.setWindowTitle("School hours")
        layout = QVBoxLayout(self)
        card, box = info_card("School hours", SCHOOL_HOURS_NOTE)
        start = (school or {}).get("start") or "08:00"
        minutes = int((school or {}).get("duration_min") or 390)
        self.days = DayPicker(list((school or {}).get("days") or ([] if school else [0, 1, 2, 3, 4])))
        self.times = TimeRange(start, minutes_to_hhmm(hhmm_to_minutes(start) + minutes), "School")
        box.addWidget(self.days)
        box.addWidget(self.times, 0, Qt.AlignmentFlag.AlignLeft)
        hint = QLabel("No school days picked means no school on the calendar.")
        hint.setObjectName("setupHint")
        box.addWidget(hint)
        self.error = _error_label()
        box.addWidget(self.error)
        layout.addWidget(card)
        buttons = _buttons(self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        days = self.days.days()
        start, minutes = self.times.span()
        if not days:
            self._result = None
            super().accept()
            return
        if minutes <= 0:
            self.error.setText("End must be after Start.")
            self.times.end.setFocus()
            return
        school = deepcopy(self._original) if self._original is not None else {
            "id": SETUP_SCHOOL_ID,
            "kind": "locked",
            "title": "School",
            "category": "class",
        }
        school.update(days=days, start=start, duration_min=minutes)
        school["missed_days"] = [day for day in school.get("missed_days", []) if day in days]
        try:
            WeekRequest(blocks=[TimeBlock.model_validate(school)])
        except ValidationError as error:
            self.error.setText(_block_problem(error))
            return
        self._result = school
        super().accept()

    def block(self) -> dict | None:
        return deepcopy(self._result)


def keep_on_screen(popup: QWidget, area: QRect) -> None:
    """Qt keeps a date's calendar on the screen under the field's corner, or on the main screen when
    that corner is on none, and leaves out any window frame, so it could open past the edge of the
    screen the window is on."""
    frame = popup.frameGeometry()
    x = max(area.left(), min(frame.left(), area.left() + area.width() - frame.width()))
    y = max(area.top(), min(frame.top(), area.top() + area.height() - frame.height()))
    if (x, y) != (frame.left(), frame.top()):
        popup.move(x, y)


class DueField(QWidget):
    """When homework is due: always a date, and a time only for work due at one, such as a lesson
    at 09:00. Without a time it is due by the end of that day."""

    changed = Signal()

    def __init__(self, due: str, name: str, *, stacked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Stacked puts the time under the date, for a form too narrow to hold them side by side.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(row)
        self.date = QDateEdit()
        self.date.setObjectName(name)
        self.date.setDisplayFormat(DUE_DATE_FORMAT)
        self.date.setCalendarPopup(True)
        self.date.setMinimumDate(QDate(2000, 1, 1))
        self.date.setMaximumDate(QDate(2099, 12, 31))
        self.date.setAccessibleName("Due date")
        self.date.calendarWidget().parentWidget().installEventFilter(self)
        self.timed = QCheckBox("At a set time")
        self.timed.setObjectName(f"{name}Timed")
        self.timed.setAccessibleName("Due at a set time")
        self.time = QTimeEdit()
        self.time.setObjectName(f"{name}Time")
        self.time.setDisplayFormat(time_format())
        self.time.setAccessibleName("Due time")
        row.addWidget(self.date)
        if stacked:
            row.addStretch(1)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            outer.addLayout(row)
        row.addWidget(self.timed)
        row.addWidget(self.time)
        row.addStretch(1)
        self.set_value(due)
        self.date.dateChanged.connect(self._say_changed)
        self.timed.toggled.connect(self._show_time)
        self.timed.toggled.connect(self._say_changed)
        self.time.timeChanged.connect(self._say_changed)

    def set_value(self, due: str) -> None:
        day, minute = parse_due(due)
        self.date.setDate(QDate(day.year, day.month, day.day))
        timed = due_is_timed(due)
        # A time box opened later starts at a usual start of lessons, not at midnight.
        self.time.setTime(QTime(minute // 60, minute % 60) if timed else QTime(9, 0))
        self.timed.setChecked(timed)
        self._show_time(timed)

    def value(self) -> str:
        day = self.date.date().toString("yyyy-MM-dd")
        return f"{day}T{self.time.time().toString('HH:mm')}" if self.timed.isChecked() else day

    def _show_time(self, timed: bool) -> None:
        self.time.setVisible(timed)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt virtual
        if event.type() == QEvent.Type.Show and watched.objectName() == "qt_datetimedit_calendar":
            keep_on_screen(watched, self.window().screen().availableGeometry())
        return super().eventFilter(watched, event)

    def _say_changed(self, *_value: object) -> None:
        # Connected straight to `changed.emit`, each signal handed its value to a signal that takes
        # none: a TypeError inside Qt, and nothing connected to `changed` ran.
        self.changed.emit()


class HomeworkDialog(Dialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        assignment: dict | None = None,
        today: str | None = None,
        category: str | None = None,
        estimate_min: int | None = None,
        due: str | None = None,
        *,
        waiting: bool = False,
        pinned: bool = False,
    ) -> None:
        super().__init__(parent, sheet=True)
        info = CATEGORIES.get(category or "")
        self._original = (
            deepcopy(assignment)
            if assignment is not None
            else {
                "id": str(uuid4()),
                # Empty, with the category as its hint. Filled in with "Homework", typing added to the word.
                "title": "",
                # Today, whatever week is on screen: the Monday of that week was often already past.
                "due": due or today or date.today().isoformat(),
                "estimate_min": estimate_min or (info or {}).get("preset", {}).get("duration_min") or 60,
                "category": category,
                "revision": 0,
                "notes": "",
                "links": [],
                "checklist": [],
                "completed": False,
                "completed_at": None,
            }
        )
        self._result: dict | None = None
        self._spread = False
        # "choose" to pick a time for a session that needs one, "unpin" to let FlexWeek move it again.
        self._request: str | None = None
        self.setWindowTitle("Edit homework" if assignment else "Add homework")
        self.setObjectName("homeworkDialog")
        layout = self.card_body()
        # The body scrolls so the dialog cannot outgrow a laptop screen. It already carried notes,
        # links and a checklist; one more row took it to 815px, past the bottom of a 768px display.
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        form = Form()
        body_layout.addLayout(form)
        self.title = _line("homeworkTitle", self._original["title"])
        # Homework saved with no category is still homework, so it gets the same hint.
        self.title.setPlaceholderText((info or CATEGORIES["assignments"])["label"])
        form.addRow("Title", self.title)
        self.due = DueField(self._original["due"], "homeworkDue", stacked=True)
        form.addRow("Due", self.due)
        self.estimate = LengthBox("homeworkEstimate", self._original["estimate_min"])
        form.addRow("Estimated time", self.estimate)
        self.estimate_hint = QLabel(SLOT_HINT)
        self.estimate_hint.setObjectName("homeworkEstimateHint")
        self.estimate_hint.setWordWrap(True)
        form.addRow("", self.estimate_hint)
        self.estimate.valueChanged.connect(self._recheck_length)
        if self._length_problem():
            # Stored before the limit, so the student is told before they try to save it.
            self._say_length()
        self.error = _error_label()
        form.addRow("", self.error)
        # The row goes with its words: an empty one left a gap above Finished.
        form.setRowVisible(self.error, False)
        self._form = form
        self.completed = QCheckBox("Finished")
        self.completed.setObjectName("homeworkCompleted")
        self.completed.setChecked(bool(self._original.get("completed")))
        form.addRow("", self.completed)
        # Placing by hand, for the keyboard and for designs with no time grid to drag onto.
        self._session_buttons: list[QPushButton] = []
        session_row = QHBoxLayout()
        for shown, text, name, kind in (
            (waiting, "Choose a time…", "homeworkChooseTime", "choose"),
            (pinned, "Let FlexWeek move it", "homeworkUnpin", "unpin"),
        ):
            if not shown:
                continue
            button = QPushButton(text)
            button.setObjectName(name)
            button.setProperty("quiet", True)
            button.setToolTip("Save these edits first.")
            button.setProperty("request", kind)
            button.clicked.connect(self._request_session)
            session_row.addWidget(button)
            self._session_buttons.append(button)
        if self._session_buttons:
            session_row.addStretch(1)
            form.addRow("", session_row)
        self.more_details = QPushButton("More details")
        self.more_details.setObjectName("homeworkMoreDetails")
        self.more_details.setProperty("quiet", True)
        self.more_details.setCheckable(True)
        form.addRow("", self.more_details)
        details = bare(QWidget())
        details.setObjectName("homeworkDetails")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        extra = Form()
        details_layout.addLayout(extra)
        self.course = _line("homeworkCourse", self._original.get("course") or "", 40)
        extra.addRow("Course", self.course)
        self.priority = QComboBox()
        self.priority.setObjectName("homeworkPriority")
        for value, label in enumerate(("Test", "Quiz", "Homework", "Reading"), 1):
            self.priority.addItem(label, value)
        self.priority.setCurrentIndex(self.priority.findData(self._original.get("priority", 3)))
        extra.addRow("Priority", self.priority)
        self.energy = QComboBox()
        self.energy.setObjectName("homeworkEnergy")
        for value, label in (("high", "Morning"), ("medium", "Afternoon"), ("low", "Evening")):
            self.energy.addItem(label, value)
        self.energy.setCurrentIndex(self.energy.findData(self._original.get("energy", "medium")))
        extra.addRow("Energy preference", self.energy)
        self.spotify = _line("homeworkSpotify", self._original.get("spotify_url") or "", 500)
        self.spotify.setPlaceholderText("https://open.spotify.com/…")
        extra.addRow("Spotify link", self.spotify)
        self.notes = QPlainTextEdit(self._original.get("notes") or "")
        self.notes.setObjectName("homeworkNotes")
        # Three boxes at their 192px default made this dialog taller than a laptop screen.
        self.notes.setMaximumHeight(DETAIL_BOX_HEIGHT)
        self.notes.setPlaceholderText("Notes")
        details_layout.addWidget(self.notes)
        link_row = QHBoxLayout()
        self.link_label = _line("homeworkLinkLabel", "", 80)
        self.link_label.setPlaceholderText("Link label")
        self.link_url = _line("homeworkLinkUrl", "", 500)
        self.link_url.setPlaceholderText("https://")
        # Save is the answer; Add link, Add step and Spread are plain beside it.
        add_link = QPushButton("Add link")
        add_link.setProperty("quiet", True)
        add_link.setObjectName("addHomeworkLink")
        add_link.clicked.connect(self._add_link)
        link_row.addWidget(self.link_label)
        link_row.addWidget(self.link_url)
        link_row.addWidget(add_link)
        details_layout.addLayout(link_row)
        self.links = QListWidget()
        self.links.setObjectName("homeworkLinks")
        self.links.setMaximumHeight(DETAIL_BOX_HEIGHT)
        details_layout.addWidget(self.links)
        for link in self._original.get("links") or []:
            self._append_link(link["label"], link["url"])
        check_row = QHBoxLayout()
        self.check_text = _line("homeworkCheckText", "", 80)
        self.check_text.setPlaceholderText("Checklist step")
        add_check = QPushButton("Add step")
        add_check.setProperty("quiet", True)
        add_check.setObjectName("addHomeworkCheck")
        add_check.clicked.connect(self._add_check)
        check_row.addWidget(self.check_text)
        check_row.addWidget(add_check)
        details_layout.addLayout(check_row)
        self.checks = QListWidget()
        self.checks.setObjectName("homeworkChecklist")
        details_layout.addWidget(self.checks)
        for step in self._original.get("checklist") or []:
            self._append_check(step["id"], step["text"], step.get("done", False))
        if assignment is not None:
            spread = QPushButton("Spread across days")
            spread.setProperty("quiet", True)
            spread.setObjectName("spreadHomework")
            spread.clicked.connect(self._request_spread)
            spread.setToolTip("Save these edits first, then spread.")
            details_layout.addWidget(spread)
            self._spread_button = spread
            self.title.textChanged.connect(self._disable_spread)
            self.notes.textChanged.connect(self._disable_spread)
            self.estimate.valueChanged.connect(self._disable_spread)
            self.due.changed.connect(self._disable_spread)
            self.course.textChanged.connect(self._disable_spread)
        else:
            self._spread_button = None
        body_layout.addWidget(details)
        self._details = details
        self.more_details.toggled.connect(details.setVisible)
        open_details = bool(
            self._original.get("course")
            or self._original.get("notes")
            or self._original.get("links")
            or self._original.get("checklist")
            or self._original.get("spotify_url")
        )
        self.more_details.setChecked(open_details)
        details.setVisible(open_details)
        # The sheet grows with the details, up to the room its window has.
        self.more_details.toggled.connect(self.refit)
        area = FitScroll(body, "homeworkScroll")
        layout.addWidget(area, 1)
        # A scroll area does not claim its content's width, so without this the dialog comes up narrow.
        self.card.setMinimumWidth(HOMEWORK_MIN_WIDTH)
        self._scroll = area
        # Delete is not one of the dialog's answers: quiet words at the left, away from Save, as the
        # block editor has it. Only homework that exists can go.
        row = QHBoxLayout()
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("deleteHomework")
        self.delete_button.setAutoDefault(False)
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.setVisible(assignment is not None)
        self.delete_button.clicked.connect(self._delete)
        row.addWidget(self.delete_button)
        row.addStretch(1)
        buttons = _buttons(self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        layout.addLayout(row)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if not self.sheet:
            fit_scroll_dialog(self)

    def _show_error(self, text: str) -> None:
        self.error.setText(text)
        self._form.setRowVisible(self.error, bool(text))
        if text:
            self._scroll.ensureWidgetVisible(self.error)

    def _length_problem(self) -> str:
        minutes = self.estimate.value()
        if minutes < SLOT_MIN:
            return ESTIMATE_SHORT
        if minutes > ESTIMATE_MAX_MIN:
            return ESTIMATE_LONG
        return ""

    def _say_length(self) -> bool:
        """Say under the box what is wrong with the length, in the error colour, or the usual hint."""
        problem = self._length_problem()
        self.estimate_hint.setText(problem or SLOT_HINT)
        self.estimate_hint.setProperty("problem", bool(problem))
        self.estimate_hint.style().unpolish(self.estimate_hint)
        self.estimate_hint.style().polish(self.estimate_hint)
        return bool(problem)

    def _recheck_length(self, *_args: object) -> None:
        # Only once Save has refused: while a length is being typed, "1" is not yet a mistake.
        if self.estimate_hint.property("problem"):
            self._say_length()

    def _disable_spread(self, *_args: object) -> None:
        # Like Spread, placing acts on the saved homework, so an unsaved edit turns them off.
        for button in self._session_buttons:
            button.setEnabled(False)
        if self._spread_button is None:
            return
        self._spread_button.setEnabled(False)

    def _request_spread(self) -> None:
        self._spread = True
        self._result = deepcopy(self._original)
        super().accept()

    def spread_requested(self) -> bool:
        return self._spread

    def _request_session(self) -> None:
        self._request = self.sender().property("request")
        self._result = deepcopy(self._original)
        super().accept()

    def _delete(self) -> None:
        name = self._original.get("title") or "this homework"
        words = f"Delete {name}? Its times on the calendar go too, in every week. You can undo this."
        if not confirm(self, "Delete homework", words, "Delete"):
            return
        self._request = "delete"
        self._result = deepcopy(self._original)
        super().accept()

    def requested(self) -> str | None:
        return self._request

    def _append_link(self, label: str, url: str) -> None:
        item = QListWidgetItem(f"{label} — {url}")
        item.setData(Qt.ItemDataRole.UserRole, {"label": label, "url": url})
        self.links.addItem(item)

    def _add_link(self) -> None:
        if self.links.count() >= 20:
            self._show_error("Up to 20 links.")
            return
        label = self.link_label.text().strip()
        url = self.link_url.text().strip()
        if not label or not url:
            self._show_error("A link needs a label and an http(s) address.")
            return
        self._append_link(label, url)
        self.link_label.clear()
        self.link_url.clear()
        self._show_error("")

    def _append_check(self, item_id: str, text: str, done: bool) -> None:
        item = QListWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if done else Qt.CheckState.Unchecked)
        item.setData(Qt.ItemDataRole.UserRole, item_id)
        self.checks.addItem(item)

    def _add_check(self) -> None:
        if self.checks.count() >= 40:
            self._show_error("Up to 40 steps.")
            return
        text = self.check_text.text().strip()
        if not text:
            self._show_error("A checklist step needs text.")
            return
        self._append_check(str(uuid4()), text, False)
        self.check_text.clear()
        self._show_error("")

    def _chosen_due(self) -> str:
        """The due as the student left it. An old 23:59 that still means the same end of the day is
        kept as it was stored, so opening and saving changes nothing."""
        chosen, before = self.due.value(), self._original["due"]
        return before if parse_due(chosen) == parse_due(before) else chosen

    def accept(self) -> None:
        if self._say_length():
            self.estimate.setFocus()
            return
        candidate = deepcopy(self._original)
        links = [self.links.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self.links.count())]
        checklist = []
        for index in range(self.checks.count()):
            item = self.checks.item(index)
            checklist.append(
                {
                    "id": item.data(Qt.ItemDataRole.UserRole),
                    "text": item.text(),
                    "done": item.checkState() == Qt.CheckState.Checked,
                }
            )
        completed = self.completed.isChecked()
        completed_at = candidate.get("completed_at") if completed else None
        if completed and not completed_at:
            completed_at = local_stamp()
        candidate.update(
            title=self.title.text().strip(),
            due=self._chosen_due(),
            estimate_min=self.estimate.value(),
            course=self.course.text() or None,
            priority=self.priority.currentData(),
            energy=self.energy.currentData(),
            spotify_url=self.spotify.text().strip() or None,
            notes=self.notes.toPlainText(),
            links=links,
            checklist=checklist,
            completed=completed,
            completed_at=completed_at,
        )
        try:
            Assignment.model_validate(
                {key: value for key, value in candidate.items() if key in Assignment.model_fields}
            )
        except ValueError as error:
            self._show_error(_homework_problem(error))
            return
        self._result = candidate
        super().accept()

    def assignment(self) -> dict:
        return deepcopy(self._result if self._result is not None else self._original)


def _grid_starts() -> list[str]:
    return [minutes_to_hhmm(minute) for minute in range(DAY_START_MIN, DAY_END_MIN, SLOT_MIN)]


class PreviewDialog(Dialog):
    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        summary: str,
        rows: list[dict],
        existing: list[dict],
    ) -> None:
        super().__init__(parent)
        self.setObjectName("stage3PreviewDialog")
        self.setWindowTitle(title)
        self._rows = deepcopy(rows)
        self._existing = existing
        self._first = True
        self._rebuilding = False
        layout = QVBoxLayout(self)
        card, box = plain_card()
        heading = QLabel(title)
        heading.setObjectName("stage3PreviewTitle")
        box.addWidget(heading)
        note = QLabel(summary)
        note.setObjectName("stage3PreviewSummary")
        note.setWordWrap(True)
        box.addWidget(note)
        self._list = QWidget()
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        box.addWidget(FitScroll(self._list, "stage3PreviewScroll"), 1)
        self.error = _error_label()
        self.error.setObjectName("stage3PreviewError")
        box.addWidget(self.error)
        layout.addWidget(card, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.confirm = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.confirm.setObjectName("stage3PreviewConfirm")
        self.confirm.setText("Save preview")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setProperty("quiet", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def rows(self) -> list[dict]:
        return deepcopy(self._rows)

    def _refresh(self) -> None:
        self._rebuilding = True
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        conflicted = False
        for index, row in enumerate(self._rows):
            conflict = row_conflict(row, self._rows, self._existing)
            if self._first and (conflict or row.get("invalid")):
                row["checked"] = False
            conflicted = conflicted or bool(row.get("checked") and (conflict or row.get("invalid")))
            self._list_layout.addWidget(self._row_widget(index, row, conflict))
        self._first = False
        selected = [row for row in self._rows if row.get("checked")]
        self.confirm.setEnabled(bool(selected) and not conflicted)
        even_fields(self)
        if conflicted:
            self.error.setText("Resolve conflicts or select at least one item before saving.")
        else:
            self.error.setText("")
        self._rebuilding = False

    def _row_widget(self, index: int, row: dict, conflict: str | None) -> QWidget:
        widget = QWidget()
        row_layout = QHBoxLayout(widget)
        include = QCheckBox(row["block"]["title"])
        include.setObjectName(f"previewInclude{index}")
        include.blockSignals(True)
        include.setChecked(bool(row.get("checked")))
        include.blockSignals(False)
        include.setEnabled(not row.get("invalid"))
        include.setProperty("row", index)
        include.toggled.connect(self._set_checked)
        row_layout.addWidget(include)
        if row.get("fixed"):
            day = QComboBox()
            day.setObjectName(f"previewDay{index}")
            for name in DAYS:
                day.addItem(name)
            day.setCurrentIndex(row["day"])
            day.setProperty("row", index)
            day.currentIndexChanged.connect(self._set_day)
            row_layout.addWidget(day)
            start = QComboBox()
            start.setObjectName(f"previewStart{index}")
            duration = int(row["block"]["duration_min"])
            last = DAY_END_MIN - duration
            current = row["block"].get("start") or minutes_to_hhmm(DAY_START_MIN)
            # Quarter hours to move it to, and its own time among them when it is not on one.
            offered = {minutes_to_hhmm(minute) for minute in range(DAY_START_MIN, last + 1, SLOT_MIN)}
            for value in sorted(offered | {current}):
                start.addItem(hhmm_text(value), value)
            start.setCurrentIndex(start.findData(current))
            row["block"]["start"] = start.currentData()
            start.setProperty("row", index)
            start.currentIndexChanged.connect(self._set_start)
            row_layout.addWidget(start)
            length = QComboBox()
            length.setObjectName(f"previewDuration{index}")
            start_min = hhmm_to_minutes(row["block"]["start"])
            maximum = min(DAY_END_MIN - start_min, int(row.get("original_duration") or duration))
            lengths = set(range(SLOT_MIN, maximum + 1, SLOT_MIN))
            if duration <= maximum:
                lengths.add(duration)
            for minutes in sorted(lengths):
                length.addItem(str(minutes), minutes)
            length.setCurrentIndex(max(0, length.findData(min(duration, maximum))))
            length.setProperty("row", index)
            length.currentIndexChanged.connect(self._set_duration)
            row_layout.addWidget(length)
        detail = QLabel(preview_conflict_message(row, self._rows, self._existing))
        detail.setObjectName(f"previewDetail{index}")
        detail.setWordWrap(True)
        row_layout.addWidget(detail, 1)
        return widget

    def _set_checked(self, checked: bool) -> None:
        if self._rebuilding:
            return
        self._rows[self.sender().property("row")]["checked"] = checked
        self._refresh()

    def _set_day(self, day: int) -> None:
        if self._rebuilding:
            return
        index = self.sender().property("row")
        self._rows[index]["day"] = day
        self._rows[index]["block"]["days"] = [day]
        if not row_conflict(self._rows[index], self._rows, self._existing):
            self._rows[index]["checked"] = True
        self._refresh()

    def _set_start(self, _index: int) -> None:
        if self._rebuilding:
            return
        box = self.sender()
        index = box.property("row")
        self._rows[index]["block"]["start"] = box.currentData()
        self._rows[index]["invalid"] = ""
        if not row_conflict(self._rows[index], self._rows, self._existing):
            self._rows[index]["checked"] = True
        self._refresh()

    def _set_duration(self) -> None:
        if self._rebuilding:
            return
        length = self.sender()
        index = length.property("row")
        self._rows[index]["block"]["duration_min"] = int(length.currentData())
        if not row_conflict(self._rows[index], self._rows, self._existing):
            self._rows[index]["checked"] = True
        self._refresh()


class UnfinishedPanel(QWidget):
    plan_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("unfinishedReview")
        layout = QVBoxLayout(self)
        heading = QLabel("Unfinished homework from earlier weeks")
        heading.setObjectName("unfinishedHeading")
        layout.addWidget(heading)
        self.list = QListWidget()
        self.list.setObjectName("unfinishedList")
        layout.addWidget(self.list)
        row = QHBoxLayout()
        dismiss = QPushButton("Hide")
        dismiss.setObjectName("unfinishedDismiss")
        dismiss.setProperty("quiet", True)
        dismiss.clicked.connect(self.hide)
        row.addWidget(dismiss)
        row.addStretch(1)
        layout.addLayout(row)
        self.hide()

    def set_items(self, items: list[dict]) -> None:
        self.list.clear()
        for item in items:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            text = QLabel(f"{item['title']} · {length_label(int(item['remaining_min']))} left")
            text.setObjectName("unfinishedRow")
            row_layout.addWidget(text, 1)
            button = QPushButton("Plan here")
            button.setObjectName(f"planUnfinished-{item['id']}")
            button.clicked.connect(
                lambda _checked=False, item_id=item["id"]: self.plan_requested.emit(item_id)
            )
            row_layout.addWidget(button)
            delete = QPushButton("Delete")
            delete.setObjectName(f"deleteUnfinished-{item['id']}")
            delete.setProperty("quiet", True)
            delete.setToolTip("Delete this homework and its times in every week. You can undo this.")
            delete.clicked.connect(
                lambda _checked=False, item_id=item["id"]: self.delete_requested.emit(item_id)
            )
            row_layout.addWidget(delete)
            wrapper = QListWidgetItem()
            wrapper.setSizeHint(row.sizeHint())
            self.list.addItem(wrapper)
            self.list.setItemWidget(wrapper, row)
        # As tall as its rows, as the plan review is: one row in a box eight rows deep read as empty.
        if items:
            height = sum(self.list.sizeHintForRow(index) for index in range(self.list.count()))
            self.list.setFixedHeight(min(height + 2 * self.list.frameWidth() + 4, UNFINISHED_MAX))
        self.setVisible(bool(items))


class AlertStrip(QWidget):
    """Alerts that stay put until the student deals with them.

    A tray message is gone in eight seconds, and on a machine that suppresses notifications it is
    never seen at all. "Leave reminders on screen" promises the opposite, so when it is on the alert is
    also shown here, in the window, where nothing outside the app can take it away.
    """

    # The student has dealt with every alert it held.
    handled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("alertStrip")
        self._notices: list[dict] = []
        layout = QHBoxLayout(self)
        self.text = QLabel()
        self.text.setObjectName("alertStripText")
        self.text.setWordWrap(True)
        layout.addWidget(self.text, 1)
        self.dismiss = QPushButton("Got it")
        self.dismiss.setObjectName("alertStripDismiss")
        self.dismiss.clicked.connect(self._drop)
        layout.addWidget(self.dismiss)
        self.setVisible(False)

    def add(self, notices: list[dict]) -> None:
        self._notices.extend(notices)
        self._render()

    def clear(self) -> None:
        self._notices.clear()
        self._render()

    def pending(self) -> int:
        return len(self._notices)

    def _drop(self) -> None:
        """One at a time, so a second alert that arrived while the first sat there is still seen."""
        if self._notices:
            self._notices.pop(0)
        self._render()
        if not self._notices:
            self.handled.emit()

    def _render(self) -> None:
        self.setVisible(bool(self._notices))
        if not self._notices:
            self.text.clear()
            return
        notice = self._notices[0]
        body = notice.get("body") or ""
        more = f"  (+{len(self._notices) - 1} more)" if len(self._notices) > 1 else ""
        self.text.setText(f"{notice.get('title') or 'FlexWeek'}{' — ' + body if body else ''}{more}")


class PlanReview(QFrame):
    """What the plan just did, in the solver's own words, as one slim bar (decision 18 of 0.17):
    "Placed 2 · 1 without a time · Details", Got it filled and Replan as text. Details opens the
    solver's sentences, and they are open already when something has no time.

    The client used to take one explanation out of however many the solver gave and drop it in the
    status line, and never mentioned a move at all outside Running late. Explaining what could not
    be placed, and what had to move, is the thing FlexWeek is for.
    """

    dismissed = Signal()
    replan_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("planReview")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.heading = QLabel()
        self.heading.setObjectName("planReviewHeading")
        row.addWidget(self.heading)
        self.details = QPushButton("Details")
        self.details.setObjectName("planReviewDetails")
        self.details.setCheckable(True)
        self.details.setToolTip("Show what the plan did, and why.")
        self.details.toggled.connect(self._show_details)
        row.addWidget(self.details)
        row.addStretch(1)
        replan = QPushButton("Replan all my homework")
        replan.setObjectName("planReviewReplan")
        replan.setToolTip(REPLAN_TIP)
        replan.clicked.connect(self.replan_requested.emit)
        dismiss = QPushButton("Got it")
        dismiss.setObjectName("planReviewDismiss")
        dismiss.setToolTip("Hide this list.")
        dismiss.clicked.connect(self._dismiss)
        row.addWidget(replan)
        row.addWidget(dismiss)
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setObjectName("planReviewList")
        self.list.setWordWrap(True)
        layout.addWidget(self.list)
        self.list.hide()
        self.hide()

    def _show_details(self, shown: bool) -> None:
        self.list.setVisible(shown)
        self.details.setText("Hide details" if shown else "Details")

    def _dismiss(self) -> None:
        self.hide()
        self.dismissed.emit()

    def rows_for(self, trace: dict, titles: dict[str, str], week_start: str) -> list[str]:
        """Every unplaced task, every move, and every deadline the solver called tight."""
        said: list[str] = []
        for block in trace.get("unplaced") or []:
            name = titles.get(block["id"], block.get("title") or "Homework")
            why = next(
                (
                    item.get("message")
                    for item in trace.get("explanations") or []
                    if item.get("block_id") == block["id"] and item.get("message")
                ),
                "There was no room for it this week.",
            )
            said.append(f"{name} has no time yet. {why}")
        stranded = {block["id"] for block in trace.get("unplaced") or []}
        for move in trace.get("moves") or []:
            # A "move" with no time at either end is the solver recording that something stayed
            # unplaced. Said out loud it read "moved from no time to no time", under a line that
            # had already explained the same block.
            if move["block_id"] in stranded or not move.get("to_start") or not move.get("from_start"):
                continue
            name = titles.get(move["block_id"], "Homework")
            been = _when(move.get("from_day"), move.get("from_start"))
            now = _when(move.get("to_day"), move.get("to_start"))
            # Running late files its moves under the missed-day code with a sentence of its own, so
            # the code alone told a student who ran late that they had missed a day.
            why = next(
                (
                    item["message"]
                    for item in trace.get("explanations") or []
                    if item.get("block_id") == move["block_id"]
                    and item.get("reason") == move.get("reason")
                    and item.get("message")
                ),
                REASON_COPY.get(move.get("reason") or "", ""),
            )
            said.append(f"{name} moved from {been} to {now}." + (f" {why}" if why else ""))
        for item in trace.get("explanations") or []:
            if item.get("slack_status") in {"tight", "danger"} and item.get("message"):
                said.append(f"{titles.get(item['block_id'], 'Homework')}: {item['message']}")
        return said

    def set_trace(
        self, trace: dict | None, titles: dict[str, str], week_start: str, counts: tuple[int, int]
    ) -> None:
        """`counts` are the plan's own, homework it gave a time and homework it could not, the
        numbers the toast says. The trace's placed list holds every block with a time, School
        included, so counted here it said 2 placed where the toast said 0."""
        self.list.clear()
        said = self.rows_for(trace or {}, titles, week_start) if trace else []
        if not said:
            self.hide()
            return
        placed, waiting = counts
        parts = [f"Placed {placed}"] + ([f"{waiting} without a time"] if waiting else [])
        self.heading.setText(" · ".join(parts))
        for line in said:
            self.list.addItem(QListWidgetItem(line))
        # As tall as it needs and no taller. One line in a box four lines deep reads as an error.
        row = self.list.sizeHintForRow(0) if self.list.count() else 0
        self.list.setFixedHeight(min(row * len(said) + 2 * self.list.frameWidth() + 4, PLAN_REVIEW_MAX))
        self.details.setChecked(bool(waiting))
        self._show_details(bool(waiting))
        self.show()


def _when(day: object, start: object) -> str:
    if not isinstance(day, int) or not start:
        return "no time"
    return f"{DAYS[day]} {hhmm_text(str(start))}"


class ChooseTimeDialog(Dialog):
    """A time for homework that needs one, without dragging: for the keyboard, and for designs that have
    no time grid to drop on. It refuses the same times a drop on the Calendar refuses."""

    def __init__(
        self,
        parent: QWidget | None,
        block: dict,
        week_start: str,
        days: list[int],
        blocks: list[dict],
        due: tuple[int, int] | None,
        today: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Choose a time for {block.get('title') or 'homework'}")
        self.setObjectName("chooseTimeDialog")
        self._block, self._blocks, self._due = block, blocks, due
        self._duration = int(block.get("duration_min") or SLOT_MIN)
        layout = QVBoxLayout(self)
        card, box = plain_card()
        form = Form()
        self.day = QComboBox()
        self.day.setObjectName("chooseTimeDay")
        monday = date.fromisoformat(week_start)
        for day in days:
            self.day.addItem((monday + timedelta(days=day)).strftime("%a %-d %b"), day)
        # Today rather than the first day the homework could go, which on a Wednesday was Monday.
        if today in days:
            self.day.setCurrentIndex(days.index(today))
        form.addRow("Day", self.day)
        self.start = QTimeEdit(QTime(16, 0))
        self.start.setObjectName("chooseTimeStart")
        self.start.setDisplayFormat(time_format())
        self.start.setMinimumTime(QTime(6, 0))
        latest = DAY_END_MIN - self._duration
        self.start.setMaximumTime(QTime(latest // 60, latest % 60))
        form.addRow("Start", self.start)
        form.addRow("Length", QLabel(length_label(self._duration)))
        box.addLayout(form)
        self.problem = QLabel()
        self.problem.setObjectName("validationError")
        self.problem.setWordWrap(True)
        box.addWidget(self.problem)
        # Another block at that time is allowed, as on the calendar; this says which, so it is a choice.
        self.beside = QLabel()
        self.beside.setObjectName("chooseTimeBeside")
        self.beside.setWordWrap(True)
        box.addWidget(self.beside)
        layout.addWidget(card)
        choices = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttons = QDialogButtonBox(choices)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setProperty("quiet", True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.day.currentIndexChanged.connect(self._check)
        self.start.timeChanged.connect(self._check)
        self._check()

    def choice(self) -> tuple[int, int]:
        """The day and the start, to the minute the student picked."""
        return int(self.day.currentData()), self.start.time().hour() * 60 + self.start.time().minute()

    def _check(self, *_args: object) -> None:
        day, start = self.choice()
        end = start + self._duration
        problem = span_problem(self._blocks, self._block["id"], day, start, end, self._due)
        self.problem.setText((problem or "").replace(", so it stayed where it was", ""))
        self.problem.setVisible(problem is not None)
        clash = span_clash(self._blocks, self._block["id"], day, start, end) if problem is None else None
        self.beside.setText(f"{clash} is at that time too. Both will show, side by side." if clash else "")
        self.beside.setVisible(clash is not None)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(problem is None)


class RoutineDialog(Dialog):
    def __init__(
        self,
        parent: QWidget | None,
        routines: dict[str, dict],
        blocks: list[dict],
        week_start: str,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("routineDialog")
        self.setWindowTitle("Routines")
        self._routines = routines
        self._blocks = routine_source_blocks(blocks)
        self._week_start = week_start
        self.action: str | None = None
        self.routine_id: str | None = None
        self.destination = week_start
        self.days = list(range(7))
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        keep, keep_box = info_card(
            "Save this week as a routine",
            "Tick the fixed times to keep, give them a name, and copy them into any week later.",
        )
        self.name = _line("routineName")
        self.name.setPlaceholderText("Routine name")
        keep_box.addWidget(self.name)
        self.choices = QListWidget()
        self.choices.setObjectName("routineBlocks")
        # Room for about four fixed times before it scrolls; squeezed, it showed one and a half.
        self.choices.setMinimumHeight(ROUTINE_LIST_MIN_HEIGHT)
        keep_box.addWidget(self.choices)
        for block in self._blocks:
            days = ", ".join(DAYS[day] for day in block["days"])
            item = QListWidgetItem(f"{block['title']} · {days} · {hhmm_text(block['start'])}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, block["id"])
            self.choices.addItem(item)
        save = QPushButton("Save this week as a routine")
        save.setObjectName("saveRoutine")
        save.clicked.connect(self._save)
        keep_box.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(keep)
        use, use_box = info_card(
            "Use a saved routine",
            "Pick a routine, the week to copy it into and the days to copy.",
        )
        self.empty = QLabel("No routines saved yet.")
        self.empty.setObjectName("routineEmpty")
        use_box.addWidget(self.empty)
        self.list = QListWidget()
        self.list.setObjectName("routineList")
        use_box.addWidget(self.list)
        for routine in routines.values():
            item = QListWidgetItem(f"{routine['name']} · {len(routine.get('blocks') or [])} fixed times")
            item.setData(Qt.ItemDataRole.UserRole, routine["id"])
            self.list.addItem(item)
        self.empty.setVisible(not routines)
        self.list.setVisible(bool(routines))
        dest = QDateEdit(QDate.fromString(week_start, "yyyy-MM-dd"))
        dest.setObjectName("routineDestination")
        dest.setDisplayFormat(DATE_FORMAT)
        dest.setCalendarPopup(True)
        dest.setMinimumDate(QDate(2000, 1, 1))
        dest.setMaximumDate(QDate(2099, 12, 31))
        dest.dateChanged.connect(self._snap_destination)
        week_row = QHBoxLayout()
        week_row.addWidget(QLabel("Week of"))
        week_row.addWidget(dest)
        week_row.addStretch(1)
        use_box.addLayout(week_row)
        self._dest = dest
        days_row = QHBoxLayout()
        self._days = []
        for index, name in enumerate(DAYS):
            check = QCheckBox(name)
            check.setObjectName(f"routineDay{index}")
            check.setChecked(True)
            days_row.addWidget(check)
            self._days.append(check)
        days_row.addStretch(1)
        use_box.addLayout(days_row)
        actions = QHBoxLayout()
        apply = QPushButton("Apply")
        apply.setObjectName("applyRoutine")
        apply.setProperty("quiet", True)
        apply.clicked.connect(self._apply)
        delete = QPushButton("Delete")
        delete.setObjectName("deleteRoutine")
        delete.setProperty("quiet", True)
        delete.clicked.connect(self._delete)
        for button in (apply, delete):
            button.setEnabled(bool(routines))
            actions.addWidget(button)
        actions.addStretch(1)
        use_box.addLayout(actions)
        layout.addWidget(use)
        self.error = _error_label()
        layout.addWidget(self.error)
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("closeRoutines")
        close.setProperty("quiet", True)
        close.clicked.connect(self.reject)
        close_row.addWidget(close)
        layout.addLayout(close_row)

    def selected_block_ids(self) -> list[str]:
        ids = []
        for index in range(self.choices.count()):
            item = self.choices.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def selected_days(self) -> list[int]:
        return [index for index, check in enumerate(self._days) if check.isChecked()]

    def _save(self) -> None:
        self.action = "save"
        super().accept()

    def _apply(self) -> None:
        item = self.list.currentItem()
        if item is None:
            self.error.setText("Choose a saved routine.")
            return
        days = self.selected_days()
        if not days:
            self.error.setText("Choose at least one weekday to copy.")
            return
        self.action = "apply"
        self.routine_id = item.data(Qt.ItemDataRole.UserRole)
        self.destination = self._dest.date().toString("yyyy-MM-dd")
        self.days = days
        super().accept()

    def _snap_destination(self, value: QDate) -> None:
        iso = value.toString("yyyy-MM-dd")
        monday = monday_of(iso)
        if monday == iso:
            return
        self._dest.blockSignals(True)
        self._dest.setDate(QDate.fromString(monday, "yyyy-MM-dd"))
        self._dest.blockSignals(False)

    def _delete(self) -> None:
        item = self.list.currentItem()
        if item is None:
            self.error.setText("Choose a saved routine.")
            return
        self.action = "delete"
        self.routine_id = item.data(Qt.ItemDataRole.UserRole)
        super().accept()


class LateDialog(Dialog):
    preview_requested = Signal()

    def __init__(self, parent: QWidget | None, context: str) -> None:
        super().__init__(parent)
        self.setObjectName("lateDialog")
        self.setWindowTitle("Running late")
        layout = QVBoxLayout(self)
        card, box = info_card(
            "Running late",
            "Say how late you are and preview what moves. Nothing changes until you accept it.",
        )
        box.addWidget(QLabel(context))
        self.minutes = QComboBox()
        self.minutes.setObjectName("lateMinutes")
        for value in LATE_MINUTES:
            self.minutes.addItem(f"{value} minutes", value)
        self.minutes.setCurrentIndex(1)
        box.addWidget(self.minutes, 0, Qt.AlignmentFlag.AlignLeft)
        self.summary = QLabel()
        self.summary.setObjectName("lateSummary")
        self.summary.setWordWrap(True)
        box.addWidget(self.summary)
        self.changes = QListWidget()
        self.changes.setObjectName("lateChanges")
        # Shown with the preview: before it, an empty box said nothing.
        self.changes.setVisible(False)
        box.addWidget(self.changes)
        layout.addWidget(card)
        self.error = _error_label()
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        preview = QPushButton("Preview")
        preview.setObjectName("latePreview")
        preview.setProperty("quiet", True)
        preview.clicked.connect(self.preview_requested.emit)
        # The answers where the platform puts them; Preview is a step before them, at the left.
        answers = QDialogButtonBox()
        self.accept_button = answers.addButton("Accept late start", QDialogButtonBox.ButtonRole.AcceptRole)
        self.accept_button.setObjectName("lateAccept")
        self.accept_button.setEnabled(False)
        cancel = answers.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        cancel.setProperty("quiet", True)
        answers.accepted.connect(self.accept)
        answers.rejected.connect(self.reject)
        buttons.addWidget(preview)
        buttons.addStretch(1)
        buttons.addWidget(answers)
        layout.addLayout(buttons)

    def chosen_minutes(self) -> int:
        return int(self.minutes.currentData())

    def show_trace(self, trace: dict, titles: dict[str, str]) -> None:
        self.changes.clear()
        for move in trace.get("moves") or []:
            self.changes.addItem(f"{titles.get(move['block_id'], move['block_id'])}: {_late_move(move)}")
        for block in trace.get("unplaced") or []:
            self.changes.addItem(block["title"] + " no longer fits and will stay on the task list.")
        if self.changes.count() == 0:
            self.changes.addItem("No homework needs to move.")
        moved = len(trace.get("moves") or [])
        unplaced = len(trace.get("unplaced") or [])
        self.summary.setText(f"{moved} tasks move · {unplaced} tasks no longer fit")
        self.changes.setVisible(True)
        self.accept_button.setEnabled(True)
        self.minutes.setEnabled(False)


def _late_move(move: dict) -> str:
    was, now = move.get("from_start"), move.get("to_start")
    if was and now:
        return f"from {hhmm_text(was)} to {hhmm_text(now)}"
    if now:
        return f"placed at {hhmm_text(now)}"
    if was:
        return f"moves off {hhmm_text(was)} and is not placed"
    return "not placed"


class SpreadDialog(Dialog):
    def __init__(self, parent: QWidget | None, assignment: dict, from_date: str) -> None:
        super().__init__(parent)
        self.setObjectName("spreadDialog")
        self.setWindowTitle("Spread " + assignment["title"])
        layout = QVBoxLayout(self)
        # The same vocabulary as every other surface: "1 h 30 min total · due Thu 17 Sep".
        due = due_label(assignment.get("due"), monday_of(from_date))
        total = length_label(int(assignment.get("estimate_min") or 0))
        card, box = info_card(assignment["title"], f"{total} total · due {due}")
        form = Form()
        box.addLayout(form)
        self.session = QComboBox()
        self.session.setObjectName("spreadSession")
        remaining = max(SLOT_MIN, int(assignment.get("unplanned_min") or SLOT_MIN))
        chosen = min(60, remaining - remaining % SLOT_MIN, 180)
        for minutes in range(SLOT_MIN, 181, SLOT_MIN):
            self.session.addItem(f"{minutes} minutes", minutes)
        self.session.setCurrentIndex(max(0, self.session.findData(chosen)))
        form.addRow("Sessions of", self.session)
        self.from_date = QDateEdit(QDate.fromString(from_date, "yyyy-MM-dd"))
        self.from_date.setObjectName("spreadFrom")
        self.from_date.setDisplayFormat(DATE_FORMAT)
        self.from_date.setCalendarPopup(True)
        self.from_date.setMaximumDate(QDate.fromString(assignment["due"][:10], "yyyy-MM-dd"))
        form.addRow("Starting", self.from_date)
        self.error = _error_label()
        box.addWidget(self.error)
        layout.addWidget(card)
        buttons = _buttons(self)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Preview sessions")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def session_min(self) -> int:
        return int(self.session.currentData())

    def from_iso(self) -> str:
        return self.from_date.date().toString("yyyy-MM-dd")


class AvailabilityDialog(Dialog):
    def __init__(self, parent: QWidget | None, preferences: dict, subjects: list[str] | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("availabilityDialog")
        self.setWindowTitle("Availability")
        self.setMinimumWidth(640)
        self._protected = deepcopy(preferences.get("protected") or [])
        self._study = deepcopy(preferences.get("study_windows") or [])
        layout = QVBoxLayout(self)
        card, box = plain_card()
        body = QWidget()
        self._body = body
        body.installEventFilter(self)
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        box.addWidget(FitScroll(body, "availabilityScroll"))
        layout.addWidget(card, 1)
        form.addWidget(QLabel("Protected time"))
        self.protected_list = QListWidget()
        self.protected_list.setObjectName("protectedWindows")
        self.protected_list.setMaximumHeight(100)
        form.addWidget(self.protected_list)
        add_protected = QPushButton("Add protected time")
        add_protected.setObjectName("protectedAdd")
        add_protected.setProperty("quiet", True)
        add_protected.clicked.connect(self._add_protected)
        form.addWidget(add_protected)
        form.addWidget(QLabel("Preferred study hours"))
        self.study_list = QListWidget()
        self.study_list.setObjectName("studyWindows")
        self.study_list.setMaximumHeight(100)
        form.addWidget(self.study_list)
        # A new window's hours, and optionally the one subject it is kept for.
        study_row = QHBoxLayout()
        self.study_start = QTimeEdit(QTime(19, 0))
        self.study_start.setObjectName("studyStart")
        self.study_start.setDisplayFormat(time_format())
        self.study_end = QTimeEdit(QTime(21, 0))
        self.study_end.setObjectName("studyEnd")
        self.study_end.setDisplayFormat(time_format())
        self.study_subject = QComboBox()
        self.study_subject.setObjectName("studySubject")
        self.study_subject.setEditable(True)
        self.study_subject.addItem("Any subject", "")
        for subject in subjects or []:
            self.study_subject.addItem(subject, subject)
        for label, widget in (("From", self.study_start), ("to", self.study_end)):
            study_row.addWidget(QLabel(label))
            study_row.addWidget(widget)
        study_row.addWidget(self.study_subject, 1)
        form.addLayout(study_row)
        add_study = QPushButton("Add study window")
        add_study.setObjectName("studyAdd")
        add_study.setProperty("quiet", True)
        add_study.clicked.connect(self._add_study)
        form.addWidget(add_study)
        self.cutoff = QComboBox()
        self.cutoff.setObjectName("availabilityCutoff")
        self.cutoff.addItem("No cutoff", None)
        for start in _grid_starts():
            if start < "06:15":
                continue
            self.cutoff.addItem(hhmm_text(start), start)
        current = preferences.get("day_cutoff")
        self.cutoff.setCurrentIndex(max(0, self.cutoff.findData(current)))
        form.addWidget(self.cutoff)
        form.addWidget(QLabel("When may FlexWeek plan homework?"))
        self.work_editor = WorkWindowsEditor(preferences.get("work_windows") or [], subjects, body)
        # Save is this dialog's answer, so the editor's Add is plain here.
        self.work_editor.add_button.setProperty("quiet", True)
        form.addWidget(self.work_editor)
        self.error = _error_label()
        form.addWidget(self.error)
        buttons = _buttons(self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._render()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._fit_width()
        fit_scroll_dialog(self, min_height=600)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        # A work window's row added later can be wider than the dialog opened. The scrolled body
        # hears that as a layout request; the dialog itself never does.
        if watched is self._body and event.type() == QEvent.Type.LayoutRequest:
            self._fit_width()
        return super().eventFilter(watched, event)

    def _fit_width(self) -> None:
        """Wide enough for every row, so the dialog only ever scrolls up and down."""
        even_fields(self)
        wanted = self._body.minimumSizeHint().width() + 2 * self.layout().contentsMargins().left() + 64
        if wanted > self.minimumWidth():
            self.setMinimumWidth(wanted)

    def accept(self) -> None:
        if self.work_editor.problem():
            return
        super().accept()

    def _render(self) -> None:
        self.protected_list.clear()
        for window in self._protected:
            item = QListWidgetItem(
                f"{window.get('kind')} · {hhmm_text(window['start'])} · {window['duration_min']}m · "
                + ",".join(DAYS[day] for day in window["days"])
            )
            self.protected_list.addItem(item)
        self.study_list.clear()
        for window in self._study:
            text = f"{hhmm_text(window['start'])} · {length_label(window['duration_min'])} · " + ",".join(
                DAYS[day] for day in window["days"]
            )
            if window.get("subject"):
                text += f" · {window['subject']} only"
            self.study_list.addItem(QListWidgetItem(text))

    def _add_protected(self) -> None:
        if len(self._protected) >= AVAILABILITY_LIMIT:
            self.error.setText("Up to 21 protected windows.")
            return
        self._protected.append(
            {"kind": PROTECTED_KINDS[0], "days": [0, 1, 2, 3, 4], "start": "18:00", "duration_min": 60}
        )
        self._render()

    def _add_study(self) -> None:
        if len(self._study) >= AVAILABILITY_LIMIT:
            self.error.setText("Up to 21 study windows.")
            return
        start = self.study_start.time().hour() * 60 + self.study_start.time().minute()
        end = self.study_end.time().hour() * 60 + self.study_end.time().minute()
        start, end = start - start % SLOT_MIN, end - end % SLOT_MIN
        if end - start < SLOT_MIN or start < DAY_START_MIN or end > DAY_END_MIN:
            self.error.setText("A study window runs between 06:00 and 23:00 and ends after it starts.")
            return
        window: dict = {"days": [0, 1, 2, 3, 4], "start": minutes_to_hhmm(start), "duration_min": end - start}
        typed = self.study_subject.currentText().strip()
        if typed and typed != "Any subject":
            window["subject"] = typed[:40]
        self.error.setText("")
        self._study.append(window)
        self._render()

    def protected(self) -> list[dict]:
        return deepcopy(self._protected)

    def study_windows(self) -> list[dict]:
        return deepcopy(self._study)

    def work_windows(self) -> list[dict]:
        return self.work_editor.windows()

    def day_cutoff(self) -> str | None:
        return self.cutoff.currentData()
