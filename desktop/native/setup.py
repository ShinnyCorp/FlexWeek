"""First-run setup: one question a page, every page skippable, remembered as the student goes.

A new account arrives here from its recovery codes. Each page is kept when the student leaves it with
Next, so a quit resumes where they were and nothing is asked twice. Look and layout belong to this
computer; everything else belongs to the account. The window does the writing: this page says what
was chosen. Once setup is finished or skipped it never returns unless the student asks for it again
in Settings.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from uuid import uuid4

from PySide6.QtCore import QRect, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from backend.models import valid_spotify_url
from backend.slots import SLOT_MIN, hhmm_to_minutes, minutes_to_hhmm
from desktop.native.calendar import (
    DAY_FULL,
    SETUP_ACTIVITY_PREFIX,
    SETUP_SCHOOL_ID,
    is_setup_block,
    sunday_due,
)
from desktop.native.hours.geometry import drag_step
from desktop.native.layouts.registry import (
    EXPERIMENTAL,
    LAYOUTS,
    LayoutSpec,
    layouts_for,
    options_for,
    sanitize_layout,
)
from desktop.native.look import PACK_LABELS, PACKS, effective_look, look_menu_items, sanitize_look
from desktop.native.motion import appear, fade_away, glide, hold_picture, slide_page
from desktop.native.previews import Previews
from desktop.native.settings import (
    DRAG_STEP_CHOICES,
    DRAG_STEP_QUESTION,
    PLANNING_STYLES,
    SPORT_FALLBACK,
    SPOTIFY_TONE_NOTE,
)
from desktop.native.sound import Bell
from desktop.native.tones import FALLBACK, RECIPES
from desktop.native.weekmodel import clock_text, hhmm_text, time_format
from desktop.native.widgets import DAYS, ChoiceCard, DueField, FlowLayout, rounded_picture
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
    REMINDERS: "One sound for reminders, alarms and the end of a focus session.",
    FIRST: "Add up to three. You can add the rest any time.",
    DONE: "Everything here is also in Settings. Run setup again from Settings, under This computer.",
}
NEXT_LABEL, FINISH_LABEL = "Next", "Open my week"
SKIP_STEP_LABEL, SKIP_ALL_LABEL = "Skip this step", "Skip setup"
OWN_LOOK_LABEL = "Choose my own look instead"
MAX_ACTIVITIES = 8
MAX_FIRST_HOMEWORK = 3
CUTOFFS = ("20:00", "20:30", "21:00", "21:30", "22:00", "22:30", "23:00")
# A tap adds one of these rather than making the student type hours for the usual answers.
TEXT_SIZES = (("small", "Small"), ("normal", "Normal"), ("large", "Large"))
SPACINGS = (("comfortable", "Comfortable"), ("compact", "Compact"))
FONTS = (("sans", "Sans"), ("serif", "Serif"), ("mono", "Mono"))
SHADOWS = (("soft", "Soft"), ("flat", "Flat"), ("hard", "Hard"))
TONE_NAMES = {tone: tone.title() for tone in RECIPES}
STYLE_THUMB, LOOK_THUMB, COLOUR_THUMB = 264, 206, 400


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


STYLES = (
    Style(
        "plain",
        "Plain calendar",
        "Calendar · Today's app. Your week as a grid, like a timetable.",
        "classic",
        None,
        "light-frost",
    ),
    Style(
        "dashboard",
        "Dashboard",
        "Dashboard · Bento in indigo. What's next and what's due, as tiles.",
        "bento",
        "indigo",
        "light-frost",
    ),
    Style(
        "night",
        "Night owl",
        "Agenda · Timeline at night, with compact spacing.",
        "timeline",
        "night",
        "dark-frost",
        {"density": "compact"},
        {"density": "compact"},
    ),
    Style(
        "retro",
        "Retro",
        "Dashboard · Retro desktop in teal, with large text.",
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
    return tuple((spec.id, f"{spec.purpose} · {spec.label}") for spec in specs)


def span_label(start: str, minutes: int) -> str:
    return f"{hhmm_text(start)}–{clock_text(hhmm_to_minutes(start) + minutes)}"


def _label(text: str, name: str = "", wrap: bool = True) -> QLabel:
    made = QLabel(text)
    if name:
        made.setObjectName(name)
    made.setWordWrap(wrap)
    return made


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _quiet(text: str, name: str = "setupQuiet") -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _card_grid(box: QVBoxLayout) -> QGridLayout:
    """A grid for picture cards, added to `box`. A grid, not a flow: a flow sizes each card by its
    hint and cannot give a name that wraps its second line, so the name was drawn over the picture."""
    cards = QWidget()
    cards.setObjectName("setupRow")
    grid = QGridLayout(cards)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(14)
    box.addWidget(cards)
    return grid


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


class DayPicker(QWidget):
    changed = Signal()

    def __init__(self, days: list[int] | tuple[int, ...] = ()) -> None:
        super().__init__()
        self.setObjectName("setupRow")
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        self.buttons: list[QPushButton] = []
        for index, name in enumerate(DAYS):
            button = QPushButton(name)
            button.setObjectName("setupDay")
            button.setCheckable(True)
            button.setChecked(index in days)
            button.setAccessibleName(DAY_FULL[index])
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.toggled.connect(self.changed)
            line.addWidget(button)
            self.buttons.append(button)

    def days(self) -> list[int]:
        return [index for index, button in enumerate(self.buttons) if button.isChecked()]

    def set_days(self, days: list[int]) -> None:
        for index, button in enumerate(self.buttons):
            button.setChecked(index in days)


class QuarterTime(QTimeEdit):
    """A time of day. The arrows and the wheel move the minutes a quarter hour at a time; a time typed
    between quarters keeps its minute, as the block editor does."""

    def __init__(self, hhmm: str) -> None:
        super().__init__(QTime.fromString(hhmm, "HH:mm"))
        self.setObjectName("setupTime")
        self.setDisplayFormat(time_format())
        self.setCorrectionMode(QAbstractSpinBox.CorrectionMode.CorrectToNearestValue)

    def minutes(self) -> int:
        time = self.time()
        return time.hour() * 60 + time.minute()

    def set_minutes(self, minutes: int) -> None:
        minutes = max(0, min(minutes, 24 * 60 - 1))
        self.setTime(QTime(minutes // 60, minutes % 60))

    def stepBy(self, steps: int) -> None:  # noqa: N802
        if self.currentSection() == QDateTimeEdit.Section.MinuteSection:
            base = self.minutes() - self.minutes() % SLOT_MIN
            # Up from 08:07 is 08:15 and down is 08:00: the quarter hour on each side.
            if steps < 0 and self.minutes() % SLOT_MIN:
                steps += 1
            self.set_minutes(base + steps * SLOT_MIN)
            return
        super().stepBy(steps)

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
        self.end = QuarterTime(end)
        self.end.setAccessibleName(f"{name} ends")
        line.addWidget(_label("from", "setupFieldLabel", wrap=False))
        line.addWidget(self.start)
        line.addWidget(_label("to", "setupFieldLabel", wrap=False))
        line.addWidget(self.end)

    def span(self) -> tuple[str, int]:
        start = hhmm_to_minutes(self.start.hhmm())
        return self.start.hhmm(), hhmm_to_minutes(self.end.hhmm()) - start

    def set_span(self, start: str, minutes: int) -> None:
        begin = hhmm_to_minutes(start)
        self.start.set_minutes(begin)
        self.end.set_minutes(begin + minutes)


class ActivityRow(QFrame):
    removed = Signal(object)

    def __init__(
        self, title: str = "", days: list[int] | None = None, start: str = "15:30", minutes: int = 90
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
        remove = _quiet("Remove")
        remove.setAccessibleName("Remove this activity")
        remove.clicked.connect(lambda: self.removed.emit(self))
        top = QHBoxLayout()
        top.addWidget(self.name, 1)
        top.addWidget(remove)
        box.addLayout(top)
        self.days = DayPicker(days or [])
        self.times = TimeRange(start, minutes_to_hhmm(hhmm_to_minutes(start) + minutes), "Activity")
        bottom = FlowLayout(gap=12)
        bottom.addWidget(self.days)
        bottom.addWidget(self.times)
        box.addLayout(bottom)


class HomeworkRow(QFrame):
    removed = Signal(object)

    def __init__(self, due: str) -> None:
        super().__init__()
        self.setObjectName("setupGroup")
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.name = QLineEdit()
        self.name.setObjectName("setupHomeworkName")
        self.name.setPlaceholderText("History essay")
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
        remove = _quiet("Remove")
        remove.setAccessibleName("Remove this homework")
        remove.clicked.connect(lambda: self.removed.emit(self))
        grid.addWidget(_label("Name", "setupFieldLabel", wrap=False), 0, 0)
        grid.addWidget(self.name, 0, 1, 1, 3)
        grid.addWidget(remove, 0, 4)
        grid.addWidget(_label("Takes", "setupFieldLabel", wrap=False), 1, 0)
        grid.addWidget(self.minutes, 1, 1)
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
        column.addWidget(self.stack, 1)
        nav = QWidget()
        nav.setObjectName("setupNav")
        nav.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        line = QHBoxLayout(nav)
        line.setContentsMargins(32, 12, 32, 16)
        line.setSpacing(10)
        self.back = QPushButton("Back")
        self.back.setObjectName("setupBack")
        self.back.clicked.connect(self._go_back)
        self.error = _label("", "setupError")
        self.skip = _quiet(SKIP_STEP_LABEL, "setupSkip")
        self.skip.clicked.connect(self._skip_step)
        self.next = QPushButton(NEXT_LABEL)
        self.next.setObjectName("setupNext")
        self.next.setDefault(True)
        self.next.clicked.connect(self._go_next)
        line.addWidget(self.back)
        line.addWidget(self.error, 1)
        line.addWidget(self.skip)
        line.addWidget(self.next)
        column.addWidget(nav)
        outer.addLayout(column, 1)
        self._sync_chrome()

    # Building

    def _build_rail(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("setupRail")
        rail.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        rail.setMinimumWidth(210)
        box = QVBoxLayout(rail)
        box.setContentsMargins(22, 28, 16, 20)
        box.setSpacing(2)
        box.addWidget(_label("Set up FlexWeek", "setupBrand", wrap=False))
        box.addSpacing(14)
        self.rail_items: list[QPushButton] = []
        for index, (name, steps) in enumerate(RAIL):
            item = QPushButton(f"{index + 1}   {name}")
            item.setObjectName("setupRailItem")
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
        scroll = QScrollArea()
        scroll.setObjectName("setupScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("setupBody")
        around = QHBoxLayout(body)
        around.setContentsMargins(32, 28, 32, 12)
        column = QWidget()
        column.setObjectName("setupRow")
        column.setMaximumWidth(900)
        box = QVBoxLayout(column)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        title = _label(TITLES[step], "setupTitle")
        box.addWidget(title)
        box.addWidget(_label(NOTES[step], "setupNote"))
        box.addSpacing(6)
        box.addWidget(content)
        box.addStretch(1)
        around.addWidget(column, 1)
        around.addStretch(0)
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
        self.style_cards: dict[str, ChoiceCard] = {}
        for experimental in (False, True):
            styles = [style for style in STYLES if LAYOUTS[style.main].experimental == experimental]
            if experimental:
                self._section(box, EXPERIMENTAL)
            grid = _card_grid(box)
            for index, style in enumerate(styles):
                card = ChoiceCard(style.name, style.note, STYLE_THUMB)
                card.chosen.connect(lambda style=style: self._choose_style(style))
                grid.addWidget(card, index // 2, index % 2)
                self.style_cards[style.key] = card
            grid.setColumnStretch(2, 1)
        own = _quiet(OWN_LOOK_LABEL, "setupOwnLook")
        own.clicked.connect(self._choose_own_look)
        box.addWidget(own, 0, Qt.AlignmentFlag.AlignLeft)
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
            grid = _card_grid(box)
            for index, spec in enumerate(layouts_for("plan", experimental)):
                card = ChoiceCard(f"{spec.purpose} · {spec.label}", spec.summary, LOOK_THUMB)
                card.chosen.connect(lambda layout_id=spec.id: self._choose_main(layout_id))
                grid.addWidget(card, index // 3, index % 3)
                self.look_cards[spec.id] = card
            grid.setColumnStretch(3, 1)
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
        self.school_days = DayPicker([0, 1, 2, 3, 4])
        self.school_times = TimeRange("08:00", "14:30", "School")
        school = QWidget()
        school.setObjectName("setupRow")
        school_line = FlowLayout(school, gap=12)
        school_line.setContentsMargins(0, 0, 0, 0)
        school_line.addWidget(self.school_days)
        school_line.addWidget(self.school_times)
        box.addWidget(school)
        box.addWidget(_label("No school days picked means no school on the calendar.", "setupHint"))
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
        self.cutoff.addItem("No limit", None)
        for hhmm in CUTOFFS:
            self.cutoff.addItem(hhmm_text(hhmm), hhmm)
        box.addWidget(_row(_label("No homework after", "setupFieldLabel", wrap=False), self.cutoff))
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
        box.addWidget(_row(self.lead))
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
            play = _quiet("▶ Play", "setupPlay")
            play.setAccessibleName(f"Play {TONE_NAMES[tone]}")
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
        self.spotify = QLineEdit()
        self.spotify.setObjectName("setupSpotify")
        self.spotify.setPlaceholderText("Paste a link from Spotify: open.spotify.com/track/… or /playlist/…")
        self.spotify.setAccessibleName("Spotify link")
        self.spotify_note = _label(SPOTIFY_TONE_NOTE, "setupHint")
        box.addWidget(self.spotify)
        box.addWidget(self.spotify_note)
        self.tones.buttonToggled.connect(lambda *_args: self._follow_tone())
        self.test = QPushButton("Send a test reminder")
        self.test.setObjectName("setupTest")
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
        QTimer.singleShot(0, lambda: self._place_marker(animate=False))

    def _fill_style(self) -> None:
        self._style_key = (
            matching_style(self._pack, self._look, self._layout) if not self._state.first_run else None
        )
        for key, card in self.style_cards.items():
            card.select(key == self._style_key)
        for layout_id, card in self.look_cards.items():
            card.select(layout_id == self._layout["main"])
        # The first page's pictures before it shows; the rest one at a time once it has.
        for style in STYLES:
            card = self.style_cards[style.key]
            card.set_picture(
                self._previews.get(style.main, style.colour, style.pack, style_look(style), STYLE_THUMB)
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
                )
        if not self.activities:
            self._add_activity()
        cutoff = self._state.preferences.get("day_cutoff")
        self.cutoff.setCurrentIndex(max(0, self.cutoff.findData(cutoff)))

    def _fill_homework(self) -> None:
        style = self._state.preferences.get("planning_style") or "suggest"
        self.planning_buttons.get(style, self.planning_buttons["suggest"]).setChecked(True)
        self.drag_buttons[drag_step(self._state.preferences.get("drag_step_min"))].setChecked(True)
        self.work_editor.set_subjects(self._state.subjects)
        self.work_editor.set_windows(self._state.preferences.get("work_windows") or [])

    def _fill_reminders(self) -> None:
        prefs = self._state.preferences
        self.reminders.setChecked(prefs.get("reminders_enabled", True) is not False)
        self.lead.setValue(int(prefs.get("reminder_lead_min", 10) if not self._state.first_run else 10))
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
        slide_page(self.stack, self.pages[step], self.motion, direction)
        self._sync_chrome()
        self._place_marker(animate=True)
        if step == DONE:
            self._reveal_summary()
        page = self.pages[step]
        if isinstance(page, QScrollArea):
            page.verticalScrollBar().setValue(0)

    def _prepare(self, step: int) -> None:
        if step == LOOK:
            for layout_id, card in self.look_cards.items():
                card.select(layout_id == self._layout["main"])
        if step == COLOURS:
            self._fill_colours()
        if step == DONE:
            self._fill_summary()

    def _sync_chrome(self) -> None:
        self.back.setVisible(self._step != STYLE)
        self.skip.setVisible(self._step != DONE)
        self.next.setText(FINISH_LABEL if self._step == DONE else NEXT_LABEL)
        for index, (_name, steps) in enumerate(RAIL):
            item = self.rail_items[index]
            item.setProperty("current", self._step in steps)
            item.setProperty("done", max(steps) < self._step or (self._furthest >= DONE and steps[0] != DONE))
            reachable = steps[0] <= self._furthest or (steps[0] == DONE and self._furthest >= DONE)
            item.setEnabled(reachable)
            _repolish(item)

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
        QTimer.singleShot(0, lambda: self._place_marker(animate=False))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        QTimer.singleShot(0, lambda: self._place_marker(animate=False))

    # The look pages

    def _preview(self) -> None:
        self.previewed.emit(
            {"pack": self._pack, "look": deepcopy(self._look), "layout": deepcopy(self._layout)}
        )

    def _restore_entered(self) -> None:
        pack, look, layout = self._entered
        if (pack, look, layout) != (self._pack, self._look, self._layout):
            self._pack, self._look, self._layout = pack, deepcopy(look), deepcopy(layout)
            self._style_key = matching_style(pack, look, layout) if not self._state.first_run else None
            for key, card in self.style_cards.items():
                card.select(key == self._style_key)
            self._preview()

    def _choose_style(self, style: Style) -> None:
        self._own_look = False
        self._style_key = style.key
        for key, card in self.style_cards.items():
            card.select(key == style.key)
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
    ) -> None:
        if len(self.activities) >= MAX_ACTIVITIES:
            return
        row = ActivityRow(title, days, start, minutes)
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
                    "category": "extra",
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
        row = HomeworkRow(
            sunday_due(self._state.week_start) if self._state.week_start else "2026-01-04T23:59"
        )
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
        if step == STYLE and self._style_key is None:
            return None
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
            colour_name = PACK_LABELS.get(state.pack, "your colours")
        text = effective_look(state.look)["text"]
        look = f"{spec.purpose} · {spec.label} in {colour_name}"
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
            reminders = f"{prefs.get('reminder_lead_min', 5)} min before things start · {sound}"
        else:
            reminders = f"Off · alarms ring {sound}"
        values = (
            look,
            "; ".join(week_parts) or "Nothing fixed yet",
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
