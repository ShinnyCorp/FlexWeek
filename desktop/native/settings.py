"""Focus panel, preferences, restore points and account dialogs."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QEvent, QMargins, QObject, QSize, Qt, QTime, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QPalette,
    QPixmap,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QBoxLayout,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.comfort import TIMER_PRESETS, snap_minutes
from backend.models import valid_spotify_url
from backend.slots import SLOT_MIN
from desktop.native import autostart
from desktop.native.calendar import DAY_FULL
from desktop.native.controller import ROUTINE_STATUS
from desktop.native.custom_look import UNNAMED, sanitize_saved, wear
from desktop.native.fields import ClockField, DayPicker, Stepper
from desktop.native.focus import FOCUS_PHASE_LABEL, format_countdown, more_time_choices, remaining_ms
from desktop.native.fonts import time_font
from desktop.native.hours.geometry import drag_step
from desktop.native.icons import pixmap as icon_pixmap
from desktop.native.layouts.dialog import SLOTS, LayoutSection
from desktop.native.layouts.registry import sanitize_layout
from desktop.native.look import (
    ACCENT_COLORS,
    ACCENTS,
    KNOB_VALUE_LABELS,
    LOOK_KNOBS,
    OWN_ACCENT,
    effective_look,
    known_pack,
    look_menu_items,
    look_menu_token,
    look_menu_value,
    look_motion,
    look_overrides,
    parse_look_menu_token,
    resolved_palette,
    sanitize_look,
    text_scale,
)
from desktop.native.look_editor import LookEditor
from desktop.native.look_preview import look_choice, look_preview
from desktop.native.motion import switch_page
from desktop.native.remind import ALARM_SNOOZE_MIN
from desktop.native.sound import Bell
from desktop.native.spotify import SpotifyPlayer, open_in_app
from desktop.native.tokens import SPACING
from desktop.native.tones import FALLBACK, SOUNDS
from desktop.native.version import VERSION
from desktop.native.weekmodel import hhmm_text, length_label
from desktop.native.widgets import (
    CARD_GAP,
    CARD_WIDTH_PAD,
    SHEET_FORM,
    SHEET_LIST,
    CardGrid,
    ChoiceCard,
    Choices,
    Dialog,
    FitScroll,
    FlowLayout,
    Form,
    Segmented,
    Swatches,
    Switch,
    bare,
    even_fields,
    even_labels,
    overlay_scroll_bars,
    sheet_button,
    sheet_footer,
    sheet_section,
)

UPDATE_MIN_WIDTH = 420
ALARM_MIN_WIDTH = 380
ALARM_PAD = 20
ALARM_GAP = 12
ALARM_BUTTON_HEIGHT = 44
# Room beside the longest name in the Settings list, for its selection edge.
PREFS_NAV_PAD = 8
# The column of cards, centred in the page up to this width (decision 24 of 0.17).
SETTINGS_COLUMN = 960
CARD_PAD = 16
SECTION_GAP_BELOW = 24
SECTIONS = ("Appearance & layout", "Planning", "Focus", "Alerts", "This computer")
# Each section's icon in the list, Lucide's names (decision 24 of 0.17). None on the rows themselves.
SECTION_ICONS = ("palette", "calendar", "timer", "bell", "laptop")
# The three looks most people choose between; every other look is under More looks.
MAIN_LOOKS = ("light-frost", "dark-frost", "system")
MORE_LOOKS = "More looks"
# A More looks card's picture is this wide at normal text, and wider as the text is larger; its
# card a little more (ChoiceCard).
LOOK_TILE = 150
ACCENT_LABELS = {"default": "Blue"}
OWN_ACCENT_NOTE = "High contrast keeps its own yellow, whatever accent is picked."
# A look of the student's own sets the accent and every knob (look.py's resolved_palette and
# effective_look), so while one is worn they show its values and say where they change instead.
OWN_LOOK_ACCENT_NOTE = "{name} sets the accent. To change it, open Customise…"
OWN_LOOK_KNOBS_NOTE = "{name} sets these. To change them, open Customise… in Colours."
CUSTOMISE = "Customise"
CUSTOMISE_TIP = "Change any look, colours, corners and fonts included, and save it as your own."
# A saved look's choice under More looks, after the ten, by its name.
SAVED_LOOK = "saved:"
YOUR_LOOKS = "Your looks"
UNSAVED_LOOK = "{name} (not saved)"
WEARING = "Wearing {name}"
# The footer says this one thing; the status line's routine "Saving…" and "Saved preferences." would
# have it swap between two sentences for the same fact (Grok Bot's 0.17.0 audit, T33).
SAVE_STATE = "Changes are saved as you make them."
MOTION_CHOICES = (("Normal", "normal"), ("More", "extra"), ("Reduce", "reduce"), ("Off", "off"))
PREFERRED_VIEWS = (("Whatever I had open", None), ("Week", "week"), ("Day", "day"))
KNOB_LABELS = {
    "surface": "Surface",
    "corners": "Corners",
    "depth": "Shadows",
    "font": "Font",
    "blocks": "Blocks",
    "density": "Spacing",
    "text": "Text size",
}
ALARM_LIST_MAX_HEIGHT = 200
ACCOUNT_MAX_WIDTH = 520
ACCOUNT_MIN_WIDTH = 560
ACCOUNT_PASSWORD_NOTE = "Your current password is needed for every change on this page."
ACCOUNT_CODES_NOTE = "Each code signs you in once if you forget your password."
ACCOUNT_DATA_NOTE = "Keep a copy of your account, or of one week or day, in a file."
SPORT_FALLBACK = "Sport or club"
ALARM_TONE_LABELS = {"spotify": "A Spotify song or playlist"}
# Said above the choice, where it can wrap: as the choice's label it was wider than the page at large text.
DRAG_STEP_QUESTION = "When you drag a block, it moves in steps of this length."
DRAG_STEP_CHOICES = ((5, "5 minutes (more control)"), (15, "15 minutes (quarter hours)"))
PLANNING_STYLES = (
    ("auto", "Plan it for me as I add it", "New homework gets a time straight away."),
    (
        "suggest",
        "Plan when I press Plan my homework",
        "Homework waits in a list until you ask. This is how FlexWeek has always worked.",
    ),
    ("manual", "I'll drag it onto the calendar myself", "The planning button becomes Suggest times."),
)
SPOTIFY_TONE_NOTE = (
    "Alarms play this in your Spotify app, and stopping the alarm stops it. A block with its own"
    " Spotify link plays that link when it starts instead. Reminders and the end of a focus session"
    " play Chime. Without the Spotify app, alarms open the link and ring Chime too."
)
# What only Today's app reads. Every other design has its own colours and shapes, so these changed
# nothing there (measured 2026-09-21: not the view, not the top bar, apart from Corners on the bar).
TODAYS_APP_KNOBS = ("surface", "corners", "blocks")
# What the switch shows, so it does not read as the design's own "more options" (Grok Bot's 0.17.0
# audit, T33: "Fine-tune this design" and "Fine-tune this look" read as one toggle).
FINE_TUNE_LOOK = "Show shape, spacing and type"
OWN_LOOK = "Your own look"
SECTION_GAP = 14
ABOUT_LINE = "FlexWeek plans your homework around school, sports and everything else in your week."
ABOUT_HERE = "Your plans are saved on this computer."
LOGO = Path(__file__).resolve().parents[1] / "assets" / "logo.png"
ABOUT_LOGO_PX = 56
# How far the words fade out at a scroll edge with more past it.
FADE_PX = 24
HELP_SCREENS = (
    ("Day", "One day hour by hour, with homework that is not placed yet beside it, ready to drag in."),
    ("Week", "Monday to Sunday: drag a block to move it, or drag across empty time to add one."),
    ("Month", "Each date's blocks and the homework due that day; click a date to open it in Day."),
    ("My day", "What is on now and what comes next, to follow once your plan is made."),
)
# Each key in brackets is drawn as a keycap; the words between are drawn plain.
HELP_KEYS = (
    ("[D] [W] [M]", "Day, Week, Month"),
    ("[T]", "My day"),
    ("[B] or [Esc]", "Back from My day"),
    ("[F]", "Focus screen"),
    ("[Ctrl]+[K]", "Command bar"),
    ("[Ctrl]+[Z]", "Undo"),
    ("[Ctrl]+[Y] or [Ctrl]+[Shift]+[Z]", "Redo"),
    ("[Ctrl]+[C] then [Ctrl]+[V]", "Copy the selected block, then paste it into the selected day"),
    ("[Ctrl]+[D]", "Duplicate the selected block"),
    ("[Delete]", "Delete the selected block"),
    ("[Ctrl]+[S]", "Save now"),
    ("[Ctrl]+[=] [-] [0]", "Zoom the hours in, out, or back to normal"),
    ("[Ctrl] and the mouse wheel", "Zoom the hours"),
    ("[Esc] while dragging", "Put the block back where it was"),
)
FOCUS_RUNNING_NOTE = "Work on this until the timer ends. Pause if something interrupts you."
FOCUS_ENDED_NOTE = "Time is up. Mark it finished, take a break, or give it more time."
BLOCK_SONG_NOTE = (
    "A block with a Spotify link plays it when the block starts. Dismiss or snooze it as you would an alarm."
)
ALARM_NOTE = "An alarm rings at its time on the days you pick, until you dismiss or snooze it."
# A checkbox's words do not wrap, so what needs more than a few words says it underneath.
DND_NOTE = "Each one stays in the window until you press Got it."
TRAY_NOTE = "FlexWeek waits in the tray, so reminders and alarms still come."
NO_SOUND = (
    "No sound played. Check that Volume is above 0 % and that your speakers or headphones are connected"
    " and not muted, then press Play again."
)


def ring_days(days: list[int]) -> str:
    """The days an alarm rings, as a student would say them."""
    chosen = sorted(set(days))
    if chosen == list(range(7)):
        return "every day"
    if chosen == [0, 1, 2, 3, 4]:
        return "Monday to Friday"
    if chosen == [5, 6]:
        return "Saturday and Sunday"
    if not chosen:
        return "no days"
    if len(chosen) == 1:
        return DAY_FULL[chosen[0]]
    short = [DAY_FULL[day][:3] for day in chosen]
    return ", ".join(short[:-1]) + " and " + short[-1]


def _note(words: str, name: str) -> QLabel:
    made = QLabel(words)
    made.setObjectName(name)
    made.setWordWrap(True)
    return made


def _page_button(words: str, name: str) -> QPushButton:
    """A button that opens something else or acts on the side. Outlined and as wide as its words, since
    Done is the one filled button in Settings; stretched and filled, each was the loudest thing on its
    page, and as words alone none looked like a button."""
    made = QPushButton(words)
    made.setObjectName(name)
    made.setProperty("outline", True)
    made.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return made


def _heading(words: str) -> QLabel:
    """A card's title, so eighteen settings stop reading as one list."""
    made = QLabel(words)
    made.setObjectName("prefsHeading")
    return made


