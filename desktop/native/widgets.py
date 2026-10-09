"""Native calendar and editors using the scheduler's existing data models."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import date, datetime, time, timedelta
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from pydantic import ValidationError
from PySide6.QtCore import (
    Property,
    QAbstractAnimation,
    QDate,
    QElapsedTimer,
    QEvent,
    QEventLoop,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSize,
    QStandardPaths,
    Qt,
    QTime,
    QTimer,
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
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QProxyStyle,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QStyleOptionButton,
    QStyleOptionSlider,
    QStylePainter,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)
from shiboken6 import isValid

from backend.availability import spread_sessions
from backend.explain import REASON_COPY
from backend.models import ESTIMATE_MAX_MIN, Assignment, TimeBlock, WeekRequest, due_is_timed, parse_due
from backend.slots import (
    DAY_END_MIN,
    DAY_START_MIN,
    SLOT_MIN,
    clock_to_minutes,
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
from desktop.native.fields import QUICK_LENGTHS, ClockField, DateField, DayPicker, Stepper
from desktop.native.fonts import caption, time_font, weighted
from desktop.native.hours.geometry import next_slot
from desktop.native.icons import pixmap as icon_pixmap
from desktop.native.look import CONFLICT_TEXT, resolved_palette
from desktop.native.menus import Menu
from desktop.native.motion import (
    EASE_MS,
    OUT,
    SEGMENT_MS,
    Clock,
    app_level,
    appear,
    between,
    duration,
    frame_interval_ms,
    moves,
    screen_rate,
    settle,
    vanish,
)
from desktop.native.reuse import (
    AVAILABILITY_LIMIT,
    DAYS_LONG,
    LATE_MINUTES,
    PROTECTED_KINDS,
    due_point,
    preview_conflict_message,
    routine_source_blocks,
    row_conflict,
)
from desktop.native.tokens import SHADOW_LARGE, SPACING, WEIGHT_REGULAR, WEIGHT_STRONG, Shadow, type_pt
from desktop.native.weekmodel import due_label, hhmm_text, length_label

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
# Meals first: 18:00–19:30 sits inside the afternoon activity window.
_MEAL_WINDOWS = ((7 * 60, 8 * 60), (12 * 60, 13 * 60), (18 * 60, 19 * 60 + 30))
_SCHOOL_START = hhmm_to_minutes(CATEGORIES["class"]["preset"]["start"])
_SCHOOL_END = hhmm_to_minutes(CATEGORIES["class"]["preset"]["end"])


def guess_locked_category(start: str) -> str:
    """A category for a new fixed time, from when it starts, until the student picks one."""
    minute = hhmm_to_minutes(start)
    for low, high in _MEAL_WINDOWS:
        if low <= minute < high:
            return "meals"
    if _SCHOOL_START <= minute < _SCHOOL_END:
        return "class"
    return "extra"


def day_range_words(days: list[int] | tuple[int, ...]) -> str:
    """Three or more days in a row as a range ("Mon–Fri"); otherwise a list ("Mon, Wed, Fri")."""
    if not days:
        return ""
    ordered = sorted(set(days))
    runs: list[list[int]] = [[ordered[0]]]
    for day in ordered[1:]:
        if day == runs[-1][-1] + 1:
            runs[-1].append(day)
        else:
            runs.append([day])
    parts: list[str] = []
    for run in runs:
        if len(run) >= 3:
            parts.append(f"{DAYS[run[0]]}–{DAYS[run[-1]]}")
        else:
            parts.extend(DAYS[day] for day in run)
    return ", ".join(parts)


SWATCH_PX = 12
# The eye inside the password box, and the room it keeps clear of the typing.
REVEAL_PX = 28
REVEAL_ICON_PX = 16
DETAIL_BOX_HEIGHT = 84
SCROLL_GAP = 16
DUE_SWITCH_EXTRA = 1
# An estimate of an hour or more can be spread over days; a shorter one is a single sitting.
SPREAD_MIN = 60
SPREAD_NOTHING = "Nothing left to spread: the rest is already done or focused."
DIALOG_USABLE_HEIGHT = 480
# Dates as a student reads them. "2026-09-27 23:59" made them work out which day that was.
DUE_DATE_FORMAT = "ddd d MMM yyyy"
DATE_FORMAT = "ddd d MMM yyyy"
DIALOG_MAX_HEIGHT = 700
# No-break space before the last word, so a narrow sheet never leaves "45." alone on a line.
SLOT_HINT = "Use a multiple of 15 minutes, such as 15, 30, or\u00a045."
DUE_BY_HINT = "FlexWeek plans it before this time."
DUE_PASSED = "That time has already passed."
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
# A day with more homework than this is called overfull in the plan's list. The planner still places
# earliest first (#41); the note only tells the student.
OVERFULL_DAY_MIN = 3 * 60
# How many rows of Unfinished homework show before the list scrolls: the half row says there is more.
UNFINISHED_ROWS = 3.5
REPEAT_NOTE = "Pick more days to repeat it."
SCHOOL_HOURS_NOTE = "The days and times you are at school, so nothing is planned then."
ROUTINE_LIST_HEIGHT = 104
REPLAN_TIP = (
    "Find new times for all of this week's homework, as if none had a time yet. Homework you placed "
    "yourself stays put. Use it when your week has changed a lot."
)
LATE_WAIT = "Press Preview first to see what moves."
# The same sentence the controller says when a preview with nothing ticked is saved anyway.
PREVIEW_NONE = "Select at least one item before saving."
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
        self._ring = QColor("transparent")
        # Where the chosen pill was last drawn, and where it leaves from for the segment just chosen.
        self._drawn: QRectF | None = None
        self._from = QRectF()
        self._slide = Clock(self)

    def _get_shade(self) -> int:
        return self._shade

    def _set_shade(self, value: int) -> None:
        self._shade = value
        self.update()

    shade = Property(int, _get_shade, _set_shade)

    def _get_ring(self) -> QColor:
        return self._ring

    def _set_ring(self, value: QColor) -> None:
        self._ring = QColor(value)
        self.update()

    ring = Property(QColor, _get_ring, _set_ring)

    def add(self, button: QAbstractButton) -> None:
        self.layout().addWidget(button)
        button.toggled.connect(self._chosen)

    def _chosen(self, on: bool) -> None:
        length = duration(SEGMENT_MS)
        if on and self._drawn is not None and self.isVisible() and length:
            self._from = QRectF(self._drawn)
            self._slide.stop()
            self._slide.start(length, lambda _at: self.update())
        self.update()

    def _pills(self, target: QRectF) -> list[tuple[QRectF, float]]:
        """The chosen pill as drawn now, with its opacity: sliding from where it was, or where things
        may not travel, fading from there to here."""
        if self._slide.state() == QAbstractAnimation.State.Stopped:
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
                painter.setPen(Qt.PenStyle.NoPen)
                # The small shadow (decision 6), 0 1 3: three widening rings, each a third of its opacity.
                for spread in (1.5, 1.0, 0.5) if shade else ():
                    painter.setBrush(QColor(0, 0, 0, round(shade / 3)))
                    painter.drawRoundedRect(
                        pill.adjusted(-spread, 1 - spread, spread, 1 + spread), radius, radius
                    )
                painter.setPen(QPen(self._ring, 1) if self._ring.alpha() else Qt.PenStyle.NoPen)
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
TOAST_MIN_HEIGHT = 44


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
        shown = self.text() or self._full
        words = self._short if self._short and shown == self._short else self._full
        width = self.fontMetrics().horizontalAdvance(words) + margins.left() + margins.right() + 2
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


class PlanButton(FittedButton):
    """Plan my homework: the window shrinks More to its icon before this shortens. The window picks
    its words (`NativeWindow._fit_plan_and_more`), so it asks for the room the words shown take."""

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._wide(self.text()), QPushButton.sizeHint(self).height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # Shown as "Plan", shorter than its short form, it asks no more: the bar decides whether it
        # has one row from its parts' smallest.
        shown = self.text()
        if shown and self._wide(shown) < self._wide(self._short):
            return QSize(self._wide(shown), super().minimumSizeHint().height())
        return super().minimumSizeHint()

    def _fit(self) -> None:
        # NativeWindow._fit_plan_and_more sets both labels; a resize mid-layout must not reset them.
        return

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        _refit_bar(self, event)


def _refit_bar(button: QPushButton, event: QEvent) -> None:
    """Large text reaches Plan and More after the window has fitted the bar. Fitted again only on
    the next resize, the bar's buttons moved under the pointer a moment after the change."""
    if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
        host = button.window()
        if hasattr(host, "_fit_plan_and_more"):
            host._fit_plan_and_more()
            host._schedule_bar_refit()


class MoreButton(FittedButton):
    """More in the top bar: its words, then its icon alone when the row is tighter still."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("More", "", parent)
        self.setIconSize(QSize(20, 20))
        icons.tint(self, "ellipsis")

    def sizeHint(self) -> QSize:  # noqa: N802
        # As Plan's: the window picks the words, so this asks for the room of those shown.
        return QSize(self._wide(self.text()), QPushButton.sizeHint(self).height())

    def _fit(self) -> None:
        # NativeWindow._fit_plan_and_more sets both labels; a resize mid-layout must not reset them.
        return

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        _refit_bar(self, event)


class EndsLayout(QLayout):
    """Two groups on one row, the first at its left and the second at its right, each as wide as it
    asks while there is room. Short of room, the first gives way first, down to its smallest, then
    the second; with no room for both at their smallest, the second goes under the first, still at
    the right. So the top bar is never squeezed until its words are cut."""

    def __init__(self, parent: QWidget | None = None, gap: int = 6, between: int | None = None) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        # `gap` between the rows once the second group goes under; `between` the groups side by side.
        self._gap = gap
        self.between = gap if between is None else between

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
            sum(hint.width() for hint in hints) + self.between * (len(hints) - 1),
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
        if least + self.between + second.minimumSize().width() <= area.width():
            right = min(second.sizeHint().width(), area.width() - self.between - least)
            left = min(first.sizeHint().width(), area.width() - self.between - right)
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
        self.card.setMinimumHeight(TOAST_MIN_HEIGHT)
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
        # Something laid over the whole window, such as Ctrl+K, stays over a notice said under it:
        # raised above it, the notice stayed bright over the dimmed window.
        host = self.parentWidget()
        if host is not None:
            direct = Qt.FindChildOption.FindDirectChildrenOnly
            for cover in host.findChildren(QWidget, options=direct):
                if cover.property("covers") and cover.isVisible():
                    cover.raise_()
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
        # Wrapping was switched back on a moment ago; asked before this, the layouts still gave the
        # height of one unwrapped line and the second line was cut.
        self.card.layout().invalidate()
        self.layout().invalidate()
        height = max(self.heightForWidth(width), self.minimumSizeHint().height())
        # Bottom right of the page, 16 pixels in from its corner, and never past the window's foot.
        # A design with a bar of its own along the foot (Retro's taskbar) is kept clear of.
        page = over.currentWidget() if isinstance(over, QStackedWidget) else over
        inset = page.bottom_inset() if hasattr(page, "bottom_inset") else 0
        right = area.left() + area.width() - TOAST_FOOT + TOAST_SHADOW
        bottom = min(area.top() + area.height(), host.height()) - inset - TOAST_FOOT + TOAST_SHADOW
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


# A card is its picture and this much around it, with this much between cards.
CARD_WIDTH_PAD = 22
CARD_GAP = 12


class ChoiceCard(QFrame):
    """A picture and a name the student picks by clicking, or by Space or Enter."""

    chosen = Signal()

    def __init__(self, name: str, note: str, width: int, tag: str = "") -> None:
        super().__init__()
        self.setObjectName("setupChoice")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(name)
        self.setAccessibleDescription(note)
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 10, 10, 12)
        box.setSpacing(6)
        self.picture = QLabel()
        self.picture.setObjectName("setupChoicePicture")
        box.addWidget(self.picture)
        name_label = QLabel(name)
        name_label.setObjectName("setupChoiceName")
        name_label.setWordWrap(True)
        box.addWidget(name_label)
        self.note = QLabel(note)
        self.note.setObjectName("setupChoiceNote")
        self.note.setWordWrap(True)
        box.addWidget(self.note)
        # Only once it has a parent: shown before, it opens as a window of its own for a moment and
        # takes the keyboard from FlexWeek's window.
        self.note.setVisible(bool(note))
        box.addStretch(1)
        # Under the note, so names line up across a row whether or not a card carries one.
        if tag:
            self.tag = QLabel(tag)
            self.tag.setObjectName("setupChoiceTag")
            box.addWidget(self.tag)
        self.set_width(width)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.select(False)

    def set_width(self, width: int) -> None:
        """The picture this wide, and the card a little more."""
        self._width = width
        self.picture.setFixedSize(width, round(width * 0.625))
        self.setFixedWidth(width + CARD_WIDTH_PAD)

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


def card_columns(count: int, room: int, card_width: int, gap: int) -> int:
    """How many cards stand in a row in `room` pixels so that every row is full: the most that fit and
    divide the count evenly (six cards in three, or in two when three do not fit); when only one
    would, the fewest rows the room allows, sharing the cards out evenly."""
    fit = min(max(1, (room + gap) // (card_width + gap)), max(count, 1))
    even = max((columns for columns in range(1, fit + 1) if count % columns == 0), default=1)
    if even > 1 or fit == 1:
        return even
    rows = -(-count // fit)
    return -(-count // rows)


class CardGrid(QWidget):
    """ChoiceCards in rows that are full, as many to a row as the width holds, every card in a row as
    tall as the tallest. A flow left the last card alone on a row of its own."""

    def __init__(self, card_width: int, gap: int = CARD_GAP) -> None:
        super().__init__()
        self.setObjectName("settingsRow")
        self.cards: list[ChoiceCard] = []
        self._card_width = card_width
        self._gap = gap
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(gap)

    def set_cards(self, cards: list[ChoiceCard]) -> None:
        for card in self.cards:
            self._grid.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.cards = list(cards)
        self._columns = 0
        self._place(self.width())

    def columns(self) -> int:
        return self._columns

    def set_card_width(self, card_width: int) -> None:
        """Cards of another width: as many to a row as the width holds now."""
        self._card_width = card_width
        self._columns = 0
        self._place(self.width())
        self.updateGeometry()

    def _place(self, room: int) -> None:
        columns = card_columns(len(self.cards), room, self._card_width, self._gap)
        if columns == self._columns:
            return
        self._columns = columns
        for at, card in enumerate(self.cards):
            self._grid.addWidget(card, at // columns, at % columns)
            card.show()
        self._grid.setColumnStretch(columns, 1)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # One card wide whatever the columns are now, or a grid set out wide could never be given less.
        return QSize(self._card_width, super().minimumSizeHint().height())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place(event.size().width())


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


def sheet_note(words: str) -> QLabel:
    """A sentence under a sheet's title or a section's heading, in the muted colour."""
    note = QLabel(words)
    note.setObjectName("cardNote")
    note.setWordWrap(True)
    return note


def sheet_section(box: QVBoxLayout, title: str, note: str) -> None:
    """A part of a longer sheet: its heading and what it is for, in place of a card inside the card."""
    heading = QLabel(title)
    heading.setObjectName("cardTitle")
    box.addWidget(heading)
    box.addWidget(sheet_note(note))


def footer_line() -> QFrame:
    """A 1-pixel line across a sheet, between its scrolled body and the answers under it."""
    line = QFrame()
    line.setObjectName("sheetFooterLine")
    line.setFixedHeight(1)
    return line


def sheet_footer(
    box: QVBoxLayout, *answers: QWidget, left: QWidget | None = None, divided: bool = False
) -> QHBoxLayout:
    """A sheet's answers in a row at its bottom right, the quietest first and the filled one last, as
    the mock-ups draw them. `left` is a step before them, at the left edge. `divided` puts the thin line
    over the row, for a sheet whose body scrolls."""
    if divided:
        box.addWidget(footer_line())
    else:
        box.addSpacing(SPACING[1])
    row = QHBoxLayout()
    row.setSpacing(SPACING[2])
    if left is not None:
        row.addWidget(left)
    row.addStretch(1)
    for answer in answers:
        row.addWidget(answer)
    box.addLayout(row)
    return row


def sheet_button(words: str, kind: str = "", name: str = "") -> QPushButton:
    """A sheet's answer: filled by default, else `kind`, any of quiet, outlined, danger and tonal said
    together ("outlined danger"). Never the Enter key's, unless the sheet makes it so."""
    button = QPushButton(words)
    if name:
        button.setObjectName(name)
    button.setAutoDefault(False)
    for word in kind.split():
        button.setProperty(word, True)
    return button


