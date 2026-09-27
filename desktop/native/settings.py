"""Focus panel, preferences, restore points and account dialogs."""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeyEvent, QShowEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QButtonGroup,
    QCheckBox,
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
    QStackedWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from backend.comfort import TIMER_PRESETS, snap_minutes
from backend.models import valid_spotify_url
from backend.slots import SLOT_MIN
from desktop.native import autostart
from desktop.native.calendar import DAY_FULL
from desktop.native.focus import FOCUS_PHASE_LABEL, format_countdown, more_time_choices, remaining_ms
from desktop.native.fonts import time_font
from desktop.native.hours.geometry import drag_step
from desktop.native.layouts.dialog import SLOTS, LayoutSection
from desktop.native.layouts.registry import EXPERIMENTAL, sanitize_layout
from desktop.native.look import (
    ACCENTS,
    LOOK_KNOBS,
    TEXT_PT,
    effective_look,
    known_pack,
    look_menu_items,
    look_menu_token,
    look_menu_value,
    look_overrides,
    pack_motion,
    parse_look_menu_token,
    sanitize_look,
)
from desktop.native.motion import slide_page
from desktop.native.remind import ALARM_SNOOZE_MIN
from desktop.native.sound import Bell
from desktop.native.spotify import SpotifyPlayer, open_in_app
from desktop.native.tones import FALLBACK, SOUNDS
from desktop.native.version import VERSION
from desktop.native.weekmodel import hhmm_text, length_label, time_format
from desktop.native.widgets import Dialog, FlowLayout, Segmented, Switch, fit_scroll_dialog