def _card(title: str, note: str = "") -> tuple[QFrame, QFormLayout]:
    """A card of settings under a title, and the form its rows go in."""
    card = QFrame()
    card.setObjectName("settingsCard")
    form = Form(card)
    form.setContentsMargins(CARD_PAD, CARD_PAD, CARD_PAD, CARD_PAD)
    form.setVerticalSpacing(10)
    # Only what is meant to stretch does: a spin box or a short dropdown as wide as the card read as a
    # text field.
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    # A long row puts its label above it, so a card never needs more room than the page has.
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.addRow(_heading(title))
    if note:
        form.addRow(_note(note, "settingsCardNote"))
    return card, form


def _section_page(title: str, cards: tuple[QWidget, ...]) -> QWidget:
    """One section: its name, then its cards, in a column no wider than reads well."""
    page = QWidget()
    page.setObjectName("settingsBody")
    around = QHBoxLayout(page)
    # 16 at the sides, a spacing step, not 24: the column is centred and capped at 960, so the sides
    # only show on a narrow window, where Large text's four Open on choices needed the room.
    around.setContentsMargins(SPACING[3], 24, SPACING[3], SECTION_GAP_BELOW)
    column = QWidget()
    column.setObjectName("settingsRow")
    column.setMaximumWidth(SETTINGS_COLUMN)
    box = QVBoxLayout(column)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(14)
    name = QLabel(title)
    name.setObjectName("settingsTitle")
    box.addWidget(name)
    for card in cards:
        box.addWidget(card)
    box.addStretch(1)
    # Centred: the column takes the room up to its widest, and what is left is shared either side.
    around.addStretch(1)
    around.addWidget(column, 1000)
    around.addStretch(1)
    return page


class LookPicker(Choices):
    """Look as "Light | Dark | System", with every other look as a small picture of a week in its own
    colours under them, and the student's own looks after those (decision 24 of 0.17; Grok Bot's
    0.17.0 audit, A10 and T15). To the code that reads it, one control whose choices are every look."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.setObjectName(name)
        bare(self)
        standard, experimental = look_menu_items()
        looks = [(label, look_menu_token(kind, look)) for look, label, kind in (*standard, *experimental)]
        main = [look_menu_token("pack", pack) for pack in MAIN_LOOKS]
        ordered = sorted(looks, key=lambda item: main.index(item[1]) if item[1] in main else len(main))
        for label, token in ordered:
            self._remember(label, token)
        self._tile_width = LOOK_TILE
        self.main = Segmented(tuple(item for item in ordered if item[1] in main), f"{name}Main")
        self.main.setAccessibleName("Look")
        self.more = CardGrid(LOOK_TILE + CARD_WIDTH_PAD, CARD_GAP)
        self.more.setObjectName(f"{name}More")
        self.more.setAccessibleName(MORE_LOOKS)
        self.more.set_cards([self._tile(label, token, []) for label, token in ordered if token not in main])
        self.yours = CardGrid(LOOK_TILE + CARD_WIDTH_PAD, CARD_GAP)
        self.yours.setObjectName(f"{name}Yours")
        self.yours.setAccessibleName(YOUR_LOOKS)
        self.worn = QLabel()
        self.worn.setObjectName("prefLookWorn")
        self.worn.setVisible(False)
        self.yours_heading = QLabel(YOUR_LOOKS)
        self.yours_heading.setObjectName("settingsCardNote")
        self.yours_heading.setVisible(False)
        self.yours.setVisible(False)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        box.addWidget(self.main, 0, Qt.AlignmentFlag.AlignLeft)
        caption = QLabel(MORE_LOOKS)
        caption.setObjectName("settingsCardNote")
        box.addWidget(caption)
        box.addWidget(self.more)
        box.addWidget(self.yours_heading)
        box.addWidget(self.yours)
        box.addWidget(self.worn)
        self.main.currentIndexChanged.connect(self._picked_main)
        self._built_in = self.count()
        self._unsaved: str | None = None
        self._saved: list[dict] = []

    def _tile(self, label: str, token: str, saved: list[dict]) -> ChoiceCard:
        """A look as a picture of a week in its colours over its name; one click, or Space or Enter,
        wears it."""
        card = ChoiceCard(label, "", self._tile_width)
        card.setProperty("token", token)
        pack, look = look_choice(token, saved)
        card.set_picture(look_preview(pack, look, self._tile_width))
        card.chosen.connect(self._picked_tile)
        return card

    def set_text_scale(self, scale: float) -> None:
        """The pictures as much wider as the text is larger, so a name keeps its one line under its
        picture: at Large text "High contrast" wrapped under a picture of the normal width."""
        width = round(LOOK_TILE * scale)
        if width == self._tile_width:
            return
        self._tile_width = width
        for grid in (self.more, self.yours):
            for card in grid.cards:
                card.set_width(width)
                pack, look = look_choice(card.property("token"), self._saved)
                card.set_picture(look_preview(pack, look, width))
            grid.set_card_width(width + CARD_WIDTH_PAD)

    def set_saved(self, looks: list[dict]) -> None:
        """The student's saved looks, after the others, each chosen by its name."""
        del self._texts[self._built_in :], self._data[self._built_in :]
        self._saved = looks
        tiles = []
        for look in looks:
            self._remember(look["name"], SAVED_LOOK + look["name"])
            tiles.append(self._tile(look["name"], SAVED_LOOK + look["name"], looks))
        self.yours.set_cards(tiles)
        self.yours_heading.setVisible(bool(tiles))
        self.yours.setVisible(bool(tiles))

    def show_unsaved(self, name: str | None) -> None:
        """A look of the student's own that is worn and not saved has no picture, so it is named
        under the pictures."""
        self._unsaved = name
        self._say_worn()

    def first_line(self) -> QWidget:
        """What the Look label sits beside: the three looks, not the middle of both lines."""
        return self.main

    def _picked_main(self, index: int) -> None:
        if index >= 0:
            self.setCurrentIndex(self.findData(self.main.itemData(index)))

    def _picked_tile(self) -> None:
        self.setCurrentIndex(self.findData(self.sender().property("token")))

    def _say_worn(self) -> None:
        """Light, Dark and System show no choice while another look is worn, so the look is named
        where the pictures are, as well as marked on its own."""
        name = self.currentText() or (UNSAVED_LOOK.format(name=self._unsaved) if self._unsaved else "")
        elsewhere = bool(name) and self.main.currentIndex() < 0
        self.worn.setText(WEARING.format(name=name) if elsewhere else "")
        self.worn.setVisible(elsewhere)

    def _show(self, index: int) -> None:
        token = self.itemData(index) if index >= 0 else None
        self.main.blockSignals(True)
        self.main.setCurrentIndex(self.main.findData(token))
        self.main.blockSignals(False)
        for card in (*self.more.cards, *self.yours.cards):
            card.select(card.property("token") == token)
        self._say_worn()