class WhyOff(QLabel):
    """One line under a main button that says why it cannot be pressed yet. It shows while the button
    is off and goes when it is on, so a button that looks off is never left unexplained (#91)."""

    def __init__(
        self,
        button: QAbstractButton,
        words: str,
        align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight,
    ) -> None:
        super().__init__(words)
        self.setObjectName("whyOff")
        self.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
        self._button = button
        button.installEventFilter(self)
        self._follow()

    def say(self, words: str) -> None:
        self.setText(words)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._button and event.type() == QEvent.Type.EnabledChange:
            self._follow()
        return False

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ParentChange:
            self._follow()
        return super().event(event)

    def _follow(self) -> None:
        off = not self._button.isEnabled()
        if off and self.parentWidget() is None:
            # Shown before it is in a sheet, it opens as a window of its own for a moment and takes
            # the keyboard from FlexWeek's window. It follows the button again once it has a parent.
            return
        self.setVisible(off)
        # A sheet is as tall as what it holds, so it grows and shrinks by this line.
        sheet = self.window()
        if isinstance(sheet, Dialog) and sheet.isVisible():
            sheet.refit()


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

    def _toggle(self) -> tuple[QStyleOptionButton, int]:
        """The style's option with no words, its rect the first line's row, and where the words start.

        The style centres the toggle in the rect it is given. Given the whole switch, the toggle sat
        by the middle of words that wrapped, and the words, drawn from there, ran past its foot."""
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        mark = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        gap = self.style().pixelMetric(QStyle.PixelMetric.PM_CheckBoxLabelSpacing, option, self)
        option.rect = QRect(0, 0, self.width(), max(mark.height(), self.fontMetrics().height()))
        return option, mark.right() + 1 + gap

    def _words(self, width: int) -> QRect:
        """Where the words go on a switch `width` wide: after the toggle, the first line level with it."""
        option, start = self._toggle()
        column = max(width - start - 2, 1)
        lines = self.fontMetrics().boundingRect(
            QRect(0, 0, column, 100_000), int(Qt.TextFlag.TextWordWrap), self.text()
        )
        top = (option.rect.height() - self.fontMetrics().height()) // 2
        return QRect(start, top, column, lines.height())

    def sizeHint(self) -> QSize:  # noqa: N802
        _option, start = self._toggle()
        width = start + self.fontMetrics().size(0, self.text()).width() + 2
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        _option, start = self._toggle()
        longest = max((self.fontMetrics().horizontalAdvance(word) for word in self.text().split()), default=0)
        # One line high, as a label's: how tall its words are when they wrap is heightForWidth's answer.
        return QSize(start + longest + 2, self.sizeHint().height())

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        option, _start = self._toggle()
        return max(option.rect.height(), self._words(width).bottom() + 1) + 2

    def hitButton(self, pos: QPoint) -> bool:  # noqa: N802
        return self.rect().contains(pos)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        option, _start = self._toggle()
        words = self._words(self.width())
        # A row taller than the words, as beside the Look editor's colour chips, keeps them in its middle.
        top = max(0, (self.height() - max(option.rect.height(), words.bottom() + 1)) // 2)
        option.rect = option.rect.translated(0, top)
        painter = QStylePainter(self)
        painter.drawControl(QStyle.ControlElement.CE_CheckBox, option)
        group = QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        painter.setPen(self.palette().color(group, QPalette.ColorRole.WindowText))
        painter.drawText(
            words.translated(0, top),
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


# Between a label and the field under it, and between one field and the next label.
STACKED_GAP = SPACING[0] + 2


class Form(QFormLayout):
    """A form whose labels sit on their fields' line of words. A text label given with its field is
    made a FieldLabel for that field.

    A stacked form, a sheet's, puts each label above its field instead (5.1 A of 0.17.2), so every
    field starts at one edge; a row given no words then spans the column rather than leaving a gap."""

    def __init__(self, parent: QWidget | None = None, *, stacked: bool = False) -> None:
        super().__init__(parent)
        self.stacked = stacked
        self.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if stacked:
            self.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
            self.setVerticalSpacing(STACKED_GAP)

    def addRow(self, *row: object) -> None:  # noqa: N802
        if len(row) == 2 and isinstance(row[0], str):
            words, field = row
            if not self.stacked:
                super().addRow(FieldLabel(words, _first_line(field)), field)
            elif words:
                label = QLabel(words)
                label.setObjectName("fieldLabel")
                super().addRow(label, field)
            else:
                super().addRow(field)
            return
        super().addRow(*row)

    def add_pair(self, *fields: tuple[str, QWidget]) -> QWidget:
        """Short fields side by side as one row, each under its label, such as Start and End: one
        under the other, the block editor was taller than a laptop's window."""
        row = bare(QWidget())
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(SPACING[3])
        for words, field in fields:
            column = QVBoxLayout()
            column.setSpacing(STACKED_GAP)
            label = QLabel(words)
            label.setObjectName("fieldLabel")
            column.addWidget(label)
            column.addWidget(field)
            line.addLayout(column)
        line.addStretch(1)
        super().addRow(row)
        return row


def even_labels(root: QWidget) -> None:
    """One label column for every form under `root`, as wide as its longest label. Each card's form
    sized its own, so its fields began at a different x from the next card's (Grok Bot's 0.17.0
    audit, T33: Updates against Account and Setup)."""
    labels = root.findChildren(FieldLabel)
    for label in labels:
        label.setMinimumWidth(0)
    widest = max((label.sizeHint().width() for label in labels), default=0)
    for label in labels:
        label.setMinimumWidth(widest)


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


class PasswordField(QLineEdit):
    """A password box with an eye inside its right edge that shows what is typed and hides it again.
    A Show button beside the box made it 76 pixels narrower than the username box above it."""

    def __init__(self) -> None:
        super().__init__()
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.setTextMargins(0, 0, REVEAL_PX, 0)
        self._colour = "#5b6474"
        self.reveal = QToolButton(self)
        self.reveal.setObjectName("passwordReveal")
        self.reveal.setCheckable(True)
        self.reveal.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reveal.setIconSize(QSize(REVEAL_ICON_PX, REVEAL_ICON_PX))
        self.reveal.toggled.connect(self._show)
        self._show(False)

    def set_colour(self, colour: str) -> None:
        self._colour = colour
        self._show(self.reveal.isChecked())

    def _show(self, shown: bool) -> None:
        self.setEchoMode(QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password)
        words = "Hide password" if shown else "Show password"
        self.reveal.setIcon(icons.icon("eye-off" if shown else "eye", self._colour))
        self.reveal.setToolTip(words)
        self.reveal.setAccessibleName(words)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        side = min(REVEAL_PX, self.height() - 4)
        self.reveal.setGeometry(self.width() - side - 4, (self.height() - side) // 2, side, side)


class FitScroll(QScrollArea):
    """A dialog's body that scrolls only past the room it is given. A plain scroll area asks for a
    modest fixed height, so a dialog opened short of its content, or tall with nothing in it."""

    def __init__(self, body: QWidget, name: str, *, gap: int | None = None) -> None:
        super().__init__()
        self.setObjectName(name)
        # Room between the content and the bar's handle; None keeps the handle's own edge.
        self._gap = OverlayBar.EDGE if gap is None else gap
        bare(self)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # The keyboard starts on the first field in it, not on the box around them.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        overlay_scroll_bars(self)
        self.setWidget(bare(body))
        self._rim = body.layout().contentsMargins().right() if body.layout() else 0
        self.verticalScrollBar().rangeChanged.connect(self._clear_of_bar)

    def _clear_of_bar(self, _low: int, high: int) -> None:
        # The thin bar lies over the content's right edge, so while it shows the content stops short of it.
        layout = self.widget().layout()
        if layout is None:
            return
        margins = layout.contentsMargins()
        right = self._rim + (OverlayBar.WIDE + OverlayBar.EDGE + self._gap if high > 0 else 0)
        if margins.right() != right:
            layout.setContentsMargins(margins.left(), margins.top(), right, margins.bottom())

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
# A sheet is as tall as its content, up to this much of its window's height, and scrolls past that.
SHEET_MOST = 0.9
# One width scale for every sheet's card (5.1 A of 0.17.2): forms, and lists such as Routines and Help.
SHEET_FORM = 440
SHEET_LIST = 600
# A row of a preview holds a tick, three choices and a sentence about it.
SHEET_PREVIEW = 720


def _give_focus_back(widget: QWidget) -> None:
    """Put the keyboard back on `widget` once the sheet over it has closed, if it is still there."""
    if isValid(widget) and widget.isVisible():
        widget.window().activateWindow()
        widget.setFocus(Qt.FocusReason.OtherFocusReason)


class SheetShade(QWidget):
    """The window under a sheet, dimmed, so the sheet reads as the one thing to answer. It only paints:
    the sheet is modal, so the window takes no clicks while it is up."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setObjectName("sheetShade")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # Made by the window before its sheet is built (dim_window), and not yet taken by that sheet.
        self.waiting = False
        # Its fade has begun, so the sheet that takes it does not start the fade over.
        self.fading = False

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, round(255 * SHEET_DIM)))
        painter.end()


def dim_window(host: QWidget) -> SheetShade:
    """Start dimming `host` for a sheet that is about to be built. Building a sheet takes tens of
    milliseconds with nothing drawn, so the dim starts first and the sheet's constructor runs behind
    it. The sheet takes this dim when it shows, so there is one dim, fading from the click."""
    top = host.window()
    shade = SheetShade(top)
    shade.waiting = True
    shade.setGeometry(top.rect())
    shade.show()
    shade.raise_()
    level = app_level()
    appear(shade, level)
    # No fade was started on a window that is not on screen or at motion Off; the sheet decides then.
    shade.fading = shade.graphicsEffect() is not None
    _draw_first_frames(shade)
    running = getattr(shade, "_motion_running", None)
    if running is not None:
        # Held while the sheet is built, so the dim goes on from its first frame when the sheet shows
        # rather than jumping ahead by the time the build took.
        running[0].pause()
    return shade


def drop_waiting_dim(host: QWidget) -> None:
    """Take down a dim no sheet took, because building or opening the sheet failed."""
    # children(), not findChildren(): the latter hands a sheet to the window to own.
    for child in host.window().children():
        if isinstance(child, SheetShade) and child.waiting:
            child.waiting = False
            child.hide()
            child.deleteLater()


def _draw_first_frames(shade: SheetShade) -> None:
    """Let the event loop paint the dim's first frame before the sheet's build holds it up. Typing and
    clicks stay queued for the sheet."""
    effect = shade.graphicsEffect()
    if effect is None:
        return
    limit = 2 * frame_interval_ms(screen_rate(shade))
    started = QElapsedTimer()
    started.start()
    flags = QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
    while getattr(effect, "opacity", 1.0) <= 0 and started.elapsed() < limit:
        QApplication.processEvents(flags)
    QApplication.processEvents(flags)


class Dialog(QDialog):
    """A dialog that eases in the first time it shows, at the app's motion level, with one width for
    each kind of field in it.

    A sheet (decision 23 of 0.17) is drawn inside its window rather than as a window of its own: its
    card, with the large shadow, over the window dimmed. To Qt it is still a modal dialog, so the
    window's keys wait for it and `activeModalWidget` finds it. Made without a parent it is a window."""

    _appeared = False
    _shade: SheetShade | None = None
    # How much of its window's height a sheet may take before it scrolls; None is the window less its gap.
    _most_share: float | None = None
    # Help, Routines and About share one top, so a short About is not centred under a tall Help.
    _pin_top = False
    # Where the keyboard was when the sheet opened, and goes back to when it closes.
    _came_from: QWidget | None = None

    def __init__(self, parent: QWidget | None = None, *, sheet: bool = False) -> None:
        super().__init__(parent)
        self.sheet = sheet and parent is not None
        self.card: QFrame | None = None
        self.card_width = SHEET_FORM
        # The sheet's card and the room for its shadow, which fade in as one: the card's own effect
        # is its shadow, and a widget holds one effect.
        self._face: QWidget | None = None
        # Widgets of the page under a sheet, held still while the sheet fades in.
        self._frozen: list[QWidget] = []
        if self.sheet:
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setProperty("sheet", True)

    def card_body(self, title: str, width: int = SHEET_FORM) -> QVBoxLayout:
        """The layout the dialog's content goes in, on its one card: the sheet itself, or the card on a
        window's page. The body is the card, not a box drawn inside it. The card is `width` wide and
        starts with `title` and a close button, since a sheet has no window frame to carry either."""
        self.setWindowTitle(title)
        self.card_width = width
        outer = QVBoxLayout(self)
        self.card = QFrame()
        self.card.setObjectName("sheetCard")
        self.card.setMinimumWidth(width)
        inner = QVBoxLayout(self.card)
        inner.setContentsMargins(SHEET_PAD, SHEET_PAD, SHEET_PAD, SHEET_PAD)
        inner.setSpacing(SPACING[2])
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        self.heading = QLabel(title)
        self.heading.setObjectName("sheetTitle")
        close = QPushButton()
        close.setObjectName("sheetClose")
        close.setProperty("quiet", True)
        close.setAccessibleName("Close")
        close.setToolTip("Close (Esc)")
        # Esc closes from the keyboard; taking focus, it would have been where typing starts.
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.setAutoDefault(False)
        icons.tint(close, "x")
        close.clicked.connect(self.reject)
        head.addWidget(self.heading, 1)
        head.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        inner.addLayout(head)
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
        if self.sheet and self._came_from is None:
            came = QApplication.focusWidget()
            self._came_from = came if came is not None and not self.isAncestorOf(came) else None
        super().showEvent(event)
        even_fields(self)
        if self.sheet:
            self._over_window()
        from desktop.native.feel import apply_feel, current, extra_stylesheet

        ctx = current()
        if ctx is not None:
            extra = extra_stylesheet(
                ctx.base_sheet, ctx.feel, ctx.palette, ctx.tokens, ctx.look, ("sheetTitle",), nested=False
            )
            base = self.property("feelBaseSheet")
            if not isinstance(base, str):
                base = self.styleSheet()
                self.setProperty("feelBaseSheet", base)
            self.setStyleSheet((base + extra) if extra else base)
            apply_feel(self, ctx)
        self.refit()
        if not self._appeared:
            self._appeared = True
            level = app_level()
            for part in self._content():
                appear(part, level, rise=True)
            if self._shade is not None and not self._shade.fading:
                appear(self._shade, level)
            elif self._shade is not None:
                running = getattr(self._shade, "_motion_running", None)
                if running is not None:
                    running[0].resume()
            if self.sheet and duration(EASE_MS) > 0:
                self._freeze_page()

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

    def _freeze_page(self) -> None:
        """The shade covers the whole window, and a frame of it would repaint everything under it.
        Those widgets keep the picture they already have until the fade has landed. The shade and the
        sheet still paint. The window itself is left able to paint, or the shade could not."""
        parent = self.parentWidget()
        if parent is None:
            return
        host = parent.window()
        frozen: list[QWidget] = []
        # Walked with children(), not findChildren(): findChildren hands the sheet itself to the
        # window to own, and an exec()'d sheet then outlives its last reference.
        waiting: list[QObject] = list(host.children())
        while waiting:
            child = waiting.pop()
            if child is self or not isinstance(child, QWidget):
                continue
            waiting.extend(child.children())
            if child is self._shade or not child.updatesEnabled():
                continue
            child.setUpdatesEnabled(False)
            frozen.append(child)
        self._frozen = frozen
        QTimer.singleShot(0, self._thaw_when_settled)

    def _thaw_when_settled(self) -> None:
        if not isValid(self):
            return
        for widget in (self._face, self._shade, *self._content()):
            if widget is not None and getattr(widget, "_motion_running", None) is not None:
                QTimer.singleShot(frame_interval_ms(60), self._thaw_when_settled)
                return
        self._thaw()

    def _thaw(self) -> None:
        frozen = self._frozen
        self._frozen = []
        for child in frozen:
            if isValid(child):
                child.setUpdatesEnabled(True)

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802
        self._thaw()
        super().hideEvent(event)
        if self._came_from is not None:
            QTimer.singleShot(0, partial(_give_focus_back, self._came_from))
            self._came_from = None
        if self._shade is not None:
            # Hidden as the sheet goes: left for deleteLater alone it stayed over the page for a frame.
            self._shade.hide()
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
        share = self._most_share
        most_h = (
            round(room.height() * share) + 2 * SHEET_ROOM
            if share is not None
            else room.height() - 2 * SHEET_GAP + 2 * SHEET_ROOM
        )
        # Measured from the card itself: the dialog's layout keeps the card's size from before its fonts
        # arrived.
        card = self.card
        shadow = 2 * SHEET_ROOM
        # The card is its width on the scale, narrower only in a window without room for it.
        inner = min(self.scaled_width(), most_w - shadow)
        card.setFixedWidth(inner)
        hint = card.sizeHint().expandedTo(card.minimumSizeHint()).expandedTo(card.minimumSize())
        # Words that wrap need the height they take at this width, not at the width they would like.
        tall = card.heightForWidth(inner) if card.hasHeightForWidth() else hint.height()
        width = inner + shadow
        height = min(max(hint.height(), tall) + shadow, most_h)
        self.setFixedSize(width, height)
        left = room.x() + (room.width() - width) // 2
        if self._pin_top:
            top = room.y() + SHEET_GAP - SHEET_ROOM
            top = min(top, room.y() + max(0, room.height() - height))
        else:
            top = room.y() + (room.height() - height) // 2
        self.move(left, top)
        if self.card is not None and self.card.graphicsEffect() is None:
            dark = self.palette().color(QPalette.ColorRole.WindowText).lightness() > 128
            lift(self.card, SHADOW_LARGE, dark)
        if self._shade is None:
            # The one the window made before building this sheet, if it did.
            self._shade = self._waiting_shade(host) or SheetShade(host)
            # Gone with the sheet however it goes, even if it is freed while still on screen.
            self.destroyed.connect(self._shade.deleteLater)
            host.installEventFilter(self)
        self._shade.setGeometry(host.rect())
        self._shade.show()
        self._shade.raise_()

    @staticmethod
    def _waiting_shade(host: QWidget) -> SheetShade | None:
        for child in host.children():
            if isinstance(child, SheetShade) and child.waiting:
                child.waiting = False
                return child
        return None

    def scaled_width(self) -> int:
        """The card's width on the scale at the student's text size: 440 and 600 are at Normal, and
        grow with Large, which set Edit event's two scope choices wider than a 440 card."""
        return round(self.card_width * max(1.0, self.font().pointSizeF() / type_pt("body")))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if (
            self._shade is not None
            and watched is self.parentWidget().window()
            and event.type() in (QEvent.Type.Resize, QEvent.Type.Move)
        ):
            self._over_window()
        return super().eventFilter(watched, event)


class ConfirmSheet(Dialog):
    """A question as a sheet over its window: what is asked, and an answer for each way out. Esc and the
    close button are "stay", so nothing is answered. The answer pressed is `self.answer`, its key."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        question: str,
        answers: tuple[tuple[str, str, str], ...],
        *,
        default: str | None = None,
        note: str = "",
        width: int = SHEET_FORM,
        left: tuple[str, str, str] | None = None,
    ) -> None:
        """`answers` are (key, words, kind) from the quietest to the filled one; `kind` as `sheet_button`
        takes it. `default` is the key Enter presses; none, so Enter changes nothing."""
        super().__init__(parent, sheet=True)
        self.setObjectName("confirmSheet")
        self.answer: str | None = None
        self._default = default
        box = self.card_body(title, width)
        self.question = QLabel(question)
        self.question.setObjectName("confirmQuestion")
        self.question.setWordWrap(True)
        box.addWidget(self.question)
        if note:
            box.addWidget(sheet_note(note))
        self.buttons: dict[str, QPushButton] = {}

        def made(key: str, words: str, kind: str) -> QPushButton:
            button = sheet_button(words, kind, f"confirm-{key}")
            # The key is read off the button that was pressed: a lambda naming the sheet kept it from
            # being freed once closed.
            button.setProperty("answer", key)
            button.clicked.connect(self._pressed)
            button.setDefault(key == default)
            button.setAutoDefault(key == default)
            self.buttons[key] = button
            return button

        sheet_footer(
            box,
            *(made(*answer) for answer in answers),
            left=made(*left) if left is not None else None,
        )

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        # The keyboard starts on the answer Enter gives, not on whichever button is first.
        if self._default in self.buttons:
            self.buttons[self._default].setFocus()

    def _pressed(self) -> None:
        self.answer = self.sender().property("answer")
        self.accept()


def confirm_sheet(
    parent: QWidget | None, title: str, question: str, yes: str, *, danger: bool = True
) -> ConfirmSheet:
    """A question before something that cannot be taken back lightly, as a sheet. The answers say what
    they do, and Cancel is the default and the one Esc gives, so Enter pressed out of habit changes
    nothing. The answer is red only when it destroys something; signing out keeps everything, so it is
    not."""
    return ConfirmSheet(
        parent,
        title,
        question,
        (("stay", "Cancel", "outlined"), ("yes", yes, "danger" if danger else "")),
        default="stay",
    )


def confirm(parent: QWidget | None, title: str, question: str, yes: str, *, danger: bool = True) -> bool:
    sheet = confirm_sheet(parent, title, question, yes, danger=danger)
    sheet.exec()
    return sheet.answer == "yes"


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
        self.setObjectName("blockDialog")
        layout = self.card_body("Edit event" if existing else "Add fixed time")
        body = QWidget()
        form = Form(body, stacked=True)
        form.setContentsMargins(0, 0, 0, 0)
        self.title = _line("blockTitle", self._original["title"])
        form.addRow("Title", self.title)
        self.day_picker = DayPicker(self._original["days"], "blockDay")
        self.days = self.day_picker.buttons
        # A week's blocks are its own, so ticking more days repeats a block within this week only.
        # One line, never wrapped, under the boxes it is about. Wrapped, the form gave it two lines'
        # height for one line of words, or one line's height for two.
        self.repeat_note = QLabel(REPEAT_NOTE)
        self.repeat_note.setObjectName("blockRepeatNote")
        days_field = bare(QWidget())
        days_column = QVBoxLayout(days_field)
        days_column.setContentsMargins(0, 0, 0, 0)
        days_column.addWidget(self.day_picker)
        days_column.addWidget(self.repeat_note)
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
        self.start = ClockField(QTime.fromString(self._original.get("start") or start, "HH:mm"))
        self.start.setObjectName("blockStart")
        # Start and End are what a student knows ("08:00 to 14:30"); the length is worked out from
        # them. A Duration box beside End was a second way to say the same thing, and could disagree.
        self._length = int(self._original["duration_min"])
        self.end = ClockField(
            self._minutes_clock(self._clock_to_minutes(self.start.time()) + self._length), end=True
        )
        self.end.setObjectName("blockEnd")
        form.add_pair(("Start", self.start), ("End", self.end))
        self.duration_line = QLabel()
        self.duration_line.setObjectName("blockDurationLine")
        form.addRow("Duration", self.duration_line)
        self.start.timeChanged.connect(self._keep_length)
        self.end.timeChanged.connect(self._show_length)
        self._show_length()
        self.category = QComboBox()
        self.category.setObjectName("blockCategory")
        self.category.addItem("None", None)
        for key, info in CATEGORIES.items():
            self.category.addItem(info["label"], key)
        self._guessing = not existing and not (self._original.get("category") or category)
        chosen = self._original.get("category") or category
        if self._guessing:
            chosen = guess_locked_category(self._original.get("start") or start)
        if chosen and self.category.findData(chosen) < 0:
            self.category.addItem(chosen, chosen)
        self._applying_guess = True
        self.category.setCurrentIndex(max(0, self.category.findData(chosen)))
        self._applying_guess = False
        form.addRow("Category", self.category)
        self.category.currentIndexChanged.connect(self._chose_category)
        self.start.timeChanged.connect(self._maybe_guess)
        self.more_details = QPushButton()
        self.more_details.setObjectName("blockMoreDetails")
        self.more_details.setProperty("outline", True)
        self.more_details.setCheckable(True)
        self.more_details.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        form.addRow("", self.more_details)
        details = bare(QWidget())
        details.setObjectName("blockDetails")
        extra = Form(details, stacked=True)
        extra.setContentsMargins(0, 0, 0, 0)
        # The link is under More details: on the main card it read as a second thing to fill in.
        self.spotify = _line("blockSpotify", self._original.get("spotify_url") or "", 500)
        self.spotify.setPlaceholderText("https://open.spotify.com/…")
        extra.addRow("Spotify link", self.spotify)
        form.addRow("", details)
        self.more_details.toggled.connect(details.setVisible)
        open_details = bool(self._original.get("spotify_url"))
        self.more_details.setChecked(open_details)
        self._name_block_toggle(open_details)
        self.more_details.toggled.connect(self._name_block_toggle)
        details.setVisible(open_details)
        self.more_details.toggled.connect(self.refit)
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

    def _name_block_toggle(self, open_: bool) -> None:
        self.more_details.setText("Fewer details" if open_ else "More details")

    def _chose_category(self, *_index: object) -> None:
        if self._applying_guess:
            return
        self._guessing = False

    def _maybe_guess(self, *_args: object) -> None:
        if not self._guessing:
            return
        key = guess_locked_category(self.start.time().toString("HH:mm"))
        self._applying_guess = True
        self.category.setCurrentIndex(max(0, self.category.findData(key)))
        self._applying_guess = False

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

    def _clock_to_minutes(self, clock: QTime) -> int:
        return clock.hour() * 60 + clock.minute()

    def _minutes_clock(self, minutes: int) -> QTime:
        minutes %= 24 * 60
        return QTime(minutes // 60, minutes % 60)

    def _span(self) -> int:
        return self.end.minutes() - self.start.minutes()

    def _span_problem(self) -> str:
        return "End must be after Start." if self._span() <= 0 else ""

    def _keep_length(self, *_args: object) -> None:
        """Moving the start moves the end with it, as a calendar does, so the length stays."""
        self.end.setTime(self._minutes_clock(self._clock_to_minutes(self.start.time()) + self._length))

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
        super().__init__(parent, sheet=True)
        # Setup's own time box, imported here: setup imports this module.
        from desktop.native.setup import QuarterTime

        self._original = deepcopy(school) if school is not None else None
        self._result: dict | None = None
        self.setObjectName("schoolHoursDialog")
        box = self.card_body("School hours")
        box.addWidget(sheet_note(SCHOOL_HOURS_NOTE))
        start = (school or {}).get("start") or "08:00"
        minutes = int((school or {}).get("duration_min") or 390)
        days = (school or {}).get("days") or ([] if school else [0, 1, 2, 3, 4])
        self.days = DayPicker(list(days), "schoolDay")
        begin = QuarterTime(start)
        begin.setAccessibleName("School starts")
        finish = QuarterTime(minutes_to_hhmm(hhmm_to_minutes(start) + minutes), end=True)
        finish.setAccessibleName("School ends")
        self.times = SimpleNamespace(
            start=begin,
            end=finish,
            span=lambda: (begin.hhmm(), finish.minutes() - begin.minutes()),
        )
        form = Form(stacked=True)
        form.addRow("Days", self.days)
        form.addRow("Start", begin)
        form.addRow("End", finish)
        box.addLayout(form)
        # Said only when it is true, as setup does: under a week of school days it read as a warning.
        self.hint = QLabel("No school days picked means no school on the calendar.")
        self.hint.setObjectName("setupHint")
        self.hint.setWordWrap(True)
        box.addWidget(self.hint)
        self._follow_days()
        self.days.changed.connect(self._follow_days)
        self.error = _error_label()
        box.addWidget(self.error)
        buttons = _buttons(self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

    def _follow_days(self) -> None:
        self.hint.setVisible(not self.days.days())

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

    def __init__(
        self,
        due: str,
        name: str,
        *,
        stacked: bool = False,
        today: str | None = None,
        default_time: int = 9 * 60,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # The time a box opened later starts at.
        self._default_time = default_time
        # Stacked puts the time under the date, for a form too narrow to hold them side by side.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(STACKED_GAP)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(row)
        # The switch sat 6 px under the date, tight beside the rows around it. One more is all an 800 px
        # window has room for with the Sessions rows in: test_sheets holds Add homework to 90 % of it.
        outer.addSpacing(DUE_SWITCH_EXTRA)
        self.date = DateField()
        self.date.setObjectName(name)
        self.date.setDisplayFormat(DUE_DATE_FORMAT)
        self.date.setMinimumDate(QDate(2000, 1, 1))
        self.date.setMaximumDate(QDate(2099, 12, 31))
        self.date.setAccessibleName("Due date")
        if today:
            self.date.today = QDate.fromString(today, "yyyy-MM-dd")
        self.date.watch_popup(self)
        # "At a set time" read like "do it at", and it sets the time the work must be done by.
        self.timed = Switch("Due by")
        self.timed.setObjectName(f"{name}Timed")
        self.timed.setAccessibleName("Due by a set time")
        self.time = ClockField()
        self.time.setObjectName(f"{name}Time")
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
        self.hint = sheet_note(DUE_BY_HINT)
        outer.addWidget(self.hint)
        self.problem = _error_label()
        self.problem.setObjectName("validationError")
        self.problem.setAccessibleName("Due date problem")
        self.problem.setVisible(False)
        outer.addWidget(self.problem)
        self.set_value(due)
        self.date.dateChanged.connect(self._follow_year)
        self.date.dateChanged.connect(self._say_changed)
        self.timed.toggled.connect(self._show_time)
        self.timed.toggled.connect(self._say_changed)
        self.time.timeChanged.connect(self._say_changed)

    def set_value(self, due: str) -> None:
        day, minute = parse_due(due)
        self.date.setDate(QDate(day.year, day.month, day.day))
        timed = due_is_timed(due)
        fallback = self._default_time
        self.time.setTime(QTime(minute // 60, minute % 60) if timed else QTime(fallback // 60, fallback % 60))
        self.timed.setChecked(timed)
        self._show_time(timed)
        self._follow_year()

    def _follow_year(self, *_value: object) -> None:
        """The year is written only for a date outside this one: "Tue 15 Sep" says enough."""
        this_year = (self.date.today or QDate.currentDate()).year()
        other_year = self.date.date().year() != this_year
        wanted = DUE_DATE_FORMAT if other_year else DUE_DATE_FORMAT.replace(" yyyy", "")
        if self.date.displayFormat() != wanted:
            self.date.setDisplayFormat(wanted)

    def value(self) -> str:
        day = self.date.date().toString("yyyy-MM-dd")
        return f"{day}T{self.time.time().toString('HH:mm')}" if self.timed.isChecked() else day

    def _show_time(self, timed: bool) -> None:
        self.time.setVisible(timed)
        self.hint.setVisible(timed)

    def show_problem(self, text: str) -> None:
        """Say what is wrong with the due, beside it in the sheet's error colour; empty clears it."""
        self.problem.setText(text)
        self.problem.setVisible(bool(text))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt virtual
        if event.type() == QEvent.Type.Show and watched.objectName() == "qt_datetimedit_calendar":
            keep_on_screen(watched, self.window().screen().availableGeometry())
        return super().eventFilter(watched, event)

    def _say_changed(self, *_value: object) -> None:
        # Connected straight to `changed.emit`, each signal handed its value to a signal that takes
        # none: a TypeError inside Qt, and nothing connected to `changed` ran.
        self.changed.emit()


def spread_session_min(remaining: int) -> int:
    """How long each spread session is: an hour, or what is left when that is less, cut to the 15-minute
    grid and never over three hours."""
    return max(SLOT_MIN, min(60, remaining - remaining % SLOT_MIN, 180))


def spread_words(sessions: list[dict], due: str) -> str:
    """What spreading will do, for the grey line under the choice: "2 × 60 min on different days before
    it is due Sun 4 Oct."."""
    if not sessions:
        return SPREAD_NOTHING
    sizes = [int(item["duration_min"]) for item in sessions]
    full = sizes[0]
    whole = sizes.count(full)
    lead = f"{whole} × {full} min" if whole > 1 else f"{full} min"
    parts = lead if whole == len(sizes) else f"{lead} and {sizes[-1]} min"
    ahead = f"before it is due {due_label(due, '')}."
    if len(sizes) == 1:
        return f"{parts} in one session {ahead}"
    days = len({item["date"] for item in sessions})
    if days == len(sizes):
        return f"{parts} on different days {ahead}"
    return f"{parts} on the same day {ahead}" if days == 1 else f"{parts} over {days} days {ahead}"


def _day_on_screen(today: str | None, now: datetime | None) -> date:
    return date.fromisoformat(today) if today else (now or datetime.now()).date()


class HomeworkDialog(Dialog):
    _most_share = SHEET_MOST

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
        now: datetime | None = None,
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
                # Tomorrow, from the day on screen: work due today at 22:41 had no evening left to plan in.
                "due": due or (_day_on_screen(today, now) + timedelta(days=1)).isoformat(),
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
        self._today = today
        self._clock = now
        self._result: dict | None = None
        self._spread = False
        # "choose" to pick a time for a session that needs one, "unpin" to let FlexWeek move it again.
        self._request: str | None = None
        self.setObjectName("homeworkDialog")
        layout = self.card_body("Edit homework" if assignment else "Add homework")
        # The body scrolls so the dialog cannot outgrow a laptop screen. It already carried notes,
        # links and a checklist; one more row took it to 815px, past the bottom of a 768px display.
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        form = Form(stacked=True)
        body_layout.addLayout(form)
        self.title = _line("homeworkTitle", self._original["title"])
        # Homework saved with no category is still homework, so it gets the same hint.
        self.title.setPlaceholderText("e.g. History essay")
        form.addRow("Title", self.title)
        # Where it is placed, said under the title in Edit; a new or unplaced homework says nothing.
        self.placed_line = sheet_note(self._placed_words())
        form.addRow("", self.placed_line)
        form.setRowVisible(self.placed_line, bool(self.placed_line.text()))
        self.due = DueField(
            self._original["due"],
            "homeworkDue",
            stacked=True,
            today=today,
            default_time=self._school_end(),
        )
        form.addRow("Due", self.due)
        self.due.changed.connect(self._clear_due_problem)
        self._add_when(form)
        self.estimate = LengthBox("homeworkEstimate", self._original["estimate_min"])
        self.stepper = Stepper(self.estimate, QUICK_LENGTHS)
        form.addRow("Estimated time", self.stepper)
        self.estimate_hint = QLabel(SLOT_HINT)
        self.estimate_hint.setObjectName("homeworkEstimateHint")
        self.estimate_hint.setWordWrap(True)
        form.addRow("", self.estimate_hint)
        # Said only for a length that is wrong, so the row goes with its words.
        form.setRowVisible(self.estimate_hint, False)
        # In one go, or spread over the days before the due: a setting of the homework, said in a line
        # under it, not a second sheet. Made right after the length it divides, so the keyboard reaches it
        # next: Tab follows the order widgets were made in.
        self.spread_choice = Segmented(
            (("In one go", "one"), ("Spread over days", "spread")), "homeworkSpread"
        )
        form.addRow("Sessions", self.spread_choice)
        self.spread_line = sheet_note("")
        form.addRow("", self.spread_line)
        self.spread_choice.currentIndexChanged.connect(self._follow_spread)
        self.estimate.valueChanged.connect(self._follow_spread)
        self.due.changed.connect(self._follow_spread)
        self.when.currentIndexChanged.connect(self._follow_spread)
        self.estimate.valueChanged.connect(self._recheck_length)
        # Not while typing: "4" on the way to 45 is not yet a mistake. A step or a pill is always good.
        self.estimate.editingFinished.connect(self._say_length)
        if self._length_problem():
            # Stored before the limit, so the student is told before they try to save it.
            self._say_length()
        self._follow_spread()
        self.error = _error_label()
        form.addRow("", self.error)
        # The row goes with its words: an empty one left a gap above Finished.
        form.setRowVisible(self.error, False)
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
        self.more_details = QPushButton()
        self.more_details.setObjectName("homeworkMoreDetails")
        self.more_details.setProperty("outline", True)
        self.more_details.setCheckable(True)
        # As wide as its words at the column's edge, not a bar across the sheet.
        self.more_details.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        form.addRow("", self.more_details)
        details = bare(QWidget())
        details.setObjectName("homeworkDetails")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        extra = Form(stacked=True)
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
        extra.addRow("Notes", self.notes)
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
        # A list with nothing in it looked like another field to fill in.
        self.no_links = sheet_note("No links yet")
        details_layout.addWidget(self.no_links)
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
        self.no_steps = sheet_note("No steps yet")
        details_layout.addWidget(self.no_steps)
        for step in self._original.get("checklist") or []:
            self._append_check(step["id"], step["text"], step.get("done", False))
        self._show_lists()
        if assignment is not None:
            self.title.textChanged.connect(self._disable_placing)
            self.notes.textChanged.connect(self._disable_placing)
            self.estimate.valueChanged.connect(self._disable_placing)
            self.due.changed.connect(self._disable_placing)
            self.course.textChanged.connect(self._disable_placing)
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
        self._name_toggle(open_details)
        self.more_details.toggled.connect(self._name_toggle)
        details.setVisible(open_details)
        # The sheet grows with the details, up to the room its window has.
        self.more_details.toggled.connect(self.refit)
        # A time box shown under the date makes the body taller: the sheet is fitted again, not scrolled.
        self.due.timed.toggled.connect(self.refit)
        area = FitScroll(body, "homeworkScroll", gap=SCROLL_GAP)
        layout.addWidget(area, 1)
        self._scroll = area
        # Delete is not one of the dialog's answers: quiet words at the left, away from Save, as the
        # block editor has it. Only homework that exists can go. The answers stay put under a line while
        # the body scrolls.
        layout.addWidget(footer_line())
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

    def _school_end(self) -> int:
        """The minute school ends, from the saved school hours, or 15:00 with none: work due at a set
        time is usually due when the school day does."""
        blocks = getattr(getattr(self.parent(), "session", None), "blocks", None) or []
        locked = [item for item in blocks if item.get("kind") == "locked"]
        school = next((item for item in locked if item.get("id") == "school"), None) or next(
            (item for item in locked if item.get("category") == "class"), None
        )
        if school is None or not school.get("start"):
            return 15 * 60
        return min(hhmm_to_minutes(school["start"]) + int(school["duration_min"]), 23 * 60 + 45)

    def _placed_words(self) -> str:
        """"Placed Fri 15:30", or with several times "Placed Fri 15:30 and Sat 10:00 · 2 times"; empty
        when none of this homework's times has a place on the calendar."""
        placed = [block for block in self._open_sessions() if block.get("start")]
        at = sorted((block["days"][0], block["start"]) for block in placed)
        if not at:
            return ""
        names = [f"{DAYS[day]} {hhmm_text(start)}" for day, start in at]
        if len(names) == 1:
            return f"Placed {names[0]}"
        return f"Placed {', '.join(names[:-1])} and {names[-1]} · {len(names)} times"

    def _name_toggle(self, open_: bool) -> None:
        self.more_details.setText("Fewer details" if open_ else "More details")
        icons.tint(self.more_details, "chevron-up" if open_ else "chevron-down", gap=6)
        self.more_details.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    def _show_lists(self) -> None:
        for items, none in ((self.links, self.no_links), (self.checks, self.no_steps)):
            items.setVisible(items.count() > 0)
            none.setVisible(items.count() == 0)

    def _open_sessions(self) -> list[dict]:
        """This homework's unfinished times on the week in the window, which the dialog reads from the
        window's session so a pinned one can be shown and set again."""
        session = getattr(self.parent(), "session", None)
        if session is None:
            return []
        return [
            block
            for block in session.blocks
            if block.get("assignment_id") == self._original["id"] and not block.get("completed")
        ]

    def _add_when(self, form: Form) -> None:
        """Under Due: "Let FlexWeek pick a time", or "Do it at" a day and time, which pins the time
        so no plan moves it. Homework spread over several times keeps Spread's own way."""
        self._form = form
        sessions = self._open_sessions()
        placed = next((block for block in sessions if block.get("pinned") and block.get("start")), None)
        self._placed = (placed["days"][0], placed["start"]) if placed else None
        self.when = Segmented((("Let FlexWeek pick a time", "plan"), ("Do it at", "fixed")), "homeworkWhen")
        form.addRow("When", self.when)
        fixed = bare(QWidget())
        fixed.setObjectName("homeworkFixed")
        column = QVBoxLayout(fixed)
        column.setContentsMargins(0, 0, 0, 0)
        day, start = self._default_placement()
        if self._placed:
            day, start = self._placed[0], hhmm_to_minutes(self._placed[1])
        self.when_day = DayPicker([day], "homeworkWhenDay")
        self._day = day
        column.addWidget(self.when_day)
        clock = QHBoxLayout()
        clock.setContentsMargins(0, 0, 0, 0)
        self.when_time = ClockField(QTime(start // 60, start % 60))
        self.when_time.setObjectName("homeworkWhenTime")
        self.when_time.setAccessibleName("Do it at time")
        clock.addWidget(self.when_time)
        clock.addStretch(1)
        column.addLayout(clock)
        self.when_problem = _error_label()
        self.when_problem.setAccessibleName("Do it at problem")
        self.when_problem.setVisible(False)
        column.addWidget(self.when_problem)
        form.addRow("", fixed)
        self.when_note = sheet_note("")
        form.addRow("", self.when_note)
        self._fixed_row = fixed
        self.when.setCurrentIndex(1 if self._placed else 0)
        if len(sessions) > 1:
            for part in (self.when, fixed, self.when_note):
                form.setRowVisible(part, False)
            self._spread_out = True
        else:
            self._spread_out = False
        self._follow_when()
        self.when.currentIndexChanged.connect(self._follow_when)
        self.when.currentIndexChanged.connect(self.refit)
        self.when_day.changed.connect(self._pick_day)
        self.when_time.timeChanged.connect(self._follow_when)

    def _default_placement(self) -> tuple[int, int]:
        """Today if the week on screen has it, else Monday, at 16:00 or the next quarter hour after it."""
        now = self._now()
        today = date.fromisoformat(self._today) if self._today else now.date()
        week = getattr(getattr(self.parent(), "session", None), "week_start", None)
        if week is not None and monday_of(today.isoformat()) != week:
            return 0, 16 * 60
        quarter = (now.hour * 60 + now.minute) // 15 * 15 + 15
        return today.weekday(), min(max(16 * 60, quarter), 23 * 60 + 45)

    def _pick_day(self) -> None:
        """One day only: ticking another unticks the first, and the last one cannot be unticked."""
        days = self.when_day.days()
        fresh = [day for day in days if day != self._day]
        self._day = fresh[0] if fresh else self._day
        if days != [self._day]:
            self.when_day.blockSignals(True)
            self.when_day.set_days([self._day])
            self.when_day.blockSignals(False)
        self._follow_when()

    def _fixed_at(self) -> dict | None:
        """The day and start picked under "Do it at", or None when FlexWeek picks the time."""
        if self.when.currentData() != "fixed":
            return None
        return {"day": self._day, "start": self.when_time.time().toString("HH:mm")}

    def _follow_when(self, *_args: object) -> None:
        fixed = self._fixed_at()
        if not self._spread_out:
            # Said only for Do it at: the dialog is already near the height of a laptop screen.
            self._form.setRowVisible(self._fixed_row, fixed is not None)
            self._form.setRowVisible(self.when_note, fixed is not None)
        self.when_problem.setVisible(False)
        self.when_note.setText(
            f"Stays on {DAYS[fixed['day']]} at {fixed['start']} when you plan again." if fixed else ""
        )

    def _when_changed(self) -> bool:
        """Whether the student changed what the dialog opened with. A choice they left alone is not
        sent, so saving never moves or pins anything they did not ask about."""
        fixed = self._fixed_at()
        if self._spread_out:
            return False
        if fixed is None:
            return self._placed is not None
        return self._placed is None or (fixed["day"], fixed["start"]) != tuple(self._placed)

    def _fixed_problem(self, fixed: dict, due: str) -> str:
        """Why that day and time cannot be kept, in the words a drop on the calendar uses."""
        session = getattr(self.parent(), "session", None)
        week = getattr(session, "week_start", None)
        if week is None:
            return ""
        start = hhmm_to_minutes(fixed["start"])
        sessions = self._open_sessions()
        length = int(sessions[0]["duration_min"]) if sessions else self.estimate.value()
        problem = span_problem([], "", fixed["day"], start, start + length, due_point(due, week))
        return (problem or "").replace(", so it stayed where it was", "")

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
        return SLOT_HINT if minutes % SLOT_MIN else ""

    def _say_length(self) -> bool:
        """Say under the box what is wrong with the length, in the error colour, or the usual hint."""
        problem = self._length_problem()
        self.estimate_hint.setText(problem or SLOT_HINT)
        self.estimate_hint.setProperty("problem", bool(problem))
        self._form.setRowVisible(self.estimate_hint, bool(problem))
        if self.isVisible():
            self.refit()
        self.estimate_hint.style().unpolish(self.estimate_hint)
        self.estimate_hint.style().polish(self.estimate_hint)
        return bool(problem)

    def _recheck_length(self, *_args: object) -> None:
        # Only once Save has refused: while a length is being typed, "1" is not yet a mistake.
        if self.estimate_hint.property("problem"):
            self._say_length()

    def _disable_placing(self, *_args: object) -> None:
        # Placing acts on the saved homework, so an unsaved edit turns the buttons off.
        for button in self._session_buttons:
            button.setEnabled(False)

    def _spread_figures(self) -> tuple[int, str, list[dict]]:
        """The session length, the day the sessions start and the sessions themselves, for the values as
        they stand now. Every open time of this homework is replaced, so only focus already given counts."""
        due = self._chosen_due()
        remaining = max(0, self.estimate.value() - int(self._original.get("focus_minutes") or 0))
        session_min = spread_session_min(remaining)
        today = self._now().date().isoformat()
        ahead = str(getattr(getattr(self.parent(), "session", None), "selected_day", "") or "")
        start = max(today, ahead)
        from_date = min(start, parse_due(due)[0].isoformat())
        sessions, _off_grid = spread_sessions(
            estimate_min=self.estimate.value(),
            focus_minutes=int(self._original.get("focus_minutes") or 0),
            planned_min=0,
            due=due,
            session_min=session_min,
            from_date=from_date,
        )
        return session_min, from_date, sessions

    def _follow_spread(self, *_args: object) -> None:
        """The choice shows for an hour or more that FlexWeek is to place: a time picked by hand is one
        time, and it is one go under an hour. Hiding it takes the choice back to one go."""
        shown = (
            self.estimate.value() >= SPREAD_MIN
            and not self._spread_out
            and self.when.currentData() != "fixed"
        )
        self._form.setRowVisible(self.spread_choice, shown)
        if not shown:
            self.spread_choice.setCurrentIndex(0)
        # The line says what Spread over days will do, so it has nothing to say for one go.
        spreading = shown and self.spread_choice.currentData() == "spread"
        self._form.setRowVisible(self.spread_line, spreading)
        if spreading:
            self.spread_line.setText(spread_words(self._spread_figures()[2], self._chosen_due()))
        if self.isVisible():
            self.refit()

    def spread_requested(self) -> bool:
        return self._spread

    def spread_plan(self) -> dict:
        """How the window spreads the saved homework: the length of each session and the day they start."""
        session_min, from_date, _sessions = self._spread_figures()
        return {"session_min": session_min, "from_date": from_date}

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
        self._show_lists()
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
        self._show_lists()
        self.check_text.clear()
        self._show_error("")

    def _chosen_due(self) -> str:
        """The due as the student left it. An old 23:59 that still means the same end of the day is
        kept as it was stored, so opening and saving changes nothing."""
        chosen, before = self.due.value(), self._original["due"]
        return before if parse_due(chosen) == parse_due(before) else chosen

    def _now(self) -> datetime:
        """Now on one clock: the one given to the dialog, else the window's, else the dialog's today."""
        if self._clock is not None:
            return self._clock
        session = getattr(self.parent(), "session", None)
        if session is not None:
            return datetime.fromtimestamp(session.now_ms() / 1000)
        if self._today:
            return datetime.combine(date.fromisoformat(self._today), time.min)
        return datetime.now()

    def _due_passed(self) -> bool:
        """Whether the student set a deadline that is already over. A saved deadline they did not
        change is left alone, and so is finished homework, so old work can still be edited."""
        if self.completed.isChecked():
            return False
        chosen = self._chosen_due()
        if chosen == self._original["due"]:
            return False
        try:
            day, minute = parse_due(chosen)
        except ValueError:
            # Not a date: the saved homework's own check says so, in its words.
            return False
        now = self._now()
        return (day, minute) < (now.date(), now.hour * 60 + now.minute)

    def _clear_due_problem(self) -> None:
        self.due.show_problem("")

    def accept(self) -> None:
        if self._say_length():
            self.estimate.setFocus()
            return
        if self._due_passed():
            self.due.show_problem(DUE_PASSED)
            self._scroll.ensureWidgetVisible(self.due)
            self.due.date.setFocus()
            return
        fixed = self._fixed_at()
        if fixed is not None and self._when_changed():
            problem = self._fixed_problem(fixed, self._chosen_due())
            if problem:
                self.when_problem.setText(problem)
                self.when_problem.setVisible(True)
                self._scroll.ensureWidgetVisible(self.when_problem)
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
        if self._when_changed():
            # Not part of the saved homework: the window's save reads it to pin or free its time.
            candidate["fixed_at"] = fixed
        try:
            Assignment.model_validate(
                {key: value for key, value in candidate.items() if key in Assignment.model_fields}
            )
        except ValueError as error:
            self._show_error(_homework_problem(error))
            return
        self._spread = self.spread_choice.currentData() == "spread"
        self._result = candidate
        super().accept()

    def assignment(self) -> dict:
        return deepcopy(self._result if self._result is not None else self._original)


# The evenings "No homework after" offers, in Setup and in Availability alike.
CUTOFFS = ("20:00", "20:30", "21:00", "21:30", "22:00", "22:30", "23:00")


def fill_cutoff(box: QComboBox, current: str | None) -> None:
    """No limit and the CUTOFFS, with the saved time chosen. A time saved before the list was shortened
    stays on it, so opening the page and saving does not quietly drop it."""
    box.clear()
    box.addItem("No limit", None)
    for hhmm in sorted({*CUTOFFS, *([current] if current else [])}):
        box.addItem(hhmm_text(hhmm), hhmm)
    box.setCurrentIndex(max(0, box.findData(current)))


def _grid_starts() -> list[str]:
    return [minutes_to_hhmm(minute) for minute in range(DAY_START_MIN, DAY_END_MIN, SLOT_MIN)]


def beside_words(clash: str) -> str:
    """What a time says when another block is already there: it is allowed, and both are drawn."""
    return f"{clash} is at that time too. Both will show, side by side."


class PreviewDialog(Dialog):
    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        summary: str,
        rows: list[dict],
        existing: list[dict],
    ) -> None:
        super().__init__(parent, sheet=True)
        self.setObjectName("stage3PreviewDialog")
        self._rows = deepcopy(rows)
        self._existing = existing
        self._first = True
        self._rebuilding = False
        box = self.card_body(title, SHEET_PREVIEW)
        if summary:
            box.addWidget(sheet_note(summary))
        self._list = QWidget()
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        box.addWidget(FitScroll(self._list, "stage3PreviewScroll"), 1)
        self.confirm = sheet_button("Save preview", "", "stage3PreviewConfirm")
        self.confirm.setDefault(True)
        self.confirm.clicked.connect(self.accept)
        cancel = sheet_button("Cancel", "outlined")
        cancel.clicked.connect(self.reject)
        sheet_footer(box, cancel, self.confirm, divided=True)
        # Whichever it is that keeps the button off, said under it.
        self.why_off = WhyOff(self.confirm, "")
        box.addWidget(self.why_off)
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
        for index, row in enumerate(self._rows):
            conflict = row_conflict(row, self._rows, self._existing)
            if self._first and row.get("invalid"):
                row["checked"] = False
            self._list_layout.addWidget(self._row_widget(index, row, conflict))
        self._first = False
        selected = [row for row in self._rows if row.get("checked")]
        self.confirm.setEnabled(bool(selected))
        even_fields(self)
        self.why_off.say(PREVIEW_NONE)
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
        # Another block at that time is allowed, as on the calendar; the row says which, so it is a choice.
        beside = conflict and not row.get("invalid")
        detail = QLabel(
            beside_words(conflict) if beside else preview_conflict_message(row, self._rows, self._existing)
        )
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


def overdue_unfinished(items: list[dict], now: datetime | None = None) -> list[dict]:
    """Homework whose deadline is already past. The engine's unfinished list also holds work due
    today or tomorrow; this list is only what is late."""
    moment = datetime.now() if now is None else now
    return [item for item in items if _deadline_passed(item.get("due"), moment)]


def _deadline_passed(due: object, now: datetime) -> bool:
    if not isinstance(due, str) or not due:
        return False
    try:
        day, minute = parse_due(due)
    except ValueError:
        return False
    return datetime.combine(day, datetime.min.time()) + timedelta(minutes=minute) <= now


class UnfinishedPanel(QWidget):
    plan_requested = Signal(str)
    delete_requested = Signal(str)
    collapsed = Signal()

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
        dismiss.setProperty("outlined", True)
        dismiss.clicked.connect(self._collapse)
        row.addWidget(dismiss)
        row.addStretch(1)
        layout.addLayout(row)
        self.hide()

    def _collapse(self) -> None:
        self.collapsed.emit()
        self.hide()

    def set_items(self, items: list[dict], now: datetime | None = None) -> None:
        items = overdue_unfinished(items, now)
        self.list.clear()
        for item in items:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            text = QLabel(f"{item['title']} · {length_label(int(item['remaining_min']))} left")
            text.setObjectName("unfinishedRow")
            row_layout.addWidget(text, 1)
            button = QPushButton("Plan here")
            button.setObjectName(f"planUnfinished-{item['id']}")
            # The row's answer, drawn as a tint beside the outlined Delete, each with room round its words.
            button.setProperty("tonal", True)
            button.setProperty("roomy", True)
            button.clicked.connect(
                lambda _checked=False, item_id=item["id"]: self.plan_requested.emit(item_id)
            )
            row_layout.addWidget(button)
            delete = QPushButton("Delete")
            delete.setObjectName(f"deleteUnfinished-{item['id']}")
            delete.setProperty("outlined", True)
            delete.setProperty("roomy", True)
            delete.setToolTip("Delete this homework and its times in every week. You can undo this.")
            delete.clicked.connect(
                lambda _checked=False, item_id=item["id"]: self.delete_requested.emit(item_id)
            )
            row_layout.addWidget(delete)
            wrapper = QListWidgetItem()
            self.list.addItem(wrapper)
            self.list.setItemWidget(wrapper, row)
        self._fit_rows()
        self.setVisible(bool(items))

    def _fit_rows(self) -> None:
        """Each row as tall as its buttons are once the look has styled them, and the list as tall as
        its rows up to about three and a half, so a fourth shows it scrolls (#79). The rows were measured
        before the look reached their buttons, so every button was cut top and bottom."""
        rows = []
        for index in range(self.list.count()):
            wrapper = self.list.item(index)
            row = self.list.itemWidget(wrapper)
            for part in (row, *row.findChildren(QWidget)):
                part.ensurePolished()
            wrapper.setSizeHint(row.sizeHint())
            rows.append(row.sizeHint().height())
        if rows:
            # As tall as its rows, as the plan review is: one row in a box eight rows deep read as empty.
            room = round(UNFINISHED_ROWS * max(rows))
            self.list.setFixedHeight(min(sum(rows), room) + 2 * self.list.frameWidth() + 4)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._fit_rows()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self._fit_rows()


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


def overfull_days(trace: dict) -> list[tuple[int, int]]:
    """Each day, in week order, whose planned homework adds up to more than OVERFULL_DAY_MIN, with its
    minutes. School and other fixed blocks are not homework, and finished sessions are not planned."""
    minutes = [0] * 7
    for block in trace.get("placed") or []:
        days = block.get("days") or []
        if block.get("assignment_id") and block.get("start") and not block.get("completed") and days:
            minutes[days[0]] += int(block.get("duration_min") or 0)
    return [(day, total) for day, total in enumerate(minutes) if total > OVERFULL_DAY_MIN]


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
        dismiss.setProperty("tonal", True)
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
        for day, total in overfull_days(trace):
            said.append(f"{DAY_FULL[day]} has {length_label(total)} of homework.")
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
        from desktop.native.controller import plan_sentence

        self.heading.setText(plan_sentence(placed, waiting))
        for line in said:
            self.list.addItem(QListWidgetItem(line))
        # As tall as it needs and no taller. One line in a box four lines deep reads as an error.
        row = self.list.sizeHintForRow(0) if self.list.count() else 0
        self.list.setFixedHeight(min(row * len(said) + 2 * self.list.frameWidth() + 4, PLAN_REVIEW_MAX))
        # Open when something needs reading: homework with no time, or a day that is too full.
        open_list = bool(waiting) or bool(overfull_days(trace or {}))
        self.details.setChecked(open_list)
        self._show_details(open_list)
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
        minute: int | None = None,
    ) -> None:
        super().__init__(parent, sheet=True)
        self.setObjectName("chooseTimeDialog")
        self._block, self._blocks, self._due = block, blocks, due
        self._duration = int(block.get("duration_min") or SLOT_MIN)
        layout = self.card_body("Choose a time")
        layout.addWidget(sheet_note(f"For {block.get('title') or 'homework'}."))
        form = Form(stacked=True)
        picked = today if today in days else (days[0] if days else 0)
        self.day = DayPicker([picked], "chooseTimeDay", exclusive=True)
        for index, button in enumerate(self.day.buttons):
            button.setEnabled(index in days)
        form.addRow("Day", self.day)
        self.start = ClockField(QTime(16, 0))
        self.start.setObjectName("chooseTimeStart")
        self.start.setMinimumTime(QTime(6, 0))
        latest = DAY_END_MIN - self._duration
        self.start.setMaximumTime(QTime(latest // 60, latest % 60))
        if today in days and minute is not None:
            # The next quarter hour today, or with none left, the first one tomorrow when homework can go
            # there and the last one today when it cannot: 16:00 had often passed already.
            ahead, slot = next_slot(minute, first=6 * 60, last=latest)
            if ahead and today + ahead in days:
                self.day.set_days([today + ahead])
            elif ahead:
                slot = latest
            self.start.setTime(QTime(slot // 60, slot % 60))
        form.addRow("Start", self.start)
        self.length = LengthBox("chooseTimeLength", self._duration)
        self.stepper = Stepper(self.length, QUICK_LENGTHS)
        form.addRow("Length", self.stepper)
        layout.addLayout(form)
        self.problem = QLabel()
        self.problem.setObjectName("validationError")
        self.problem.setWordWrap(True)
        layout.addWidget(self.problem)
        # Another block at that time is allowed, as on the calendar; this says which, so it is a choice.
        self.beside_row = QFrame()
        self.beside_row.setObjectName("conflictRow")
        beside_line = QHBoxLayout(self.beside_row)
        beside_line.setContentsMargins(SPACING[2] + 4, SPACING[2], SPACING[2] + 4, SPACING[2])
        beside_line.setSpacing(SPACING[2])
        mark = QLabel()
        mark.setObjectName("conflictMark")
        ratio = self.devicePixelRatioF()
        mark.setPixmap(icon_pixmap("triangle-alert", CONFLICT_TEXT, 16, ratio))
        beside_line.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
        self.beside = QLabel()
        self.beside.setObjectName("chooseTimeBeside")
        self.beside.setWordWrap(True)
        beside_line.addWidget(self.beside, 1)
        layout.addWidget(self.beside_row)
        choices = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttons = QDialogButtonBox(choices)
        choose = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        choose.setText("Choose this time")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setProperty("quiet", True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.day.changed.connect(self._check)
        self.start.timeChanged.connect(self._check)
        self.length.valueChanged.connect(self._length_changed)
        self._check()

    def choice(self) -> tuple[int, int]:
        """The day and the start, to the minute the student picked."""
        return int(self.day.currentData()), self.start.time().hour() * 60 + self.start.time().minute()

    def length_min(self) -> int:
        return int(self.length.value())

    def _length_changed(self, *_args: object) -> None:
        self._duration = int(self.length.value())
        latest = DAY_END_MIN - self._duration
        self.start.setMaximumTime(QTime(latest // 60, latest % 60))
        self._check()

    def _check(self, *_args: object) -> None:
        day, start = self.choice()
        end = start + self._duration
        problem = span_problem(self._blocks, self._block["id"], day, start, end, self._due)
        self.problem.setText((problem or "").replace(", so it stayed where it was", ""))
        self.problem.setVisible(problem is not None)
        clash = span_clash(self._blocks, self._block["id"], day, start, end) if problem is None else None
        self.beside.setText(beside_words(clash) if clash else "")
        self.beside_row.setVisible(clash is not None)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(problem is None)


class RoutineDialog(Dialog):
    _pin_top = True

    def __init__(
        self,
        parent: QWidget | None,
        routines: dict[str, dict],
        blocks: list[dict],
        week_start: str,
    ) -> None:
        super().__init__(parent, sheet=True)
        self.setObjectName("routineDialog")
        self._routines = routines
        self._blocks = routine_source_blocks(blocks)
        self._week_start = week_start
        self.action: str | None = None
        self.routine_id: str | None = None
        self.destination = week_start
        self.days = list(range(7))
        layout = self.card_body("Routines", SHEET_LIST)
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACING[1])
        sheet_section(
            column,
            "Make a routine from this week",
            "Tick the fixed times to keep, give them a name, and copy them into any week later.",
        )
        self.name = _line("routineName")
        self.name.setPlaceholderText("Routine name")
        self.choices = QListWidget()
        self.choices.setObjectName("routineBlocks")
        # Room for about four fixed times before it scrolls; squeezed, it showed one and a half, and
        # at its own height it pushed Apply out of the sheet.
        self.choices.setFixedHeight(ROUTINE_LIST_HEIGHT)
        column.addWidget(self.choices)
        for block in self._blocks:
            days = day_range_words(block["days"])
            item = QListWidgetItem(f"{block['title']} · {days} · {hhmm_text(block['start'])}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, block["id"])
            self.choices.addItem(item)
        save = QPushButton("Save routine")
        save.setObjectName("saveRoutine")
        save.clicked.connect(self._save)
        # The name and the button that keeps it on one line, under the times they keep.
        keep = QHBoxLayout()
        keep.addWidget(self.name, 1)
        keep.addWidget(save)
        column.addLayout(keep)
        column.addSpacing(SPACING[2])
        sheet_section(
            column, "Use a saved routine", "Pick a routine, the week to copy it into and the days to copy."
        )
        self.empty = QLabel("No routines saved yet.")
        self.empty.setObjectName("routineEmpty")
        column.addWidget(self.empty)
        self.list = QListWidget()
        self.list.setObjectName("routineList")
        self.list.setFixedHeight(ROUTINE_LIST_HEIGHT)
        column.addWidget(self.list)
        for routine in routines.values():
            item = QListWidgetItem(f"{routine['name']} · {len(routine.get('blocks') or [])} fixed times")
            item.setData(Qt.ItemDataRole.UserRole, routine["id"])
            self.list.addItem(item)
        self.empty.setVisible(not routines)
        self.list.setVisible(bool(routines))
        dest = DateField(QDate.fromString(week_start, "yyyy-MM-dd"))
        dest.setObjectName("routineDestination")
        dest.setDisplayFormat(DATE_FORMAT)
        dest.setMinimumDate(QDate(2000, 1, 1))
        dest.setMaximumDate(QDate(2099, 12, 31))
        dest.dateChanged.connect(self._snap_destination)
        self._dest = dest
        self.day_picker = DayPicker(range(7), "routineDay")
        self._days = self.day_picker.buttons
        form = Form(stacked=True)
        form.addRow("Week of", dest)
        form.addRow("Days to copy", self.day_picker)
        column.addLayout(form)
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
            button.setVisible(bool(routines))
            button.setEnabled(bool(routines))
            actions.addWidget(button)
        actions.addStretch(1)
        column.addLayout(actions)
        layout.addWidget(FitScroll(body, "routineScroll"), 1)
        self.error = _error_label()
        layout.addWidget(self.error)

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
        super().__init__(parent, sheet=True)
        self.setObjectName("lateDialog")
        layout = self.card_body("Running late")
        layout.addWidget(
            sheet_note("Say how late you are and preview what moves. Nothing changes until you accept it.")
        )
        layout.addWidget(QLabel(context))
        self.minutes = QComboBox()
        self.minutes.setObjectName("lateMinutes")
        for value in LATE_MINUTES:
            self.minutes.addItem(f"{value} minutes", value)
        self.minutes.setCurrentIndex(1)
        form = Form(stacked=True)
        form.addRow("How late", self.minutes)
        layout.addLayout(form)
        self.summary = QLabel()
        self.summary.setObjectName("lateSummary")
        self.summary.setWordWrap(True)
        # Shown with the preview, like the list under it: empty, it left a gap above the buttons.
        self.summary.setVisible(False)
        layout.addWidget(self.summary)
        self.changes = QListWidget()
        self.changes.setObjectName("lateChanges")
        # Shown with the preview: before it, an empty box said nothing.
        self.changes.setVisible(False)
        layout.addWidget(self.changes)
        self.error = _error_label()
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        preview = QPushButton("Preview")
        preview.setObjectName("latePreview")
        preview.setProperty("outlined", True)
        preview.clicked.connect(self.preview_requested.emit)
        # The answers where the platform puts them; Preview is a step before them, at the left.
        answers = QDialogButtonBox()
        self.accept_button = answers.addButton("Accept late start", QDialogButtonBox.ButtonRole.AcceptRole)
        self.accept_button.setObjectName("lateAccept")
        self.accept_button.setProperty("roomy", True)
        self.accept_button.setEnabled(False)
        cancel = answers.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        cancel.setProperty("quiet", True)
        answers.accepted.connect(self.accept)
        answers.rejected.connect(self.reject)
        buttons.addWidget(preview)
        buttons.addStretch(1)
        buttons.addWidget(answers)
        layout.addLayout(buttons)
        layout.addWidget(WhyOff(self.accept_button, LATE_WAIT))

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
        self.summary.setVisible(True)
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
        super().__init__(parent, sheet=True)
        self.setObjectName("spreadDialog")
        layout = self.card_body("Spread homework")
        # The same vocabulary as every other surface: "1 h 30 min total · due Thu 17 Sep".
        due = due_label(assignment.get("due"), monday_of(from_date))
        total = length_label(int(assignment.get("estimate_min") or 0))
        layout.addWidget(sheet_note(f"{assignment['title']} · {total} total · due {due}"))
        form = Form(stacked=True)
        layout.addLayout(form)
        self.session = QComboBox()
        self.session.setObjectName("spreadSession")
        chosen = spread_session_min(int(assignment.get("unplanned_min") or SLOT_MIN))
        for minutes in range(SLOT_MIN, 181, SLOT_MIN):
            self.session.addItem(f"{minutes} minutes", minutes)
        self.session.setCurrentIndex(max(0, self.session.findData(chosen)))
        form.addRow("Sessions of", self.session)
        self.from_date = DateField(QDate.fromString(from_date, "yyyy-MM-dd"))
        self.from_date.setObjectName("spreadFrom")
        self.from_date.setDisplayFormat(DATE_FORMAT)
        self.from_date.setMaximumDate(QDate.fromString(assignment["due"][:10], "yyyy-MM-dd"))
        form.addRow("Starting", self.from_date)
        self.error = _error_label()
        layout.addWidget(self.error)
        buttons = _buttons(self)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Preview sessions")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def session_min(self) -> int:
        return int(self.session.currentData())

    def from_iso(self) -> str:
        return self.from_date.date().toString("yyyy-MM-dd")


AVAILABILITY_TABS = (("Study hours", "study"), ("Protected", "protected"), ("Cut-off", "cutoff"))
PROTECTED_WORDS = {"downtime": "Downtime", "commute": "Commute", "meal": "Meal"}
NO_STUDY_HOURS = "No study hours yet, so homework can go at any time of day."
NO_PROTECTED = "Nothing protected yet. Add practice, family time or a job."
# The strip starts at 06:00 unless a window starts earlier; it always runs to the end of the day.
STRIP_FIRST_MIN = 6 * 60


def _span_words(start: int, end: int) -> str:
    return f"{hhmm_text(minutes_to_hhmm(start))}–{hhmm_text(minutes_to_hhmm(end))}"


def _joined(entries: list[dict]) -> list[dict]:
    """Entries of one day each back into saved windows: equal hours on several days are one window
    with those days, in the order the hours first appear."""
    joined: dict[tuple, dict] = {}
    for entry in entries:
        rest = {key: value for key, value in entry.items() if key != "day"}
        window = joined.setdefault(tuple(sorted(rest.items())), {"days": [], **rest})
        if entry["day"] not in window["days"]:
            window["days"].append(entry["day"])
    for window in joined.values():
        window["days"].sort()
    return list(joined.values())


def _by_day(windows: list[dict]) -> list[dict]:
    return [
        {"day": day, **{key: value for key, value in window.items() if key != "days"}}
        for window in windows
        for day in sorted(window["days"])
    ]


class AvailabilityStrip(QWidget):
    """The week at a glance, Monday to Sunday: study hours in the accent, protected time in grey over
    them and the cut-off as a line across. Painted to be read; the tabs under it change what it shows."""

    HEAD = 18
    GAP = 6

    def __init__(self, palette: dict) -> None:
        super().__init__()
        self.setObjectName("availabilityStrip")
        self.setFixedHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("This week's study hours, protected time and cut-off")
        self.colours = palette
        self.first = STRIP_FIRST_MIN
        self._hours: list[tuple[int, int, int]] = []
        self._protected: list[tuple[int, int, int]] = []
        self._cutoff: int | None = None

    def show_week(
        self, hours: list[tuple[int, int, int]], protected: list[tuple[int, int, int]], cutoff: int | None
    ) -> None:
        """Each span is (day, start minute, end minute)."""
        self._hours, self._protected, self._cutoff = hours, protected, cutoff
        starts = [start - start % 60 for _day, start, _end in hours + protected]
        self.first = min([STRIP_FIRST_MIN, *starts])
        self.update()

    def column(self, day: int) -> QRectF:
        width = (self.width() - 6 * self.GAP) / 7
        return QRectF(day * (width + self.GAP), self.HEAD, width, self.height() - self.HEAD - 1)

    def y_of(self, minute: int) -> float:
        track = self.column(0)
        return track.top() + (minute - self.first) / (DAY_END_MIN - self.first) * track.height()

    def paintEvent(self, _event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(caption(self.font()))
        for day, letter in enumerate("MTWTFSS"):
            track = self.column(day)
            painter.setPen(QColor(self.colours["muted"]))
            head = QRectF(track.left(), 0, track.width(), self.HEAD)
            painter.drawText(head, Qt.AlignmentFlag.AlignCenter, letter)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.colours["hairline"]))
            painter.drawRoundedRect(track, 4, 4)
        # Protected time is drawn over study hours: the planner keeps out of it either way.
        for key, spans in (("accent", self._hours), ("muted", self._protected)):
            painter.setBrush(QColor(self.colours[key]))
            for day, start, end in spans:
                track = self.column(day)
                top, bottom = self.y_of(max(start, self.first)), self.y_of(end)
                painter.drawRoundedRect(QRectF(track.left(), top, track.width(), bottom - top), 3, 3)
        if self._cutoff is not None:
            # Crisp, two pixels on the pixel grid: smoothed, a thin line came out a paler red.
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(QPen(QColor(self.colours["error"]), 2))
            line = round(self.y_of(self._cutoff))
            painter.drawLine(0, line, self.width(), line)
        painter.end()


class AvailabilityDialog(Dialog):
    """When homework may go (#54 and J7): the week strip on top, then Study hours, Protected and
    Cut-off as tabs. Study hours is the one list the planner uses; Setup fills it too.

    A window Setup saved for several days shows as a chip on each of them. Removing a chip takes only
    that day out of the window, and the other days keep it: each day is edited on its own, and equal
    hours are joined back into one window with several days when the sheet answers."""

    def __init__(
        self,
        parent: QWidget | None,
        preferences: dict,
        subjects: list[str] | None = None,
        palette: dict | None = None,
    ) -> None:
        super().__init__(parent, sheet=True)
        self.setObjectName("availabilityDialog")
        self._hours = _by_day(deepcopy(preferences.get("work_windows") or []))
        self._protected = _by_day(deepcopy(preferences.get("protected") or []))
        self._picking: tuple[str, int] | None = None
        layout = self.card_body("Availability")
        body = QWidget()
        self._body = body
        body.installEventFilter(self)
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(SPACING[2])
        layout.addWidget(FitScroll(body, "availabilityScroll"), 1)
        self.strip = AvailabilityStrip(palette or resolved_palette("system", False, None))
        form.addWidget(self.strip)
        self.legend = sheet_note("")
        self.legend.setObjectName("availabilityLegend")
        form.addWidget(self.legend)
        self.tabs = Segmented(AVAILABILITY_TABS, "availabilityTabs")
        form.addWidget(self.tabs, 0, Qt.AlignmentFlag.AlignLeft)
        self.pages = QStackedWidget()
        self.tabs.currentIndexChanged.connect(self.pages.setCurrentIndex)
        form.addWidget(self.pages)
        self.study_empty, self._study_rows = self._page("When may FlexWeek plan homework?", NO_STUDY_HOURS)
        self.protected_empty, self._protected_rows = self._page("When must homework stay away?", NO_PROTECTED)
        cutoff_page = bare(QWidget())
        cutoff_column = QVBoxLayout(cutoff_page)
        cutoff_column.setContentsMargins(0, 0, 0, 0)
        cutoff_column.setSpacing(STACKED_GAP)
        question = QLabel("No homework after")
        question.setObjectName("fieldLabel")
        cutoff_column.addWidget(question)
        self.cutoff = QComboBox()
        self.cutoff.setObjectName("availabilityCutoff")
        self.cutoff.setAccessibleName("No homework after")
        fill_cutoff(self.cutoff, preferences.get("day_cutoff"))
        self.cutoff.currentIndexChanged.connect(self._render)
        cutoff_column.addWidget(self.cutoff, 0, Qt.AlignmentFlag.AlignLeft)
        cutoff_column.addStretch(1)
        self.pages.addWidget(cutoff_page)
        self._build_picker(subjects or [])
        self.error = _error_label()
        form.addWidget(self.error)
        form.addStretch(1)
        save = sheet_button("Save", "", "availabilitySave")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        cancel = sheet_button("Cancel", "outlined")
        cancel.clicked.connect(self.reject)
        sheet_footer(layout, cancel, save, divided=True)
        self._render()

    def _page(self, question_words: str, empty_words: str) -> tuple[QLabel, QVBoxLayout]:
        page = bare(QWidget())
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(STACKED_GAP)
        question = QLabel(question_words)
        question.setObjectName("fieldLabel")
        column.addWidget(question)
        empty = sheet_note(empty_words)
        column.addWidget(empty)
        rows = QVBoxLayout()
        rows.setSpacing(SPACING[1])
        column.addLayout(rows)
        column.addStretch(1)
        self.pages.addWidget(page)
        return empty, rows

    def _build_picker(self, subjects: list[str]) -> None:
        """The small form a + opens under its day: the hours, and a subject or a kind of time."""
        self.picker = bare(QWidget())
        self.picker.setObjectName("availabilityPicker")
        column = QVBoxLayout(self.picker)
        column.setContentsMargins(0, 0, 0, SPACING[1])
        column.setSpacing(STACKED_GAP)
        fields = QHBoxLayout()
        fields.setSpacing(SPACING[3])
        self.picker_start = ClockField(QTime(16, 0))
        self.picker_start.setObjectName("availabilityStart")
        self.picker_start.setAccessibleName("From")
        self.picker_end = ClockField(QTime(18, 0), end=True)
        self.picker_end.setObjectName("availabilityEnd")
        self.picker_end.setAccessibleName("To")
        self.picker_subject = QComboBox()
        self.picker_subject.setObjectName("availabilitySubject")
        self.picker_subject.setAccessibleName("Subject")
        self.picker_subject.setEditable(True)
        self.picker_subject.addItem("Any subject", "")
        for subject in subjects:
            self.picker_subject.addItem(subject, subject)
        self.picker_kind = QComboBox()
        self.picker_kind.setObjectName("availabilityKind")
        self.picker_kind.setAccessibleName("Kind of time")
        for kind in PROTECTED_KINDS:
            self.picker_kind.addItem(PROTECTED_WORDS[kind], kind)
        self.picker_title = QLineEdit()
        self.picker_title.setObjectName("availabilityTitle")
        self.picker_title.setAccessibleName("Name (optional)")
        self.picker_title.setPlaceholderText("e.g. Piano")
        self.picker_title.setMaxLength(40)
        self._picker_extra: dict[str, list[QWidget]] = {"study": [], "protected": []}
        for words, field, kind in (
            ("From", self.picker_start, ""),
            ("To", self.picker_end, ""),
            ("Subject", self.picker_subject, "study"),
            ("Kind", self.picker_kind, "protected"),
            ("Name (optional)", self.picker_title, "protected"),
        ):
            holder = bare(QWidget())
            pair = QVBoxLayout(holder)
            pair.setContentsMargins(0, 0, 0, 0)
            pair.setSpacing(STACKED_GAP)
            label = QLabel(words)
            label.setObjectName("fieldLabel")
            pair.addWidget(label)
            pair.addWidget(field)
            if field is self.picker_title:
                # On its own line: beside the times it made the sheet jump wider as it opened.
                column.addLayout(fields)
                column.addWidget(holder)
            else:
                fields.addWidget(holder)
            if kind:
                self._picker_extra[kind].append(holder)
        fields.addStretch(1)
        answers = QHBoxLayout()
        self.picker_add = sheet_button("Add", "outlined", "availabilityPickerAdd")
        self.picker_add.clicked.connect(self._add_picked)
        self.picker_cancel = sheet_button("Cancel", "quiet", "availabilityPickerCancel")
        self.picker_cancel.clicked.connect(self._close_picker)
        answers.addWidget(self.picker_add)
        answers.addWidget(self.picker_cancel)
        answers.addStretch(1)
        column.addLayout(answers)
        self.picker.setVisible(False)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._fit_width()
        if not self.sheet:
            fit_scroll_dialog(self, min_height=600)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        # A day with many chips, or the picker, can be wider than the sheet opened. The scrolled body
        # hears that as a layout request; the dialog itself never does.
        if watched is self._body and event.type() == QEvent.Type.LayoutRequest:
            self._fit_width()
        return super().eventFilter(watched, event)

    def _fit_width(self) -> None:
        """Wide enough for every row, so the sheet only ever scrolls up and down."""
        even_fields(self)
        wanted = self._body.minimumSizeHint().width() + 2 * SHEET_PAD + 64
        if self.sheet:
            if wanted > self.card_width:
                self.card_width = wanted
                self.refit()
        elif wanted > self.minimumWidth():
            self.setMinimumWidth(wanted)

    def _render(self) -> None:
        cutoff = self.cutoff.currentData()
        hours = [
            (entry["day"], clock_to_minutes(entry["start"]), clock_to_minutes(entry["end"]))
            for entry in self._hours
        ]
        protected = []
        for entry in self._protected:
            start = clock_to_minutes(entry["start"])
            protected.append((entry["day"], start, start + entry["duration_min"]))
        self.strip.show_week(hours, protected, clock_to_minutes(cutoff) if cutoff else None)
        legend = "Coloured: study hours. Grey: protected."
        if cutoff:
            legend += f" The line: no homework after {hhmm_text(cutoff)}."
        self.legend.setText(legend)
        self._fill_rows("study", self._study_rows, self._hours)
        self._fill_rows("protected", self._protected_rows, self._protected)
        self.study_empty.setVisible(not self._hours)
        self.protected_empty.setVisible(not self._protected)

    def _fill_rows(self, kind: str, rows: QVBoxLayout, entries: list[dict]) -> None:
        if rows.indexOf(self.picker) >= 0:
            rows.removeWidget(self.picker)
        while rows.count():
            widget = rows.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for day in range(7):
            row = bare(QWidget())
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(SPACING[1])
            name = QLabel(DAYS[day])
            name.setMinimumWidth(40)
            line.addWidget(name)
            for index, entry in enumerate(entries):
                if entry["day"] != day:
                    continue
                if kind == "study":
                    words = _span_words(clock_to_minutes(entry["start"]), clock_to_minutes(entry["end"]))
                    named = entry.get("subject")
                else:
                    start = clock_to_minutes(entry["start"])
                    words = _span_words(start, start + entry["duration_min"])
                    named = entry.get("title") or PROTECTED_WORDS.get(entry["kind"], entry["kind"])
                chip = sheet_button(f"{words} {named}  ×" if named else f"{words}  ×", "tonal", f"{kind}Chip")
                chip.setProperty("kind", kind)
                chip.setProperty("entry", index)
                chip.setAccessibleName(f"Remove {words}{' ' + named if named else ''} on {DAYS_LONG[day]}")
                chip.setToolTip("Remove")
                chip.clicked.connect(self._remove_chip)
                line.addWidget(chip)
            add = sheet_button("+", "outlined", f"{kind}Add")
            add.setProperty("kind", kind)
            add.setProperty("day", day)
            what = "study hours" if kind == "study" else "protected time"
            add.setAccessibleName(f"Add {what} on {DAYS_LONG[day]}")
            add.clicked.connect(self._open_picker)
            line.addWidget(add)
            line.addStretch(1)
            rows.addWidget(row)
            if self._picking == (kind, day):
                rows.addWidget(self.picker)
                self.picker.setVisible(True)

    def _remove_chip(self) -> None:
        chip = self.sender()
        entries = self._hours if chip.property("kind") == "study" else self._protected
        del entries[int(chip.property("entry"))]
        self._render()

    def _open_picker(self, *, kind: str | None = None, day: int | None = None) -> None:
        """Open the picker under a day's row: the + that was pressed, or `kind` and `day`."""
        if kind is None or day is None:
            button = self.sender()
            kind, day = str(button.property("kind")), int(button.property("day"))
        self._picking = (kind, day)
        self.tabs.setCurrentIndex(self.tabs.findData(kind))
        study = kind == "study"
        self.picker_start.setTime(QTime(16, 0) if study else QTime(17, 0))
        self.picker_end.setTime(QTime(18, 0))
        self.picker_subject.setCurrentIndex(0)
        self.picker_kind.setCurrentIndex(0)
        self.picker_title.clear()
        for holder in self._picker_extra["study"]:
            holder.setVisible(study)
        for holder in self._picker_extra["protected"]:
            holder.setVisible(not study)
        self.error.setText("")
        self._render()
        self.picker_start.setFocus()

    def _close_picker(self) -> None:
        self._picking = None
        self.picker.setVisible(False)
        self.error.setText("")
        self._render()

    def _add_picked(self) -> None:
        if self._picking is None:
            return
        kind, day = self._picking
        start, end = self.picker_start.minutes(), self.picker_end.minutes()
        start, end = start - start % SLOT_MIN, end - end % SLOT_MIN
        if end - start < SLOT_MIN:
            self.error.setText("End must be after Start.")
            return
        if kind == "study":
            entry: dict = {"day": day, "start": minutes_to_hhmm(start), "end": minutes_to_hhmm(end)}
            typed = self.picker_subject.currentText().strip()
            if typed and typed != "Any subject":
                entry["subject"] = typed[:40]
            entries = self._hours
        else:
            entry = {"day": day, "kind": self.picker_kind.currentData(), "start": minutes_to_hhmm(start),
                     "duration_min": end - start}  # fmt: skip
            title = self.picker_title.text().strip()
            if title:
                entry["title"] = title[:40]
            entries = self._protected
            for other in entries:
                other_start = clock_to_minutes(other["start"])
                if other["day"] == day and start < other_start + other["duration_min"] and other_start < end:
                    self.error.setText(f"That overlaps protected time already on {DAYS_LONG[day]}.")
                    return
        if entry not in entries:
            if len(_joined([*entries, entry])) > AVAILABILITY_LIMIT:
                what = "sets of study hours" if kind == "study" else "protected times"
                self.error.setText(f"Up to {AVAILABILITY_LIMIT} {what}.")
                return
            entries.append(entry)
        self._close_picker()

    def protected(self) -> list[dict]:
        return _joined(self._protected)

    def work_windows(self) -> list[dict]:
        return _joined(self._hours)

    def day_cutoff(self) -> str | None:
        return self.cutoff.currentData()
