"""First-run setup: one question a page, every page skippable, remembered as the student goes.

A new account arrives here from its recovery codes. Each page is kept when the student leaves it with
Next, so a quit resumes where they were and nothing is asked twice. Look and layout belong to this
computer; everything else belongs to the account. The window does the writing: this page says what
was chosen. Once setup is finished or skipped it never returns unless the student asks for it again
in Settings.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, timedelta
from uuid import uuid4

from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTime, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (
    QColor,
    QFocusEvent,
    QFont,
    QFontMetrics,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.models import valid_spotify_url
from backend.slots import hhmm_to_minutes, minutes_to_hhmm
from desktop.native import icons
from desktop.native.calendar import (
    SETUP_ACTIVITY_PREFIX,
    SETUP_SCHOOL_ID,
    is_setup_block,
)
from desktop.native.fields import END_OF_DAY, QUICK_LENGTHS, ClockField, DayPicker, Stepper
from desktop.native.fonts import numeral
from desktop.native.hours.geometry import drag_step
from desktop.native.layouts.registry import (
    EXPERIMENTAL,
    LAYOUTS,
    LayoutSpec,
    layouts_for,
    options_for,
    sanitize_layout,
)
from desktop.native.look import (
    KNOB_VALUE_LABELS,
    LOOK_KNOBS,
    PACKS,
    effective_look,
    look_menu_items,
    resolved_palette,
    sanitize_look,
)
from desktop.native.motion import (
    EASE_MS,
    appear,
    duration,
    fade_away,
    glide,
    hold_picture,
    settle,
    switch_page,
)
from desktop.native.previews import Previews
from desktop.native.remind import reminder_lead_min
from desktop.native.settings import (
    DRAG_STEP_CHOICES,
    DRAG_STEP_QUESTION,
    PLANNING_STYLES,
    SPORT_FALLBACK,
    SPOTIFY_TONE_NOTE,
)
from desktop.native.sound import Bell
from desktop.native.tokens import WEIGHT_STRONG
from desktop.native.tones import FALLBACK, RECIPES
from desktop.native.weekmodel import clock_text, hhmm_text
from desktop.native.widgets import (
    CARD_WIDTH_PAD,
    DAYS,
    CardGrid,
    ChoiceCard,
    DueField,
    FlowLayout,
    fill_cutoff,
    rounded_picture,
)
from desktop.native.work_windows import WorkWindowsEditor

SETUP_VERSION = 1
STYLE, LOOK, COLOURS, WEEK, HOMEWORK, REMINDERS, FIRST, DONE = range(8)
# The rail names six steps. Style has two more pages behind it for a student who builds their own.
RAIL = (
    ("Style", (STYLE, LOOK, COLOURS)),
    ("Your week", (WEEK,)),
    ("Homework time", (HOMEWORK,)),
    ("Reminders and alarm", (REMINDERS,)),
    ("First homework", (FIRST,)),
    ("Done", (DONE,)),
)
LOOK_STEPS = (STYLE, LOOK, COLOURS)
TITLES = {
    STYLE: "Start from a style",
    LOOK: "How do you want to see your week?",
    COLOURS: "Colours and size",
    WEEK: "Your week",
    HOMEWORK: "How should homework get a time?",
    REMINDERS: "Reminders and your alarm sound",
    FIRST: "What homework is due first?",
    DONE: "You're set",
}
NOTES = {
    STYLE: "Each sets the view, the colours and the text size together. Change any of it later in Settings.",
    LOOK: "Each one shows the same week its own way.",
    COLOURS: "The picture follows what you pick.",
    WEEK: "Fixed times the planner works around. Skip anything you don't have.",
    HOMEWORK: "You can change this any time in Settings, under Planning.",
    REMINDERS: (
        "Pick the sound for reminders, alarms and the end of a focus session. A Spotify song plays for"
        " alarms and when a block starts; the rest play Chime."
    ),
    FIRST: "Add up to three. You can add the rest any time.",
    DONE: "Everything here is also in Settings. Run setup again from Settings, under This computer.",
}
NEXT_LABEL, FINISH_LABEL = "Next", "Open my week"
SKIP_STEP_LABEL, SKIP_ALL_LABEL = "Skip this step", "Skip setup"
OWN_LOOK_LABEL = "Choose my own look instead"
MAX_ACTIVITIES = 8
MAX_FIRST_HOMEWORK = 3
# A tap adds one of these rather than making the student type hours for the usual answers.
TEXT_SIZES = (("small", "Small"), ("normal", "Normal"), ("large", "Large"))
SPACINGS = (("comfortable", "Comfortable"), ("compact", "Compact"))
FONTS = (("sans", "Sans"), ("serif", "Serif"), ("mono", "Mono"))
SHADOWS = tuple((value, KNOB_VALUE_LABELS[value]) for value in LOOK_KNOBS["depth"])
TONE_NAMES = {tone: tone.title() for tone in RECIPES}
STYLE_PICTURE, LOOK_THUMB, COLOUR_THUMB = 520, 206, 400
# The pages and the row of buttons under them, centred up to this width (decision 26 of 0.17).
SETUP_COLUMN = 880
# The style carousel: the middle picture at most STYLE_PICTURE wide, never less than STYLE_PICTURE_MIN,
# with at least PEEK_PX of each neighbour showing past a CAROUSEL_GAP. CAROUSEL_CHROME is a slide's
# ring and padding, both sides.
STYLE_PICTURE_MIN, PEEK_PX, CAROUSEL_GAP, CAROUSEL_CHROME = 240, 56, 12, 16
NEIGHBOUR_OPACITY = 0.45
EXPERIMENTAL_TAG = "Experimental"
# How the summary says the colours of a look that has no colour choices of its own.
PACK_IN = {
    "system": "your system's colours",
    "light-frost": "light colours",
    "dark-frost": "dark colours",
    "nocturne": "Nocturne colours",
    "slate": "Slate colours",
}
DOT_PX, ARROW_PX = 16, 32
RAIL_MIN = 210
# The margin the pages keep at the sides, and the fade over the last stretch above the footer.
PAGE_MARGIN, FADE_PX = 32, 24
# A step on the rail is marked by its number in a ring, or once it is done by a tick on the accent.
BADGE_PX, TICK_PX = 20, 16
PENDING, CURRENT, FINISHED = "pending", "current", "finished"
PLAY_PX = 20


@dataclass(frozen=True)
class Style:
    key: str
    name: str
    note: str
    main: str
    colour: str | None
    pack: str
    knobs: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)


DEFAULT_STYLE = "plain"
STYLES = (
    Style(
        "plain",
        "Plain calendar",
        "Your week as a timetable grid",
        "classic",
        None,
        "light-frost",
    ),
    Style(
        "dashboard",
        "Dashboard",
        "Next up and due soon, as tiles",
        "bento",
        "indigo",
        "light-frost",
    ),
    Style(
        "night",
        "Night owl",
        "Dark colours, compact spacing",
        "timeline",
        "night",
        "dark-frost",
        {"density": "compact"},
        {"density": "compact"},
    ),
    Style(
        "retro",
        "Retro",
        "A retro desktop, with large text",
        "retro",
        "teal",
        "light-frost",
        {"text": "large"},
    ),
)


@dataclass
class SetupState:
    """What is in place now: setup opens on it, and keeps it up to date as pages are kept."""

    pack: str
    look: dict
    layout: dict
    preferences: dict
    blocks: list[dict]
    week_start: str
    subjects: list[str] = field(default_factory=list)
    first_run: bool = True
    homework: list[str] = field(default_factory=list)


def style_layout(style: Style, layout: dict) -> dict:
    options = deepcopy(sanitize_layout(layout)["options"])
    if style.colour is not None or style.options:
        chosen = dict(options.get(style.main, {}))
        if style.colour is not None:
            chosen["colour"] = style.colour
        chosen.update(style.options)
        options[style.main] = chosen
    return sanitize_layout({"main": style.main, "day": sanitize_layout(layout)["day"], "options": options})


def style_look(style: Style) -> dict:
    return sanitize_look({"preset": "default", "knobs": dict(style.knobs)})


def matching_style(pack: str, look: dict, layout: dict) -> str | None:
    """The style these choices amount to, so running setup again shows it picked."""
    for style in STYLES:
        if (
            style_layout(style, layout)["main"] == layout["main"]
            and style_layout(style, layout)["options"].get(style.main) == layout["options"].get(style.main)
            and (style.main != "classic" or pack == style.pack)
            and effective_look(style_look(style)) == effective_look(look)
        ):
            return style.key
    return None


def days_label(days: list[int]) -> str:
    """Mon–Fri for a run of days, Tue, Thu for the rest."""
    ordered = sorted(set(days))
    if len(ordered) == 7:
        return "every day"
    if len(ordered) > 2 and ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"{DAYS[ordered[0]]}–{DAYS[ordered[-1]]}"
    return ", ".join(DAYS[day] for day in ordered)


def _design_chips(specs: tuple[LayoutSpec, ...]) -> tuple[tuple[str, str], ...]:
    return tuple((spec.id, spec.label) for spec in specs)


def span_label(start: str, minutes: int) -> str:
    return f"{hhmm_text(start)}–{clock_text(hhmm_to_minutes(start) + minutes)}"


def _label(text: str, name: str = "", wrap: bool = True) -> QLabel:
    made = QLabel(text)
    if name:
        made.setObjectName(name)
    made.setWordWrap(wrap)
    return made


def step_badge(number: int, state: str, palette: dict, family: str, ratio: float = 1.0) -> QPixmap:
    """A step's mark on the rail: its number in a ring, the ring in the accent on the step shown, and
    a tick on the accent once the step is done."""
    side = round(BADGE_PX * ratio)
    made = QPixmap(side, side)
    made.fill(Qt.GlobalColor.transparent)
    made.setDevicePixelRatio(ratio)
    painter = QPainter(made)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    ring = QRectF(1, 1, BADGE_PX - 2, BADGE_PX - 2)
    if state == FINISHED:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette["accent"]))
        painter.drawEllipse(ring)
        tick = icons.pixmap("check", palette["accent_ink"], TICK_PX, ratio)
        inset = (BADGE_PX - TICK_PX) / 2
        painter.drawPixmap(QRectF(inset, inset, TICK_PX, TICK_PX), tick, QRectF(tick.rect()))
    else:
        current = state == CURRENT
        painter.setPen(QPen(QColor(palette["accent" if current else "hairline_strong"]), 1.5))
        painter.drawEllipse(ring)
        font = numeral(QFont(family), 11, WEIGHT_STRONG)
        painter.setFont(font)
        painter.setPen(QColor(palette["text" if current else "muted"]))
        painter.drawText(QRectF(0, 0, BADGE_PX, BADGE_PX), Qt.AlignmentFlag.AlignCenter, str(number))
    painter.end()
    return made


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _quiet(text: str, name: str = "setupQuiet") -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _outlined(text: str, name: str = "") -> QPushButton:
    button = QPushButton(text)
    if name:
        button.setObjectName(name)
    button.setProperty("outline", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class Level(QWidget):
    """`inner` centred in a cell as tall as `like`, for a neighbour that is taller than `inner`: the
    two then read on one line instead of one hanging from the top of the cell."""

    def __init__(self, inner: QWidget, like: QWidget) -> None:
        super().__init__()
        self.setObjectName("setupRow")
        self._inner, self._like = inner, like
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        box.addStretch(1)
        box.addWidget(inner)
        box.addStretch(1)
        self.setSizePolicy(inner.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        hint = self._inner.sizeHint()
        return QSize(hint.width(), max(hint.height(), self._like.sizeHint().height()))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        hint = self._inner.minimumSizeHint()
        return QSize(hint.width(), max(hint.height(), self._like.sizeHint().height()))


class Footer(QWidget):
    """The buttons along the bottom of setup, with a fade above them for the page to run out under.
    It says its height when it changes, as Large text and a wrapped error make it taller."""

    resized = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("setupRow")
        self._box = QVBoxLayout(self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.setSpacing(0)
        self.fade = QWidget()
        self.fade.setObjectName("setupFade")
        self.fade.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.fade.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.fade.setFixedHeight(FADE_PX)
        self._box.addWidget(self.fade)

    def add(self, buttons: QWidget) -> None:
        self._box.addWidget(buttons)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.resized.emit(self.height())


class PageScroll(QScrollArea):
    """A setup page. Its column starts at one x on every page, whether or not this page has a scroll bar,
    since the gutter is worked out from the whole width and not the part the bar leaves. It scrolls
    under the footer, with room at the end for the footer's height so the last thing is not hidden."""

    def __init__(self, around: QHBoxLayout) -> None:
        super().__init__()
        self._around = around
        self._footer = 0
        self._pad()

    def set_footer(self, height: int) -> None:
        self._footer = height
        self._pad()

    def _pad(self) -> None:
        gutter = max(PAGE_MARGIN, (self.width() - SETUP_COLUMN) // 2)
        self._around.setContentsMargins(gutter, 28, PAGE_MARGIN, self._footer)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._pad()


def _card_grid(box: QVBoxLayout, picture: int) -> CardGrid:
    """A grid for picture cards, added to `box`. A grid, not a flow: a flow sizes each card by its
    hint and cannot give a name that wraps its second line, so the name was drawn over the picture.
    As many columns as the page has room for: two fixed columns ran off the right edge of a narrow
    window."""
    cards = CardGrid(picture + CARD_WIDTH_PAD, 14)
    cards.setObjectName("setupRow")
    box.addWidget(cards)
    return cards


def _centred_column(line: QHBoxLayout) -> QWidget:
    """A column in the middle of `line`, as wide as it allows up to SETUP_COLUMN, with what is left
    split evenly either side. A page pinned to the left left the right third of a wide window empty.

    The column's stretch outweighs the two sides', so it takes the room until its maximum; Qt then
    shares the rest between the sides alone. Centred by alignment instead, it kept its narrow hint.
    """
    column = QWidget()
    column.setObjectName("setupRow")
    column.setMaximumWidth(SETUP_COLUMN)
    column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    line.addStretch(1)
    line.addWidget(column, SETUP_COLUMN)
    line.addStretch(1)
    return column


def _row(*widgets: QWidget, stretch: bool = True) -> QWidget:
    holder = QWidget()
    holder.setObjectName("setupRow")
    line = QHBoxLayout(holder)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(8)
    for widget in widgets:
        line.addWidget(widget)
    if stretch:
        line.addStretch(1)
    return holder


class StyleSlide(QFrame):
    """One style's picture in the carousel: ringed in the accent while it is the chosen one, and asking
    to be brought to the middle when it is clicked."""

    chosen = Signal()

    def __init__(self, style: Style, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("setupSlide")
        self.setAccessibleName(style.name)
        self.setAccessibleDescription(style.note)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.offset = 0
        self._source = QPixmap()
        box = QVBoxLayout(self)
        box.setContentsMargins(*(CAROUSEL_CHROME // 2 - 2,) * 4)
        self.picture = QLabel()
        self.picture.setObjectName("setupSlidePicture")
        box.addWidget(self.picture)
        # Over the picture's corner, so a card carries it wherever it stands in the row.
        self.tag: QLabel | None = None
        if LAYOUTS[style.main].experimental:
            self.tag = QLabel(EXPERIMENTAL_TAG, self.picture)
            self.tag.setObjectName("setupSlideTag")
            self.tag.move(8, 8)
        self.fade = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fade)
        self.select(False)

    def set_picture(self, picture: QPixmap) -> None:
        self._source = picture
        self._draw()

    def set_picture_width(self, width: int) -> None:
        self.picture.setFixedSize(width, round(width * 0.625))
        self._draw()

    def _draw(self) -> None:
        if self._source.isNull():
            return
        size = self.picture.size()
        fitted = self._source.scaled(
            size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.picture.setPixmap(rounded_picture(fitted, 6))

    def select(self, on: bool) -> None:
        self.setProperty("selected", on)
        _repolish(self)

    def is_selected(self) -> bool:
        return bool(self.property("selected"))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.chosen.emit()
            return
        super().mouseReleaseEvent(event)


class StyleCarousel(QFrame):
    """One style's picture large in the middle, the one before and the one after peeking at the sides
    dimmed, an arrow and a dot for each below, then the name and one note. Whatever is in the middle is
    the chosen style, once the student has moved it or a style was chosen already; Left and Right move
    it, and a click on a neighbour brings it to the middle. The styles wrap round, so the last one
    stands left of the first."""

    # The key of the style that is now in the middle and chosen.
    moved = Signal(str)

    def __init__(self, styles: tuple[Style, ...], motion: Callable[[], str]) -> None:
        super().__init__()
        self.setObjectName("setupRow")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Style")
        self._motion = motion
        # The plain ones first, then the experimental, as the roadmap's picture has them.
        self._order = tuple(sorted(styles, key=lambda style: LAYOUTS[style.main].experimental))
        self._index = 0
        self._chosen = False
        self._width = STYLE_PICTURE
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        self.stage = QWidget()
        self.stage.setObjectName("setupRow")
        self.stage.setFixedHeight(self._slide_height(STYLE_PICTURE))
        box.addWidget(self.stage)
        self.slides: dict[str, StyleSlide] = {}
        for style in self._order:
            slide = StyleSlide(style, self.stage)
            slide.chosen.connect(lambda key=style.key: self.go_to(key))
            self.slides[style.key] = slide
        self.previous = self._arrow("chevron-left", "Previous style", -1)
        self.following = self._arrow("chevron-right", "Next style", 1)
        self.dots: dict[str, QPushButton] = {}
        line = QHBoxLayout()
        line.setSpacing(10)
        line.addStretch(1)
        line.addWidget(self.previous)
        for style in self._order:
            dot = QPushButton()
            dot.setObjectName("setupDot")
            dot.setFixedSize(DOT_PX, DOT_PX)
            dot.setIconSize(QSize(DOT_PX - 4, DOT_PX - 4))
            dot.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            dot.setCursor(Qt.CursorShape.PointingHandCursor)
            dot.setAccessibleName(f"Show {style.name}")
            dot.clicked.connect(lambda _checked=False, key=style.key: self.go_to(key))
            self.dots[style.key] = dot
            line.addWidget(dot)
        line.addWidget(self.following)
        line.addStretch(1)
        box.addLayout(line)
        self.name = _label("", "setupChoiceName")
        self.name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.note = _label("", "setupChoiceNote")
        self.note.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        box.addWidget(self.name)
        box.addWidget(self.note)
        self._arrange(delta=0)
        self._refresh()

    def _arrow(self, icon_name: str, label: str, delta: int) -> QPushButton:
        arrow = QPushButton()
        arrow.setObjectName("setupArrow")
        arrow.setFixedSize(ARROW_PX, ARROW_PX)
        arrow.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        arrow.setCursor(Qt.CursorShape.PointingHandCursor)
        arrow.setAccessibleName(label)
        arrow.clicked.connect(lambda: self.step(delta))
        icons.tint(arrow, icon_name)
        return arrow

    @staticmethod
    def _slide_height(picture: int) -> int:
        return round(picture * 0.625) + CAROUSEL_CHROME

    def key(self) -> str:
        return self._order[self._index].key

    def is_chosen(self) -> bool:
        return self._chosen

    def show_style(self, key: str, chosen: bool) -> None:
        """The middle at `key`, and whether it counts as chosen, without moving or saying so."""
        index = next(at for at, style in enumerate(self._order) if style.key == key)
        if (index, chosen) == (self._index, self._chosen):
            return
        moved = index != self._index
        self._index, self._chosen = index, chosen
        if moved:
            self._arrange(delta=0)
        self._refresh()

    def go_to(self, key: str) -> None:
        """The student's move: `key` to the middle and chosen."""
        target = next(at for at, style in enumerate(self._order) if style.key == key)
        count = len(self._order)
        delta = (target - self._index + count // 2) % count - count // 2
        if delta == 0 and self._chosen:
            return
        self._index, self._chosen = target, True
        self._arrange(delta=delta)
        self._refresh()
        self.moved.emit(key)

    def step(self, delta: int) -> None:
        self.go_to(self._order[(self._index + delta) % len(self._order)].key)

    def _slot(self, offset: int) -> int:
        slide_width = self._width + CAROUSEL_CHROME
        return (self.width() - slide_width) // 2 + offset * (slide_width + CAROUSEL_GAP)

    def _arrange(self, delta: int) -> None:
        """Every slide to its place. A step of one slides them there; anything else, and a resize,
        puts them there. A slide that wraps from one end to the other goes on past the edge it was
        heading for, or comes in from the far one, so none crosses the middle."""
        room = self.width()
        if room <= 0:
            return
        count = len(self._order)
        picture = max(
            STYLE_PICTURE_MIN, min(STYLE_PICTURE, room - 2 * (PEEK_PX + CAROUSEL_GAP) - CAROUSEL_CHROME)
        )
        resized = picture != self._width
        self._width = picture
        height = self._slide_height(picture)
        self.stage.setFixedHeight(height)
        slides_move = abs(delta) == 1 and not resized
        level = self._motion()
        for at, style in enumerate(self._order):
            slide = self.slides[style.key]
            offset = (at - self._index + count // 2) % count - count // 2
            if abs(slide.offset) > 1:
                # Out of sight since the last move, where it may have stopped short of its place.
                settle(slide)
                slide.move(self._slot(slide.offset), 0)
            if resized or slide.picture.width() != picture:
                slide.set_picture_width(picture)
            target = QRect(self._slot(offset), 0, picture + CAROUSEL_CHROME, height)
            if slides_move and abs(offset - slide.offset) > 1:
                if abs(slide.offset) <= 1:
                    target.moveLeft(self._slot(slide.offset - delta))
                else:
                    slide.setGeometry(self._slot(2 * (1 if offset > 0 else -1)), 0, target.width(), height)
            if slides_move:
                glide(slide, target, level)
            else:
                settle(slide)
                slide.setGeometry(target)
            slide.offset = offset
            self._dim(slide, abs(offset) != 0, animate=slides_move)

    def _dim(self, slide: StyleSlide, dimmed: bool, animate: bool) -> None:
        goal = NEIGHBOUR_OPACITY if dimmed else 1.0
        length = duration(EASE_MS, self._motion()) if animate else 0
        if length == 0:
            slide.fade.setOpacity(goal)
            return
        run = QVariantAnimation(slide)
        run.setStartValue(slide.fade.opacity())
        run.setEndValue(goal)
        run.setDuration(length)
        run.valueChanged.connect(lambda value: slide.fade.setOpacity(float(value)))
        run.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def _refresh(self) -> None:
        count = len(self._order)
        current = self._order[self._index]
        for style in self._order:
            here = style.key == current.key
            self.slides[style.key].select(here and self._chosen)
            dot = self.dots[style.key]
            dot.setProperty("current", here)
            dot.setProperty("chosen", here and self._chosen)
            icons.tint(dot, "check" if here and self._chosen else None)
            _repolish(dot)
        self.name.setText(current.name)
        self.note.setText(current.note)
        state = ", chosen" if self._chosen else ""
        self.setAccessibleDescription(f"{current.name}, {self._index + 1} of {count}{state}")

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        arrows = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}
        if event.key() in arrows and not event.modifiers():
            self.step(arrows[event.key()])
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        super().focusInEvent(event)
        self._mark_focus(True)

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self._mark_focus(False)

    def _mark_focus(self, on: bool) -> None:
        for slide in self.slides.values():
            slide.setProperty("focused", on)
            _repolish(slide)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._arrange(delta=0)


class Chips(QWidget):
    """One of a few choices, as a row of pills. Experimental choices, when there are any, sit in a
    second row under their own heading; the two rows are still one choice."""

    changed = Signal()

    def __init__(
        self,
        choices: tuple[tuple[str, str], ...],
        name: str,
        experimental: tuple[tuple[str, str], ...] = (),
    ) -> None:
        super().__init__()
        self.setObjectName("setupRow")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        self._lines: list[FlowLayout] = []
        for index in range(2):
            holder = QWidget()
            holder.setObjectName("setupRow")
            line = FlowLayout(holder, gap=6)
            line.setContentsMargins(0, 0, 0, 0)
            self._lines.append(line)
            if index:
                self.experimental_heading = _label(EXPERIMENTAL, "setupFieldLabel")
                column.addWidget(self.experimental_heading)
            column.addWidget(holder)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._name = name
        self.set_choices(choices, experimental)

    def set_choices(
        self, choices: tuple[tuple[str, str], ...], experimental: tuple[tuple[str, str], ...] = ()
    ) -> None:
        for button in self._group.buttons():
            self._group.removeButton(button)
            for line in self._lines:
                line.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
        for line, entries in zip(self._lines, (choices, experimental), strict=True):
            for value, text in entries:
                button = QPushButton(text)
                button.setObjectName("setupChip")
                button.setCheckable(True)
                button.setProperty("value", value)
                button.setAccessibleName(f"{self._name}: {text}")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(self.changed)
                self._group.addButton(button)
                line.addWidget(button)
            line.parentWidget().setVisible(bool(entries))
        self.experimental_heading.setVisible(bool(experimental))
        self.updateGeometry()

    def value(self) -> str | None:
        checked = self._group.checkedButton()
        return None if checked is None else str(checked.property("value"))

    def set_value(self, value: object) -> None:
        for button in self._group.buttons():
            if button.property("value") == value:
                button.setChecked(True)
                return
        buttons = self._group.buttons()
        if buttons:
            buttons[0].setChecked(True)

    def buttons(self) -> list[QPushButton]:
        return [button for button in self._group.buttons() if isinstance(button, QPushButton)]


class QuarterTime(ClockField):
    """A time of day, typed. The arrow keys and the wheel move it a quarter hour at a time; a time typed
    between quarters keeps its minute, as the block editor does."""

    def __init__(self, hhmm: str, *, end: bool = False) -> None:
        # QTime holds no 24:00; an end box reads 00:00 as the end of the day.
        super().__init__(QTime(0, 0) if hhmm == "24:00" else QTime.fromString(hhmm, "HH:mm"), end=end)
        self.setObjectName("setupTime")
        self.setCorrectionMode(QAbstractSpinBox.CorrectionMode.CorrectToNearestValue)

    def set_minutes(self, minutes: int) -> None:
        minutes = max(0, min(minutes, END_OF_DAY if self._end else END_OF_DAY - 1))
        self.setTime(QTime(minutes // 60 % 24, minutes % 60))

    def hhmm(self) -> str:
        return minutes_to_hhmm(self.minutes())


class TimeRange(QWidget):
    def __init__(self, start: str, end: str, name: str) -> None:
        super().__init__()
        self.setObjectName("setupRow")
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        self.start = QuarterTime(start)
        self.start.setAccessibleName(f"{name} starts")
        self.end = QuarterTime(end, end=True)
        self.end.setAccessibleName(f"{name} ends")
        line.addWidget(_label("from", "setupFieldLabel", wrap=False))
        line.addWidget(self.start)
        line.addWidget(_label("to", "setupFieldLabel", wrap=False))
        line.addWidget(self.end)

    def span(self) -> tuple[str, int]:
        return self.start.hhmm(), self.end.minutes() - self.start.minutes()

    def set_span(self, start: str, minutes: int) -> None:
        begin = hhmm_to_minutes(start)
        self.start.set_minutes(begin)
        self.end.set_minutes(begin + minutes)


SPORT_WORDS = frozenset(
    {
        "soccer",
        "football",
        "basketball",
        "swim",
        "swimming",
        "track",
        "tennis",
        "volleyball",
        "baseball",
        "hockey",
        "lacrosse",
        "softball",
        "golf",
        "wrestling",
        "cheer",
        "cheerleading",
        "rugby",
        "gym",
    }
)


def activity_category_for(title: str) -> str:
    words = {part.strip(".,!?").lower() for part in title.split() if part.strip(".,!?")}
    return "exercise" if words & SPORT_WORDS else "extra"


class ActivityRow(QFrame):
    removed = Signal(object)

    def __init__(
        self, title: str = "", days: list[int] | None = None, start: str = "15:30", minutes: int = 90,
        category: str = "extra",
        guess: bool = True,
    ) -> None:
        super().__init__()
        self.setObjectName("setupGroup")
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 10, 12, 10)
        box.setSpacing(8)
        self.name = QLineEdit(title)
        self.name.setObjectName("setupActivityName")
        self.name.setPlaceholderText("Soccer, band, a job…")
        self.name.setMaxLength(80)
        self.name.setAccessibleName("Activity name")
        remove = _outlined("Remove")
        remove.setAccessibleName("Remove this activity")
        remove.clicked.connect(lambda: self.removed.emit(self))
        self.category = QComboBox()
        self.category.setObjectName("setupActivityCategory")
        self.category.setAccessibleName("Sports or Activity")
        self.category.addItem("Activity", "extra")
        self.category.addItem("Sports", "exercise")
        self.category.setCurrentIndex(max(0, self.category.findData(category)))
        self._category_touched = not guess
        self.category.activated.connect(self._keep_category)
        self.name.textChanged.connect(self._guess_category)
        if guess and title:
            self._guess_category(title)
        top = QHBoxLayout()
        top.addWidget(self.name, 1)
        top.addWidget(self.category)
        top.addWidget(remove)
        box.addLayout(top)
        # The days and times as School's line has them, under the name, so the two columns of times
        # stand at one x down the page.
        self.days = DayPicker(days or [], "setupDay")
        self.times = TimeRange(start, minutes_to_hhmm(hhmm_to_minutes(start) + minutes), "Activity")
        bottom = FlowLayout(gap=12)
        bottom.addWidget(Level(self.days, self.times.start))
        bottom.addWidget(self.times)
        box.addLayout(bottom)

    def _keep_category(self, _index: int = 0) -> None:
        self._category_touched = True

    def _guess_category(self, _text: str = "") -> None:
        if self._category_touched:
            return
        wanted = activity_category_for(self.name.text())
        self.category.setCurrentIndex(max(0, self.category.findData(wanted)))


def next_school_day(school_days: list[int], today: date | None = None) -> str:
    """The first day after today that is a school day, as the day first homework is most likely due:
    the default of Sunday was a day with no school. With no school days picked, tomorrow."""
    today = today or date.today()
    for ahead in range(1, 8):
        day = today + timedelta(days=ahead)
        if not school_days or day.weekday() in school_days:
            return day.isoformat()
    return (today + timedelta(days=1)).isoformat()


class HomeworkRow(QFrame):
    removed = Signal(object)

    def __init__(self, due: str) -> None:
        super().__init__()
        # What the date was made as, so a date the student never touched can follow the school days.
        self.default_due = due
        self.setObjectName("setupGroup")
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.name = QLineEdit()
        self.name.setObjectName("setupHomeworkName")
        self.name.setPlaceholderText("e.g. History essay")
        self.name.setMaxLength(80)
        self.name.setAccessibleName("Homework name")
        self.minutes = QSpinBox()
        self.minutes.setObjectName("setupHomeworkMinutes")
        self.minutes.setRange(15, 600)
        self.minutes.setSingleStep(15)
        self.minutes.setValue(60)
        self.minutes.setSuffix(" min")
        self.minutes.setAccessibleName("How long it takes")
        self.due = DueField(due, "setupHomeworkDue")
        remove = _outlined("Remove")
        remove.setAccessibleName("Remove this homework")
        remove.clicked.connect(lambda: self.removed.emit(self))
        grid.addWidget(_label("Name", "setupFieldLabel", wrap=False), 0, 0)
        grid.addWidget(self.name, 0, 1, 1, 3)
        grid.addWidget(remove, 0, 4)
        # On the line of the box, not the middle of the box and the lengths under it.
        takes = Level(_label("Takes", "setupFieldLabel", wrap=False), self.minutes)
        grid.addWidget(takes, 1, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(Stepper(self.minutes, QUICK_LENGTHS), 1, 1)
        grid.addWidget(_label("Due", "setupFieldLabel", wrap=False), 1, 2)
        grid.addWidget(self.due, 1, 3, 1, 2)
        grid.setColumnStretch(3, 1)


class SetupPage(QWidget):
    """The whole window, from the recovery codes to the first week."""

    # Show this look now without keeping it: {"pack", "look", "layout"}.
    previewed = Signal(dict)
    # A page left: its step, where the student went, and what to keep (None when nothing is kept).
    left = Signal(int, int, object)
    finished = Signal()
    # The alarm sound and Spotify link on screen, for a reminder sent now.
    test_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("setupPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.motion = "normal"
        self.volume = 80
        self._previews = Previews()
        self._bell = Bell(self)
        self._step = STYLE
        self._furthest = STYLE
        self._own_look = False
        self._state = SetupState("system", sanitize_look(None), sanitize_layout(None), {}, [], "")
        self._pack, self._look, self._layout = self._state.pack, self._state.look, self._state.layout
        self._entered: tuple[str, dict, dict] = (self._pack, deepcopy(self._look), deepcopy(self._layout))
        self._style_key: str | None = None
        # Homework this run of setup made, by name, so Back and Next again edits it rather than adding
        # it twice.
        self._made: dict[str, str] = {}
        self._pending_pictures: list[tuple[ChoiceCard, str, str | None, str, int]] = []
        # The look's colours, for what a stylesheet cannot tint: the rail's marks and the Play icons.
        self._palette = resolved_palette("light-frost", False, None)
        self.play_buttons: list[QPushButton] = []
        self._warm = QTimer(self)
        self._warm.setSingleShot(True)
        self._warm.setInterval(0)
        self._warm.timeout.connect(self._draw_next_picture)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_rail())
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.setObjectName("setupStack")
        self.pages: dict[int, QWidget] = {}
        builders = (
            (STYLE, self._build_style),
            (LOOK, self._build_look),
            (COLOURS, self._build_colours),
            (WEEK, self._build_week),
            (HOMEWORK, self._build_homework),
            (REMINDERS, self._build_reminders),
            (FIRST, self._build_first),
            (DONE, self._build_done),
        )
        for step, builder in builders:
            self.pages[step] = self._page(step, builder())
            self.stack.addWidget(self.pages[step])
        # The pages run under the footer, which fades them out above it; each page keeps the footer's
        # height clear at its end so the last thing on it can be reached.
        under = QWidget()
        under.setObjectName("setupRow")
        stacked = QGridLayout(under)
        stacked.setContentsMargins(0, 0, 0, 0)
        stacked.addWidget(self.stack, 0, 0)
        self.footer = Footer()
        self.footer.resized.connect(self._clear_footer)
        stacked.addWidget(self.footer, 0, 0, Qt.AlignmentFlag.AlignBottom)
        column.addWidget(under, 1)
        nav = QWidget()
        nav.setObjectName("setupNav")
        nav.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        around = QHBoxLayout(nav)
        around.setContentsMargins(32, 12, 32, 16)
        buttons = _centred_column(around)
        line = QHBoxLayout(buttons)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(10)
        self.back = QPushButton("Back")
        self.back.setObjectName("setupBack")
        self.back.clicked.connect(self._go_back)
        self.error = _label("", "setupError")
        self.skip = _outlined(SKIP_STEP_LABEL, "setupSkip")
        self.skip.clicked.connect(self._skip_step)
        self.next = QPushButton(NEXT_LABEL)
        self.next.setObjectName("setupNext")
        self.next.setDefault(True)
        self.next.clicked.connect(self._go_next)
        line.addWidget(self.back)
        line.addWidget(self.error, 1)
        line.addWidget(self.skip)
        line.addWidget(self.next)
        self.footer.add(nav)
        outer.addLayout(column, 1)
        self._sync_chrome()

    # Building

    def _build_rail(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("setupRail")
        rail.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        rail.setMinimumWidth(RAIL_MIN)
        box = QVBoxLayout(rail)
        box.setContentsMargins(22, 28, 16, 20)
        box.setSpacing(2)
        box.addWidget(_label("Set up FlexWeek", "setupBrand", wrap=False))
        box.addSpacing(14)
        self.rail_items: list[QPushButton] = []
        for index, (name, steps) in enumerate(RAIL):
            item = QPushButton(name)
            item.setObjectName("setupRailItem")
            item.setIconSize(QSize(BADGE_PX, BADGE_PX))
            item.setCursor(Qt.CursorShape.PointingHandCursor)
            item.setAccessibleName(f"Step {index + 1}: {name}")
            item.clicked.connect(lambda _checked=False, step=steps[0]: self._jump(step))
            box.addWidget(item)
            self.rail_items.append(item)
        box.addStretch(1)
        self.skip_all = _quiet(SKIP_ALL_LABEL, "setupSkipAll")
        self.skip_all.clicked.connect(self._skip_all)
        box.addWidget(self.skip_all, 0, Qt.AlignmentFlag.AlignLeft)
        box.addWidget(_label("You can run it again from Settings.", "setupHint"))
        # The bar beside the current step. It glides from step to step rather than jumping.
        self.marker = QFrame(rail)
        self.marker.setObjectName("setupRailMarker")
        self.marker.setFixedWidth(3)
        self._rail = rail
        return rail

    def _page(self, step: int, content: QWidget) -> QWidget:
        body = QWidget()
        body.setObjectName("setupBody")
        around = QHBoxLayout(body)
        scroll = PageScroll(around)
        scroll.setObjectName("setupScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        column = QWidget()
        column.setObjectName("setupRow")
        column.setMaximumWidth(SETUP_COLUMN)
        column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # The column's stretch outweighs the spacer's, so it takes the room up to its maximum and the
        # rest goes after it, not on both sides.
        around.addWidget(column, SETUP_COLUMN)
        around.addStretch(1)
        box = QVBoxLayout(column)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        title = _label(TITLES[step], "setupTitle")
        box.addWidget(title)
        box.addWidget(_label(NOTES[step], "setupNote"))
        box.addSpacing(6)
        box.addWidget(content)
        box.addStretch(1)
        scroll.setWidget(body)
        return scroll

    def _section(self, box: QVBoxLayout, text: str) -> None:
        box.addSpacing(6)
        box.addWidget(_label(text, "setupSection"))

    def _build_style(self) -> QWidget:
        content = QWidget()
        content.setObjectName("setupRow")
        box = QVBoxLayout(content)
        box.setContentsMargins(0, 0, 0, 0)
        self.carousel = StyleCarousel(STYLES, lambda: self.motion)
        self.carousel.moved.connect(lambda key: self._choose_style(next(s for s in STYLES if s.key == key)))
        self.style_cards = self.carousel.slides
        box.addWidget(self.carousel)
        own = QPushButton(OWN_LOOK_LABEL)
        own.setObjectName("setupOwnLook")
        own.setProperty("outline", True)
        own.setCursor(Qt.CursorShape.PointingHandCursor)
        own.clicked.connect(self._choose_own_look)
        box.addWidget(own, 0, Qt.AlignmentFlag.AlignHCenter)
        return content

    def _build_look(self) -> QWidget:
        content = QWidget()
        content.setObjectName("setupRow")
        box = QVBoxLayout(content)
        box.setContentsMargins(0, 0, 0, 0)
        self.look_cards: dict[str, ChoiceCard] = {}
        for experimental in (False, True):
            if experimental:
                self._section(box, EXPERIMENTAL)
            cards = []
            for spec in layouts_for("plan", experimental):
                card = ChoiceCard(spec.label, spec.summary, LOOK_THUMB)
                card.chosen.connect(lambda layout_id=spec.id: self._choose_main(layout_id))
                cards.append(card)
                self.look_cards[spec.id] = card
            _card_grid(box, LOOK_THUMB).set_cards(cards)
        return content

    def _build_colours(self) -> QWidget:
        content = QWidget()
        content.setObjectName("setupRow")
        line = QHBoxLayout(content)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(_label("Colours", "setupSection"))
        self.colours = Chips((), "Colours")
        self.colours.changed.connect(self._colours_changed)
        left.addWidget(self.colours)
        left.addWidget(_label("Text size", "setupSection"))
        self.text_size = Chips(TEXT_SIZES, "Text size")
        self.text_size.changed.connect(self._colours_changed)
        left.addWidget(self.text_size)
        left.addWidget(_label("Spacing", "setupSection"))
        self.spacing = Chips(SPACINGS, "Spacing")
        self.spacing.changed.connect(self._colours_changed)
        left.addWidget(self.spacing)
        fine = _quiet("Fine-tune fonts and shadows", "setupFineTune")
        fine.setCheckable(True)
        left.addWidget(fine, 0, Qt.AlignmentFlag.AlignLeft)
        self.fine = QWidget()
        self.fine.setObjectName("setupRow")
        fine_box = QVBoxLayout(self.fine)
        fine_box.setContentsMargins(0, 0, 0, 0)
        fine_box.addWidget(_label("Font", "setupFieldLabel"))
        self.font_choice = Chips(FONTS, "Font")
        self.font_choice.changed.connect(self._colours_changed)
        fine_box.addWidget(self.font_choice)
        fine_box.addWidget(_label("Shadows", "setupFieldLabel"))
        self.shadows = Chips(SHADOWS, "Shadows")
        self.shadows.changed.connect(self._colours_changed)
        fine_box.addWidget(self.shadows)
        self.fine.setVisible(False)
        fine.toggled.connect(self.fine.setVisible)
        left.addWidget(self.fine)
        left.addWidget(_label("Day screen, for when you are doing the plan", "setupSection"))
        self.day_screen = Chips(
            _design_chips(layouts_for("day", False)), "Day screen", _design_chips(layouts_for("day", True))
        )
        self.day_screen.changed.connect(self._colours_changed)
        left.addWidget(self.day_screen)
        left.addStretch(1)
        line.addLayout(left, 1)
        frame = QFrame()
        frame.setObjectName("setupGroup")
        framed = QVBoxLayout(frame)
        framed.setContentsMargins(8, 8, 8, 8)
        self.colour_preview = QLabel()
        self.colour_preview.setObjectName("setupPreview")
        self.colour_preview.setFixedSize(COLOUR_THUMB, round(COLOUR_THUMB * 0.625))
        self.colour_preview.setAccessibleName("Preview of your week")
        framed.addWidget(self.colour_preview)
        line.addWidget(frame, 0, Qt.AlignmentFlag.AlignTop)
        return content

    def _build_week(self) -> QWidget:
        content = QWidget()
        content.setObjectName("setupRow")
        box = QVBoxLayout(content)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        box.addWidget(_label("School", "setupSection"))
        self.school_days = DayPicker([0, 1, 2, 3, 4], "setupDay")
        self.school_times = TimeRange("08:00", "14:30", "School")
        school = QFrame()
        school.setObjectName("setupGroup")
        school_line = FlowLayout(school, gap=12)
        school_line.setContentsMargins(12, 10, 12, 10)
        school_line.addWidget(Level(self.school_days, self.school_times.start))
        school_line.addWidget(self.school_times)
        box.addWidget(school)
        # Said only when it is true: under a week of school days it read as a warning.
        self.school_hint = _label("No school days picked means no school on the calendar.", "setupHint")
        box.addWidget(self.school_hint)
        self.school_days.changed.connect(self._follow_school)
        self._section(box, "Sports, clubs and jobs")
        self.activity_box = QVBoxLayout()
        self.activity_box.setSpacing(8)
        box.addLayout(self.activity_box)
        self.activities: list[ActivityRow] = []
        self.add_activity = _quiet("+ Add a sport, club or job", "setupAddActivity")
        self.add_activity.clicked.connect(lambda: self._add_activity(focus=True))
        box.addWidget(self.add_activity, 0, Qt.AlignmentFlag.AlignLeft)
        self._section(box, "Bedtime")
        self.cutoff = QComboBox()
        self.cutoff.setObjectName("setupCutoff")
        self.cutoff.setAccessibleName("No homework after")
        fill_cutoff(self.cutoff, None)
        bedtime = QFrame()
        bedtime.setObjectName("setupGroup")
        bedtime_line = QHBoxLayout(bedtime)
        bedtime_line.setContentsMargins(12, 10, 12, 10)
        bedtime_line.setSpacing(8)
        bedtime_line.addWidget(_label("No homework after", "setupFieldLabel", wrap=False))
        bedtime_line.addWidget(self.cutoff)
        bedtime_line.addStretch(1)
        box.addWidget(bedtime)
        return content

    def _build_homework(self) -> QWidget:
        content = QWidget()
        content.setObjectName("setupRow")
        box = QVBoxLayout(content)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        self.planning = QButtonGroup(content)
        self.planning_buttons: dict[str, QRadioButton] = {}
        for value, text, note in PLANNING_STYLES:
            button = QRadioButton(text)
            button.setObjectName(f"setupPlanning-{value}")
            self.planning.addButton(button)
            self.planning_buttons[value] = button
            box.addWidget(button)
            hint = _label(note, "setupHint")
            hint.setContentsMargins(28, 0, 0, 6)
            box.addWidget(hint)
        self._section(box, DRAG_STEP_QUESTION)
        self.drag_step = QButtonGroup(content)
        self.drag_buttons: dict[int, QRadioButton] = {}
        for minutes, text in DRAG_STEP_CHOICES:
            button = QRadioButton(text)
            button.setObjectName(f"setupDragStep-{minutes}")
            self.drag_step.addButton(button, minutes)
            self.drag_buttons[minutes] = button
            box.addWidget(button)
        self._section(box, "When may FlexWeek plan homework?")
        self.work_editor = WorkWindowsEditor([])
        # Next is the one filled button on every page; a second filled one here read as the way on.
        # The presets are pills like the day picker's, which add a row rather than pick one; an
        # outlined button adds the custom one.
        for preset in self.work_editor.findChildren(QPushButton):
            if not preset.objectName().startswith("workWindowPreset"):
                continue
            preset.setProperty("quiet", False)
            preset.setProperty("chip", True)
        self.work_editor.add_button.setProperty("outline", True)
        box.addWidget(self.work_editor)
        return content

    def _build_reminders(self) -> QWidget:
        content = QWidget()
        content.setObjectName("setupRow")
        box = QVBoxLayout(content)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        self.reminders = QCheckBox("Remind me before things start")
        self.reminders.setObjectName("setupReminders")
        box.addWidget(self.reminders)
        self.lead = QSpinBox()
        self.lead.setObjectName("setupLead")
        self.lead.setRange(0, 120)
        self.lead.setSingleStep(5)
        self.lead.setSuffix(" min before")
        self.lead.setAccessibleName("How long before")
        box.addWidget(_row(Stepper(self.lead)))
        self.reminders.toggled.connect(self.lead.setEnabled)
        self._section(box, "Alarm sound")
        self.tones = QButtonGroup(content)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(2)
        self.tone_buttons: dict[str, QRadioButton] = {}
        for row, tone in enumerate(RECIPES):
            button = QRadioButton(TONE_NAMES[tone])
            button.setObjectName(f"setupTone-{tone}")
            self.tones.addButton(button)
            self.tone_buttons[tone] = button
            play = _quiet("", "setupPlay")
            play.setIcon(icons.icon("circle-play", self._palette["accent"]))
            play.setIconSize(QSize(PLAY_PX, PLAY_PX))
            play.setToolTip("Play")
            play.setAccessibleName(f"Play {TONE_NAMES[tone]}")
            self.play_buttons.append(play)
            play.clicked.connect(lambda _checked=False, tone=tone: self._bell.once(tone, self.volume))
            grid.addWidget(button, row, 0, Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(play, row, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.setColumnStretch(2, 1)
        box.addLayout(grid)
        spotify = QRadioButton("A Spotify song or playlist")
        spotify.setObjectName("setupTone-spotify")
        self.tones.addButton(spotify)
        self.tone_buttons["spotify"] = spotify
        box.addWidget(spotify)
        self.spotify_label = _label("Default Spotify link", "setupFieldLabel", wrap=False)
        box.addWidget(self.spotify_label)
        self.spotify = QLineEdit()
        self.spotify.setObjectName("setupSpotify")
        self.spotify.setPlaceholderText("Paste a link from Spotify: open.spotify.com/track/… or /playlist/…")
        self.spotify.setAccessibleName("Default Spotify link")
        self.spotify_note = _label(SPOTIFY_TONE_NOTE, "setupHint")
        box.addWidget(self.spotify)
        box.addWidget(self.spotify_note)
        self.tones.buttonToggled.connect(lambda *_args: self._follow_tone())
        self.test = QPushButton("Send a test reminder")
        self.test.setObjectName("setupTest")
        self.test.setProperty("outline", True)
        self.test.clicked.connect(self._send_test)
        self.test_result = _label("", "setupHint")
        box.addSpacing(6)
        box.addWidget(self.test, 0, Qt.AlignmentFlag.AlignLeft)
        box.addWidget(self.test_result)
        return content

    def _build_first(self) -> QWidget:
        content = QWidget()
        content.setObjectName("setupRow")
        box = QVBoxLayout(content)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        self.homework_box = QVBoxLayout()
        self.homework_box.setSpacing(8)
        box.addLayout(self.homework_box)
        self.homework_rows: list[HomeworkRow] = []
        self.add_homework = _quiet("+ Add another", "setupAddHomework")
        self.add_homework.clicked.connect(lambda: self._add_homework_row(focus=True))
        box.addWidget(self.add_homework, 0, Qt.AlignmentFlag.AlignLeft)
        return content

    def _build_done(self) -> QWidget:
        content = QWidget()
        content.setObjectName("setupRow")
        self.summary = QGridLayout(content)
        self.summary.setContentsMargins(0, 0, 0, 0)
        self.summary.setHorizontalSpacing(18)
        self.summary.setVerticalSpacing(12)
        self.summary.setColumnStretch(1, 1)
        self.summary_rows: list[tuple[QLabel, QLabel, QPushButton]] = []
        for row, (name, steps) in enumerate(RAIL[:-1]):
            heading = _label(name, "setupSummaryName", wrap=False)
            value = _label("", "setupSummaryValue")
            change = _quiet("Change", "setupChange")
            change.setAccessibleName(f"Change {name.lower()}")
            change.clicked.connect(lambda _checked=False, step=steps[0]: self._jump(step))
            self.summary.addWidget(heading, row, 0, Qt.AlignmentFlag.AlignTop)
            self.summary.addWidget(value, row, 1, Qt.AlignmentFlag.AlignTop)
            self.summary.addWidget(change, row, 2, Qt.AlignmentFlag.AlignTop)
            self.summary_rows.append((heading, value, change))
        return content

    # Opening

    @property
    def step(self) -> int:
        return self._step

    def open(self, state: SetupState, step: int = STYLE) -> None:
        """Fill every page from what is in place now and show `step`, without animating."""
        self._state = deepcopy(state)
        self._pack, self._look, self._layout = (
            state.pack,
            sanitize_look(state.look),
            sanitize_layout(state.layout),
        )
        self._made = {}
        self._fill_style()
        self._fill_week()
        self._fill_homework()
        self._fill_reminders()
        self._fill_first()
        step = step if step in self.pages else STYLE
        self._own_look = step in (LOOK, COLOURS)
        self._step = step
        self._furthest = step
        self._entered = (self._pack, deepcopy(self._look), deepcopy(self._layout))
        self.error.clear()
        self.test_result.clear()
        self._prepare(step)
        self.stack.setCurrentWidget(self.pages[step])
        self._sync_chrome()
        QTimer.singleShot(0, self, lambda: self._place_marker(animate=False))

    def _style_in_use(self) -> str | None:
        if self._state.first_run:
            return DEFAULT_STYLE
        return matching_style(self._pack, self._look, self._layout)

    def _fill_style(self) -> None:
        # A new account starts on Plain calendar, chosen, so Next without a click keeps it.
        self._style_key = self._style_in_use()
        self.carousel.show_style(self._style_key or DEFAULT_STYLE, chosen=self._style_key is not None)
        for layout_id, card in self.look_cards.items():
            card.select(layout_id == self._layout["main"])
        # The first page's pictures before it shows; the rest one at a time once it has.
        for style in STYLES:
            card = self.style_cards[style.key]
            card.set_picture(
                self._previews.get(style.main, style.colour, style.pack, style_look(style), STYLE_PICTURE)
            )
        self._pending_pictures = []
        for spec in layouts_for("plan"):
            colour = spec.colourways[0][0] if spec.colourways else None
            self._pending_pictures.append((self.look_cards[spec.id], spec.id, colour, self._pack, LOOK_THUMB))
        self._warm.start()

    def _draw_next_picture(self) -> None:
        if not self._pending_pictures:
            return
        card, main, colour, pack, width = self._pending_pictures.pop(0)
        card.set_picture(self._previews.get(main, colour, pack, None, width))
        if self._pending_pictures:
            self._warm.start()

    def _fill_week(self) -> None:
        blocks = self._state.blocks
        school = next((block for block in blocks if block.get("id") == SETUP_SCHOOL_ID), None)
        if school is not None and school.get("start"):
            self.school_days.set_days(list(school.get("days") or []))
            self.school_times.set_span(str(school["start"]), int(school["duration_min"]))
        else:
            self.school_days.set_days([0, 1, 2, 3, 4])
            self.school_times.set_span("08:00", 390)
        for row in list(self.activities):
            self._remove_activity(row)
        for block in blocks:
            if is_setup_block(block) and block.get("id") != SETUP_SCHOOL_ID and block.get("start"):
                self._add_activity(
                    title=str(block.get("title") or ""),
                    days=list(block.get("days") or []),
                    start=str(block["start"]),
                    minutes=int(block["duration_min"]),
                    category=str(block.get("category") or "extra"),
                    guess=False,
                )
        if not self.activities:
            self._add_activity()
        fill_cutoff(self.cutoff, self._state.preferences.get("day_cutoff"))
        self._follow_school()

    def _follow_school(self) -> None:
        self.school_hint.setVisible(not self.school_days.days())

    def _fill_homework(self) -> None:
        style = self._state.preferences.get("planning_style") or "suggest"
        self.planning_buttons.get(style, self.planning_buttons["suggest"]).setChecked(True)
        self.drag_buttons[drag_step(self._state.preferences.get("drag_step_min"))].setChecked(True)
        self.work_editor.set_subjects(self._state.subjects)
        self.work_editor.set_windows(self._state.preferences.get("work_windows") or [])

    def _fill_reminders(self) -> None:
        prefs = self._state.preferences
        self.reminders.setChecked(prefs.get("reminders_enabled", True) is not False)
        self.lead.setValue(reminder_lead_min(None if self._state.first_run else prefs))
        self.lead.setEnabled(self.reminders.isChecked())
        tone = str(prefs.get("alarm_tone") or FALLBACK)
        self.tone_buttons.get(tone, self.tone_buttons[FALLBACK]).setChecked(True)
        self.spotify.setText(str(prefs.get("default_spotify_url") or ""))
        self.volume = int(prefs.get("alert_volume", 80))
        self._follow_tone()

    def _fill_first(self) -> None:
        for row in list(self.homework_rows):
            self._remove_homework_row(row)
        self._add_homework_row()

    # Moving between pages

    def _after(self, step: int) -> int:
        if step == STYLE:
            return WEEK
        return min(step + 1, DONE)

    def _before(self, step: int) -> int:
        if step == WEEK:
            return COLOURS if self._own_look else STYLE
        return max(step - 1, STYLE)

    def _go_next(self) -> None:
        if self._step == DONE:
            self.finished.emit()
            return
        self._leave(self._after(self._step), keep=True)

    def _skip_step(self) -> None:
        self._leave(self._after(self._step), keep=False)

    def _go_back(self) -> None:
        if self._step != STYLE:
            self._leave(self._before(self._step), keep=False)

    def _jump(self, step: int) -> None:
        if step == self._step:
            return
        if step > self._furthest and step != DONE:
            return
        if step == DONE and self._furthest < DONE:
            return
        self._leave(step, keep=step > self._step)

    def _choose_own_look(self) -> None:
        self._own_look = True
        self._leave(LOOK, keep=False)

    def _skip_all(self) -> None:
        if self._step in LOOK_STEPS:
            self._restore_entered()
        self.finished.emit()

    def _leave(self, destination: int, keep: bool) -> None:
        step = self._step
        answer = None
        if keep:
            problem = self._problem(step)
            if problem:
                self.error.setText(problem)
                return
            answer = self._answer(step)
        elif step in LOOK_STEPS and destination not in LOOK_STEPS:
            # A look tried and then skipped is not kept, so the app goes back to the one it had.
            self._restore_entered()
        self.error.clear()
        if answer is not None:
            self._absorb(step, answer)
        self.left.emit(step, destination, answer)
        self._show(destination)

    def _show(self, step: int) -> None:
        direction = 1 if step > self._step else -1
        if step in LOOK_STEPS and self._step not in LOOK_STEPS:
            # What a skip on the look pages goes back to.
            self._entered = (self._pack, deepcopy(self._look), deepcopy(self._layout))
        self._step = step
        self._furthest = max(self._furthest, step)
        self._prepare(step)
        switch_page(self.stack, self.pages[step], self.motion, direction)
        self._sync_chrome()
        self._place_marker(animate=True)
        if step == DONE:
            self._reveal_summary()
        page = self.pages[step]
        if isinstance(page, QScrollArea):
            page.verticalScrollBar().setValue(0)

    def _prepare(self, step: int) -> None:
        if step == STYLE:
            self.carousel.setFocus(Qt.FocusReason.OtherFocusReason)
        if step == LOOK:
            for layout_id, card in self.look_cards.items():
                card.select(layout_id == self._layout["main"])
        if step == COLOURS:
            self._fill_colours()
        if step == FIRST:
            self._follow_school_days()
        if step == DONE:
            self._fill_summary()

    def _follow_school_days(self) -> None:
        """The school days may have changed since this page's date was made; one still as it was made
        moves to the new next school day."""
        fresh = next_school_day(self.school_days.days())
        for row in self.homework_rows:
            if row.due.value() == row.default_due:
                row.default_due = fresh
                row.due.set_value(fresh)

    def _clear_footer(self, height: int) -> None:
        for page in self.pages.values():
            if isinstance(page, PageScroll):
                page.set_footer(height)

    def _sync_chrome(self) -> None:
        self.back.setVisible(self._step != STYLE)
        self.skip.setVisible(self._step != DONE)
        self.next.setText(FINISH_LABEL if self._step == DONE else NEXT_LABEL)
        for index, (_name, steps) in enumerate(RAIL):
            item = self.rail_items[index]
            current = self._step in steps
            done = max(steps) < self._step or (self._furthest >= DONE and steps[0] != DONE)
            item.setProperty("current", current)
            item.setProperty("done", done)
            reachable = steps[0] <= self._furthest or (steps[0] == DONE and self._furthest >= DONE)
            item.setEnabled(reachable)
            _repolish(item)
            state = CURRENT if current else FINISHED if done else PENDING
            item.setIcon(self._badge(index + 1, state, item.font().family()))
            item.setAccessibleDescription("Done" if state == FINISHED else "")
        self._fit_rail()

    def _fit_rail(self) -> None:
        """The rail as wide as it is with its widest step bold, as the current step is, so the pages do
        not slide sideways as the steps change."""
        margins = self._rail.layout().contentsMargins()
        widest = 0
        for item in self.rail_items:
            item.ensurePolished()
            bold = item.font()
            bold.setWeight(QFont.Weight(WEIGHT_STRONG))
            around = item.sizeHint().width() - item.fontMetrics().horizontalAdvance(item.text())
            widest = max(widest, around + QFontMetrics(bold).horizontalAdvance(item.text()))
        # A few pixels over, then up to a multiple of 8, since bold text measured on its own rounds a
        # little differently from step to step and the rail must not follow that.
        wanted = -(-(widest + margins.left() + margins.right() + 3) // 8) * 8
        self._rail.setMinimumWidth(max(RAIL_MIN, wanted, self._rail.minimumWidth()))

    def _badge(self, number: int, state: str, family: str) -> QIcon:
        made = QIcon()
        for ratio in (1.0, 2.0):
            badge = step_badge(number, state, self._palette, family, ratio)
            # The same mark on a step not reached yet, not Qt's washed-out copy of it.
            made.addPixmap(badge, QIcon.Mode.Normal)
            made.addPixmap(badge, QIcon.Mode.Disabled)
        return made

    def set_palette(self, palette: dict) -> None:
        """Tint what the stylesheet cannot reach in the look's colours."""
        self._palette = palette
        for play in self.play_buttons:
            play.setIcon(icons.icon("circle-play", palette["accent"]))
        self._sync_chrome()

    def _place_marker(self, animate: bool) -> None:
        current = next(
            (item for item, (_name, steps) in zip(self.rail_items, RAIL, strict=True) if self._step in steps),
            None,
        )
        if current is None:
            return
        self.marker.show()
        self.marker.raise_()
        target = QRect(current.x() - 12, current.y() + 6, 3, max(current.height() - 12, 8))
        if animate:
            glide(self.marker, target, self.motion)
        else:
            self.marker.setGeometry(target)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self, lambda: self._place_marker(animate=False))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        QTimer.singleShot(0, self, lambda: self._place_marker(animate=False))

    # The look pages

    def _preview(self) -> None:
        self.previewed.emit(
            {"pack": self._pack, "look": deepcopy(self._look), "layout": deepcopy(self._layout)}
        )

    def _restore_entered(self) -> None:
        pack, look, layout = self._entered
        if (pack, look, layout) != (self._pack, self._look, self._layout):
            self._pack, self._look, self._layout = pack, deepcopy(look), deepcopy(layout)
            self._style_key = self._style_in_use()
            self.carousel.show_style(self._style_key or DEFAULT_STYLE, chosen=self._style_key is not None)
            self._preview()

    def _choose_style(self, style: Style) -> None:
        self._own_look = False
        self._style_key = style.key
        self.carousel.show_style(style.key, chosen=True)
        self._pack = style.pack
        self._look = style_look(style)
        self._layout = style_layout(style, self._layout)
        self._preview()

    def _choose_main(self, layout_id: str) -> None:
        for key, card in self.look_cards.items():
            card.select(key == layout_id)
        self._layout = sanitize_layout({**self._layout, "main": layout_id})
        self._preview()

    def _colour_choices(self) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
        """The colours on offer, standard then experimental."""
        main = self._layout["main"]
        spec = LAYOUTS[main]
        if not spec.colourways:
            standard, experimental = look_menu_items()
            return (
                tuple((name, label) for name, label, kind in standard if kind == "pack"),
                tuple((name, label) for name, label, kind in experimental if kind == "pack"),
            )
        return tuple((value, label) for value, label, _tokens in spec.colourways), ()

    def _fill_colours(self) -> None:
        main = self._layout["main"]
        self.colours.set_choices(*self._colour_choices())
        if LAYOUTS[main].colourways:
            self.colours.set_value(options_for(self._layout, main).get("colour"))
        else:
            self.colours.set_value(self._pack)
        knobs = effective_look(self._look)
        self.text_size.set_value(knobs["text"])
        self.spacing.set_value(knobs["density"])
        self.font_choice.set_value(knobs["font"])
        self.shadows.set_value(knobs["depth"])
        self.day_screen.set_value(self._layout["day"])
        self._draw_colour_preview(fade=False)

    def _colours_changed(self) -> None:
        main = self._layout["main"]
        colour = self.colours.value()
        options = deepcopy(self._layout["options"])
        if LAYOUTS[main].colourways and colour:
            options[main] = {**options.get(main, {}), "colour": colour}
            if main == "timeline":
                options[main]["density"] = self.spacing.value() or "comfortable"
        elif colour in PACKS:
            self._pack = colour
        knobs = dict(sanitize_look(self._look)["knobs"])
        for knob, chips in (
            ("text", self.text_size),
            ("density", self.spacing),
            ("font", self.font_choice),
            ("depth", self.shadows),
        ):
            if chips.value():
                knobs[knob] = chips.value()
        self._look = sanitize_look({"preset": "default", "knobs": knobs})
        self._layout = sanitize_layout({**self._layout, "options": options, "day": self.day_screen.value()})
        self._draw_colour_preview(fade=True)
        self._preview()

    def _draw_colour_preview(self, fade: bool) -> None:
        main = self._layout["main"]
        colour = options_for(self._layout, main).get("colour") if LAYOUTS[main].colourways else None
        picture = hold_picture(self.colour_preview, self.motion) if fade else None
        self.colour_preview.setPixmap(
            rounded_picture(self._previews.get(main, colour, self._pack, self._look, COLOUR_THUMB), 8)
        )
        fade_away(picture, self.motion)

    # Your week

    def _add_activity(
        self,
        title: str = "",
        days: list[int] | None = None,
        start: str = "15:30",
        minutes: int = 90,
        focus: bool = False,
        category: str = "extra",
        guess: bool = True,
    ) -> None:
        if len(self.activities) >= MAX_ACTIVITIES:
            return
        row = ActivityRow(title, days, start, minutes, category, guess=guess)
        row.removed.connect(self._remove_activity)
        self.activity_box.addWidget(row)
        self.activities.append(row)
        self.add_activity.setEnabled(len(self.activities) < MAX_ACTIVITIES)
        if focus:
            row.name.setFocus(Qt.FocusReason.OtherFocusReason)
            appear(row, self.motion, rise=False)

    def _remove_activity(self, row: object) -> None:
        if not isinstance(row, ActivityRow) or row not in self.activities:
            return
        self.activities.remove(row)
        self.activity_box.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self.add_activity.setEnabled(True)

    def week_blocks(self) -> list[dict]:
        blocks: list[dict] = []
        days = self.school_days.days()
        start, minutes = self.school_times.span()
        if days and minutes > 0:
            blocks.append(
                {
                    "id": SETUP_SCHOOL_ID,
                    "title": "School",
                    "kind": "locked",
                    "category": "class",
                    "start": start,
                    "duration_min": minutes,
                    "days": days,
                }
            )
        for index, row in enumerate(self.activities):
            days = row.days.days()
            start, minutes = row.times.span()
            if not days or minutes <= 0:
                continue
            blocks.append(
                {
                    "id": f"{SETUP_ACTIVITY_PREFIX}{index + 1}",
                    "title": row.name.text().strip() or SPORT_FALLBACK,
                    "kind": "locked",
                    "category": row.category.currentData(),
                    "start": start,
                    "duration_min": minutes,
                    "days": days,
                }
            )
        return blocks

    # Homework time

    # Reminders and alarm

    def _tone(self) -> str:
        checked = self.tones.checkedButton()
        for tone, button in self.tone_buttons.items():
            if button is checked:
                return tone
        return FALLBACK

    def _follow_tone(self) -> None:
        spotify = self._tone() == "spotify"
        self.spotify.setEnabled(spotify)
        self.spotify_label.setVisible(spotify)
        self.spotify_note.setVisible(spotify)

    def _spotify_link(self) -> str | None:
        typed = self.spotify.text().strip()
        if not typed:
            return None
        try:
            return valid_spotify_url(typed) or None
        except ValueError:
            return None

    def _send_test(self) -> None:
        if self._tone() == "spotify" and self._spotify_link() is None:
            self.test_result.setText("Paste a Spotify link first.")
            return
        self.test_requested.emit(self._tone(), self._spotify_link() or "")

    def show_test_result(self, text: str) -> None:
        self.test_result.setText(text)
        appear(self.test_result, self.motion)

    # First homework

    def _add_homework_row(self, focus: bool = False) -> None:
        if len(self.homework_rows) >= MAX_FIRST_HOMEWORK:
            return
        row = HomeworkRow(next_school_day(self.school_days.days()))
        row.removed.connect(self._remove_homework_row)
        self.homework_box.addWidget(row)
        self.homework_rows.append(row)
        self.add_homework.setEnabled(len(self.homework_rows) < MAX_FIRST_HOMEWORK)
        if focus:
            row.name.setFocus(Qt.FocusReason.OtherFocusReason)
            appear(row, self.motion)

    def _remove_homework_row(self, row: object) -> None:
        if not isinstance(row, HomeworkRow) or row not in self.homework_rows:
            return
        self.homework_rows.remove(row)
        self.homework_box.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self.add_homework.setEnabled(True)
        if not self.homework_rows:
            self._add_homework_row()

    def first_homework(self) -> list[dict]:
        made = []
        for row in self.homework_rows:
            title = row.name.text().strip()
            if not title:
                continue
            made.append(
                {
                    "id": self._made.get(title) or str(uuid4()),
                    "title": title,
                    "estimate_min": row.minutes.value(),
                    "due": row.due.value(),
                    "revision": 0,
                }
            )
        return made

    # Answers

    def _problem(self, step: int) -> str | None:
        if step == WEEK:
            if self.school_days.days() and self.school_times.span()[1] <= 0:
                return "School has to end after it starts."
            for row in self.activities:
                if row.days.days() and row.times.span()[1] <= 0:
                    name = row.name.text().strip() or "An activity"
                    return f"{name} has to end after it starts."
        if step == REMINDERS and self._tone() == "spotify" and self._spotify_link() is None:
            return "Paste a link that starts with https://open.spotify.com, or pick another sound."
        if step == HOMEWORK:
            return self.work_editor.problem()
        return None

    def _answer(self, step: int) -> dict | None:
        if step == STYLE:
            style = next((style for style in STYLES if style.key == self._style_key), None)
            if style is None:
                return None
            # The one in the middle, whether or not the student moved it.
            self._pack, self._look, self._layout = (
                style.pack,
                style_look(style),
                style_layout(style, self._layout),
            )
        if step in LOOK_STEPS:
            return {"pack": self._pack, "look": deepcopy(self._look), "layout": deepcopy(self._layout)}
        if step == WEEK:
            return {"blocks": self.week_blocks(), "day_cutoff": self.cutoff.currentData()}
        if step == HOMEWORK:
            checked = next(
                (value for value, button in self.planning_buttons.items() if button.isChecked()), "suggest"
            )
            return {
                "planning_style": checked,
                "drag_step_min": drag_step(self.drag_step.checkedId()),
                "work_windows": self.work_editor.windows(),
            }
        if step == REMINDERS:
            return {
                "reminders_enabled": self.reminders.isChecked(),
                "reminder_lead_min": self.lead.value(),
                "alarm_tone": self._tone(),
                "default_spotify_url": self._spotify_link()
                or self._state.preferences.get("default_spotify_url"),
            }
        if step == FIRST:
            homework = self.first_homework()
            for item in homework:
                self._made[item["title"]] = item["id"]
            return {"homework": homework} if homework else None
        return None

    def _absorb(self, step: int, answer: dict) -> None:
        """Keep the state in step with what was kept, so the summary says what is actually saved."""
        if step in LOOK_STEPS:
            self._state.pack, self._state.look, self._state.layout = (
                answer["pack"],
                deepcopy(answer["look"]),
                deepcopy(answer["layout"]),
            )
            self._entered = (self._pack, deepcopy(self._look), deepcopy(self._layout))
        elif step == WEEK:
            kept = [block for block in self._state.blocks if not is_setup_block(block)]
            self._state.blocks = kept + deepcopy(answer["blocks"])
            self._state.preferences["day_cutoff"] = answer["day_cutoff"]
        elif step in (HOMEWORK, REMINDERS):
            self._state.preferences.update(deepcopy(answer))
        elif step == FIRST:
            for item in answer["homework"]:
                if item["title"] not in self._state.homework:
                    self._state.homework.append(item["title"])

    # Done

    def _fill_summary(self) -> None:
        state = self._state
        main = state.layout["main"]
        spec = LAYOUTS[main]
        if spec.colourways:
            colour = options_for(state.layout, main).get("colour")
            colour_name = next(
                (label for value, label, _ in spec.colourways if value == colour), "your colours"
            )
        else:
            colour_name = PACK_IN.get(state.pack, "your colours")
        text = effective_look(state.look)["text"]
        look = f"{spec.label} in {colour_name}"
        if text != "normal":
            look += f", {text} text"
        week_parts = []
        for block in state.blocks:
            if is_setup_block(block) and block.get("start"):
                when = span_label(block["start"], block["duration_min"])
                week_parts.append(f"{block['title']} {days_label(block['days'])} {when}")
        cutoff = state.preferences.get("day_cutoff")
        if cutoff:
            week_parts.append(f"no homework after {hhmm_text(cutoff)}")
        prefs = state.preferences
        planning = next(
            (
                text
                for value, text, _note in PLANNING_STYLES
                if value == (prefs.get("planning_style") or "suggest")
            ),
            PLANNING_STYLES[1][1],
        )
        work_windows = prefs.get("work_windows") or []
        if work_windows:
            shown = [
                f"{days_label(window['days'])} {hhmm_text(window['start'])}–{hhmm_text(window['end'])}"
                for window in work_windows[:2]
            ]
            planning += " · homework only " + ", ".join(shown)
            if len(work_windows) > 2:
                planning += f" and {len(work_windows) - 2} more"
        else:
            planning += " · homework can be planned at any time of day"
        planning += f" · a drag moves {drag_step(prefs.get('drag_step_min'))} minutes at a time"
        tone = str(prefs.get("alarm_tone") or FALLBACK)
        sound = "Spotify" if tone == "spotify" else TONE_NAMES.get(tone, tone.title())
        if prefs.get("reminders_enabled"):
            reminders = f"{reminder_lead_min(prefs)} min before things start · {sound}"
        else:
            reminders = f"Off · alarms ring {sound}"
        values = (
            look,
            " · ".join(week_parts) or "Nothing fixed yet",
            planning,
            reminders,
            ", ".join(state.homework) or "None yet",
        )
        for (_heading, value, _change), text_value in zip(self.summary_rows, values, strict=True):
            value.setText(text_value)

    def _reveal_summary(self) -> None:
        # One line after another, so the eye reads down the list rather than taking it in as a block.
        for index, (heading, value, change) in enumerate(self.summary_rows):
            for widget in (heading, value, change):
                appear(widget, self.motion, delay_ms=90 + index * 45)

    def summary_text(self) -> list[str]:
        return [value.text() for _heading, value, _change in self.summary_rows]