class FocusPanel(QWidget):
    quick_requested = Signal()
    screen_requested = Signal()
    finished_requested = Signal()
    break_requested = Signal()
    more_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("focusPanel")
        layout = QVBoxLayout(self)
        self.now_next = QLabel()
        self.now_next.setObjectName("nowNext")
        self.now_next.setWordWrap(True)
        self.now_next.setFont(time_font(self.now_next.font()))
        layout.addWidget(self.now_next)
        # A running timer is a card: what it is for, one sentence on what to do, and its buttons, of
        # which only the next step is filled. Three filled buttons in a row read as three equal asks.
        self.card = QFrame()
        self.card.setObjectName("dialogCard")
        card_box = QVBoxLayout(self.card)
        card_box.setContentsMargins(16, 12, 16, 12)
        card_box.setSpacing(6)
        layout.addWidget(self.card)
        # One status line, not four stacked labels. Over a design of its own the timer used to
        # arrive as loose text: the homework, then "Focus session", then "30:00", each on its own row.
        status = QHBoxLayout()
        self.task = QLabel()
        self.task.setObjectName("focusTask")
        self.phase = QLabel()
        self.phase.setObjectName("focusPhase")
        self.time = QLabel()
        self.time.setObjectName("focusTime")
        for widget in (self.task, self.phase, self.time):
            status.addWidget(widget)
        status.addStretch(1)
        card_box.addLayout(status)
        # Pause, Skip and Finish are on the focus screen, where the timer is large; here the running
        # timer is one line and a way to that screen.
        self.screen = QPushButton("Focus screen")
        self.screen.setObjectName("focusScreenOpen")
        # Outlined: filled, and full width in the rail, it was louder than Add (Grok Bot's 0.17.0
        # audit, X8).
        self.screen.setProperty("outline", True)
        self.screen.setToolTip("Show the timer on its own, large. F")
        self.screen.clicked.connect(self.screen_requested.emit)
        status.insertWidget(status.count() - 1, self.screen)
        self.note = QLabel()
        self.note.setObjectName("cardNote")
        self.note.setWordWrap(True)
        card_box.addWidget(self.note)
        controls = QHBoxLayout()
        self.quick = QPushButton("Quick focus")
        self.quick.setObjectName("focusQuick")
        self.quick.clicked.connect(self.quick_requested.emit)
        self.quick.setProperty("quiet", True)
        controls.addWidget(self.quick)
        # Without this the button takes the window's width over a layout of its own. It keeps its
        # natural width and the row fills with space instead.
        controls.addStretch(1)
        card_box.addLayout(controls)
        choices = QHBoxLayout()
        self.finished = QPushButton("Finished")
        self.finished.setObjectName("focusFinished")
        self.finished.clicked.connect(self.finished_requested.emit)
        self.take_break = QPushButton("Take a break")
        self.take_break.setObjectName("focusBreak")
        self.take_break.clicked.connect(self.break_requested.emit)
        self.more_min = QComboBox()
        self.more_min.setObjectName("focusMoreMin")
        self.more = QPushButton("Need more time")
        self.more.setObjectName("focusMoreAdd")
        self.more.clicked.connect(self._emit_more)
        self.take_break.setProperty("quiet", True)
        self.more.setProperty("quiet", True)
        for widget in (self.finished, self.take_break, self.more_min, self.more):
            choices.addWidget(widget)
        choices.addStretch(1)
        card_box.addLayout(choices)
        self._rows = (status, choices)
        self._margins = layout.contentsMargins()
        self._compact = False
        self._ended_widgets = (self.finished, self.take_break, self.more_min, self.more)
        # Nothing to show until a timer runs, and blank rows cost the calendar height. The homework to
        # start one on is in Week's side.
        for widget in (self.card, self.task, self.phase, self.time, self.screen):
            widget.setVisible(False)

    def _emit_more(self) -> None:
        self.more_requested.emit(int(self.more_min.currentData() or 0))

    def set_compact(self, compact: bool) -> None:
        """Stacked, for the top of Today's app's rail: its parts one under another, not in a row
        wider than the rail."""
        direction = QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        for row in self._rows:
            if row.direction() != direction:
                row.setDirection(direction)
        self.layout().setContentsMargins(QMargins() if compact else self._margins)
        self._compact = compact

    def show_now_next(self, text: str) -> None:
        self.now_next.setText(text)
        self.now_next.setVisible(bool(text))

    def set_state(self, session) -> None:
        self.show_now_next(session.now_next_text())
        state = session.focus
        ended = state is not None and state.get("phase") == "ended"
        self.task.setText("" if state is None else state.get("title") or "")
        self.phase.setText("" if state is None else FOCUS_PHASE_LABEL.get(state.get("phase"), ""))
        if state is None:
            self.time.setText("")
        else:
            self.time.setText(format_countdown(remaining_ms(state, session.now_ms())))
        # Once the timer ends, the next step is Finished or a break, not the large timer.
        self.screen.setVisible(state is not None and not ended)
        assignment = None if state is None else session.assignments.get(state.get("assignmentId"))
        choices = more_time_choices(int((assignment or {}).get("estimate_min") or 0)) if ended else []
        self.more_min.clear()
        for minutes in choices:
            self.more_min.addItem(length_label(minutes), minutes)
        for widget in self._ended_widgets:
            widget.setVisible(ended)
        self.card.setVisible(state is not None)
        self.note.setText(FOCUS_ENDED_NOTE if ended else FOCUS_RUNNING_NOTE)
        # A running timer is one line: its name, time and way to the focus screen. Now and Next, Quick
        # focus and the sentence on what to do made three strips over the week (Grok Bot's 0.17.0
        # audit, X3); the sentence is the time's tooltip, and what to do next is said once it ends.
        running = state is not None and not ended
        self.note.setVisible(ended)
        self.time.setToolTip(FOCUS_RUNNING_NOTE if running else "")
        self.quick.setVisible(not running)
        if running:
            self.now_next.setVisible(False)
        self.more.setEnabled(bool(choices))
        for label in (self.task, self.phase, self.time):
            label.setVisible(bool(label.text()))