UPDATE_MIN_WIDTH = 420
ALARM_MIN_WIDTH = 380
ALARM_PAD = 20
ALARM_GAP = 12
ALARM_BUTTON_HEIGHT = 44
# Room beside the longest name in the Settings list, for its selection edge.
PREFS_NAV_PAD = 8
SETTINGS_COLUMN = 760
CARD_PAD = 16
SECTIONS = ("Appearance & layout", "Planning", "Focus", "Alerts", "This computer")
MOTION_CHOICES = (("Normal", "normal"), ("More movement", "extra"), ("Off", "off"))
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
SPORT_FALLBACK = "Sport or club"
ALARM_TONE_LABELS = {"spotify": "A Spotify song or playlist"}
DRAG_STEP_QUESTION = "When you drag a block, it moves in steps of:"
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
FINE_TUNE_LOOK = "Fine-tune this look"
ABOUT_MIN_WIDTH = 420
HELP_MIN_WIDTH = 600
# Screens on the left and shortcuts on the right, over a window at least this wide.
HELP_TWO_COLUMN_WIDTH = 900
SECTION_GAP = 14
ABOUT_LINE = "FlexWeek plans your homework around school, sports and everything else in your week."
ABOUT_HERE = "Your plans are saved on this computer."
HELP_INTRO = (
    "A tutorial and short guides are coming in a later version. Until then, this is the short version."
)
HELP_SCREENS = (
    ("Day", "One day hour by hour, with homework that is not placed yet beside it, ready to drag in."),
    ("Week", "Monday to Sunday: drag a block to move it, or drag across empty time to add one."),
    ("Month", "Each date's blocks and the homework due that day; click a date to open it in Day."),
    ("My day", "What is on now and what comes next, to follow once your plan is made."),
)
HELP_KEYS = (
    ("D, W, M", "Day, Week, Month"),
    ("T", "My day"),
    ("B or Esc", "Back from My day"),
    ("F", "Focus screen"),
    ("Ctrl+K", "Command bar"),
    ("Ctrl+Z", "Undo"),
    ("Ctrl+Y or Ctrl+Shift+Z", "Redo"),
    ("Ctrl+C, then Ctrl+V", "Copy the selected block, then paste it into the selected day"),
    ("Ctrl+D", "Duplicate the selected block"),
    ("Delete", "Delete the selected block"),
    ("Ctrl+S", "Save now"),
    ("Ctrl and =, - or 0", "Zoom the hours in, out, or back to normal"),
    ("Ctrl and the mouse wheel", "Zoom the hours"),
    ("Esc while dragging", "Put the block back where it was"),
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
    """A button that opens something else. Plain and as wide as its words, since Done is the one
    filled button in Settings; stretched and filled, each was the loudest thing on its page."""
    made = QPushButton(words)
    made.setObjectName(name)
    made.setProperty("quiet", True)
    made.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return made


def _add_heading_item(box: QComboBox, words: str) -> None:
    """A row in a dropdown that names the rows under it and cannot be picked."""
    box.addItem(words, None)
    item = box.model().item(box.count() - 1)
    item.setEnabled(False)
    item.setSelectable(False)


def _heading(words: str) -> QLabel:
    """A card's title, so eighteen settings stop reading as one list."""
    made = QLabel(words)
    made.setObjectName("prefsHeading")
    return made


def _card(title: str, note: str = "") -> tuple[QFrame, QFormLayout]:
    """A card of settings under a title, and the form its rows go in."""
    card = QFrame()
    card.setObjectName("settingsCard")
    form = QFormLayout(card)
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
    around.setContentsMargins(24, 24, 24, 24)
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
    around.addWidget(column, 1)
    around.addStretch(0)
    return page


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
        self._ended_widgets = (self.finished, self.take_break, self.more_min, self.more)
        # Nothing to show until a timer runs, and blank rows cost the calendar height. The homework to
        # start one on is in Week's side.
        for widget in (self.card, self.task, self.phase, self.time, self.screen):
            widget.setVisible(False)

    def _emit_more(self) -> None:
        self.more_requested.emit(int(self.more_min.currentData() or 0))

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
        self.look = QComboBox()
        self.look.setObjectName("prefTheme")
        standard, experimental = look_menu_items()
        for name, label, kind in standard:
            self.look.addItem(label, look_menu_token(kind, name))
        _add_heading_item(self.look, EXPERIMENTAL)
        for name, label, kind in experimental:
            self.look.addItem(label, look_menu_token(kind, name))
        index = self.look.findData(look_menu_value(self._pack, self._look))
        self.look.setCurrentIndex(max(0, index))
        self.accent = QComboBox()
        self.accent.setObjectName("prefAccent")
        for name in ACCENTS:
            self.accent.addItem(name.title(), name)
        index = self.accent.findData(preferences.get("accent") or "default")
        self.accent.setCurrentIndex(max(0, index))
        self.accent_chips = Switch("Use the accent on category chips")
        self.accent_chips.setObjectName("prefAccentChips")
        self.accent_chips.setChecked(bool(preferences.get("accent_chips")))
        # How much the app moves: pages cross-fade, a new week slides in, notices rise into place.
        self.motion = Segmented(MOTION_CHOICES, "prefMotion")
        chosen_motion = preferences.get("motion") or pack_motion(self._pack)
        self.motion.setCurrentIndex(max(0, self.motion.findData(chosen_motion)))
        self.knobs: dict[str, Segmented] = {}
        shown = effective_look(self._look)
        self.fine_host = QWidget()
        self.fine_host.setObjectName("prefFineHost")
        fine_form = QFormLayout(self.fine_host)
        self._fine_form = fine_form
        fine_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        fine_form.setContentsMargins(0, 0, 0, 0)
        for knob, values in LOOK_KNOBS.items():
            box = Segmented(tuple((value.title(), value) for value in values), "look" + knob.title())
            box.setCurrentIndex(max(0, box.findData(shown[knob])))
            self.knobs[knob] = box
            fine_form.addRow(KNOB_LABELS[knob], box)
        self.fine_tune = Switch(FINE_TUNE_LOOK)
        self.fine_tune.setObjectName("prefFineTune")
        self.fine_tune.setChecked(bool(self._look.get("knobs")))
        self.fine_host.setVisible(self.fine_tune.isChecked())
        self.fine_tune.toggled.connect(self.fine_host.setVisible)
        self.look.currentIndexChanged.connect(self._apply_look_menu)
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
        self.volume.setSuffix(" %")
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
        appear.addRow("Accent", self.accent)
        appear.addRow(self.accent_chips)
        everywhere_card, everywhere = _card("Every screen")
        everywhere.addRow("Animations", self.motion)
        everywhere.addRow(self.fine_tune)
        everywhere.addRow(self.fine_host)
        appearance = _section_page(
            "Appearance & layout", (main_section, self.colours_card, day_section, everywhere_card)
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
        drag_card, drag_form = _card("Dragging")
        self.drag_step = Segmented(
            tuple((f"{minutes} minutes", minutes) for minutes, _words in DRAG_STEP_CHOICES), "prefDragStep"
        )
        chosen_step = drag_step(preferences.get("drag_step_min"))
        self.drag_step.setCurrentIndex(max(0, self.drag_step.findData(chosen_step)))
        drag_form.addRow(DRAG_STEP_QUESTION, self.drag_step)
        planning = _section_page("Planning", (planning_card, where_card, drag_card))
        focus_card, focus_form = _card("Focus timer")
        focus_form.addRow("Focus minutes", self.work)
        focus_form.addRow("Break minutes", self.break_min)
        focus_form.addRow("Long break minutes", self.long_break)
        focus_form.addRow("Timer preset", self.preset_timer)
        focus_form.addRow("Long break after", self.long_every)
        focus_form.addRow(self.auto_split)
        focus = _section_page("Focus", (focus_card,))
        reminders_card, alerts_form = _card("Reminders")
        alerts_form.addRow(self.reminders)
        # Everything a reminder does, in one box that greys as one while reminders are off. The switch
        # was one unticked box among controls that looked live.
        self.reminder_controls = QWidget()
        self.reminder_controls.setObjectName("prefReminderControls")
        reminder_form = QFormLayout(self.reminder_controls)
        reminder_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        reminder_form.setContentsMargins(0, 0, 0, 0)
        reminder_form.addRow("How long before", self.lead)
        reminder_form.addRow(self.reminder_sound)
        tone_row = QHBoxLayout()
        tone_row.addWidget(self.alarm_tone, 1)
        tone_row.addWidget(self.play_tone)
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
        alarm_row = QHBoxLayout()
        self.alarm_name = QLineEdit()
        self.alarm_name.setObjectName("alarmName")
        self.alarm_name.setPlaceholderText("Alarm name")
        self.alarm_time = QTimeEdit()
        self.alarm_time.setDisplayFormat(time_format())
        self.alarm_sound = QComboBox()
        self.alarm_sound.setObjectName("alarmSound")
        self.alarm_name.setMinimumWidth(120)
        self.alarm_sound.setMinimumContentsLength(8)
        for name in SOUNDS:
            self.alarm_sound.addItem("Spotify link" if name == "spotify" else name.title(), name)
        # The name on a line of its own: with the dropdown's chevron room, name, time and sound side by
        # side were wider than the page at large text.
        alarms_form.addRow("New alarm", self.alarm_name)
        for widget in (self.alarm_time, self.alarm_sound):
            alarm_row.addWidget(widget)
        alarm_row.addStretch(1)
        alarms_form.addRow("Rings at", alarm_row)
        self.alarm_spotify = QLineEdit()
        self.alarm_spotify.setObjectName("alarmSpotify")
        self.alarm_spotify.setPlaceholderText("Spotify link (optional)")
        alarms_form.addRow(self.alarm_spotify)
        # Two rows, Monday to Thursday and Friday to Sunday. Seven in a line were wider than the page.
        day_row = QGridLayout()
        day_row.setHorizontalSpacing(14)
        self.alarm_days: list[QCheckBox] = []
        for index, name in enumerate(DAY_FULL):
            day_box = QCheckBox(name[:3])
            day_box.setObjectName(f"alarmDay{index}")
            day_box.setChecked(index < 5)
            self.alarm_days.append(day_box)
            day_row.addWidget(day_box, index // 4, index % 4)
        add_alarm = _page_button("Add alarm", "addAlarm")
        add_alarm.clicked.connect(self._add_alarm)
        remove_alarm = _page_button("Remove alarm", "removeAlarm")
        remove_alarm.clicked.connect(self._remove_alarm)
        day_row.setColumnStretch(4, 1)
        alarms_form.addRow(day_row)
        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addWidget(add_alarm)
        button_row.addWidget(remove_alarm)
        button_row.addStretch(1)
        alarms_form.addRow(button_row)
        all_card, all_form = _card("All alerts")
        all_form.addRow("Volume", self.volume)
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
        rail_box.addWidget(self.nav, 1)
        self.stack = QStackedWidget()
        self.stack.setObjectName("prefsStack")
        for page in (appearance, planning, focus, alerts, computer):
            area = QScrollArea()
            area.setObjectName("settingsScroll")
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
        self.save_state = QLabel("Changes are saved as you make them.")
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
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(rail)
        outer.addLayout(column, 1)
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
        """The list fits its longest name once the pack's font has arrived; at large text a fixed
        width cut "Appearance & layout" off."""
        super().showEvent(event)
        margins = self.nav.contentsMargins()
        self.nav.setFixedWidth(
            self.nav.sizeHintForColumn(0) + margins.left() + margins.right() + 2 * self.nav.frameWidth()
            + PREFS_NAV_PAD
        )

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
        slide_page(self.stack, page, self.motion_level, 1 if row > self.stack.currentIndex() else -1)

    def _announce(self, *_value: object) -> None:
        """Takes and drops the value a box sends. Wired straight to `changed.emit`, that value made
        every emit raise inside Qt, which swallows it, so nothing showed until Settings closed."""
        self.changed.emit()

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
            "accent": self.accent.currentData(),
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
            "motion": self.motion.currentData(),
            "alarm_tone": self.alarm_tone.currentData(),
            "planning_style": self._planning_style(),
            "drag_step_min": drag_step(self.drag_step.currentData()),
        }

    def _planning_style(self) -> str:
        checked = self.planning_style.checkedButton()
        return str(checked.property("style")) if checked is not None else "suggest"

    def _apply_look_menu(self) -> None:
        """Keep knobs moved by hand; the chosen look fills in only the rest."""
        previous = self._look.get("preset") or "default"
        shown = {knob: box.currentData() for knob, box in self.knobs.items()}
        kept = look_overrides(previous, shown)
        parsed = parse_look_menu_token(self.look.currentData())
        if parsed is None:
            return
        kind, name = parsed
        if kind == "pack":
            self._pack = name
            preset = "default"
        else:
            preset = name
        self._look = sanitize_look({"preset": preset, "knobs": kept})
        bundle = effective_look(self._look)
        for knob, box in self.knobs.items():
            box.blockSignals(True)
            box.setCurrentIndex(max(0, box.findData(bundle[knob])))
            box.blockSignals(False)

    def look_choice(self) -> dict:
        parsed = parse_look_menu_token(self.look.currentData())
        preset = parsed[1] if parsed and parsed[0] == "preset" else "default"
        shown = {knob: box.currentData() for knob, box in self.knobs.items()}
        return sanitize_look({"preset": preset, "knobs": look_overrides(preset, shown)})

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
        super().__init__(parent)
        self.setWindowTitle("Account")
        self.action: str | None = None
        layout = QVBoxLayout(self)
        where = "your FlexWeek server" if (storage or {}).get("mode") == "hosted" else "this computer"
        info = QLabel(
            f"Signed in as {(storage or {}).get('username') or ''}. Your plans are saved on {where}."
        )
        info.setWordWrap(True)
        # Word wrap alone does not bound a label: it still claims the width of its longest
        # unwrapped line, which made this dialog 1338 pixels wide. The button row was not the
        # cause; with the label bounded a plain row measures 560 by 260.
        info.setMaximumWidth(ACCOUNT_MAX_WIDTH)
        info.setObjectName("accountLocation")
        layout.addWidget(info)
        remaining_text = "Recovery-code status unavailable."
        if remaining == 0:
            remaining_text = "No unused recovery codes remain. Replace them before logging out."
        elif remaining == 1:
            remaining_text = "1 unused recovery code remains."
        elif isinstance(remaining, int):
            remaining_text = f"{remaining} unused recovery codes remain."
        status = QLabel(remaining_text)
        status.setObjectName("recoveryStatus")
        layout.addWidget(status)
        form = QFormLayout()
        self.current_password = QLineEdit()
        self.current_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.current_password.setObjectName("currentPassword")
        form.addRow("Current password", self.current_password)
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password.setObjectName("newPassword")
        form.addRow("New password", self.new_password)
        layout.addLayout(form)
        self.setMinimumWidth(ACCOUNT_MIN_WIDTH)
        row = FlowLayout()
        for words, name, action in (
            ("Replace password", "changePassword", "password"),
            ("Replace recovery codes", "replaceCodes", "codes"),
            ("Delete account", "deleteAccount", "delete"),
            ("Export account", "exportAccount", "export"),
            ("Import account", "importAccount", "import"),
            ("Export week", "exportWeek", "week"),
            ("Export day", "exportDay", "day"),
            ("Import week or day file", "importFile", "import-week"),
        ):
            button = QPushButton(words)
            button.setObjectName(name)
            button.setProperty("action", action)
            # Replace password is the answer to the two fields above; the rest open something else.
            button.setProperty("quiet", action != "password")
            button.clicked.connect(self._set)
            row.addWidget(button)
        layout.addLayout(row)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setProperty("quiet", True)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

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


def _close_row(dialog: QDialog) -> QDialogButtonBox:
    # A Close of its own words, not the standard button, which carries an icon on KDE.
    buttons = QDialogButtonBox()
    buttons.addButton("Close", QDialogButtonBox.ButtonRole.RejectRole)
    buttons.rejected.connect(dialog.reject)
    return buttons


def _line(words: str, name: str) -> QLabel:
    made = QLabel(words)
    made.setObjectName(name)
    made.setWordWrap(True)
    return made


class AboutDialog(Dialog):
    def __init__(self, parent: QWidget | None, storage: dict | None, folder: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("About FlexWeek")
        self.setMinimumWidth(ABOUT_MIN_WIDTH)
        layout = QVBoxLayout(self)
        layout.addWidget(_line(f"FlexWeek {VERSION}", "aboutVersion"))
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
        layout.addWidget(_close_row(self))


class HelpDialog(Dialog):
    """Enough to find your way until the tutorial and guides exist: the screens on the left, the
    keys on the right. One column at large text or over a narrow window, where two would each be
    too narrow to read."""

    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Help")
        self.ensurePolished()
        large = self.font().pointSizeF() >= TEXT_PT["large"]
        wide = parent is not None and parent.window().width() >= HELP_TWO_COLUMN_WIDTH
        self.columns = 2 if wide and not large else 1
        self.setMinimumWidth(HELP_TWO_COLUMN_WIDTH if self.columns == 2 else HELP_MIN_WIDTH)
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(_line(HELP_INTRO, "helpIntro"))
        column.addSpacing(SECTION_GAP)
        sides = QBoxLayout(
            QBoxLayout.Direction.LeftToRight if self.columns == 2 else QBoxLayout.Direction.TopToBottom
        )
        sides.setSpacing(SECTION_GAP * 2)
        column.addLayout(sides)
        screens = QVBoxLayout()
        screens.setSpacing(SECTION_GAP // 2)
        screens.addWidget(_heading("The screens"))
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
            screens.addWidget(card)
        screens.addStretch(1)
        sides.addLayout(screens, 1)
        keys_side = QVBoxLayout()
        keys_side.addWidget(_heading("Keyboard shortcuts"))
        # A form, not a grid: a grid gave a two-line description one line and a bit, and cut it.
        key_list = QWidget()
        key_list.setObjectName("helpKeys")
        keys = QFormLayout(key_list)
        keys.setContentsMargins(0, 0, 0, 0)
        keys.setHorizontalSpacing(SECTION_GAP)
        keys.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        for key, what in HELP_KEYS:
            name = QLabel(key)
            name.setObjectName("helpKey")
            name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            keys.addRow(name, _line(what, "helpKeyDoes"))
        keys_side.addWidget(key_list)
        keys_side.addStretch(1)
        sides.addLayout(keys_side, 1)
        column.addStretch(1)
        # A dialog's minimum counts a wrapped line as one line, so at large text on a laptop, Help at
        # its minimum squeezed the shortcuts to half their height. A scroll area gives the words the
        # height they need at the width they get, and the dialog fits the screen.
        area = QScrollArea()
        area.setObjectName("helpScroll")
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(body)
        layout = QVBoxLayout(self)
        layout.addWidget(area)
        layout.addWidget(_close_row(self))

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        fit_scroll_dialog(self)


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