class SettingsPage(QWidget):
    """Settings fill the window: the sections listed on the left, each one's settings in cards on the
    right. Settings apply as they change: there is no OK to press and no Cancel to undo with. The page
    says a choice changed; the window shows it and saves it. Done or Esc goes back to the week."""

    changed = Signal()
    closed = Signal()
    account_requested = Signal()
    availability_requested = Signal()
    updates_requested = Signal()
    setup_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None,
        preferences: dict,
        look: dict,
        reminder_limits: dict,
        week_layout: dict | None = None,
        saved_looks: list[dict] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Settings")
        self._preferences = deepcopy(preferences)
        self._look = sanitize_look(look)
        chosen_layout = sanitize_layout(week_layout)
        self._alarms = [deepcopy(item) for item in preferences.get("alarms") or []]
        self._pack = known_pack(preferences.get("theme_pack"))
        # The looks the student saved, which the window keeps with the device's look.
        self.saved_looks = sanitize_saved(saved_looks)
        self.look = LookPicker("prefTheme")
        self._show_look()
        swatches = tuple((ACCENT_LABELS.get(name, name.title()), name) for name in ACCENTS)
        self.accent = Swatches(swatches, "prefAccent")
        index = self.accent.findData(preferences.get("accent") or "default")
        self.accent.setCurrentIndex(max(0, index))
        # The account's accent, kept apart from the swatches, which show a custom look's own while it
        # is worn.
        self._accent_chosen = self.accent.currentData()
        self.accent.currentIndexChanged.connect(self._choose_accent)
        self.accent_note = _note(OWN_ACCENT_NOTE, "settingsCardNote")
        # The width of the swatches' column, so the line under them is one line.
        self.accent_note.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.customise = _page_button(f"{CUSTOMISE}…", "prefCustomise")
        self.customise.setToolTip(CUSTOMISE_TIP)
        self.customise.clicked.connect(self._open_customise)
        self.accent_chips = Switch("Use the accent on category chips")
        self.accent_chips.setObjectName("prefAccentChips")
        self.accent_chips.setChecked(bool(preferences.get("accent_chips")))
        # How much the app moves (decision 33 of 0.17). Until the student picks a level it shows the
        # look's own and follows the look, so choosing Paper here starts it at Reduce.
        self.motion = Segmented(MOTION_CHOICES, "prefMotion")
        self._motion_chosen = preferences.get("motion")
        self._show_motion(self._look)
        self.knobs: dict[str, Segmented] = {}
        self.fine_host = QWidget()
        self.fine_host.setObjectName("prefFineHost")
        fine_form = Form(self.fine_host)
        self._fine_form = fine_form
        fine_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        fine_form.setContentsMargins(0, 0, 0, 0)
        for knob, values in LOOK_KNOBS.items():
            labelled = tuple((KNOB_VALUE_LABELS[value], value) for value in values)
            box = Segmented(labelled, "look" + knob.title())
            self.knobs[knob] = box
            fine_form.addRow(KNOB_LABELS.get(knob, knob.title()), box)
        self.own_look_note = _note("", "settingsCardNote")
        fine_form.addRow(self.own_look_note)
        self.fine_tune = Switch(FINE_TUNE_LOOK)
        self.fine_tune.setObjectName("prefFineTune")
        self.fine_tune.setChecked(bool(self._look.get("knobs")))
        self.fine_host.setVisible(self.fine_tune.isChecked())
        self.fine_tune.toggled.connect(self.fine_host.setVisible)
        self.look.currentIndexChanged.connect(self._apply_look_menu)
        self.look.currentIndexChanged.connect(lambda _index: self._show_motion(self.look_choice()))
        self.motion.currentIndexChanged.connect(self._choose_motion)
        self.work = QSpinBox()
        self.work.setRange(1, 180)
        self.work.setSingleStep(1)
        self.work.setValue(int(preferences.get("timer_work_min") or 30))
        self.break_min = QSpinBox()
        self.break_min.setRange(1, 60)
        self.break_min.setSingleStep(1)
        self.break_min.setValue(int(preferences.get("timer_break_min") or 15))
        self.long_break = QSpinBox()
        self.long_break.setRange(1, 120)
        self.long_break.setSingleStep(1)
        self.long_break.setValue(int(preferences.get("timer_long_break_min") or 30))
        self.preset_timer = QComboBox()
        self.preset_timer.setObjectName("timerPreset")
        self.preset_timer.addItem("Custom", None)
        for item in TIMER_PRESETS:
            self.preset_timer.addItem(item["label"], item["id"])
        chosen = None
        for item in TIMER_PRESETS:
            if (
                item["timer_work_min"] == self.work.value()
                and item["timer_break_min"] == self.break_min.value()
                and item["timer_long_break_min"] == self.long_break.value()
            ):
                chosen = item["id"]
                break
        self.preset_timer.setCurrentIndex(max(0, self.preset_timer.findData(chosen)))
        self.preset_timer.activated.connect(self._apply_timer_preset)
        self.long_every = QSpinBox()
        self.long_every.setObjectName("prefLongEvery")
        self.long_every.setRange(2, 12)
        self.long_every.setSuffix(" focus sessions")
        self.long_every.setValue(int(preferences.get("timer_long_break_every") or 4))
        self.auto_split = Switch("Split long homework into focus sessions")
        self.auto_split.setObjectName("prefAutoSplit")
        self.auto_split.setChecked(bool(preferences.get("auto_split_pomodoro")))
        self.reminders = Switch("Remind me before each block starts")
        self.reminders.setObjectName("prefReminders")
        self.reminders.setChecked(preferences.get("reminders_enabled", True) is not False)
        self.lead = QSpinBox()
        self.lead.setObjectName("prefLead")
        self.lead.setRange(0, 120)
        self.lead.setSuffix(" min")
        lead = preferences.get("reminder_lead_min")
        self.lead.setValue(5 if lead is None else int(lead))
        self.reminder_sound = Switch("Play a sound")
        self.reminder_sound.setObjectName("prefReminderSound")
        self.reminder_sound.setChecked(preferences.get("reminder_sound", True) is not False)
        self.dnd_override = Switch("Leave reminders on screen")
        self.dnd_override.setObjectName("prefDndOverride")
        self.dnd_override.setChecked(bool(preferences.get("reminder_dnd_override")))
        self.volume = QSpinBox()
        self.volume.setObjectName("prefAlertVolume")
        self.volume.setRange(0, 100)
        self.volume.setSuffix("%")
        self.volume.setValue(int(preferences.get("alert_volume", 80)))
        self.end_chime = Switch("Chime when a session ends")
        self.end_chime.setObjectName("prefEndChime")
        self.end_chime.setChecked(bool(preferences.get("end_chime")))
        self.tray = Switch("Keep running when I close the window")
        self.tray.setObjectName("prefTray")
        self.tray.setChecked(preferences.get("tray_notifications", True) is not False)
        self.start_at_login = Switch("Start FlexWeek when I log in")
        self.start_at_login.setObjectName("prefStartAtLogin")
        self.start_at_login.setChecked(autostart.enabled_on_disk())
        self.preferred_view = Segmented(PREFERRED_VIEWS, "prefPreferredView")
        self.preferred_view.setCurrentIndex(
            max(0, self.preferred_view.findData(preferences.get("preferred_view")))
        )
        self.clock = Segmented((("24-hour", True), ("12-hour", False)), "prefClock")
        self.clock.setCurrentIndex(0 if preferences.get("clock_24h", True) is not False else 1)
        self.spotify = QLineEdit(preferences.get("default_spotify_url") or "")
        self.spotify.setObjectName("prefSpotify")
        self.spotify.setPlaceholderText("Paste a Spotify link")
        self.spotify.setCursorPosition(0)
        # One sound for reminders, the end of a focus session and new alarms.
        self.alarm_tone = QComboBox()
        self.alarm_tone.setObjectName("prefAlarmTone")
        for name in SOUNDS:
            self.alarm_tone.addItem(ALARM_TONE_LABELS.get(name, name.title()), name)
        chosen_tone = preferences.get("alarm_tone") or FALLBACK
        self.alarm_tone.setCurrentIndex(max(0, self.alarm_tone.findData(chosen_tone)))
        self.play_tone = QPushButton("Play")
        self.play_tone.setObjectName("prefPlayTone")
        self.play_tone.setProperty("quiet", True)
        self.play_tone.clicked.connect(self._play_tone)
        self.tone_note = QLabel(SPOTIFY_TONE_NOTE)
        self.tone_note.setObjectName("prefToneNote")
        self.tone_note.setWordWrap(True)
        self._tone_bell = Bell(self)
        self._spotify_player = SpotifyPlayer(self)
        # The design first, since it decides what the rest of the page offers; then its colours, the
        # day screen, and what applies to every screen last.
        self.layout_sections = [
            LayoutSection(slot, role, title, blurb, chosen_layout, self._pack)
            for slot, role, title, blurb in SLOTS
        ]
        main_section, day_section = self.layout_sections
        self.colours_card, appear = _card("Colours")
        appear.addRow("Look", self.look)
        appear.addRow(OWN_LOOK, self.customise)
        appear.addRow("Accent", self.accent)
        appear.addRow("", self.accent_note)
        appear.addRow(self.accent_chips)
        appear.addRow(self.fine_tune)
        appear.addRow(self.fine_host)
        self._colours_form = appear
        self._show_look_settings()
        self._fit_look_cards()
        self.changed.connect(self._fit_look_cards)
        everywhere_card, everywhere = _card("Every screen")
        everywhere.addRow("Animations", self.motion)
        # Colours first: it is what most students change, and below every design card it was not found
        # (Grok Bot's 0.17.0 audit, X1 and A11).
        appearance = _section_page(
            "Appearance & layout", (self.colours_card, main_section, day_section, everywhere_card)
        )
        planning_card, planning_form = _card("How homework gets a time")
        self.planning_style = QButtonGroup(planning_card)
        chosen_style = preferences.get("planning_style") or "suggest"
        for value, text, note in PLANNING_STYLES:
            button = QRadioButton(text)
            button.setObjectName(f"prefPlanning-{value}")
            button.setChecked(value == chosen_style)
            self.planning_style.addButton(button)
            button.setProperty("style", value)
            planning_form.addRow(button)
            hint = QLabel(note)
            hint.setObjectName("prefPlanningNote")
            hint.setWordWrap(True)
            # Under its choice's words, not under the round button.
            hint.setContentsMargins(26, 0, 0, 4)
            planning_form.addRow(hint)
        where_card, where_form = _card(
            "Study times", "Preferred study times, including ones kept for one subject, are in Availability."
        )
        open_availability = _page_button("Availability…", "prefsAvailability")
        open_availability.clicked.connect(self.availability_requested.emit)
        where_form.addRow(open_availability)
        drag_card, drag_form = _card("Dragging", DRAG_STEP_QUESTION)
        self.drag_step = Segmented(
            tuple((f"{minutes} minutes", minutes) for minutes, _words in DRAG_STEP_CHOICES), "prefDragStep"
        )
        chosen_step = drag_step(preferences.get("drag_step_min"))
        self.drag_step.setCurrentIndex(max(0, self.drag_step.findData(chosen_step)))
        drag_form.addRow("Steps", self.drag_step)
        planning = _section_page("Planning", (planning_card, where_card, drag_card))
        focus_card, focus_form = _card("Focus timer")
        boxes = (self.work, self.break_min, self.long_break, self.long_every)
        self.focus_steppers = [Stepper(box) for box in boxes]
        work, rest, long_rest, every = self.focus_steppers
        focus_form.addRow("Focus minutes", work)
        focus_form.addRow("Break minutes", rest)
        focus_form.addRow("Long break minutes", long_rest)
        focus_form.addRow("Timer preset", self.preset_timer)
        focus_form.addRow("Long break after", every)
        focus_form.addRow(self.auto_split)
        focus = _section_page("Focus", (focus_card,))
        reminders_card, alerts_form = _card("Reminders")
        alerts_form.addRow(self.reminders)
        # Everything a reminder does, in one box that greys as one while reminders are off. The switch
        # was one unticked box among controls that looked live.
        self.reminder_controls = QWidget()
        self.reminder_controls.setObjectName("prefReminderControls")
        reminder_form = Form(self.reminder_controls)
        reminder_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        reminder_form.setContentsMargins(0, 0, 0, 0)
        reminder_form.addRow("How long before", Stepper(self.lead))
        reminder_form.addRow(self.reminder_sound)
        tone_row = QHBoxLayout()
        tone_row.addWidget(self.alarm_tone)
        tone_row.addWidget(self.play_tone)
        tone_row.addStretch(1)
        reminder_form.addRow("Sound", tone_row)
        reminder_form.addRow("Spotify link", self.spotify)
        reminder_form.addRow(self.tone_note)
        reminder_form.addRow(self.dnd_override)
        reminder_form.addRow(_note(DND_NOTE, "prefDndNote"))
        self.block_song_note = _note(BLOCK_SONG_NOTE, "prefBlockSongNote")
        reminder_form.addRow(self.block_song_note)
        self._alerts_form = reminder_form
        alerts_form.addRow(self.reminder_controls)
        self.reminder_controls.setEnabled(self.reminders.isChecked())
        self.reminders.toggled.connect(self.reminder_controls.setEnabled)
        alarms_card, alarms_form = _card("Alarms", ALARM_NOTE)
        self.alarm_empty = QLabel("No alarms yet.")
        self.alarm_empty.setObjectName("alarmEmpty")
        alarms_form.addRow(self.alarm_empty)
        self.alarm_list = QListWidget()
        self.alarm_list.setObjectName("alarmList")
        # As tall as its alarms, up to about three, and never wider than the page: a line that does not
        # fit wraps rather than hiding the days behind a sideways scroll.
        self.alarm_list.setSizeAdjustPolicy(QListWidget.SizeAdjustPolicy.AdjustToContents)
        self.alarm_list.setMaximumHeight(ALARM_LIST_MAX_HEIGHT)
        self.alarm_list.setWordWrap(True)
        self.alarm_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.alarm_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        alarms_form.addRow(self.alarm_list)
        self._alarms_form = alarms_form
        self.alarm_name = QLineEdit()
        self.alarm_name.setObjectName("alarmName")
        self.alarm_name.setPlaceholderText("Alarm name")
        # A usual time to wake, not midnight (T21 of the 0.17.0 audit).
        self.alarm_time = ClockField(QTime(7, 0))
        self.alarm_time.setObjectName("alarmTime")
        self.alarm_sound = QComboBox()
        self.alarm_sound.setObjectName("alarmSound")
        self.alarm_name.setMinimumWidth(120)
        self.alarm_sound.setMinimumContentsLength(8)
        for name in SOUNDS:
            self.alarm_sound.addItem("Spotify link" if name == "spotify" else name.title(), name)
        # A line each: with every dropdown as wide as the page's widest, name, time and sound side by
        # side were wider than the page at large text.
        alarms_form.addRow("New alarm", self.alarm_name)
        alarms_form.addRow("Rings at", self.alarm_time)
        alarms_form.addRow("Sound", self.alarm_sound)
        self.alarm_spotify = QLineEdit()
        self.alarm_spotify.setObjectName("alarmSpotify")
        self.alarm_spotify.setPlaceholderText("Optional")
        alarms_form.addRow("Spotify link", self.alarm_spotify)
        # The days as pills on one line, as everywhere else. As check boxes they took two rows, Monday
        # to Thursday and then Friday to Sunday (T21 of the 0.17.0 audit).
        self.alarm_day_picker = DayPicker(range(5), "alarmDay")
        self.alarm_days = self.alarm_day_picker.buttons
        add_alarm = _page_button("Add alarm", "addAlarm")
        add_alarm.clicked.connect(self._add_alarm)
        self.remove_alarm = _page_button("Remove alarm", "removeAlarm")
        self.remove_alarm.clicked.connect(self._remove_alarm)
        alarms_form.addRow("Days", self.alarm_day_picker)
        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addWidget(add_alarm)
        button_row.addWidget(self.remove_alarm)
        button_row.addStretch(1)
        alarms_form.addRow(button_row)
        all_card, all_form = _card("All alerts")
        all_form.addRow("Volume", Stepper(self.volume))
        all_form.addRow(self.end_chime)
        all_form.addRow(self.tray)
        all_form.addRow(_note(TRAY_NOTE, "prefTrayNote"))
        keys = ("spotify", "duplicate")
        limits = QLabel(" ".join(reminder_limits.get(key, "") for key in keys))
        limits.setWordWrap(True)
        limits.setObjectName("reminderLimits")
        all_form.addRow(limits)
        alerts = _section_page("Alerts", (reminders_card, alarms_card, all_card))
        start_card, start_form = _card("Starting FlexWeek")
        start_form.addRow(self.start_at_login)
        start_form.addRow("Open on", self.preferred_view)
        start_form.addRow("Clock", self.clock)
        computer_card, computer_form = _card("Account, setup and updates")
        open_account = _page_button("Manage account…", "prefsAccount")
        open_account.setToolTip("Change your password, export or import, or delete the account.")
        open_account.clicked.connect(self.account_requested.emit)
        computer_form.addRow("Account", open_account)
        run_setup = _page_button("Run setup again", "prefsRunSetup")
        run_setup.setToolTip("Style, your week, homework time and reminders, filled in as they are now.")
        run_setup.clicked.connect(self.setup_requested.emit)
        computer_form.addRow("Setup", run_setup)
        update_col = QVBoxLayout()
        version = QLabel(f"FlexWeek {VERSION}")
        version.setObjectName("prefsVersion")
        check_updates = _page_button("Check for updates", "prefsCheckUpdates")
        check_updates.clicked.connect(self.updates_requested.emit)
        update_col.addWidget(version)
        update_col.addWidget(check_updates)
        computer_form.addRow("Updates", update_col)
        computer = _section_page("This computer", (start_card, computer_card))
        rail = QWidget()
        rail.setObjectName("settingsRail")
        rail.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        rail_box = QVBoxLayout(rail)
        rail_box.setContentsMargins(0, 0, 0, 0)
        rail_box.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("prefsNav")
        self.nav.setAccessibleName("Settings sections")
        for name in SECTIONS:
            self.nav.addItem(name)
        # Restyled with the look: the icons are drawn in its colours, and the fields measured in its font.
        self._redress = QTimer(self)
        self._redress.setSingleShot(True)
        self._redress.setInterval(0)
        self._redress.timeout.connect(self._dress)
        rail_box.addWidget(self.nav, 1)
        self.stack = QStackedWidget()
        self.stack.setObjectName("prefsStack")
        for page in (appearance, planning, focus, alerts, computer):
            area = QScrollArea()
            area.setObjectName("settingsScroll")
            overlay_scroll_bars(area)
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            area.setWidget(page)
            self.stack.addWidget(area)
        # Set by the window from the Animations setting.
        self.motion_level = "off"
        self.nav.currentRowChanged.connect(self._show_section)
        self.nav.setCurrentRow(0)
        footer = QWidget()
        footer.setObjectName("settingsFooter")
        footer_line = QHBoxLayout(footer)
        footer_line.setContentsMargins(32, 12, 32, 16)
        self.save_state = QLabel(SAVE_STATE)
        self.save_state.setObjectName("prefsSaveState")
        self.save_state.setWordWrap(True)
        footer_line.addWidget(self.save_state, 1)
        self.done = QPushButton("Done")
        self.done.setObjectName("settingsDone")
        self.done.setToolTip("Back to your week (Esc)")
        self.done.clicked.connect(self.close_page)
        footer_line.addWidget(self.done)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.stack, 1)
        column.addWidget(footer)
        # Settings, and over them the look editor while it is open.
        self.body = QWidget()
        outer = QHBoxLayout(self.body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(rail)
        outer.addLayout(column, 1)
        self._screens = QStackedLayout(self)
        self._screens.addWidget(self.body)
        self.editor: LookEditor | None = None
        self._render_alarms()
        self._split_lengths(self.auto_split.isChecked(), say=False)
        self.auto_split.toggled.connect(self._split_lengths)
        for box in (self.work, self.break_min, self.long_break):
            box.editingFinished.connect(self._round_if_splitting)
        self.spotify.editingFinished.connect(self._check_spotify)
        # Every choice says it changed. Connected last, so building the page says nothing, and after
        # the handlers above, so a look or a timer preset has filled in its knobs by then.
        choices = (
            self.look, self.accent, self.preferred_view, self.clock, self.motion, self.alarm_tone,
            self.drag_step,
        )
        for box in (*choices, *self.knobs.values()):
            box.currentIndexChanged.connect(self._announce)
        for spin in (self.work, self.break_min, self.long_break, self.long_every, self.lead, self.volume):
            spin.valueChanged.connect(self._announce)
        for check in (
            self.accent_chips,
            self.auto_split,
            self.reminders,
            self.reminder_sound,
            self.dnd_override,
            self.end_chime,
            self.tray,
            self.start_at_login,
        ):
            check.toggled.connect(self._announce)
        self.planning_style.buttonToggled.connect(self._style_toggled)
        self.spotify.editingFinished.connect(self.changed.emit)
        for section in self.layout_sections:
            section.changed.connect(self.changed.emit)
            section.changed.connect(self._show_what_applies)
        self._show_what_applies()
        self.alarm_tone.currentIndexChanged.connect(self._follow_tone)
        self._follow_tone()

    def say(self, text: str) -> None:
        """What the footer says: anything that needs reading, and otherwise the one standing sentence."""
        self.save_state.setText(SAVE_STATE if text in ROUTINE_STATUS else text)

    def _follow_tone(self, *_index: object) -> None:
        """New alarms start with the chosen sound, and the note says what Spotify means for the rest."""
        tone = self.alarm_tone.currentData()
        for row in (self.spotify, self.tone_note):
            self._alerts_form.setRowVisible(row, tone == "spotify")
        index = self.alarm_sound.findData(tone)
        if index >= 0:
            self.alarm_sound.setCurrentIndex(index)

    def _play_tone(self) -> None:
        tone = self.alarm_tone.currentData()
        if tone == "spotify":
            link = self._spotify_link()
            if link and self._spotify_player.play(link):
                return
            tone = FALLBACK
        if not self._tone_bell.once(str(tone), self.volume.value()):
            self.save_state.setText(NO_SOUND)

    def _show_what_applies(self) -> None:
        """Only the settings that change the chosen views. Surface, Corners and Blocks stayed on screen
        for every design while only Today's app read them, so a student changed them in Bento and saw
        nothing happen. Look and Accent stay: they dress the top bar and every window in any design."""
        main = next(section for section in self.layout_sections if section.slot == "main")
        todays_app = main.chosen() == "classic"
        for knob in TODAYS_APP_KNOBS:
            self._fine_form.setRowVisible(self.knobs[knob], todays_app)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._dress()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.Type.StyleChange, QEvent.Type.FontChange) and self.isVisible():
            self._redress.start()

    def shown_palette(self) -> dict:
        """The colours on screen, as the window works them out from what this page holds."""
        system_dark = QGuiApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128
        return resolved_palette(self._pack, system_dark, self.look_choice(), self._accent_chosen)

    def _dress(self) -> None:
        """What the style sheet cannot draw: the sections' icons and the accent swatches in the look's
        colours, and one width for each kind of field in the look's font. Then the list fits its longest
        name; at large text a fixed width cut "Appearance & layout" off."""
        palette = self.shown_palette()
        self.accent.set_colours({name: ACCENT_COLORS[name][palette["axis"]] for name in ACCENTS})
        size = 16
        self.nav.setIconSize(QSize(size, size))
        ratio = self.devicePixelRatioF()
        for row, name in enumerate(SECTION_ICONS):
            made = QIcon()
            made.addPixmap(icon_pixmap(name, palette["muted"], size, ratio), QIcon.Mode.Normal)
            made.addPixmap(icon_pixmap(name, palette["text"], size, ratio), QIcon.Mode.Selected)
            self.nav.item(row).setIcon(made)
        # Section by section: a dropdown on Alerts need not make Appearance's wider than its page.
        for index in range(self.stack.count()):
            even_fields(self.stack.widget(index))
            even_labels(self.stack.widget(index))
        # Once the steppers have their look: before it, their − and + had no width yet.
        QTimer.singleShot(0, self, self._even_focus)
        margins = self.nav.contentsMargins()
        self.nav.setFixedWidth(
            self.nav.sizeHintForColumn(0) + margins.left() + margins.right() + 2 * self.nav.frameWidth()
            + PREFS_NAV_PAD
        )

    def _even_focus(self) -> None:
        """Timer preset as wide as the − value + fields above and below it (T20 of the 0.17.0 audit);
        when its longest name is wider, every box widens with it instead."""
        stepped = self.focus_steppers[0].sizeHint().width()
        width = max(self.preset_timer.sizeHint().width(), stepped)
        for stepper in self.focus_steppers:
            stepper.box.setFixedWidth(stepper.box.width() + width - stepped)
        self.preset_timer.setFixedWidth(width)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close_page()
            event.accept()
            return
        super().keyPressEvent(event)

    def _show_section(self, row: int) -> None:
        """The section picked, sliding in from the side the student moved toward in the list."""
        page = self.stack.widget(row)
        if page is None:
            return
        switch_page(self.stack, page, self.motion_level, 1 if row > self.stack.currentIndex() else -1)

    def _announce(self, *_value: object) -> None:
        """Takes and drops the value a box sends. Wired straight to `changed.emit`, that value made
        every emit raise inside Qt, which swallows it, so nothing showed until Settings closed."""
        self.changed.emit()
        if self.isVisible():
            self._redress.start()

    def _style_toggled(self, _button: object, on: bool) -> None:
        if on:
            self._announce()

    def close_page(self) -> None:
        """Closing is the end of any typing, so a length typed while splitting is on is rounded now,
        before the window saves what is left."""
        self._round_if_splitting()
        self.closed.emit()

    def _split_lengths(self, on: bool, say: bool = True) -> None:
        """The server refuses splitting with lengths off the 15-minute grid. There is no OK left to
        ask at, so turning splitting on rounds them, and says so, and they then step in 15s."""
        for box in (self.work, self.break_min, self.long_break):
            box.setSingleStep(SLOT_MIN if on else 1)
        if on and self._round_if_splitting() and say:
            self.save_state.setText(f"Focus lengths rounded to {SLOT_MIN} minutes, which splitting needs.")

    def _round_if_splitting(self) -> bool:
        if not self.auto_split.isChecked():
            return False
        moved = False
        for box, ceiling in ((self.work, 180), (self.break_min, 60), (self.long_break, 120)):
            snapped = snap_minutes(box.value(), 1, ceiling)
            if snapped != box.value():
                box.setValue(snapped)
                moved = True
        return moved

    def _lengths(self) -> tuple[int, int, int]:
        """What is saved. While splitting is on, a length typed halfway ("4" on the way to "45") is
        saved rounded, so a pause mid-number never sends the server a length it refuses."""
        values = (self.work.value(), self.break_min.value(), self.long_break.value())
        if not self.auto_split.isChecked():
            return values
        work, rest, long_rest = values
        return (snap_minutes(work, 1, 180), snap_minutes(rest, 1, 60), snap_minutes(long_rest, 1, 120))

    def _spotify_link(self) -> str | None:
        """The link to save: the one typed if it is a Spotify share link, else the one already saved."""
        typed = self.spotify.text().strip()
        if not typed:
            return None
        try:
            return valid_spotify_url(typed) or None
        except ValueError:
            return self._preferences.get("default_spotify_url") or None

    def _check_spotify(self) -> None:
        typed = self.spotify.text().strip()
        try:
            if typed:
                valid_spotify_url(typed)
        except ValueError:
            self.save_state.setText("That link was not saved. Use an https://open.spotify.com link.")

    def _apply_timer_preset(self, _index: int = 0) -> None:
        chosen = self.preset_timer.currentData()
        if chosen is None:
            return
        preset = next((item for item in TIMER_PRESETS if item["id"] == chosen), None)
        if preset is None:
            return
        self.work.setValue(preset["timer_work_min"])
        self.break_min.setValue(preset["timer_break_min"])
        self.long_break.setValue(preset["timer_long_break_min"])

    def _render_alarms(self) -> None:
        self.alarm_list.clear()
        for alarm in self._alarms:
            sound = str(alarm.get("sound") or FALLBACK)
            label = "Spotify" if sound == "spotify" else sound.title()
            off = "" if alarm.get("enabled", True) else " · off"
            when = f"Rings at {hhmm_text(str(alarm.get('time')))}, {ring_days(alarm.get('days') or [])}"
            self.alarm_list.addItem(f"{alarm.get('name')} · {label}{off}\n{when}")
        self._alarms_form.setRowVisible(self.alarm_list, bool(self._alarms))
        self._alarms_form.setRowVisible(self.alarm_empty, not self._alarms)
        # Nothing to remove until there is an alarm.
        self.remove_alarm.setVisible(bool(self._alarms))

    def _add_alarm(self) -> None:
        if len(self._alarms) >= 20:
            return
        days = [index for index, box in enumerate(self.alarm_days) if box.isChecked()]
        if not days:
            # An alarm on no days never rings, so say so rather than storing one that cannot fire.
            self.alarm_name.setPlaceholderText("Pick at least one day")
            return
        link = self.alarm_spotify.text().strip()
        if link:
            # valid_spotify_url raises on a bad link rather than returning None.
            try:
                link = valid_spotify_url(link) or ""
            except ValueError:
                self.alarm_spotify.setPlaceholderText("Use an https://open.spotify.com share link.")
                self.alarm_spotify.clear()
                return
        self._alarms.append(
            {
                "id": str(uuid4()),
                "name": self.alarm_name.text().strip() or "Alarm",
                "time": self.alarm_time.time().toString("HH:mm"),
                "days": days,
                "enabled": True,
                "sound": str(self.alarm_sound.currentData() or FALLBACK),
                "spotify_url": link or None,
            }
        )
        self.alarm_name.clear()
        self.alarm_spotify.clear()
        self._render_alarms()
        self.changed.emit()

    def _remove_alarm(self) -> None:
        row = self.alarm_list.currentRow()
        if row < 0 or row >= len(self._alarms):
            return
        self._alarms.pop(row)
        self._render_alarms()
        self.changed.emit()

    def updates(self) -> dict:
        work, rest, long_rest = self._lengths()
        return {
            "theme_pack": self._pack,
            "accent": self._accent_chosen,
            "timer_work_min": work,
            "timer_break_min": rest,
            "timer_long_break_min": long_rest,
            "reminders_enabled": self.reminders.isChecked(),
            "reminder_lead_min": self.lead.value(),
            "tray_notifications": self.tray.isChecked(),
            "default_spotify_url": self._spotify_link(),
            "alarms": deepcopy(self._alarms),
            # These eight could only be set from the web client, which stopped being the way most
            # students meet FlexWeek when the browser shell was retired.
            "timer_long_break_every": self.long_every.value(),
            "auto_split_pomodoro": self.auto_split.isChecked(),
            "reminder_sound": self.reminder_sound.isChecked(),
            "reminder_dnd_override": self.dnd_override.isChecked(),
            "alert_volume": self.volume.value(),
            "end_chime": self.end_chime.isChecked(),
            "accent_chips": self.accent_chips.isChecked(),
            "start_at_login": self.start_at_login.isChecked(),
            "preferred_view": self.preferred_view.currentData(),
            "clock_24h": bool(self.clock.currentData()),
            "motion": self._motion_chosen,
            "alarm_tone": self.alarm_tone.currentData(),
            "planning_style": self._planning_style(),
            "drag_step_min": drag_step(self.drag_step.currentData()),
        }

    def _show_motion(self, look: dict) -> None:
        shown = self._motion_chosen or look_motion(look)
        self.motion.blockSignals(True)
        self.motion.setCurrentIndex(max(0, self.motion.findData(shown)))
        self.motion.blockSignals(False)

    def _choose_motion(self, _index: int) -> None:
        self._motion_chosen = self.motion.currentData()

    def _choose_accent(self, _index: int) -> None:
        self._accent_chosen = self.accent.currentData()

    def _planning_style(self) -> str:
        checked = self.planning_style.checkedButton()
        return str(checked.property("style")) if checked is not None else "suggest"

    def _apply_look_menu(self) -> None:
        """Keep knobs moved by hand; the chosen look fills in only the rest."""
        before = self._built_in_look()
        parsed = parse_look_menu_token(self.look.currentData())
        if parsed is None:
            saved = self._saved_look(self.look.currentData())
            if saved is not None:
                self._look = wear(before, saved)
                self._show_look_settings()
            return
        kind, name = parsed
        if kind == "pack":
            self._pack = name
            preset = "default"
        else:
            preset = name
        self._look = sanitize_look({"preset": preset, "knobs": before["knobs"]})
        self._show_look_settings()

    def _built_in_look(self) -> dict:
        """The look chosen under Look and the knobs moved on it, which a custom look is worn over and
        keeps for when it is taken off. While one is worn the knobs show its values, not these."""
        if "custom" in self._look:
            return {key: value for key, value in self._look.items() if key != "custom"}
        preset = self._look["preset"]
        shown = {knob: box.currentData() for knob, box in self.knobs.items()}
        return {"preset": preset, "knobs": look_overrides(preset, shown)}

    def _show_look_settings(self) -> None:
        """The knobs and the accent as the look worn draws them. A look of the student's own sets
        them all, so while one is worn they cannot be changed here and a line says where they can."""
        custom = self._look.get("custom")
        bundle = effective_look(self._look)
        for knob, box in self.knobs.items():
            box.blockSignals(True)
            box.setCurrentIndex(max(0, box.findData(bundle[knob])))
            box.blockSignals(False)
            box.setEnabled(custom is None)
        accent = self._accent_chosen
        if custom is not None:
            accent = custom.get("accent", None if custom["base"] in OWN_ACCENT else accent)
        self.accent.blockSignals(True)
        self.accent.setCurrentIndex(self.accent.findData(accent))
        self.accent.blockSignals(False)
        self.accent.setEnabled(custom is None)
        if custom is None:
            self.accent_note.setText(OWN_ACCENT_NOTE)
        else:
            name = custom.get("name") or UNNAMED
            self.accent_note.setText(OWN_LOOK_ACCENT_NOTE.format(name=name))
            self.own_look_note.setText(OWN_LOOK_KNOBS_NOTE.format(name=name))
        own_accent = custom is None and self._look["preset"] in OWN_ACCENT
        self._colours_form.setRowVisible(self.accent_note, custom is not None or own_accent)
        self._fine_form.setRowVisible(self.own_look_note, custom is not None)

    def _fit_look_cards(self) -> None:
        self.look.set_text_scale(text_scale(self.look_choice()))

    def _saved_look(self, token: object) -> dict | None:
        if not isinstance(token, str) or not token.startswith(SAVED_LOOK):
            return None
        name = token.removeprefix(SAVED_LOOK)
        return next((look for look in self.saved_looks if look["name"] == name), None)

    def _show_look(self) -> None:
        """Look as worn: one of the looks, a saved look by its name, or nothing for a look of the
        student's own that is not saved."""
        self.look.set_saved(self.saved_looks)
        custom = self._look.get("custom")
        unsaved = custom is not None and custom not in self.saved_looks
        if custom is None:
            index = max(0, self.look.findData(look_menu_value(self._pack, self._look)))
        else:
            index = -1 if unsaved else self.look.findData(SAVED_LOOK + custom["name"])
        self.look.show_unsaved(custom.get("name") if unsaved else None)
        self.look.blockSignals(True)
        self.look.setCurrentIndex(index)
        self.look.blockSignals(False)

    def _open_customise(self) -> None:
        """The look editor over Settings (plan, "Customise", B). What it changes is worn at once, as
        every other setting here is."""
        if self.editor is not None:
            return
        self.editor = LookEditor(self, self.look_choice(), self.saved_looks, self._pack, self._accent_chosen)
        self.editor.worn.connect(self._wear_look)
        self.editor.closed.connect(self._close_customise)
        self._screens.addWidget(self.editor)
        self._screens.setCurrentWidget(self.editor)
        self.editor.back.setFocus()

    def _wear_look(self, look: dict, saved: list[dict]) -> None:
        self._look = sanitize_look(look)
        self.saved_looks = saved
        self._show_look_settings()
        self.changed.emit()

    def _close_customise(self) -> None:
        editor, self.editor = self.editor, None
        self._show_look()
        self._screens.setCurrentWidget(self.body)
        if editor is not None:
            self._screens.removeWidget(editor)
            editor.deleteLater()
        self.customise.setFocus()

    def look_choice(self) -> dict:
        # A custom look stays until another look is chosen from the menu, which drops it.
        kept = {"custom": self._look["custom"]} if "custom" in self._look else {}
        return sanitize_look({**self._built_in_look(), **kept})

    def layout_choice(self) -> dict:
        picked: dict = {"options": {}}
        for section in self.layout_sections:
            picked[section.slot] = section.chosen()
            picked["options"].update(section.options())
        return sanitize_layout(picked)


class RestoreDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        points: list[dict],
        preview: dict | None,
        storage: dict | None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Restore points")
        self.selected_id: str | None = None
        layout = QVBoxLayout(self)
        location = QLabel((storage or {}).get("label") or "Backup location unavailable")
        location.setObjectName("storageLocation")
        layout.addWidget(location)
        self.label = QLineEdit()
        self.label.setObjectName("restoreLabel")
        self.label.setPlaceholderText("Restore point name")
        layout.addWidget(self.label)
        create = QPushButton("Save restore point")
        create.setProperty("quiet", True)
        create.setObjectName("restoreCreate")
        create.clicked.connect(self._create)
        layout.addWidget(create)
        self.list = QListWidget()
        self.list.setObjectName("restoreList")
        for point in points:
            item = QListWidgetItem(
                f"{point.get('label')} · {point.get('created_at') or ''} · "
                f"{point.get('weeks_count', point.get('week_count', 0))} weeks"
            )
            item.setData(Qt.ItemDataRole.UserRole, point.get("id"))
            self.list.addItem(item)
        layout.addWidget(self.list)
        self.summary = QLabel()
        self.summary.setObjectName("restorePreviewSummary")
        if preview:
            changes = preview.get("changes") or {}
            weeks = changes.get("weeks") or {}
            homework = changes.get("assignments") or {}
            added = len(weeks.get("added") or []) + len(homework.get("added") or [])
            changed = len(weeks.get("changed") or []) + len(homework.get("changed") or [])
            removed = len(weeks.get("removed") or []) + len(homework.get("removed") or [])
            self.summary.setText(f"{added} added, {changed} changed, {removed} removed.")
        layout.addWidget(self.summary)
        actions = QHBoxLayout()
        preview_btn = QPushButton("Preview")
        preview_btn.setObjectName("restorePreview")
        preview_btn.setProperty("quiet", True)
        preview_btn.clicked.connect(self._preview)
        restore_btn = QPushButton("Restore")
        restore_btn.setObjectName("restoreApply")
        restore_btn.clicked.connect(self._restore)
        actions.addWidget(preview_btn)
        actions.addWidget(restore_btn)
        layout.addLayout(actions)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setProperty("quiet", True)
        close.rejected.connect(self.reject)
        close.accepted.connect(self.reject)
        layout.addWidget(close)
        self.action: str | None = None
        self.create_label = ""
        self.selected_id: str | None = None
        preview_id = None if not preview else preview.get("id")
        if preview_id:
            for index in range(self.list.count()):
                item = self.list.item(index)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == preview_id:
                    self.list.setCurrentRow(index)
                    break

    def _selected(self) -> str | None:
        item = self.list.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _create(self) -> None:
        self.action = "create"
        self.create_label = self.label.text().strip()
        self.accept()

    def _preview(self) -> None:
        chosen = self._selected()
        if not chosen:
            self.summary.setText("Choose a restore point.")
            return
        self.selected_id = chosen
        self.action = "preview"
        self.accept()

    def _restore(self) -> None:
        chosen = self._selected()
        if not chosen:
            self.summary.setText("Choose a restore point.")
            return
        self.selected_id = chosen
        self.action = "restore"
        self.accept()


class AccountDialog(Dialog):
    def __init__(self, parent: QWidget | None, remaining: int | None, storage: dict | None) -> None:
        super().__init__(parent, sheet=True)
        self.setObjectName("accountDialog")
        self.action: str | None = None
        layout = self.card_body("Manage account", SHEET_FORM)
        where = "your FlexWeek server" if (storage or {}).get("mode") == "hosted" else "this computer"
        info = QLabel(
            f"Signed in as {(storage or {}).get('username') or ''}. Your plans are saved on {where}."
        )
        info.setWordWrap(True)
        info.setObjectName("accountLocation")
        layout.addWidget(info)
        remaining_text = "Recovery-code status unavailable."
        if remaining == 0:
            remaining_text = "No unused recovery codes remain. Replace them before signing out."
        elif remaining == 1:
            remaining_text = "1 unused recovery code remains."
        elif isinstance(remaining, int):
            remaining_text = f"{remaining} unused recovery codes remain."
        status = QLabel(remaining_text)
        status.setObjectName("recoveryCount")
        status.setProperty("problem", remaining == 0)
        # One body that scrolls past 90 % of the window, its answers fixed under it. Sections, each about
        # one thing, with every label above its field (#70: the two password boxes were drawn over each
        # other and the red action was cut off).
        left = Qt.AlignmentFlag.AlignLeft
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACING[2])
        sheet_section(column, "Password", ACCOUNT_PASSWORD_NOTE)
        form = Form(stacked=True)
        self.current_password = QLineEdit()
        self.current_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.current_password.setObjectName("currentPassword")
        form.addRow("Current password", self.current_password)
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password.setObjectName("newPassword")
        form.addRow("New password", self.new_password)
        column.addLayout(form)
        # Replace password is the answer to the two fields above; the rest open something else.
        column.addWidget(self._action("Replace password", "changePassword", "password", False), 0, left)
        sheet_section(column, "Recovery codes", ACCOUNT_CODES_NOTE)
        column.addWidget(status)
        column.addWidget(self._action("Replace recovery codes", "replaceCodes", "codes"), 0, left)
        sheet_section(column, "Your data", ACCOUNT_DATA_NOTE)
        files = FlowLayout()
        for words, name, action in (
            ("Export account", "exportAccount", "export"),
            ("Import account", "importAccount", "import"),
            ("Export week", "exportWeek", "week"),
            ("Export day", "exportDay", "day"),
            ("Import week or day file", "importFile", "import-week"),
        ):
            files.addWidget(self._action(words, name, action))
        column.addLayout(files)
        # Deleting is in red, apart from the rest, and shown whole: an outlined button, not words.
        delete = QPushButton("Delete account")
        delete.setObjectName("deleteAccount")
        delete.setProperty("action", "delete")
        delete.setProperty("outlined", True)
        delete.setProperty("danger", True)
        delete.setAutoDefault(False)
        delete.setCursor(Qt.CursorShape.PointingHandCursor)
        delete.clicked.connect(self._set)
        column.addSpacing(SPACING[2])
        column.addWidget(delete, 0, left)
        layout.addWidget(FitScroll(body, "accountScroll"), 1)
        close = sheet_button("Close", "outlined", "accountClose")
        close.clicked.connect(self.reject)
        sheet_footer(layout, close, divided=True)

    def _action(self, words: str, name: str, action: str, outlined: bool = True) -> QPushButton:
        button = QPushButton(words)
        button.setObjectName(name)
        button.setProperty("action", action)
        button.setProperty("outlined", outlined)
        button.clicked.connect(self._set)
        return button

    def _set(self) -> None:
        self.action = self.sender().property("action")
        self.accept()


class AlarmRingDialog(QDialog):
    def __init__(self, parent: QWidget | None, alarm: dict, spotify: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("Alarm")
        self.setModal(True)
        self.snoozed = False
        self.open_spotify = False
        self._url = spotify
        # It came up 209px wide, which is smaller than a notification and easy to miss. An alarm is
        # the one thing in the app that is meant to interrupt, so it is given room to be seen.
        self.setMinimumWidth(ALARM_MIN_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(ALARM_PAD, ALARM_PAD, ALARM_PAD, ALARM_PAD)
        layout.setSpacing(ALARM_GAP)
        title = QLabel(alarm.get("name") or "Alarm")
        title.setObjectName("alarmTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        ringing = "Starting now" if alarm.get("block") else "Alarm is ringing"
        detail = QLabel(f"{alarm.get('time') or ''} · {ringing}")
        detail.setObjectName("alarmDetail")
        layout.addWidget(detail)
        layout.addSpacing(ALARM_GAP)
        self.playing = QLabel()
        self.playing.setObjectName("alarmPlaying")
        self.playing.setWordWrap(True)
        self.playing.hide()
        layout.addWidget(self.playing)
        if spotify:
            link = QPushButton("Open in Spotify")
            link.setObjectName("alarmOpenSpotify")
            link.setMinimumHeight(ALARM_BUTTON_HEIGHT)
            link.clicked.connect(self._spotify)
            layout.addWidget(link)
        snooze = QPushButton(f"Snooze {ALARM_SNOOZE_MIN} minutes")
        snooze.setObjectName("alarmSnooze")
        snooze.setProperty("quiet", True)
        snooze.clicked.connect(self._snooze)
        dismiss = QPushButton("Dismiss")
        dismiss.setObjectName("alarmDismiss")
        dismiss.setDefault(True)
        dismiss.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.setSpacing(ALARM_GAP)
        for button in (snooze, dismiss):
            button.setMinimumHeight(ALARM_BUTTON_HEIGHT)
            row.addWidget(button)
        layout.addLayout(row)

    def _snooze(self) -> None:
        self.snoozed = True
        self.accept()

    def _spotify(self) -> None:
        self.open_spotify = True
        if self._url:
            open_in_app(self._url)

    def show_playing(self, words: str) -> None:
        """What Spotify is playing for this alarm, once it is heard."""
        self.playing.setText(words)
        self.playing.show()


class TransferPreviewDialog(QDialog):
    def __init__(self, parent: QWidget | None, preview: dict) -> None:
        super().__init__(parent)
        self.setWindowTitle("Account transfer")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("From " + str(preview.get("source_username") or "another account")))
        changes = preview.get("changes") or {}
        detail = QPlainTextEdit()
        detail.setReadOnly(True)
        detail.setPlainText(str(changes))
        layout.addWidget(detail)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setProperty("quiet", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def _line(words: str, name: str) -> QLabel:
    made = QLabel(words)
    made.setObjectName(name)
    made.setWordWrap(True)
    return made


def keys_words(marked: str) -> str:
    """A shortcut as it is said: its keys without their brackets."""
    return marked.replace("[", "").replace("]", "")


def keycaps(marked: str) -> QWidget:
    """A shortcut drawn as keys: each key in brackets a keycap, the words between them plain."""
    row = QWidget()
    row.setObjectName("helpKey")
    row.setAccessibleName(keys_words(marked))
    line = QHBoxLayout(row)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(4)
    for part in re.split(r"(\[[^\]]+\])", marked):
        if not part.strip():
            continue
        cap = part.startswith("[")
        made = QLabel(part[1:-1] if cap else part.strip())
        made.setObjectName("helpKeycap" if cap else "helpKeyJoin")
        made.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # At the top of the row, at their own height: stretched to a two-line description they were
        # drawn as tall slabs.
        line.addWidget(made, 0, Qt.AlignmentFlag.AlignTop)
    line.addStretch(1)
    return row


class ScrollFade(QWidget):
    """The words fading out at one edge of a scroll area while there is more past it, so a cut line
    reads as more to scroll to, not as the end."""

    def __init__(self, area: QScrollArea, top: bool) -> None:
        super().__init__(area.viewport())
        self.setObjectName("scrollFadeTop" if top else "scrollFadeBottom")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._area, self._top = area, top
        bar = area.verticalScrollBar()
        bar.valueChanged.connect(self._follow)
        bar.rangeChanged.connect(self._follow)
        area.viewport().installEventFilter(self)
        self._follow()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Resize:
            self._follow()
        return False

    def _follow(self, *_args: object) -> None:
        view = self._area.viewport()
        self.setGeometry(0, 0 if self._top else view.height() - FADE_PX, view.width(), FADE_PX)
        bar = self._area.verticalScrollBar()
        self.setVisible(bar.value() > bar.minimum() if self._top else bar.value() < bar.maximum())
        self.raise_()

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802
        # The card the words sit on, not the window: a sheet's window is only room for its shadow.
        page = self._area.parentWidget().palette().color(QPalette.ColorRole.Window)
        clear = QColor(page)
        clear.setAlpha(0)
        ramp = QLinearGradient(0, 0, 0, self.height())
        ramp.setColorAt(0, page if self._top else clear)
        ramp.setColorAt(1, clear if self._top else page)
        painter = QPainter(self)
        painter.fillRect(self.rect(), ramp)
        painter.end()


def _logo(side: int) -> QLabel:
    ratio = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
    made = QLabel()
    made.setObjectName("aboutLogo")
    made.setFixedSize(side, side)
    picture = QPixmap(str(LOGO))
    if not picture.isNull():
        picture = picture.scaled(
            round(side * ratio),
            round(side * ratio),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        picture.setDevicePixelRatio(ratio)
        made.setPixmap(picture)
    return made


class AboutDialog(Dialog):
    def __init__(self, parent: QWidget | None, storage: dict | None, folder: str) -> None:
        super().__init__(parent, sheet=True)
        layout = self.card_body("About FlexWeek")
        brand = QHBoxLayout()
        brand.setSpacing(SECTION_GAP)
        brand.addWidget(_logo(ABOUT_LOGO_PX))
        brand.addWidget(_line(f"FlexWeek {VERSION}", "aboutVersion"), 1)
        layout.addLayout(brand)
        layout.addSpacing(SECTION_GAP // 2)
        layout.addWidget(_line(ABOUT_LINE, "aboutWhat"))
        if (storage or {}).get("mode") == "hosted":
            saved = _line(
                f"Your plans are saved on your FlexWeek server, {(storage or {}).get('origin') or ''}.",
                "aboutWhere",
            )
            saved.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(saved)
        else:
            # The folder as a button, not a path: a path is read, copied and pasted into a file
            # manager, and a student only ever wants to look inside it.
            layout.addWidget(_line(ABOUT_HERE, "aboutWhere"))
            open_folder = _page_button("Open folder", "aboutOpenFolder")
            open_folder.setToolTip(folder)
            open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(folder)))
            layout.addWidget(open_folder)


class HelpDialog(Dialog):
    """Enough to find your way: the screens two by two, then the keys, drawn as keycaps. A list's sheet,
    600 wide (5.1 A of 0.17.2), so the shortcuts are one column: beside the screens, their words wrapped
    a word or two to a line."""

    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent, sheet=True)
        layout = self.card_body("Help", SHEET_LIST)
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SECTION_GAP // 2)
        column.addWidget(_heading("The screens"))
        screens = QGridLayout()
        screens.setSpacing(SECTION_GAP // 2)
        for index, (name, words) in enumerate(HELP_SCREENS):
            card = QFrame()
            card.setObjectName("helpCard")
            inside = QVBoxLayout(card)
            # The frame's own padding is the card's margin; the layout's default doubled it.
            inside.setContentsMargins(4, 2, 4, 2)
            inside.setSpacing(2)
            title = QLabel(name)
            title.setObjectName("helpScreenName")
            inside.addWidget(title)
            inside.addWidget(_line(words, f"helpScreen{index}"))
            inside.addStretch(1)
            screens.addWidget(card, index // 2, index % 2)
        column.addLayout(screens)
        column.addSpacing(SECTION_GAP // 2)
        column.addWidget(_heading("Keyboard shortcuts"))
        # A form, not a grid: a grid gave a two-line description one line and a bit, and cut it.
        key_list = bare(QWidget())
        key_list.setObjectName("helpKeys")
        keys = QFormLayout(key_list)
        keys.setContentsMargins(0, 0, 0, 0)
        keys.setHorizontalSpacing(SECTION_GAP)
        keys.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        for key, what in HELP_KEYS:
            keys.addRow(keycaps(key), _line(what, "helpKeyDoes"))
        column.addWidget(key_list)
        column.addStretch(1)
        # A dialog's minimum counts a wrapped line as one line, so at large text on a laptop, Help at
        # its minimum squeezed the shortcuts to half their height. A scroll area gives the words the
        # height they need at the width they get, and the sheet fits its window.
        area = FitScroll(body, "helpScroll")
        self.fades = (ScrollFade(area, top=True), ScrollFade(area, top=False))
        layout.addWidget(area, 1)


class UpdateDialog(QDialog):
    """A newer FlexWeek exists. Says what it is, and does nothing until the student chooses."""

    def __init__(self, parent: QWidget | None, update: dict, current: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("Update FlexWeek")
        self.setModal(True)
        self.setObjectName("updateDialog")
        self.setMinimumWidth(UPDATE_MIN_WIDTH)
        self.choice = "later"
        self.skip_this = False
        layout = QVBoxLayout(self)
        heading = QLabel(f"FlexWeek {update['version']} is ready")
        heading.setObjectName("updateHeading")
        layout.addWidget(heading)
        detail = QLabel(f"You have {current}. Updating keeps your account and your weeks.")
        detail.setObjectName("updateDetail")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        notes = _first_lines(update.get("notes") or "")
        if notes:
            body = QLabel(notes)
            body.setObjectName("updateNotes")
            body.setWordWrap(True)
            layout.addWidget(body)
        self.status = QLabel("")
        self.status.setObjectName("updateStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setObjectName("updateProgress")
        self.bar.setVisible(False)
        layout.addWidget(self.bar)
        row = QHBoxLayout()
        self.install = QPushButton("Update now")
        self.install.setObjectName("updateInstall")
        self.install.setDefault(True)
        self.install.clicked.connect(self._install)
        later = QPushButton("Not now")
        later.setObjectName("updateLater")
        later.setProperty("quiet", True)
        later.clicked.connect(self.reject)
        skip = QPushButton("Skip this version")
        skip.setObjectName("updateSkip")
        skip.setFlat(True)
        skip.clicked.connect(self._skip)
        for button in (self.install, later):
            row.addWidget(button)
        layout.addLayout(row)
        layout.addWidget(skip)

    def _install(self) -> None:
        self.choice = "install"
        self.install.setEnabled(False)
        self.bar.setVisible(True)
        self.status.setText("Downloading…")

    def _skip(self) -> None:
        self.skip_this = True
        self.reject()

    def show_progress(self, got: int, total: int) -> None:
        self.bar.setMaximum(max(total, 0))
        self.bar.setValue(got)

    def show_problem(self, why: str) -> None:
        self.bar.setVisible(False)
        self.install.setEnabled(True)
        self.status.setText(why)


def _first_lines(notes: str, limit: int = 6) -> str:
    """The top of the release notes, which is where what changed is written.

    GitHub release bodies are Markdown, and a QLabel shows it raw, so the few markers that actually
    appear in these notes are turned into something readable rather than left as "## What changed".
    """
    kept: list[str] = []
    for raw in notes.splitlines():
        line = raw.strip()
        if not line or set(line) <= {"-", "="} and len(line) > 2:
            continue
        line = line.lstrip("#").strip()
        if line.startswith(("- ", "* ")):
            line = "•  " + line[2:]
        kept.append(line.replace("**", ""))
        if len(kept) == limit:
            break
    return "\n".join(kept)
