"""Qt widgets window for the native FlexWeek desktop client."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QContextMenuEvent,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QKeyEvent,
    QPalette,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from backend.slots import DAY_END_MIN, SLOT_MIN, hhmm_to_minutes, minutes_to_hhmm
from desktop.native import autostart, icons
from desktop.native.calendar import (
    CATEGORIES,
    DAY_FULL,
    FLEX_CATEGORIES,
    date_for_day,
    is_series,
    monday_of,
    span_clash,
    sunday_due,
)
from desktop.native.client import PASSWORD_LENGTH_HINT, USERNAME_HINT, sign_in_problem, sign_up_problem
from desktop.native.command_bar import Command, CommandBar
from desktop.native.controller import ROUTINE_STATUS, NativeSession
from desktop.native.custom_look import sanitize_saved
from desktop.native.elevation import lift
from desktop.native.files import EXPORT_FORMAT, parse_import_payload
from desktop.native.focus import focus_now, phase_duration_ms
from desktop.native.focus_screen import FocusScreen
from desktop.native.fonts import load_fonts
from desktop.native.hours.canvas import HoursCanvas
from desktop.native.hours.classic import ClassicDay, ClassicWeek
from desktop.native.hours.geometry import Span, drag_step, next_slot
from desktop.native.hours.hand import Create, Hand, Move, MoveDate, Place, span_words
from desktop.native.hours.hand import Verdict as HandVerdict
from desktop.native.hours.month import MonthGrid
from desktop.native.hours.rail import Rail
from desktop.native.hours.zoom import ZOOM_KEYS, HoursScroll, sanitize_zoom
from desktop.native.kept import KeptSession
from desktop.native.layouts.base import NARROW_WIDTH, LayoutView, Scene
from desktop.native.layouts.empty import EmptyWeek, start_here_week
from desktop.native.layouts.registry import MATCH, options_for, sanitize_layout, tokens_for
from desktop.native.layouts.views import VIEW_CLASSES
from desktop.native.look import (
    MENU_EDGE,
    effective_look,
    look_measures,
    look_motion,
    pack_stylesheet,
    palette_from_tokens,
    resolved_palette,
    sanitize_look,
    text_scale,
    toast_colours,
)
from desktop.native.menus import Menu, mark, menu_colours
from desktop.native.motion import (
    DRIFT_PX,
    appear,
    apply_ui_effects,
    fade_away,
    fade_through,
    hold_picture,
    motion_level,
    slide_over,
    switch_page,
    trim_picture,
)
from desktop.native.remind import REMINDER_POLL_MS, clock_parts
from desktop.native.reuse import (
    due_point,
    late_from_start,
    late_locked_line,
    planner_title,
    restore_point_label,
    running_late_refusal,
    week_label,
)
from desktop.native.settings import (
    SECTIONS,
    AboutDialog,
    AccountDialog,
    AlarmRingDialog,
    FocusPanel,
    HelpDialog,
    RestoreDialog,
    SettingsPage,
    TransferPreviewDialog,
    UpdateDialog,
)
from desktop.native.setup import REMINDERS, SETUP_VERSION, STYLE, SetupPage, SetupState
from desktop.native.sound import Bell
from desktop.native.spotify import LISTENING, STARTING, SpotifyPlayer, open_in_app
from desktop.native.tokens import SHADOW_LARGE, SHADOW_SMALL, SPACING
from desktop.native.tones import FALLBACK
from desktop.native.update import RELEASE_PAGE, due_for_check, sanitize_updates
from desktop.native.updater import Updater, apply_update
from desktop.native.version import VERSION
from desktop.native.weekmodel import (
    added_words,
    build_week,
    clock_text,
    dated_words,
    hhmm_text,
    moved_words,
    set_clock_24h,
)
from desktop.native.widgets import (
    REPLAN_TIP,
    AddMenu,
    AlertStrip,
    AvailabilityDialog,
    BlockDialog,
    ChooseTimeDialog,
    ConfirmSheet,
    EndsLayout,
    FittedLabel,
    FlowLayout,
    HomeworkDialog,
    LateDialog,
    MoreButton,
    PlanButton,
    PlanReview,
    PreviewDialog,
    RoutineDialog,
    SchoolHoursDialog,
    Segment,
    SegmentTrack,
    SpreadDialog,
    Toast,
    UnfinishedPanel,
    WhyOff,
    add_heading,
    confirm,
    control_art,
    keyboard_focus_rings,
    steady_wheel,
    swatch,
    use_app_style,
)

WINDOW_SIZE = (1280, 800)
# The smallest window FlexWeek is for: at 800 the top bar still fits and nothing is cut in half.
WINDOW_MIN_WIDTH = 800
# The longest the old week's picture waits for the next one before it fades anyway.
TRAVEL_WAIT_MS = 900
# Greyed while the session is busy, but only once it has been busy this long: a plan takes a few
# milliseconds, and greying for them flashed the whole top bar (Grok Bot's 0.17.0 audit, T7). They
# take no clicks, keys or shortcuts from the moment it is busy (BusyGuard).
BUSY_LOOK_MS = 250
# Boxes that keep Ctrl+Z for the text typed in them.
EDITABLE = (QLineEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox)
BUSY_BUTTONS = (
    "createAccount",
    "signIn",
    "recoveryContinue",
    "addFixed",
    "addHomework",
    "addButton",
    "addArrow",
    "solveButton",
    "saveButton",
    "signOut",
    "prevWeek",
    "nextWeek",
    "reloadWeek",
    "viewDay",
    "viewWeek",
    "viewMonth",
    "undoButton",
    "redoButton",
    "copyBlock",
    "pasteBlock",
    "duplicateBlock",
    "copyDay",
    "routinesButton",
    "unfinishedOpen",
    "runningLate",
    "availabilityButton",
    "settingsButton",
    "restoreButton",
    "accountButton",
    "openSpotify",
    "checkUpdates",
    "forgotPassword",
    "recoverAccount",
    "moreButton",
)
# The views in the order the top bar's segments show them, which a change of view slides along.
VIEW_ORDER = ("day", "week", "month")
PLAN_LABEL = "Plan my homework"
SUGGEST_LABEL = "Suggest times"
PLAN_TIP = (
    "Find a time for homework that has none, around your fixed times and before it is due. Homework "
    "that already has a time keeps it."
)
SUGGEST_TIP = "Give homework without a time a suggested time. Drag any of them somewhere else if you like."
NOTHING_UNFINISHED = "Nothing is unfinished: no homework from earlier weeks still needs time."
QUICK_FOCUS_TIP = (
    "Open the focus timer, ready to start {minutes} minutes without picking homework. "
    "Change its length in Settings > Focus."
)
# The More menu's submenu, named for what it holds (decision 22 of 0.17); it was "Advanced".
EDIT_MENU = "Undo, copy and save"
EDIT_HEADING = "Edit"
HELP_HEADING = "Help and info"
ACCOUNT_HEADING = "Account"
# Unfinished's row while there is nothing under it, beside its greyed name.
NONE_UNFINISHED = "None left"
# The icon on each row of More, by the object name of the button the row presses.
MORE_ICONS = {
    "runningLate": "clock",
    "unfinishedOpen": "list-todo",
    "routinesButton": "repeat",
    "quickFocusAction": "timer",
    "openSpotify": "circle-play",
    "replanAll": "sparkles",
    "undoButton": "undo-2",
    "redoButton": "redo-2",
    "copyBlock": "copy",
    "pasteBlock": "clipboard-paste",
    "duplicateBlock": "copy-plus",
    "copyDay": "calendar-days",
    "saveButton": "save",
    "restoreButton": "archive-restore",
    "reloadWeek": "rotate-ccw",
    "helpButton": "circle-question-mark",
    "aboutButton": "info",
    "signOut": "log-out",
}
# Hover words for More and its submenu, by the object name of the button each action presses.
MORE_TIPS = {
    "addHomework": (
        "Add an assignment with its due date and how long it will take. FlexWeek finds time for it."
    ),
    "schoolHours": "Set the days and times you are at school, so nothing is planned then.",
    "addFixed": (
        "Add something that happens at a set time, like practice or a lesson. Homework is planned around it."
    ),
    "runningLate": (
        "Behind today? Say how late you are, and FlexWeek moves the rest of today's homework later."
    ),
    "unfinishedOpen": "Homework from earlier weeks that still needs time. Plan it into this week.",
    "routinesButton": "Save this week's fixed times as a routine, or add a saved routine to a week.",
    "openSpotify": "Open the selected block's Spotify link in Spotify.",
    "replanAll": REPLAN_TIP,
    "undoButton": "Undo your last change. Ctrl+Z",
    "redoButton": "Redo the change you just undid. Ctrl+Y",
    "copyBlock": "Copy the selected block to paste into another day. Ctrl+C",
    "pasteBlock": "Paste what you copied into the selected day, with a preview first. Ctrl+V",
    "duplicateBlock": "Make a copy of the selected block, with a preview first. Ctrl+D",
    "copyDay": "Copy every block on the selected day to paste into another day.",
    "saveButton": "Save now. FlexWeek already saves after every change. Ctrl+S",
    "restoreButton": "Go back to an earlier copy of your plans. FlexWeek keeps one before big changes.",
    "reloadWeek": "Load this week again as it is saved. Use it if something looks out of date.",
    "helpButton": "What each screen is for, and the keyboard shortcuts.",
    "aboutButton": "The version, and where your plans are saved.",
    "signOut": "Sign out on this computer. Your plans stay saved in your account.",
}
# Why an action is greyed, when the reason is not simply that FlexWeek is busy.
GREYED_TIPS = {
    "unfinishedOpen": NOTHING_UNFINISHED,
    "undoButton": "Nothing to undo yet.",
    "redoButton": "Nothing to redo.",
    "pasteBlock": "Copy a block or a day first.",
}
WAIT_TIP = "Wait a moment: FlexWeek is still saving or planning."
SIGN_OUT_QUESTION = "Your week stays saved on {where}. Sign in again to see it."
RECOVERY_KEEP = "Keep this file somewhere private. Anyone who has it can reset your password."
RECOVERY_CHOOSE = "Choose where to save"
RECOVERY_WAIT = "Tick the box above to continue."
# What they say on a top bar with no room for the whole words.
PLAN_SHORT = "Plan homework"
SUGGEST_SHORT = "Suggest"
# The top bar's icons, the larger of the system's two sizes (decision 7).
BAR_ICON_PX = 20
AUTH_CARD_WIDTH = 420
# One heading on the sign-in card: a greeting there, and what the page is for when making an account.
FIRST_GREETING = "Welcome"
AGAIN_GREETING = "Welcome back"
CREATE_HEADING = "Create your account"
CREATE_NOTE = "FlexWeek fits homework around school and sports. Your week is saved to your account."
RESET_HEADING = "Reset your password"
RESET_NOTE = "Use one of the recovery codes you saved when you made your account."
# What the sign-in card is for at the moment.
SIGN_IN, CREATE, RESET = "sign in", "create", "reset"
# The eye inside the password box, and the room it keeps clear of the typing.
REVEAL_PX = 28
REVEAL_ICON_PX = 16
# Long enough for the student to read that the update installed before the window goes.
UPDATE_QUIT_MS = 1200
# How long after the last change the week saves itself. Long enough that dragging a block does not
# post on every pixel, short enough that closing the laptop straight after a change keeps it.
AUTOSAVE_AFTER_MS = 1500
# A failed save keeps its payload and its operation id, so trying again writes the same thing once.
AUTOSAVE_RETRY_MS = 6000
AUTOSAVE_TICK_MS = 500
LAYOUT_TICK_MS = 20_000
# How long Settings waits after the last change before saving it to the account. Long enough that
# typing a number or clicking through a menu is one save.
SETTINGS_SAVE_MS = 600
LOGO = Path(__file__).resolve().parents[1] / "assets" / "logo.png"
LOGO_PX = 28
RECOVERY_COPY = "Copy"
RECOVERY_SAVE = "Save…"
RECOVERY_FILE = "flexweek-recovery-codes.txt"
# How long Copy says Copied, and Save says Saved.
RECOVERY_SAID_MS = 2000
# Homework named on a Find a new time notice before the rest is counted.
NOTICE_LINES = 3


def brand_row() -> QHBoxLayout:
    """The icon beside the wordmark, as on the app's window and installer, centred over the card."""
    row = QHBoxLayout()
    row.setSpacing(10)
    row.addStretch(1)
    ratio = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
    picture = QPixmap(str(LOGO))
    if not picture.isNull():
        side = round(LOGO_PX * ratio)
        picture = picture.scaled(
            side, side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        picture.setDevicePixelRatio(ratio)
        icon = QLabel()
        icon.setObjectName("authLogo")
        icon.setPixmap(picture)
        icon.setFixedSize(LOGO_PX, LOGO_PX)
        row.addWidget(icon)
    brand = QLabel("FlexWeek")
    brand.setObjectName("authBrand")
    row.addWidget(brand)
    row.addStretch(1)
    return row


class BusyGuard(QObject):
    """Takes no clicks, keys or shortcuts on the buttons it watches while the session is busy, from
    the first moment: they are greyed only after BUSY_LOOK_MS."""

    SWALLOWED = (
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.KeyPress,
        QEvent.Type.Shortcut,
    )

    def __init__(self, parent: QObject, busy: Callable[[], bool]) -> None:
        super().__init__(parent)
        self._busy = busy

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        return event.type() in self.SWALLOWED and self._busy()


class LastInput(QObject):
    """Whether the student's last press was a key or the pointer, so keyboard focus put back on the
    week is shown with its ring after a key and without one after a click. One for the whole
    application: a filter for each window slowed every event down by the number of windows made."""

    _shared: LastInput | None = None

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.keyboard = False
        QApplication.instance().installEventFilter(self)

    @classmethod
    def shared(cls) -> LastInput:
        if cls._shared is None or not isValid(cls._shared):
            cls._shared = cls(QApplication.instance())
        return cls._shared

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        kind = event.type()
        if kind == QEvent.Type.KeyPress:
            self.keyboard = True
        elif kind == QEvent.Type.MouseButtonPress:
            self.keyboard = False
        return False


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


class NativeWindow(QMainWindow):
    def __init__(
        self,
        origin: str,
        icon: QIcon | None = None,
        parent: QWidget | None = None,
        kept: KeptSession | None = None,
    ) -> None:
        super().__init__(parent)
        application = QApplication.instance()
        if isinstance(application, QApplication):
            steady_wheel(application)
            keyboard_focus_rings(application)
            use_app_style(application)
        # main() has loaded them already; a window made anywhere else, as in the tests, is drawn alike.
        load_fonts()
        self.session = NativeSession(origin, self, kept)
        self._instance_server: QLocalServer | None = None
        self.setWindowTitle("FlexWeek")
        if icon is not None:
            self.setWindowIcon(icon)
        self.resize(*WINDOW_SIZE)
        self._stack = QStackedWidget(self)
        # The Animations level, set from the look in _apply_appearance, and the picture of the planner
        # held while the student moves to another week.
        self._motion = "normal"
        # What the window was last dressed in, so a change that leaves the look alone skips restyling.
        self._dressed: tuple = ()
        self._page_sheet = ""
        self._travel_picture: QLabel | None = None
        self._travel_direction = 0
        # What the planner last showed (_planner_now), so a change of view, My day or design is seen.
        self._planner_shown: tuple | None = None
        self._stack.setObjectName("nativeStack")
        self.setCentralWidget(self._stack)
        self._more_pairs = []
        self._layout = sanitize_layout(None)
        self._day_mode = False
        self._opened_on_preference = False
        self._views: dict[str, LayoutView] = {}
        self._entry_mode = SIGN_IN
        self._updates = sanitize_updates(None)
        self._zoom: dict[str, int] = {}
        # The student's own looks, kept by name (custom_look.py); Settings will list them.
        self._saved_looks: list[dict] = []
        self._shown: tuple | None = None
        self._hours_week: tuple | None = None
        self._update_asked = False
        self._update_dialog: UpdateDialog | None = None
        self._updater = Updater(self)
        self._updater.found.connect(self._on_update_found)
        self._updater.none_found.connect(self._no_update)
        self._updater.unreachable.connect(self._update_unreachable)
        # Connected once here, not per dialog: a second check would otherwise wire them again and
        # every later signal would arrive as many times as the dialog had been opened.
        self._updater.progress.connect(self._on_update_progress)
        self._updater.failed.connect(self._on_update_problem)
        self._updater.ready.connect(self._on_update_ready)
        # Setup is on screen; this sign-in has decided whether it should be; and what setup has kept
        # that is still to be written, one request at a time.
        self._setup_active = False
        self._setup_checked = False
        self._setup_prefs: dict = {}
        self._setup_work_windows: list[dict] | None = None
        self._setup_week = False
        # Settings while it is on screen, and what closing it has to save.
        self._settings: SettingsPage | None = None
        self._settings_finish: Callable[[bool], None] | None = None
        # A block let go while a save is under way, moved once it is done: the save's reply replaces
        # the week, so a move made before it arrived would be lost.
        self._move_waiting: tuple[str, int, int, int, int] | None = None
        self._date_waiting: MoveDate | None = None
        # What a drag changed, said with Undo once its save lands: the words for the save on its way,
        # and words waiting for the pointer to let go, since nothing new appears under a held block.
        self._change_saving: str | None = None
        self._change_saved: str | None = None
        # The Undo step the toast offers to take back.
        self._notice_step: dict | None = None
        # Something asked for is under way; the next thing the session says is what it did.
        self._telling = False
        # The last reminder the toast said, so Got it on the same reminder takes it away.
        self._reminder_said = ""
        self._month_revealed: tuple | None = None
        self._changed_ms = 0
        self._last_try_ms = 0
        self._autosave = QTimer(self)
        self._autosave.setInterval(AUTOSAVE_TICK_MS)
        self._autosave.timeout.connect(self._autosave_tick)
        self._autosave.start()
        # The sign-in and recovery cards, which the look lifts off the page with the large shadow.
        self._entry_cards: list[QFrame] = []
        self._build_auth()
        self._build_recovery()
        self._build_week()
        self._build_setup()
        self._build_focus_screen()
        self.command_bar = CommandBar(self)
        self.command_bar.chosen.connect(self._run_command)
        self.session.account_changed.connect(self._on_account)
        self.session.recovery_codes.connect(self._show_recovery)
        self.session.week_changed.connect(self._on_week)
        self.session.status.connect(self._on_status)
        self._busy_guard = BusyGuard(self, lambda: self.session.busy)
        self._last_input = LastInput.shared()
        self._last_input.keyboard = False
        self._relaying = False
        QApplication.instance().focusChanged.connect(self._watch_field)
        self._busy_look = QTimer(self)
        self._busy_look.setSingleShot(True)
        self._busy_look.setInterval(BUSY_LOOK_MS)
        self._busy_look.timeout.connect(self._grey_while_busy)
        self.session.busy_changed.connect(self._on_busy)
        self.session.save_finished.connect(self._on_save_finished)
        self.session.plan_conflicts.connect(self._on_plan_conflicts)
        self.session.planned.connect(self._on_planned)
        self._late_dialog: LateDialog | None = None
        # The late start accepted but not stored yet, and the sentence its save will confirm.
        self._late_waiting: tuple[str, str] | None = None
        self._pending_spread_ui = False
        self._quitting = False
        self._tray_icon: QSystemTrayIcon | None = None
        self._tray_hinted = False
        self._icon = icon or QIcon()
        self._alarm_dialog: AlarmRingDialog | None = None
        self._bell = Bell(self)
        # A Spotify alarm plays in the student's Spotify app. Until it is heard the tone rings, so an
        # alarm is never silent, and once it is the tone stops.
        self._spotify = SpotifyPlayer(self)
        self._spotify.late.connect(self._spotify_late)
        self._spotify.heard.connect(self._spotify_heard)
        self._look = sanitize_look(None)
        self._allow_week_page = True
        self._load_look()
        for hours in (self.week_table.scroll, self.day_view.scroll):
            hours.restore(self._zoom)
        self.session.look = self._look
        self.session.focus_changed.connect(self._on_focus)
        self.session.focus_replace_needed.connect(self._confirm_replace_focus)
        self.session.alerts.connect(self._present_alerts)
        self.session.alarm_due.connect(self._on_alarm)
        self._focus_tick = QTimer(self)
        self._focus_tick.setInterval(500)
        self._focus_tick.timeout.connect(self.session.tick_focus)
        self._focus_tick.start()
        self._alert_tick = QTimer(self)
        self._alert_tick.setInterval(REMINDER_POLL_MS)
        self._alert_tick.timeout.connect(self.session.check_alerts)
        self._alert_tick.start()
        # A day screen is about the minute, so it is looked at again well inside one.
        self._layout_tick = QTimer(self)
        self._layout_tick.setInterval(LAYOUT_TICK_MS)
        self._layout_tick.timeout.connect(self._refresh_layout)
        self._layout_tick.timeout.connect(self._count_down)
        self._layout_tick.start()
        self._apply_appearance()
        if QSystemTrayIcon.isSystemTrayAvailable() and not self._icon.isNull():
            self._install_tray()
        self._sync_auth_mode()
        self._show_page("authPage")
        self.setMinimumWidth(WINDOW_MIN_WIDTH)
        # After the window exists, so a kept session opens the week the ordinary way.
        QTimer.singleShot(0, self.session.resume)

    def _autosave_tick(self) -> None:
        """Save the week without being asked.

        Save stopped being a button, so this has to be dependable rather than clever. It waits for
        the student to stop changing things, refuses while a request is in flight, and never touches
        a week whose save came back 409: a conflict means another window wrote this week, and
        answering that is the student's decision, not a timer's.
        """
        session = self.session
        if session.account is None or session.busy or session.conflict:
            return
        now = session.now_ms()
        if session.pending_save is not None:
            # A save that failed. Its payload and operation id are kept, so this writes the same
            # thing once however many times it is tried.
            if now - self._last_try_ms >= AUTOSAVE_RETRY_MS:
                self._last_try_ms = now
                session.save()
            return
        if not session.dirty or now - self._changed_ms < AUTOSAVE_AFTER_MS:
            return
        self._last_try_ms = now
        session.save()

    def _toggle_auth_mode(self) -> None:
        self._entry_mode = CREATE if self._entry_mode == SIGN_IN else SIGN_IN
        self._sync_auth_mode()

    def _open_reset(self) -> None:
        self._entry_mode = RESET
        self._sync_auth_mode()

    def _sync_auth_mode(self) -> None:
        """Sign in is the door, and creating an account is the small print under it: a student signs
        in many times and creates an account once. A forgotten password is the card's third use, with
        its own heading and its own one filled button, rather than a second form under Sign in."""
        mode = self._entry_mode
        kept = self.session.kept
        back = kept is not None and kept.signed_in_before()
        greeting = AGAIN_GREETING if back else FIRST_GREETING
        self.auth_heading.setText({SIGN_IN: greeting, CREATE: CREATE_HEADING, RESET: RESET_HEADING}[mode])
        note = {SIGN_IN: "", CREATE: CREATE_NOTE, RESET: RESET_NOTE}[mode]
        self.auth_note.setText(note)
        self.auth_note.setVisible(bool(note))
        self.password.setVisible(mode != RESET)
        self.password_hint.setVisible(mode == CREATE)
        self.username_hint.setVisible(mode == CREATE)
        self.sign_in_button.setVisible(mode == SIGN_IN)
        self.create_button.setVisible(mode == CREATE)
        self._show_recover(mode == RESET)
        # A new account has no password to forget.
        self.forgot_button.setVisible(mode == SIGN_IN)
        self.auth_switch.setText(
            {SIGN_IN: "New here? Create an account", CREATE: "Already have an account? Sign in"}.get(
                mode, "Back to sign in"
            )
        )
        self.sign_in_button.setDefault(mode == SIGN_IN)
        self.create_button.setDefault(mode == CREATE)
        self.recover_button.setDefault(mode == RESET)

    def listen_for_instances(self, name: str) -> bool:
        server = QLocalServer(self)
        if not server.listen(name):
            QLocalServer.removeServer(name)
            if not server.listen(name):
                return False
        server.newConnection.connect(self._on_instance_knock)
        self._instance_server = server
        return True

    def _on_instance_knock(self) -> None:
        server = self._instance_server
        while server is not None and server.hasPendingConnections():
            connection = server.nextPendingConnection()
            connection.disconnected.connect(connection.deleteLater)
            connection.disconnectFromServer()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _show_page(self, name: str) -> None:
        for index in range(self._stack.count()):
            page = self._stack.widget(index)
            if page.objectName() == name:
                leaving = self._stack.currentWidget()
                if page is not leaving:
                    # What the toast said was about the page the student is leaving.
                    self.toast.hide()
                if name == "settingsPage":
                    slide_over(self._stack, page, self._motion)
                elif leaving is not None and leaving.objectName() == "settingsPage":
                    slide_over(self._stack, page, self._motion, back=True)
                else:
                    switch_page(self._stack, page, self._motion)
                return

    def _entry_card(self, name: str) -> QVBoxLayout:
        """A page for signing in or for the recovery codes: the wordmark on the page, and under it the
        page's card in the middle of the window. The layout inside the card is returned to fill.

        The first screen anyone sees. Left to a plain page layout it stretched every field and button
        the full width of the window, so it read as an unstyled form with a lot of nothing under it.
        """
        page = QWidget()
        page.setObjectName(name)
        outer = QVBoxLayout(page)
        outer.addStretch(1)
        outer.addLayout(brand_row())
        outer.addSpacing(SPACING[4])
        middle = QHBoxLayout()
        middle.addStretch(1)
        card = QFrame()
        card.setObjectName("authCard")
        card.setFixedWidth(AUTH_CARD_WIDTH)
        middle.addWidget(card)
        middle.addStretch(1)
        outer.addLayout(middle)
        outer.addStretch(1)
        self._entry_cards.append(card)
        self._stack.addWidget(page)
        layout = QVBoxLayout(card)
        # A frame, so the card's padding is the look's, as every card's is.
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING[2])
        return layout

    def _link(self, words: str, name: str, layout: QVBoxLayout) -> QPushButton:
        """Small print under the card's button, drawn as a link and centred under it."""
        link = QPushButton(words)
        link.setObjectName(name)
        link.setFlat(True)
        link.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(link, 0, Qt.AlignmentFlag.AlignHCenter)
        return link

    def _build_auth(self) -> None:
        layout = self._entry_card("authPage")
        self.auth_heading = QLabel()
        self.auth_heading.setObjectName("authHeading")
        self.auth_heading.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.auth_heading.setWordWrap(True)
        layout.addWidget(self.auth_heading)
        self.auth_note = QLabel()
        self.auth_note.setObjectName("authNote")
        self.auth_note.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.auth_note.setWordWrap(True)
        layout.addWidget(self.auth_note)
        layout.addSpacing(SPACING[0])
        self.username = QLineEdit()
        self.username.setObjectName("username")
        self.username.setMaxLength(32)
        self.username.setPlaceholderText("Username")
        self.username.setAccessibleName("Username")
        layout.addWidget(self.username)
        self.username_hint = QLabel(USERNAME_HINT)
        self.username_hint.setObjectName("usernameHint")
        self.username_hint.setWordWrap(True)
        layout.addWidget(self.username_hint)
        self.password = PasswordField()
        self.password.setObjectName("password")
        self.password.setMaxLength(128)
        self.password.setPlaceholderText("Password")
        self.password.setAccessibleName("Password")
        self.password_reveal = self.password.reveal
        layout.addWidget(self.password)
        self.password_hint = QLabel(PASSWORD_LENGTH_HINT)
        self.password_hint.setObjectName("passwordHint")
        self.password_hint.setWordWrap(True)
        layout.addWidget(self.password_hint)
        self.recovery_code = QLineEdit()
        self.recovery_code.setObjectName("recoveryCode")
        self.recovery_code.setPlaceholderText("Recovery code")
        self.recovery_code.setAccessibleName("Recovery code")
        layout.addWidget(self.recovery_code)
        self.new_recovery_password = PasswordField()
        self.new_recovery_password.setObjectName("recoverPassword")
        self.new_recovery_password.setPlaceholderText("New password")
        self.new_recovery_password.setAccessibleName("New password")
        layout.addWidget(self.new_recovery_password)
        # On by default: most students plan on their own laptop, and signing in was the first thing
        # FlexWeek asked at every launch. Log out forgets it, for a shared computer.
        self.keep_signed_in = QCheckBox("Keep me signed in on this computer")
        self.keep_signed_in.setObjectName("keepSignedIn")
        self.keep_signed_in.setChecked(True)
        layout.addWidget(self.keep_signed_in)
        # One way in at a time. Offering Create account and Sign in as equal buttons made the student
        # choose between them before reading anything, and most arrivals after the first are sign-ins.
        self.sign_in_button = QPushButton("Sign in")
        self.sign_in_button.setObjectName("signIn")
        self.sign_in_button.setDefault(True)
        self.sign_in_button.clicked.connect(self._sign_in)
        layout.addWidget(self.sign_in_button)
        self.create_button = QPushButton("Create account")
        self.create_button.setObjectName("createAccount")
        self.create_button.clicked.connect(self._create_account)
        layout.addWidget(self.create_button)
        self.recover_button = QPushButton("Reset password")
        self.recover_button.setObjectName("recoverAccount")
        self.recover_button.clicked.connect(self._recover_account)
        layout.addWidget(self.recover_button)
        self.forgot_button = self._link("Forgot password", "forgotPassword", layout)
        self.forgot_button.clicked.connect(self._open_reset)
        self.auth_switch = self._link("", "authSwitch", layout)
        self.auth_switch.clicked.connect(self._toggle_auth_mode)
        self.auth_status = QLabel()
        self.auth_status.setObjectName("authStatus")
        self.auth_status.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.auth_status.setWordWrap(True)
        # Nothing said, nothing drawn: an empty line left a band of card under the last link.
        self.auth_status.setVisible(False)
        layout.addWidget(self.auth_status)

    def _build_recovery(self) -> None:
        layout = self._entry_card("recoveryPage")
        heading = QLabel("Save these recovery codes")
        heading.setObjectName("authHeading")
        heading.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        note = QLabel(
            "They are the only way to reset your password. FlexWeek cannot email you. "
            "Copy them somewhere you will still have if this computer is gone."
        )
        note.setWordWrap(True)
        note.setObjectName("authNote")
        note.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(note)
        self.recovery_list = QLabel()
        self.recovery_list.setObjectName("recoveryList")
        self.recovery_list.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.recovery_list)
        # Selecting eight lines by mouse was the only way to keep them.
        keep_row = QHBoxLayout()
        self.recovery_copy = QPushButton(RECOVERY_COPY)
        self.recovery_copy.setObjectName("recoveryCopy")
        self.recovery_copy.setProperty("outline", True)
        self.recovery_copy.clicked.connect(self._copy_recovery_codes)
        keep_row.addWidget(self.recovery_copy)
        self.recovery_save = QPushButton(RECOVERY_SAVE)
        self.recovery_save.setObjectName("recoverySave")
        self.recovery_save.setProperty("outline", True)
        self.recovery_save.clicked.connect(self._save_recovery_codes)
        keep_row.addWidget(self.recovery_save)
        keep_row.addStretch(1)
        layout.addLayout(keep_row)
        self._recovery_said = QTimer(self)
        self._recovery_said.setSingleShot(True)
        self._recovery_said.setInterval(RECOVERY_SAID_MS)
        self._recovery_said.timeout.connect(self._reset_recovery_buttons)
        self.recovery_status = QLabel()
        self.recovery_status.setObjectName("recoveryStatus")
        self.recovery_status.setWordWrap(True)
        self.recovery_status.setVisible(False)
        layout.addWidget(self.recovery_status)
        self.recovery_ack = QCheckBox("I have saved these codes")
        self.recovery_ack.setObjectName("recoveryAck")
        self.recovery_ack.toggled.connect(self._on_recovery_ack)
        layout.addWidget(self.recovery_ack)
        self.recovery_continue = QPushButton("Continue to my week")
        self.recovery_continue.setObjectName("recoveryContinue")
        self.recovery_continue.setEnabled(False)
        self.recovery_continue.clicked.connect(self._finish_recovery)
        layout.addWidget(self.recovery_continue)
        layout.addWidget(WhyOff(self.recovery_continue, RECOVERY_WAIT, Qt.AlignmentFlag.AlignHCenter))

    def _build_week(self) -> None:
        page = QWidget()
        page.setObjectName("weekPage")
        layout = QVBoxLayout(page)
        # Where you are at the left, what to show and do at the right; on a narrow window the second
        # goes under the first rather than both being cut.
        bar = EndsLayout()
        where = QHBoxLayout()
        self._bar_views = QHBoxLayout()
        bar.add_group(where)
        bar.add_group(self._bar_views)
        # ‹ › Today, then where you are, said once and said large. After the title, the arrows moved
        # sideways with its width on every switch between Day, Week and Month (decision 11).
        self.prev_nav = QPushButton()
        self.prev_nav.setObjectName("prevWeek")
        self.prev_nav.setToolTip("Previous week")
        self.prev_nav.clicked.connect(self._go_previous)
        self.next_nav = QPushButton()
        self.next_nav.setObjectName("nextWeek")
        self.next_nav.setToolTip("Next week")
        self.next_nav.clicked.connect(self._go_next)
        today = QPushButton("Today")
        today.setObjectName("todayWeek")
        today.setToolTip("Jump to today")
        today.clicked.connect(self._go_today)
        today.setProperty("quiet", True)
        for arrow, name in ((self.prev_nav, "chevron-left"), (self.next_nav, "chevron-right")):
            arrow.setProperty("quiet", True)
            arrow.setIconSize(QSize(BAR_ICON_PX, BAR_ICON_PX))
            icons.tint(arrow, name)
            where.addWidget(arrow)
        where.addWidget(today)
        where.addSpacing(SPACING[1])
        # Thirteen buttons of equal weight and no title at all was the clutter: nothing told the eye
        # where to land.
        self.week_title = FittedLabel()
        self.week_title.setObjectName("weekTitle")
        where.addWidget(self.week_title)
        # One control, not four loose buttons: switching view is one decision.
        segments = SegmentTrack()
        segments.setObjectName("segments")
        segment_row = QHBoxLayout(segments)
        segment_row.setContentsMargins(0, 0, 0, 0)
        segment_row.setSpacing(2)
        for view, label, tip in (
            ("day", "Day", "One day as a list"),
            ("week", "Week", "The week you are planning"),
            ("month", "Month", "The month as a calendar"),
        ):
            button = Segment(label)
            button.setObjectName(f"view{view.title()}")
            button.setCheckable(True)
            button.setToolTip(tip)
            button.clicked.connect(lambda checked=False, value=view: self._choose_view(value))
            segments.add(button)
        my_day = Segment("My day")
        my_day.setObjectName("viewMyDay")
        my_day.setCheckable(True)
        my_day.setToolTip("Watch today")
        my_day.clicked.connect(self._enter_day)
        segments.add(my_day)
        self._bar_views.addWidget(segments)
        self.account_name = QLabel()
        self.account_name.setObjectName("accountName")
        self.account_name.setVisible(False)
        self._bar_views.addWidget(self.account_name)
        sign_out = QPushButton("Sign out")
        sign_out.setObjectName("signOut")
        sign_out.clicked.connect(self._log_out)
        sign_out.setVisible(False)
        self._bar_views.addWidget(sign_out)
        self._top_bar = bar
        layout.addLayout(bar)
        # Everything between the bar and the calendar is for planning, so a day screen can put it away.
        self.plan_chrome = QWidget()
        self.plan_chrome.setObjectName("planChrome")
        chrome = QVBoxLayout(self.plan_chrome)
        chrome.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plan_chrome)
        # Wrapping, because twenty buttons in one row made the window wider than any laptop screen.
        actions = FlowLayout()
        self.add_menu = AddMenu(self)
        self.add_menu.homework_requested.connect(self._add_homework)
        self.add_menu.fixed_requested.connect(self._add_fixed)
        self.add_menu.school_requested.connect(self._school_hours)
        self.add_menu.category_chosen.connect(self._add_from_chip)
        for action_name, tip in (
            ("addMenuHomework", "addHomework"),
            ("addMenuFixed", "addFixed"),
            ("addMenuSchool", "schoolHours"),
        ):
            self.add_menu.findChild(QAction, action_name).setToolTip(MORE_TIPS[tip])
        # The one filled button on the bar. A click adds homework, the thing a student adds most; the
        # arrow beside it offers the rest.
        add_button = QPushButton("Add")
        add_button.setObjectName("addButton")
        add_button.setToolTip(MORE_TIPS["addHomework"])
        add_button.clicked.connect(self._add_now)
        add_arrow = QPushButton()
        add_arrow.setObjectName("addArrow")
        icons.tint(add_arrow, "chevron-down")
        add_arrow.setAccessibleName("More ways to add")
        add_arrow.setToolTip("Add fixed time or school hours, or pick a type to drag onto the calendar.")
        add_arrow.setMenu(self.add_menu)
        add_split = QHBoxLayout()
        add_split.setSpacing(0)
        add_split.addWidget(add_button)
        add_split.addWidget(add_arrow)
        # Kept so the shortcuts, the command bar and the tests that press them still have something to
        # press; the Add menu reaches the same actions.
        add_fixed = QPushButton("Add fixed time")
        add_fixed.setObjectName("addFixed")
        add_fixed.clicked.connect(self._add_fixed)
        add_fixed.setVisible(False)
        add_homework = QPushButton("Add homework")
        add_homework.setObjectName("addHomework")
        add_homework.clicked.connect(self._add_homework)
        add_homework.setVisible(False)
        school_hours = QPushButton("School hours")
        school_hours.setObjectName("schoolHours")
        school_hours.clicked.connect(self._school_hours)
        school_hours.setVisible(False)
        undo = QPushButton("Undo")
        undo.setObjectName("undoButton")
        undo.clicked.connect(self.session.undo)
        redo = QPushButton("Redo")
        redo.setObjectName("redoButton")
        redo.clicked.connect(self.session.redo)
        solve = PlanButton(PLAN_LABEL, PLAN_SHORT)
        solve.setObjectName("solveButton")
        # Second only to Add: accent words on a tint, not a third outlined button beside Today and More.
        solve.setProperty("secondary", True)
        solve.clicked.connect(self.session.solve)
        replan = QPushButton("Replan all my homework")
        replan.setObjectName("replanAll")
        replan.clicked.connect(lambda: self.session.solve(everything=True))
        save = QPushButton("Save")
        save.setObjectName("saveButton")
        save.clicked.connect(self.session.save)
        retry = QPushButton("Retry save")
        retry.setObjectName("retrySave")
        retry.clicked.connect(self.session.retry_save)
        reload_week = QPushButton("Reload")
        reload_week.setObjectName("reloadWeek")
        reload_week.clicked.connect(self.session.reload)
        copy_block = QPushButton("Copy")
        copy_block.setObjectName("copyBlock")
        copy_block.clicked.connect(self._copy_selected)
        paste_block = QPushButton("Paste")
        paste_block.setObjectName("pasteBlock")
        paste_block.clicked.connect(self._paste_clipboard)
        duplicate = QPushButton("Duplicate")
        duplicate.setObjectName("duplicateBlock")
        duplicate.clicked.connect(self._duplicate_selected)
        copy_day = QPushButton("Copy day")
        copy_day.setObjectName("copyDay")
        copy_day.clicked.connect(self._copy_day)
        routines = QPushButton("Routines")
        routines.setObjectName("routinesButton")
        routines.clicked.connect(self._open_routines)
        unfinished = QPushButton("Unfinished")
        unfinished.setObjectName("unfinishedOpen")
        unfinished.clicked.connect(self._show_unfinished)
        late = QPushButton("Running late")
        late.setObjectName("runningLate")
        late.clicked.connect(self._open_late)
        availability = QPushButton("Availability")
        availability.setObjectName("availabilityButton")
        availability.clicked.connect(self._open_availability)
        settings = QPushButton("Settings")
        settings.setObjectName("settingsButton")
        settings.clicked.connect(self._open_settings)
        restore = QPushButton("Restore")
        restore.setObjectName("restoreButton")
        restore.clicked.connect(self._open_restore)
        account = QPushButton("Account")
        account.setObjectName("accountButton")
        account.clicked.connect(self._open_account)
        updates = QPushButton("Check for updates")
        updates.setObjectName("checkUpdates")
        updates.clicked.connect(lambda: self._check_updates(asked=True))
        spotify = QPushButton("Open Spotify link")
        spotify.setObjectName("openSpotify")
        spotify.clicked.connect(self._open_spotify)
        more = MoreButton()
        more.setObjectName("moreButton")
        more.setProperty("quiet", True)
        overflow = QWidget(page)
        overflow.setObjectName("moreOverflow")
        overflow.hide()
        more_menu = Menu(more)
        self._more_pairs = []
        self._spotify_action = None
        self.quick_focus = QPushButton("Quick focus")
        self.quick_focus.setObjectName("quickFocusAction")
        self.quick_focus.clicked.connect(self._quick_focus)
        # Adding moved to the Add button's menu.
        school_hours.setParent(overflow)
        self._groups = (("Planning", (late, unfinished, routines, self.quick_focus, spotify, replan)),)
        self._advanced = (
            undo,
            redo,
            copy_block,
            paste_block,
            duplicate,
            copy_day,
            save,
            restore,
            reload_week,
        )
        for leftover in (availability, settings, account, updates):
            leftover.setParent(overflow)
            leftover.hide()
        for index, (heading, buttons) in enumerate(self._groups):
            if index:
                more_menu.addSeparator()
            add_heading(more_menu, heading)
            for button in buttons:
                if button.parent() is not overflow:
                    button.setParent(overflow)
                action = mark(more_menu.addAction(button.text()), MORE_ICONS[button.objectName()])
                action.triggered.connect(button.click)
                self._more_pairs.append((action, button))
                if button is spotify:
                    self._spotify_action = action
        # Every group under a heading of its own; only Planning had one (T23 of the 0.17.0 audit).
        more_menu.addSeparator()
        add_heading(more_menu, EDIT_HEADING)
        advanced_menu = more_menu.add_menu(EDIT_MENU, "pencil")
        for button in self._advanced:
            if button.parent() is not overflow:
                button.setParent(overflow)
            action = mark(advanced_menu.addAction(button.text()), MORE_ICONS[button.objectName()])
            action.triggered.connect(lambda _=False, pressed=button: self._told(pressed.click))
            self._more_pairs.append((action, button))
        help_button = QPushButton("Help")
        help_button.setObjectName("helpButton")
        help_button.clicked.connect(self._open_help)
        about = QPushButton("About FlexWeek")
        about.setObjectName("aboutButton")
        about.clicked.connect(self._open_about)
        more_menu.addSeparator()
        add_heading(more_menu, HELP_HEADING)
        for button in (help_button, about, sign_out):
            if button.parent() is not overflow:
                button.setParent(overflow)
            button.hide()
            if button is sign_out:
                # Set apart from Help and About: leaving is not one of the things to look up.
                more_menu.addSeparator()
                add_heading(more_menu, ACCOUNT_HEADING)
            action = mark(more_menu.addAction(button.text()), MORE_ICONS[button.objectName()])
            action.triggered.connect(button.click)
            self._more_pairs.append((action, button))
        more_menu.aboutToShow.connect(self._sync_more_menu)
        more.setMenu(more_menu)
        self.more_menu = more_menu
        gear = QPushButton()
        gear.setObjectName("settingsGear")
        gear.setProperty("quiet", True)
        gear.setToolTip("Settings")
        gear.setAccessibleName("Settings")
        gear.setIconSize(QSize(BAR_ICON_PX, BAR_ICON_PX))
        icons.tint(gear, "settings")
        gear.clicked.connect(self._open_settings)
        # The week saves itself now, so Save is not a thing to press; it stays reachable under More
        # and on Ctrl+S for anyone who wants to be sure. Retry appears only when a save has failed.
        self._bar_views.addLayout(add_split)
        for shown in (solve, retry, more, gear):
            self._bar_views.addWidget(shown)
        self.solve_button = solve
        self.more_button = more
        self.settings_gear = gear
        for hidden in (add_homework, add_fixed, save, self.quick_focus):
            actions.addWidget(hidden)
        for hidden in (add_homework, add_fixed, save, self.quick_focus):
            hidden.setVisible(False)
        chrome.addLayout(actions)
        self.retry_button = retry
        self.clipboard_summary = QLabel("Nothing copied")
        self.clipboard_summary.setObjectName("clipboardSummary")
        chrome.addWidget(self.clipboard_summary)
        self.focus_panel = FocusPanel()
        self.focus_panel.quick_requested.connect(self._quick_focus)
        self.focus_panel.screen_requested.connect(self._open_focus_screen)
        self.focus_panel.finished_requested.connect(self.session.finish_focused_homework)
        self.focus_panel.break_requested.connect(self.session.take_focus_break)
        self.focus_panel.more_requested.connect(self.session.add_focus_time)
        # Today's app keeps a rail left of its Day and Week; the notices and the planner are beside it.
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self._rail_row = body
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        self._column = column
        column.addWidget(self.focus_panel)
        # Neither is inside the planning chrome, which a design of its own hides: More > Unfinished
        # and Plan can be pressed from any design, and what they show is the point of pressing them.
        self.unfinished_panel = UnfinishedPanel()
        self.unfinished_badge = QPushButton()
        self.unfinished_badge.setObjectName("unfinishedBadge")
        self.unfinished_badge.setProperty("quiet", True)
        self.unfinished_badge.hide()
        self.unfinished_badge.clicked.connect(self._open_unfinished_from_badge)
        self._unfinished_introduced = False
        self.unfinished_panel.plan_requested.connect(self._plan_unfinished)
        self.unfinished_panel.delete_requested.connect(self._delete_homework)
        self.unfinished_panel.collapsed.connect(self._collapse_unfinished)
        column.addWidget(self.unfinished_panel)
        column.addWidget(self.unfinished_badge)
        self.plan_review = PlanReview()
        self.plan_review.replan_requested.connect(lambda: self.session.solve(everything=True))
        column.addWidget(self.plan_review)
        self.alert_strip = AlertStrip()
        self.alert_strip.handled.connect(self._reminder_handled)
        column.addWidget(self.alert_strip)
        self.planner = QStackedWidget()
        self.planner.setObjectName("plannerStack")
        # One pointer for every gesture on every surface: it follows a drag and reports one change.
        self.hand = Hand(self._hand_judge, self)
        self.hand.committed.connect(self._apply_change)
        self.hand.refused.connect(self.session._say)
        self.hand.opened.connect(self._edit_block)
        self.hand.menu_requested.connect(self._block_menu)
        self.hand.spot_menu_requested.connect(self._spot_menu)
        self.hand.selected.connect(self.session.select_block)
        self.hand.cleared.connect(lambda: self.session.select_block(None, None))
        self.hand.holding.connect(self._hold_renders)
        self.hand.date_judge = self._date_judge
        # Today's app, as Daily Scheduler draws it: a Week that scrolls and a full-width Day.
        self.week_table = ClassicWeek(self.hand)
        self.week_table.day_opened.connect(self._open_week_day)
        self.planner.addWidget(self.week_table)
        self.rail = Rail(self.hand)
        self.rail.focus_requested.connect(self._start_focus)
        self.rail.date_chosen.connect(self._go_to_date)
        self.rail.month_shown_changed.connect(self._keep_rail)
        body.addWidget(self.rail)
        body.addLayout(column, 1)
        self.day_view = ClassicDay(self.hand)
        self.planner.addWidget(self.day_view)
        for hours in (self.week_table.scroll, self.day_view.scroll):
            hours.zoomed.connect(self._remember_zoom)
        self.month_grid = MonthGrid(hand=self.hand)
        self.month_grid.day_activated.connect(self.session.open_day)
        self.planner.addWidget(self.month_grid)
        self.empty_week = EmptyWeek()
        self.empty_week.add_requested.connect(self._add_homework)
        self.empty_week.copy_last_requested.connect(self._copy_last_week_fixed)
        self.empty_week.routine_requested.connect(self._open_routines)
        self.planner.addWidget(self.empty_week)
        for widget in (
            self.week_table.hours,
            self.day_view.hours,
            self.month_grid.canvas,
            self.rail.tasks,
        ):
            widget.installEventFilter(self)
        # The calendar is the point of this page, so it takes whatever height the rest does not need,
        # down to the window's foot. Notices float over it rather than taking a row.
        column.addWidget(self.planner, 1)
        layout.addLayout(body, 1)
        self._stack.addWidget(page)
        self._week_page = page
        self.toast = Toast(self, self.planner)
        self._toast_where: tuple | None = None

    def _planner_widget(self, view: str) -> QWidget:
        """The chosen main view stands in for the week grid, and for Day and Month too.

        Today's app keeps the clock-order Day list and the chip Month. My day is still its own
        screen. A design of its own rebuilds Day and Month in that design, so the app is not two
        programs once you leave the week. A new account's empty week shows Today's app one button
        instead of empty hours.
        """
        if self._day_mode:
            return self._layout_view(self._layout["day"])
        main = self._layout["main"]
        if main in VIEW_CLASSES and view in {"week", "day", "month"}:
            return self._layout_view(main)
        session = self.session
        if view in {"week", "day"} and self._layout["main"] == "classic":
            week = build_week(session.week_start, session.blocks, session.assignments, session.trace)
            if not session.blocks:
                self.empty_week.set_blank(
                    not start_here_week(week, session.assignments, session.week_start, session.saved_weeks)
                )
                return self.empty_week
        return {"day": self.day_view, "month": self.month_grid}.get(view, self.week_table)

    def _layout_view(self, layout_id: str) -> LayoutView:
        view = self._views.get(layout_id)
        if view is None:
            view = VIEW_CLASSES[layout_id](hand=self.hand)
            # A layout only says what the student wants. What happens is what the window already does.
            view.add_requested.connect(
                lambda category: self._add_from_chip(category) if category else self._add_homework()
            )
            view.plan_requested.connect(self.session.solve)
            view.block_activated.connect(self._edit_block)
            view.finished_requested.connect(self._finish_homework)
            view.focus_requested.connect(self._start_focus)
            view.late_requested.connect(self._open_late)
            view.my_day_requested.connect(self._enter_day)
            view.back_requested.connect(self._leave_day)
            view.menu_requested.connect(self._menu_from)
            view.day_activated.connect(self.session.open_day)
            view.watched_day_changed.connect(self._watched_day_title)
            view.remembered_zoom = self._zoom
            view.zoomed.connect(self._remember_zoom)
            self.planner.addWidget(view)
            self._views[layout_id] = view
        view.show_week(self._scene_for(layout_id))
        return view

    def _finish_homework(self, assignment_id: str) -> None:
        item = self.session.assignments.get(assignment_id) or {}
        title = item.get("title") or "Homework"
        self.session.complete_homework(assignment_id, True)
        self.session.save()
        self._set_notice(f"Finished {title}.", "Undo", self._undo_from_notice)

    def _look_inputs(self) -> tuple[str, bool, str]:
        pack = (self.session.preferences or {}).get("theme_pack") or "system"
        accent = (self.session.preferences or {}).get("accent") or "default"
        system_dark = QGuiApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128
        return pack, system_dark, accent

    def _scene_for(self, layout_id: str) -> Scene:
        clock = clock_parts(self.session.now_ms())
        options = options_for(self._layout, layout_id)
        pack, system_dark, accent = self._look_inputs()
        palette = resolved_palette(pack, system_dark, self._look, accent)
        session = self.session
        surface = "week"
        if not self._day_mode and layout_id in VIEW_CLASSES and session.planner_view in {"day", "month"}:
            surface = session.planner_view
        week = build_week(session.week_start, session.blocks, session.assignments, session.trace)
        running = session.focus_elapsed_min()
        if running:
            # A running session counts as it goes; the homework is credited only when it ends.
            week = replace(week, focus_min=week.focus_min + running)
        return Scene(
            week=week,
            today=clock["day"] if monday_of(clock["iso"]) == session.week_start else None,
            minute=clock["minute"],
            options=options,
            tokens=tokens_for(layout_id, options["colour"], palette),
            scale=text_scale(self._look),
            surface=surface,
            month=session.month_data,
            iso_day=session.selected_day,
            dirty=session.dirty,
            unsaved_weeks=session.unsaved_weeks(),
            focus=focus_now(session.focus),
            today_iso=clock["iso"],
        )

    def _refresh_layout(self) -> None:
        shown = self.planner.currentWidget()
        if isinstance(shown, LayoutView) and self.session.account is not None:
            shown.show_week(self._scene_for(shown.layout_id))
        elif shown in (self.week_table, self.day_view) and self.session.account is not None:
            # The line that says now moves with the minute.
            today, minute = self._clock_in_week()
            for hours in (self.week_table.hours, self.day_view.hours):
                hours.set_clock(today, minute)

    def _hours_shown(self) -> list[HoursScroll]:
        """The hours on screen now, in Today's app or a design, for the zoom keys."""
        page = self.planner.currentWidget()
        return [hours for hours in page.findChildren(HoursScroll) if hours.isVisible()] if page else []

    def _count_down(self) -> None:
        """The countdown in "Next: … (in 23m)" moves on with the minute, whether or not a focus timer
        is running to redraw it."""
        self._show_next()

    def _rail_shown(self) -> bool:
        """Whether Today's app's rail is beside the planner: on its Day and Week."""
        return self.planner.currentWidget() in (self.week_table, self.day_view)

    def _show_next(self) -> None:
        """What is next goes in the rail when it is on screen, else above the planner."""
        words = self.session.now_next_text()
        today, minute = self._clock_in_week()
        self.rail.set_clock(today, minute)
        self.focus_panel.show_now_next("" if self._rail_shown() else words)

    def _sync_chrome(self) -> None:
        """Planning chips and the clipboard line step aside for a design of its own. Plan my
        homework and More stay in the top bar in every layout, every view, and My day. The hand
        drags in the step the student chose, and times are written on the clock they chose."""
        if self._set_clock():
            self._on_week()
        self.hand.step = drag_step((self.session.preferences or {}).get("drag_step_min"))
        manual = (self.session.preferences or {}).get("planning_style") == "manual"
        # A student who places homework by hand asks for ideas; the plan is theirs.
        self.solve_button.set_texts(*((SUGGEST_LABEL, SUGGEST_SHORT) if manual else (PLAN_LABEL, PLAN_SHORT)))
        self.solve_button.setToolTip(SUGGEST_TIP if manual else PLAN_TIP)
        self._keep_bar_whole()
        self._fit_plan_and_more()
        own = isinstance(self.planner.currentWidget(), LayoutView)
        # The rail holds what is next and the focus list, so beside it the panel is only the running
        # timer, which is the rail's first card (decision 15 of 0.17).
        side = self._rail_shown()
        self.plan_chrome.setVisible(not own)
        self._place_rail(side)
        self.focus_panel.setVisible((not own and not side) or self.session.focus is not None)
        self._show_next()
        self.rail.set_tasks(self.session.focus_tasks(), self._clock_in_week()[0])
        # Quick focus is in the action row whenever there is one, so the panel's own copy would be
        # the same button twice; it belongs to the panel only where no action row is shown.
        self.focus_panel.quick.setVisible(own and self._day_mode)

    def _set_clock(self) -> bool:
        """Whether the clock changed. Only a change redraws the week, so this is safe to call from
        the redraw itself."""
        changed = set_clock_24h((self.session.preferences or {}).get("clock_24h", True) is not False)
        if changed:
            # Every design's hours, shown or not: a redraw that finds no new blocks does not tell
            # them their labels got wider or narrower.
            for scroll in self.planner.findChildren(HoursScroll):
                scroll.canvas.labels_changed.emit()
                scroll.canvas.update()
        return changed

    def _fit_plan_and_more(self) -> None:
        """More loses its words before Plan my homework shortens, at every width and text size."""
        if getattr(self, "_fitting_plan_row", False):
            return
        self._fitting_plan_row = True
        more, plan = self.more_button, self.solve_button
        if self.width() >= 1000:
            plan.setText(plan._full)
            more.setText(more._full)
            if plan.width() < plan._wide(plan._full):
                more.setText("")
            self._fitting_plan_row = False
            return
        more.setText(more._full)
        if plan.width() >= plan._wide(plan._full):
            plan.setText(plan._full)
            self._fitting_plan_row = False
            return
        more.setText("")
        plan.setText(plan._short if plan.width() >= plan._wide(plan._short) else plan._short)
        self._fitting_plan_row = False

    def _keep_bar_whole(self) -> None:
        """The window is never narrower than the top bar's buttons at their smallest, which large
        text, Suggest times and Retry save each widen."""
        # Add and its chevron are one pill, so the chevron, an icon, is as tall as Add's words.
        add = self.findChild(QPushButton, "addButton")
        add.ensurePolished()
        self.findChild(QPushButton, "addArrow").setFixedHeight(add.sizeHint().height())
        self._bar_views.invalidate()
        margins = self._bar_views.parentWidget().layout().contentsMargins()
        needed = self._bar_views.minimumSize().width() + margins.left() + margins.right()
        self.setMinimumWidth(max(WINDOW_MIN_WIDTH, needed))

    def _choose_view(self, view: str) -> None:
        self._day_mode = False
        self.session.set_view(view)

    def _honour_preferred_view(self) -> None:
        """Open on whatever "Open on" says, once per sign-in. The web reads the same preference at
        startup; here it was saved and never looked at, so the app always came up on the week."""
        if self._opened_on_preference or self.session.preferences is None:
            return
        self._opened_on_preference = True
        wanted = (self.session.preferences or {}).get("preferred_view")
        if wanted == "day":
            self._day_mode = True
        elif wanted == "week":
            self._day_mode = False

    def _menu_from(self, point: QPoint) -> None:
        """More's menu, opening up from `point` on the screen, as Retro desktop's Start opens it."""
        menu = self.more_menu
        menu.popup(point - QPoint(0, menu.sizeHint().height() - 2 * MENU_EDGE))

    def _enter_day(self) -> None:
        if self.session.account is None:
            return
        self._day_mode = True
        self._on_week()
        self._views[self._layout["day"]].setFocus()

    def _watched_day_title(self, iso: str) -> None:
        if self._day_mode:
            self.week_title.set_full_text(
                planner_title(self.session, "day", selected_day=iso),
                planner_title(self.session, "day", short=True, selected_day=iso),
            )

    def _leave_day(self) -> None:
        self._day_mode = False
        self._on_week()

    def _on_account(self, account: object) -> None:
        if account is None:
            self._close_settings(save=False)
            self._day_mode = False
            self._opened_on_preference = False
            self._entry_mode = SIGN_IN
            self._setup_active = False
            self._setup_checked = False
            self._setup_prefs = {}
            self._setup_work_windows = None
            self._setup_week = False
            self._sync_auth_mode()
            self.username.clear()
            self.password.clear()
            # Left shown on a shared computer, the next student's password would be shown too.
            self.password_reveal.setChecked(False)
            self._show_page("authPage")
            return
        self.account_name.setText(account["username"])

    def _on_recovery(self) -> bool:
        return self.findChild(QWidget, "recoveryPage") is self._stack.currentWidget()

    def _finish_recovery(self) -> None:
        self._allow_week_page = True
        self.session.finish_recovery()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.week_table.set_narrow(False)
        self._place_rail(self._rail_shown())
        self._fit_plan_and_more()
        if self.toast.isVisible():
            self.toast.reposition()

    def _build_setup(self) -> None:
        self.setup_page = SetupPage()
        self.setup_page.previewed.connect(self._preview_setup_look)
        self.setup_page.left.connect(self._setup_step_left)
        self.setup_page.finished.connect(self._finish_setup)
        self.setup_page.test_requested.connect(self._test_reminder)
        self._stack.addWidget(self.setup_page)

    def _maybe_open_setup(self) -> None:
        """Setup opens once a sign-in, for an account that has neither finished nor skipped it.

        A new account opens it at once. Any other waits for its preferences, which say whether setup
        was finished and, if not, the step to resume on. An account from before setup kept its place
        opens it only when it has nothing in it yet, as the first-week card did.
        """
        session = self.session
        if self._setup_active or self._setup_checked or session.account is None:
            return
        prefs = session.preferences
        if prefs is None and not session.new_account:
            return
        self._setup_checked = True
        progress = (prefs or {}).get("setup")
        if progress is None:
            if session.new_account or (not session.blocks and not session.assignments):
                self._open_setup(STYLE, first_run=True)
            return
        if not progress.get("finished_at"):
            step = int(progress.get("step") or STYLE)
            self._open_setup(step, first_run=step <= REMINDERS)

    def _setup_state(self, first_run: bool) -> SetupState:
        session = self.session
        prefs = session.preferences or {}
        courses = {str(item.get("course") or "").strip() for item in session.assignments.values()}
        return SetupState(
            pack=str(prefs.get("theme_pack") or "system"),
            look=self._look,
            layout=self._layout,
            preferences=dict(prefs),
            blocks=list(session.blocks),
            week_start=session.week_start,
            subjects=sorted(course for course in courses if course),
            first_run=first_run,
        )

    def _open_setup(self, step: int, *, first_run: bool) -> None:
        self._close_settings(show_week=False)
        self._setup_active = True
        self.setup_page.motion = self._motion
        self.setup_page.open(self._setup_state(first_run), step)
        self._show_page("setupPage")

    def _run_setup_again(self) -> None:
        self._setup_checked = True
        self._open_setup(STYLE, first_run=False)

    def _preview_setup_look(self, choice: dict) -> None:
        """Dress the whole window in a look the student is trying, without keeping it. The old look
        fades out over the new one rather than snapping."""
        picture = hold_picture(self._stack, self._motion)
        self._look = choice["look"]
        self.session.look = self._look
        self._layout = choice["layout"]
        if self.session.preferences is not None:
            self.session.preferences = {**self.session.preferences, "theme_pack": choice["pack"]}
        self._apply_appearance()
        self.setup_page.motion = self._motion
        fade_away(picture, self._motion)

    def _setup_step_left(self, _step: int, destination: int, answer: object) -> None:
        """Keep what a page answered, and where the student went, so a quit resumes there."""
        updates: dict = {"setup": {"version": SETUP_VERSION, "step": destination}}
        if isinstance(answer, dict):
            if "layout" in answer:
                self._look = answer["look"]
                self.session.look = self._look
                self._layout = answer["layout"]
                self._save_look()
                updates["theme_pack"] = answer["pack"]
            if "blocks" in answer:
                self.session.set_setup_blocks(answer["blocks"])
                updates["day_cutoff"] = answer["day_cutoff"]
                self._setup_week = True
            if "homework" in answer:
                auto = (self.session.preferences or {}).get("planning_style") == "auto"
                for item in answer["homework"]:
                    self.session.add_homework(item)
                    if auto:
                        self.session.plan_after_save(item["id"])
                self._setup_week = True
            for key in (
                "planning_style",
                "drag_step_min",
                "study_windows",
                "reminders_enabled",
                "reminder_lead_min",
                "alarm_tone",
                "default_spotify_url",
            ):
                if key in answer:
                    updates[key] = answer[key]
            if "work_windows" in answer:
                self._setup_work_windows = deepcopy(answer["work_windows"])
        self._setup_prefs.update(updates)
        if self.session.preferences is not None:
            # Seen at once, as Settings does: the save that follows stores them.
            self.session.preferences = {**self.session.preferences, **self._setup_prefs}
        self._flush_setup()

    def _flush_setup(self) -> None:
        """Write what setup kept, one request at a time. A second request replaces the first on the
        session, so two at once would drop the first one's reply, and an answer typed a moment
        before a quit would be lost. The preferences go first: the week's save can start a plan."""
        session = self.session
        if session.account is None or session.busy:
            return
        if self._setup_prefs and session.preferences is not None:
            updates, self._setup_prefs = self._setup_prefs, {}
            session.save_preferences(updates)
            return
        if self._setup_work_windows is not None and session.preferences is not None:
            windows, self._setup_work_windows = self._setup_work_windows, None
            prefs = session.preferences
            session.save_availability(
                prefs.get("protected") or [],
                prefs.get("study_windows") or [],
                prefs.get("day_cutoff"),
                windows,
            )
            return
        if self._setup_week:
            self._setup_week = False
            session.save()

    def _finish_setup(self) -> None:
        stamp = datetime.now().strftime("%Y-%m-%dT%H:%M")
        progress = {"version": SETUP_VERSION, "step": self.setup_page.step, "finished_at": stamp}
        self._setup_prefs["setup"] = progress
        if self.session.preferences is not None:
            self.session.preferences = {**self.session.preferences, **self._setup_prefs}
        self._setup_active = False
        self._flush_setup()
        self._sync_chrome()
        self._on_week()

    def _test_reminder(self, tone: str, link: str) -> None:
        """A reminder now, in the sound on screen, so the student hears and sees what they chose."""
        volume = (self.session.preferences or {}).get("alert_volume", 80)
        # A reminder never starts music, so it chimes; the Spotify song is what an alarm will play.
        opened = tone == "spotify" and bool(link) and bool(self._spotify.play(link))
        self._bell.once(FALLBACK if tone == "spotify" else tone, volume)
        title, body = "Test reminder", "This is how a reminder from FlexWeek looks."
        if self._tray_icon is not None and self._tray_icon.supportsMessages():
            self._tray_icon.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 8000)
            said = "Sent. It shows in the corner of your screen."
        else:
            said = "Sent. This computer shows no notifications, so reminders appear in FlexWeek instead."
        if opened:
            said += (
                " Alarms and block starts play your Spotify link in the Spotify app,"
                " which it has just been given."
            )
        self.setup_page.show_test_result(said)

    def _show_recovery(self, codes: list) -> None:
        self._allow_week_page = False
        self.recovery_list.setText("\n".join(str(code) for code in codes))
        self._reset_recovery_buttons()
        self.recovery_status.setVisible(False)
        self.recovery_ack.setChecked(False)
        self.recovery_continue.setEnabled(False)
        self._show_page("recoveryPage")

    def _copy_recovery_codes(self) -> None:
        QApplication.clipboard().setText(self.recovery_list.text() + "\n")
        self._reset_recovery_buttons()
        self.recovery_copy.setText("Copied")
        self._recovery_said.start()

    def _save_recovery_codes(self) -> None:
        path = self._choose_recovery_file()
        if not path:
            return
        try:
            Path(path).write_text(self.recovery_list.text() + "\n")
        except OSError:
            self.recovery_status.setText("FlexWeek could not save the codes there. Try another folder.")
            self.recovery_status.setVisible(True)
            return
        self.recovery_status.setVisible(False)
        self._reset_recovery_buttons()
        self.recovery_save.setText("Saved")
        self._recovery_said.start()

    def _choose_recovery_file(self) -> str:
        """Its own method so a test can answer it without a sheet on screen. The sheet says what the file
        is before the system's file dialog, which is the system's to show, picks where it goes."""
        sheet = ConfirmSheet(
            self,
            "Save recovery codes",
            RECOVERY_KEEP,
            (("stay", "Cancel", "outlined"), ("choose", RECOVERY_CHOOSE, "")),
            default="choose",
        )
        sheet.exec()
        if sheet.answer != "choose":
            return ""
        return self._pick_recovery_file()

    def _pick_recovery_file(self) -> str:
        """The file dialog, opened on Documents (#50); a test answers it with a path."""
        documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        start = str(Path(documents or Path.home()) / RECOVERY_FILE)
        path, _ = QFileDialog.getSaveFileName(self, "Save recovery codes", start, "Text (*.txt)")
        return path

    def _reset_recovery_buttons(self) -> None:
        self._recovery_said.stop()
        self.recovery_copy.setText(RECOVERY_COPY)
        self.recovery_save.setText(RECOVERY_SAVE)

    def _on_week(self) -> None:
        if self.session.account is None:
            return
        if self.hand.busy and self._where() != self._shown:
            # Somewhere else was asked for while a block was held: another view, week, day or design.
            # The block goes back and nothing moves, as Escape does.
            self.hand.cancel()
        if not self.hand.busy:
            self._shown = self._where()
        if self._where() != self._toast_where:
            # Another view, week, day or design: what the toast said was about where the student was.
            self._toast_where = self._where()
            self.toast.hide()
        if self.unfinished_panel.isVisible():
            # A row deleted, planned or finished leaves the list, and an Undo brings it back.
            self.unfinished_panel.set_items(self.session.unfinished())
        if self.session.dirty:
            # Every change reaches here, so this is where the clock on "stopped changing" restarts.
            self._changed_ms = self.session.now_ms()
        if self._on_recovery() and not self._allow_week_page:
            return
        current = (self.session.account["id"], self.session.week_start)
        if current != self._hours_week:
            if self._hours_week is not None and (
                current[0] != self._hours_week[0] or self._clock_in_week()[0] is not None
            ):
                self._reset_hours(clear_all=current[0] != self._hours_week[0])
            self._hours_week = current
        turn = self._begin_turn()
        self._honour_preferred_view()
        self._set_clock()
        self._check_updates(asked=False)
        self._fill_classic()
        self.month_grid.set_month(
            self.session.month_data, self.session.dirty,
            datetime.fromtimestamp(self.session.now_ms() / 1000).date().isoformat(),
        )
        opened = (self.session.planner_view, self.session.selected_month, self.session.month_data is not None)
        if opened[0] == "month" and opened[2] and opened != self._month_revealed:
            # Once, when a month opens: after that it stays wherever the student scrolled it, through
            # saves and refreshes. After the month has been laid out, or there is nothing to measure.
            self._month_revealed = opened
            QTimer.singleShot(0, lambda day=self.session.selected_day: self.month_grid.reveal(day))
        elif opened[0] != "month":
            self._month_revealed = None
        self._sync_add_button()
        view = self.session.planner_view
        shown = self._planner_widget(view)
        # The rail goes with Today's app's Day and Week. Put away before the page changes, another
        # design is laid out once at its whole width, not first cramped beside the rail and again.
        self._place_rail(shown in (self.week_table, self.day_view))
        if turn is None:
            switch_page(self.planner, shown, self._motion)
        else:
            self.planner.setCurrentWidget(shown)
        self._release_travel()
        for name in ("viewDay", "viewWeek", "viewMonth", "viewMyDay"):
            button = self.findChild(QPushButton, name)
            if button is not None:
                button.setChecked(name == ("viewMyDay" if self._day_mode else f"view{view.title()}"))
        month = view == "month"
        day = view == "day"
        period = "month" if month else ("day" if day else "week")
        self.prev_nav.setToolTip(f"Previous {period}")
        self.next_nav.setToolTip(f"Next {period}")
        self.prev_nav.setAccessibleName(f"Previous {period}")
        self.next_nav.setAccessibleName(f"Next {period}")
        title_view = "myday" if self._day_mode else view
        watched = shown.watched_date() if self._day_mode and isinstance(shown, LayoutView) else None
        self.week_title.set_full_text(
            planner_title(self.session, title_view, selected_day=watched),
            planner_title(self.session, title_view, short=True, selected_day=watched),
        )
        self._maybe_open_setup()
        if self._setup_prefs or self._setup_work_windows is not None or self._setup_week:
            # The account's preferences may only now have arrived, and what setup kept before they did,
            # a skip included, is written with them.
            QTimer.singleShot(0, self._flush_setup)
        on_focus = self._stack.currentWidget() is self.focus_screen
        if not self._setup_active and not on_focus and self._settings is None:
            self._show_page("weekPage")
        can_retry = self.session.pending_save is not None and not self.session.conflict
        # Hidden, not merely greyed: a button that is never pressable is a permanent piece of
        # furniture that says a save failed when none has. A save on its way has a pending save too,
        # so only a finished one shows or hides it: drawn mid-save, as Month's fetch landing does,
        # Retry showed and pushed the view buttons aside.
        if not self.session.busy:
            self.retry_button.setVisible(can_retry)
        self.retry_button.setEnabled(can_retry and not self.session.busy)
        undo = self.findChild(QPushButton, "undoButton")
        redo = self.findChild(QPushButton, "redoButton")
        if undo is not None:
            undo.setEnabled(self.session.can_undo())
        if redo is not None:
            redo.setEnabled(self.session.can_redo())
        clip = self.session.clipboard
        # A permanent line saying nothing has happened is noise. It appears when there is something
        # on the clipboard and goes away again when there is not.
        self.clipboard_summary.setVisible(clip is not None)
        self.clipboard_summary.setText("Copied: " + clip["label"] if clip else "")
        destination = self.session.paste_destination()
        copy_day = self.findChild(QPushButton, "copyDay")
        paste = self.findChild(QPushButton, "pasteBlock")
        if copy_day is not None:
            if destination is None:
                copy_day.setText("Copy a selected day")
            else:
                copy_day.setText("Copy " + DAY_FULL[destination[0]])
        if paste is not None:
            paste.setEnabled(clip is not None and destination is not None)
            if destination is None:
                paste.setText("Paste into a selected day")
            else:
                paste.setText("Paste into " + DAY_FULL[destination[0]])
        items = self.session.unfinished()
        unfinished = self.findChild(QPushButton, "unfinishedOpen")
        if unfinished is not None:
            unfinished.setEnabled(bool(items))
        prompt = self.session.consume_unfinished()
        if prompt:
            self.unfinished_panel.set_items(prompt)
            self._unfinished_introduced = True
            self.unfinished_badge.hide()
        elif items and self._unfinished_introduced:
            self.unfinished_panel.hide()
            self._sync_unfinished_badge(items)
        elif not items:
            self.unfinished_panel.hide()
            self.unfinished_badge.hide()
        if self._late_dialog is not None and self.session.late_preview:
            titles = {block["id"]: block["title"] for block in self.session.blocks}
            self._late_dialog.show_trace(self.session.late_preview["trace"], titles)
        self.focus_panel.set_state(self.session)
        fresh = self.session.consume_plan_review()
        if fresh is not None:
            titles = {block["id"]: block["title"] for block in self.session.blocks}
            was_open = self.plan_review.isVisible()
            self.plan_review.set_trace(fresh, titles, self.session.week_start, self.session.plan_counts)
            self._reveal_placed()
            if self.plan_review.isVisible() and not was_open:
                appear(self.plan_review, self._motion, grow=True)
        self._sync_chrome()
        self._apply_appearance()
        self._finish_turn(turn)
        if self._pending_spread_ui and self.session.spread_preview:
            self._pending_spread_ui = False
            preview = self.session.spread_preview
            item = self.session.assignments.get(preview["assignment_id"])
            title = item["title"] if item else "homework"
            QTimer.singleShot(
                0,
                lambda: self._show_preview(
                    "Spread " + title,
                    preview["summary"],
                    preview["rows"],
                    label="spreading " + title,
                    attempt_key=(
                        f"spread|{self.session.account['id']}|{preview['assignment_id']}|"
                        f"{preview['from_date']}|{preview['session_min']}"
                        if self.session.account
                        else None
                    ),
                ),
            )

    def _on_status(self, message: str) -> None:
        """What the session says goes in the toast, on the week's page, unless it is still going
        ("Saving…") or routine ("Saved."). The student's own request is answered either way."""
        self.auth_status.setText(message)
        self.auth_status.setVisible(bool(message))
        if not message:
            # The session took back what it said, as Cancel on Running late's preview does.
            if not self.toast.button.isVisible():
                self.toast.hide()
            return
        if message.endswith("…"):
            return
        asked, self._telling = self._telling, False
        if (asked or message not in ROUTINE_STATUS) and self._stack.currentWidget() is self._week_page:
            self._say_in_toast(message)

    def _say_in_toast(self, message: str) -> None:
        if self.toast.isVisible() and self.toast.text() == message:
            # Said again as its save lands: the toast already says it, perhaps with its Undo.
            return
        self._notice_step = None
        self.toast.show_message(message)

    def _reminder_handled(self) -> None:
        """Got it on a reminder left on screen: the toast saying the same goes too."""
        if self.toast.isVisible() and self.toast.text() == self._reminder_said:
            self.toast.hide()

    def _sync_more_menu(self) -> None:
        unfinished = self.findChild(QPushButton, "unfinishedOpen")
        if unfinished is not None:
            # Worked out as the menu opens: the busy flag turns every action back on when a save
            # ends, and left to that "Unfinished" was pressable with nothing to show.
            unfinished.setEnabled(not self.session.busy and bool(self.session.unfinished()))
        for action, button in self._more_pairs:
            action.setEnabled(button.isEnabled())
            tip = self._more_tip(button.objectName(), button.isEnabled())
            # Greyed with nothing to show, Unfinished says so on its row, not only in a tooltip (T23).
            said = f"\t{NONE_UNFINISHED}" if tip == NOTHING_UNFINISHED else ""
            action.setText(button.text() + said)
            action.setToolTip(tip)
        if self._spotify_action is not None:
            self._spotify_action.setVisible(bool(self.session.spotify_url()))

    def _more_tip(self, name: str, enabled: bool) -> str:
        if name == "quickFocusAction":
            minutes = phase_duration_ms("work", self.session.preferences) // 60_000
            return QUICK_FOCUS_TIP.format(minutes=minutes)
        if enabled:
            return MORE_TIPS.get(name, "")
        session = self.session
        if session.busy or session.dirty or session.pending_save is not None:
            return WAIT_TIP
        if name == "pasteBlock" and session.clipboard is not None:
            return "Click a day first, then paste into it."
        return GREYED_TIPS.get(name, "")

    def _on_busy(self, busy: bool) -> None:
        if busy:
            self._leave_greyed_button()
        for name in BUSY_BUTTONS:
            button = self.findChild(QPushButton, name)
            if button is not None and button.property("busyGuard") is None:
                button.setProperty("busyGuard", True)
                button.installEventFilter(self._busy_guard)
        if busy:
            self._busy_look.start()
            if self.session.planning:
                # At once, not after the busy look's delay: a second click in that gap was a second plan.
                self.solve_button.setEnabled(False)
        else:
            self._busy_look.stop()
            self._grey_while_busy()
        retry = self.findChild(QPushButton, "retrySave")
        can_retry = not busy and self.session.pending_save is not None and not self.session.conflict
        if retry is not None:
            retry.setEnabled(can_retry)
        undo = self.findChild(QPushButton, "undoButton")
        redo = self.findChild(QPushButton, "redoButton")
        if undo is not None:
            undo.setEnabled(not busy and self.session.can_undo())
        if redo is not None:
            redo.setEnabled(not busy and self.session.can_redo())
        on_recovery = self.findChild(QWidget, "recoveryPage") is self._stack.currentWidget()
        if not busy and self.session.account is not None and on_recovery:
            self.recovery_continue.setEnabled(self.recovery_ack.isChecked())
        if not busy and self._move_waiting is not None:
            waiting, self._move_waiting = self._move_waiting, None
            QTimer.singleShot(0, lambda: self._move_block(*waiting))
        if not busy and self._date_waiting is not None:
            dated, self._date_waiting = self._date_waiting, None
            QTimer.singleShot(0, lambda: self._move_to_date(dated))
        if not busy and (self._setup_prefs or self._setup_work_windows is not None or self._setup_week):
            # A moment later, so a plan that finished just now saves its week before setup writes.
            QTimer.singleShot(0, self._flush_setup)

    def _leave_greyed_button(self) -> None:
        """A button greyed with the keyboard on it hands the keyboard to the next one along, such as the
        previous-week arrow; it goes to the week instead."""
        focus = QApplication.focusWidget()
        if isinstance(focus, QPushButton) and focus.objectName() in BUSY_BUTTONS:
            self._focus_week()

    def _grey_while_busy(self) -> None:
        busy = self.session.busy
        if busy:
            self._leave_greyed_button()
        for name in BUSY_BUTTONS:
            button = self.findChild(QPushButton, name)
            if button is not None:
                button.setEnabled(not busy)

    def _on_recovery_ack(self, checked: bool) -> None:
        self.recovery_continue.setEnabled(checked and not self.session.busy)

    def _create_account(self) -> None:
        name, password = self.username.text().strip(), self.password.text()
        problem = sign_up_problem(name, password)
        if problem:
            self.session._say(problem)
            return
        self.session.keep_signed_in = self.keep_signed_in.isChecked()
        self.session.register(name, password)

    def _sign_in(self) -> None:
        name, password = self.username.text().strip(), self.password.text()
        problem = sign_in_problem(name, password)
        if problem:
            self.session._say(problem)
            return
        self.session.keep_signed_in = self.keep_signed_in.isChecked()
        self.session.login(name, password)

    def _planner_now(self) -> tuple:
        """What the planner shows, as far as a change of it is a new page."""
        return (self._day_mode, self.session.planner_view, self._layout["main"], self._layout["day"])

    def _turn_pieces(self) -> tuple[QWidget, ...]:
        """What sits under the top bar beside the planner, and may come or go with a view."""
        return (
            self.plan_chrome,
            self.rail,
            self.focus_panel,
            self.unfinished_panel,
            self.plan_review,
            self.alert_strip,
            self.planner,
        )

    def _places(self) -> dict[QWidget, QRect | None]:
        page = self._week_page
        return {
            piece: QRect(piece.mapTo(page, QPoint(0, 0)), piece.size()) if piece.isVisibleTo(page) else None
            for piece in self._turn_pieces()
        }

    def _begin_turn(self) -> tuple[QLabel, dict, int, QLabel | None, str] | None:
        """Before another view, My day or another design is shown: a picture of everything under the
        top bar, where each part of it was, and which way the segments go, so the new page, with its
        chrome and colours, fades through in one frame once it is built (decisions 28 and 29)."""
        was, now = self._planner_shown, self._planner_now()
        self._planner_shown = now
        page = self._week_page
        if was is None or was == now or self._stack.currentWidget() is not page:
            return None
        top = self._top_bar.geometry().bottom() + 1
        picture = hold_picture(page, self._motion, QRect(0, top, page.width(), page.height() - top))
        if picture is None:
            return None
        # The title is in the top bar, outside the picture: it changes with the page, not a frame early.
        title = self.week_title
        title_picture = hold_picture(title.parentWidget(), self._motion, title.geometry(), beside=True)
        direction = 0
        # Day, Week and Month slide toward the segment chosen; My day and a new design only fade.
        if not was[0] and not now[0] and was[2:] == now[2:] and {was[1], now[1]} <= set(VIEW_ORDER):
            step = VIEW_ORDER.index(now[1]) - VIEW_ORDER.index(was[1])
            direction = (step > 0) - (step < 0)
        return picture, self._places(), direction, title_picture, title.full_text()

    def _finish_turn(self, turn: tuple[QLabel, dict, int, QLabel | None, str] | None) -> None:
        """The new page is built and dressed: what changed fades through to it, the title with it. The
        parts that stayed where they were are left out of the picture, so they neither blink nor
        drift."""
        if turn is None:
            return
        picture, before, direction, title_picture, title_was = turn
        if title_picture is not None and self.week_title.full_text() != title_was:
            fade_through(title_picture, [self.week_title], self._motion)
        elif title_picture is not None:
            title_picture.deleteLater()
        self._week_page.layout().activate()
        after = self._places()
        changed = [piece for piece in self._turn_pieces() if before[piece] != after[piece]]
        area = before[self.planner] or QRect()
        for piece in changed:
            area = area.united(before[piece] or QRect())
        if area.isEmpty():
            picture.deleteLater()
            return
        trim_picture(picture, area)
        incoming = [piece for piece in changed if piece is not self.planner and piece.isVisible()]
        fade_through(picture, [*incoming, self.planner.currentWidget()], self._motion, direction)

    def _travel(self, direction: int) -> None:
        """Hold a picture of the planner while the next week, day or month loads, then let it drift
        away in the direction the student went. Without it the old week blinked to the new one."""
        self._release_travel()
        self._travel_picture = hold_picture(self.planner, self._motion)
        self._travel_direction = direction
        if self._travel_picture is not None:
            QTimer.singleShot(TRAVEL_WAIT_MS, self._release_travel)

    def _release_travel(self) -> None:
        picture, self._travel_picture = self._travel_picture, None
        fade_away(picture, self._motion, drift=self._travel_direction * DRIFT_PX)

    def _go_previous(self) -> None:
        self._travel(1)
        if self.session.planner_view == "month":
            self.session.shift_month(-1)
            return
        if self.session.planner_view == "day":
            current = date.fromisoformat(self.session.selected_day)
            self.session.open_day((current + timedelta(days=-1)).isoformat())
            return
        self._shift_week(-7)

    def _go_next(self) -> None:
        self._travel(-1)
        if self.session.planner_view == "month":
            self.session.shift_month(1)
            return
        if self.session.planner_view == "day":
            current = date.fromisoformat(self.session.selected_day)
            self.session.open_day((current + timedelta(days=1)).isoformat())
            return
        self._shift_week(7)

    def _go_today(self) -> None:
        self._travel(0)
        today = datetime.fromtimestamp(self.session.now_ms() / 1000).date()
        if self._clock_in_week()[0] is not None:
            # From another week, the week changing to this one opens it at now (_on_week), and that
            # other week stays where it was left.
            self._reset_hours()
        self.session.load_week(monday_of(today.isoformat()))
        if self.session.planner_view == "day" or self._day_mode:
            self.session.open_day(today.isoformat())

    def _shift_week(self, days: int) -> None:
        monday = date.fromisoformat(self.session.week_start) + timedelta(days=days)
        self.session.load_week(monday.isoformat())

    def _run_sheet(self, dialog: QDialog) -> bool:
        """Open a sheet and wait for it. Once it is closed the keyboard is back on the week, not on the
        button that opened it."""
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self._focus_week()
        return accepted

    def _commit_block(self, dialog: BlockDialog) -> None:
        if not self._run_sheet(dialog):
            return
        if dialog.deleted():
            self._delete_block(dialog.block(), dialog.scope(), dialog.occurrence_day())
            return
        before = {item["id"] for item in self.session.blocks}
        self.session.add_block(dialog.block(), scope=dialog.scope(), day=dialog.occurrence_day())
        day = dialog.occurrence_day()
        if dialog.recover_missed() and day is not None:
            # "This day only" splits the series and gives that day a new id. recover_missed returns
            # without saving when its block does not hold the day, so it only gets one that does;
            # otherwise the edit is saved the ordinary way instead of staying an unsaved draft.
            ids = {dialog.block()["id"]} | ({item["id"] for item in self.session.blocks} - before)
            holder = next(
                (item for item in self.session.blocks if item["id"] in ids and day in item["days"]),
                None,
            )
            if holder is not None:
                self.session.recover_missed(holder["id"], day)
                return
        self.session.save()

    def _commit_homework(self, dialog: HomeworkDialog, days: list[int] | None = None) -> None:
        if not self._run_sheet(dialog):
            return
        if dialog.spread_requested():
            self._open_spread(dialog.assignment()["id"])
            return
        if dialog.requested() == "choose":
            self._choose_time(dialog.assignment()["id"])
            return
        if dialog.requested() == "unpin":
            if self.session.unpin_assignment(dialog.assignment()["id"]):
                self.session.save()
            return
        if dialog.requested() == "delete":
            # The editor has asked already.
            self._delete_homework(dialog.assignment()["id"], ask=False)
            return
        body = dialog.assignment()
        known = self.session.assignments.get(body.get("id") or "")
        self.session.add_homework(body, days=days)
        style = (self.session.preferences or {}).get("planning_style")
        if style == "auto" and known is None and not body.get("completed") and days is None:
            # Plan it for me as I add it: new homework gets its time once it is saved, in the same step.
            self.session.plan_after_save(body["id"])
        self.session.save()
        if body.get("completed") and not (known or {}).get("completed"):
            self._set_notice(f"Finished {body.get('title') or 'Homework'}.", "Undo", self._undo_from_notice)

    def _add_fixed(self) -> None:
        category = self.session.armed_category
        if category in FLEX_CATEGORIES:
            category = None
        self._commit_block(self._new_event(category))

    def _new_event(self, category: str | None) -> BlockDialog:
        """A new event opens on the next quarter hour still ahead today, or with none left, the first one
        tomorrow. The usual start stays for another week, which has no "now", and for tomorrow when that is
        a day of the next week, which the open one cannot hold."""
        today, minute = self._clock_in_week()
        if today is None or minute is None:
            return BlockDialog(self, category=category)
        ahead, slot = next_slot(minute)
        if today + ahead > 6:
            return BlockDialog(self, category=category)
        return BlockDialog(self, day=today + ahead, start=minutes_to_hhmm(slot), category=category)

    def _add_fixed_at(self, day: int, minute: int) -> None:
        category = self.session.armed_category
        if category in FLEX_CATEGORIES:
            category = None
        self._commit_block(BlockDialog(self, day=day, start=minutes_to_hhmm(minute), category=category))

    def _add_homework_due(self, due: str) -> None:
        category = self.session.armed_category
        if category not in FLEX_CATEGORIES:
            category = "assignments"
        self._commit_homework(HomeworkDialog(self, today=self._today(), category=category, due=due))

    def _delete_block(self, block: dict, scope: str, day: int | None) -> None:
        self.session.delete_block(block["id"], scope=scope, day=day)
        self.session.save()
        # The question before deleting promised an undo; this is where it is.
        self._set_notice(f"Deleted {block.get('title') or 'the event'}.", "Undo", self._undo_from_notice)

    def _school_hours(self) -> None:
        """School's days and times, asked as setup asks them: the student's School if they have one,
        otherwise Monday to Friday 08:00-14:30 to start from. Saved as any edit of a block is; no day
        ticked takes School off the calendar."""
        locked = [item for item in self.session.blocks if item.get("kind") == "locked"]
        school = next((item for item in locked if item["id"] == "school"), None) or next(
            (item for item in locked if item.get("category") == "class"), None
        )
        dialog = SchoolHoursDialog(self, school)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        made = dialog.block()
        if made is not None:
            self.session.add_block(made)
            self.session.save()
        elif school is not None:
            self._delete_block(school, "series", None)

    def _add_now(self) -> None:
        """Add adds homework, or the type picked in its menu for a drag, which the button then names."""
        armed = self.session.armed_category
        if armed:
            self._add_from_chip(armed)
        else:
            self._add_homework()

    def _add_homework(self) -> None:
        category = self.session.armed_category
        if category not in FLEX_CATEGORIES:
            category = "assignments"
        self._commit_homework(HomeworkDialog(self, today=self._today(), category=category))

    def _today(self) -> str:
        return clock_parts(self.session.now_ms())["iso"]

    def _sync_add_button(self) -> None:
        """The Add button carries the type a drag on the calendar will make, so the armed type is
        still visible now that the chip strip is gone."""
        armed = self.session.armed_category
        self.add_menu.set_armed(armed)
        button = self.findChild(QPushButton, "addButton")
        info = CATEGORIES.get(armed or "")
        if button is not None:
            button.setText(f"Add {info['label'].lower()}" if info else "Add")
            icons.tint(button, None if info else "plus")
            if info:
                button.setIcon(QIcon(swatch(info["mark"])))

    def _clock_in_week(self) -> tuple[int | None, int | None]:
        """Today's weekday and minute when the open week is this week, else nothing to mark."""
        moment = datetime.fromtimestamp(self.session.now_ms() / 1000.0)
        if monday_of(moment.date().isoformat()) != self.session.week_start:
            return None, None
        return moment.weekday(), moment.hour * 60 + moment.minute

    def _fill_classic(self) -> None:
        """Today's app's Day and Week from the open week. Held while the pointer holds something."""
        if self.hand.busy:
            return
        week = build_week(
            self.session.week_start, self.session.blocks, self.session.assignments, self.session.trace
        )
        today, minute = self._clock_in_week()
        self.week_table.set_week(week, today, minute)
        self.day_view.set_day(week, date.fromisoformat(self.session.selected_day).weekday(), today, minute)
        self.rail.set_week(week, today, minute, self.session.assignments)
        self.month_grid.set_unsaved(self.session.unsaved_weeks())
        self.month_grid.set_week(week)

    def _where(self) -> tuple:
        """What the planner is showing: a held block belongs to this, and to nothing else."""
        session = self.session
        return (
            session.planner_view,
            session.week_start,
            session.selected_day,
            self._day_mode,
            repr(self._layout),
        )

    def _remember_zoom(self, key: str, px: int) -> None:
        """How close a surface's hours are is kept for this device, as the look is."""
        # In place: every design holds this dict and reads it for the hours it makes later.
        self._zoom[key] = px
        self._save_look()

    def _place_rail(self, shown: bool) -> None:
        """The rail beside the planner, or folded into a line above it on a narrow window; and the
        running timer at the top of the rail while it shows."""
        narrow = self.width() < NARROW_WIDTH
        if narrow != self.rail.folded:
            for home in (self._rail_row, self._column):
                home.removeWidget(self.rail)
            if narrow:
                self._column.insertWidget(self._column.indexOf(self.planner), self.rail)
            else:
                self._rail_row.insertWidget(0, self.rail)
            self.rail.set_folded(narrow)
        self.rail.setVisible(shown)
        in_rail = shown and not narrow
        slot = self.rail.timer_slot
        if in_rail and slot.indexOf(self.focus_panel) < 0:
            self._column.removeWidget(self.focus_panel)
            slot.addWidget(self.focus_panel)
        elif not in_rail and self._column.indexOf(self.focus_panel) < 0:
            slot.removeWidget(self.focus_panel)
            self._column.insertWidget(0, self.focus_panel)
        self.focus_panel.set_compact(in_rail)

    def _reset_hours(self, *, clear_all: bool = False) -> None:
        # Designs park cached grids outside the window and may reuse an unchanged scene.
        today, minute = self._clock_in_week()
        for scroll in QApplication.allWidgets():
            if isinstance(scroll, HoursScroll) and scroll.canvas.hand is self.hand:
                key = scroll._opened
                scroll.forget(None if clear_all else self.session.week_start)
                if scroll._opened is None and minute is not None and (
                    not isinstance(key, tuple) or key[1] == today
                ):
                    scroll.scroll_to(minute, None)

    def _reveal_placed(self) -> None:
        """After Plan, the hours on screen scroll to the first homework it placed, so what it did is
        seen (decision 34 of 0.17). On Day, only when that is the day shown."""
        first = self.session.plan_first
        shown = self.planner.currentWidget()
        if first is None or shown not in (self.week_table, self.day_view):
            return
        day, minute = first
        if shown is self.day_view and day != shown.day:
            return
        shown.scroll.reveal(minute, 60, self._motion)

    def _keep_rail(self, _shown: bool) -> None:
        """The month folded or shown in the rail is kept on this computer, as the zoom is."""
        self._save_look()

    def _go_to_date(self, iso: str) -> None:
        """A date picked in the rail's month: that day on Day, else its week."""
        if self.session.planner_view == "day":
            self.session.open_day(iso)
        else:
            self.session.load_week(monday_of(iso))

    def _open_week_day(self, day: int) -> None:
        self.session.open_day(date_for_day(self.session.week_start, day))

    def _hand_judge(self, block_id: str, from_day: int, span) -> HandVerdict:
        return self._judge_span(block_id, from_day, span.day, span.start, span.end)

    def _apply_change(self, change: object) -> None:
        """What the pointer did, turned into the change the week keeps."""
        if isinstance(change, Move):
            span = change.span
            self._move_block(change.block_id, change.from_day, span.day, span.start, span.end)
            self._focus_week((change.block_id, span.day, span.start))
        elif isinstance(change, Place):
            span = change.span
            self._move_block(change.block_id, -1, span.day, span.start, span.end)
            self._focus_week((change.block_id, span.day, span.start))
        elif isinstance(change, Create):
            span = change.span
            # After the release has been handled: Add is a dialog with its own event loop.
            QTimer.singleShot(0, lambda: self._create_by_drag(span))
        elif isinstance(change, MoveDate):
            self._move_to_date(change)

    def _date_judge(self, block_id: str, from_iso: str, to_iso: str) -> HandVerdict:
        """Whether a block carried on Month can go on a date: the same rule a save applies. A chip
        from a week that is not loaded is judged by the time and homework the month reply gives it."""
        days = (self.session.month_data or {}).get("days") or []
        day = next((item for item in days if item.get("date") == from_iso), {})
        chip = next((item for item in day.get("blocks") or [] if item.get("id") == block_id), {})
        problem = self.session.date_problem(
            block_id,
            from_iso,
            to_iso,
            start=chip.get("start"),
            duration_min=chip.get("duration_min"),
            assignment_id=chip.get("assignment_id"),
        )
        return HandVerdict(problem is None, problem or "")

    def _move_to_date(self, change: MoveDate) -> None:
        """A chip let go on another date. While a save is on its way it waits for it, as a block let
        go on the hours does; nothing is shown moved until the server has it. A change that did not
        save is not waited on: the drop is refused in words, not kept to happen later."""
        if self.session.busy:
            self._date_waiting = change
            return
        if self.session.pending_save is not None or self.session.conflict:
            self.session._say("Not moved: your last change has not saved yet. Try again once it has.")
            return
        if self.session.move_to_date(change.block_id, change.from_iso, change.to_iso):
            self._say_when_saved(dated_words(self._title_of(change.block_id, change.from_iso), change.to_iso))

    def _title_of(self, block_id: str, iso: str) -> str:
        """A block's title, from this week or, for a chip from another week, from what Month shows."""
        block = next((item for item in self.session.blocks if item["id"] == block_id), None)
        if block is None:
            days = (self.session.month_data or {}).get("days") or []
            day = next((item for item in days if item.get("date") == iso), {})
            block = next((item for item in day.get("blocks") or [] if item.get("id") == block_id), None)
        return (block or {}).get("title") or "the block"

    def _hold_renders(self, holding: bool) -> None:
        """Nothing a press started on is rebuilt until it is let go, whether it becomes a drag or a tap."""
        for view in self._views.values():
            view.hold(holding)
        if not holding:
            QTimer.singleShot(0, self._refresh_after_hold)

    def _refresh_after_hold(self) -> None:
        if self.session.account is not None and not self.hand.busy:
            self._fill_classic()
            self._show_change()

    def _set_notice(self, text: str, button: str, callback) -> None:
        """Words with one thing to do about them, such as Undo, in the toast."""
        self._notice_step = None
        self.toast.show_message(text, button, callback)

    def _first_placed(self) -> tuple[str, int, int] | None:
        """The block the plan placed first: its id, the day it is on and where it starts."""
        placed = (self.session.trace or {}).get("placed") or []
        for item in placed:
            block = next((b for b in self.session.blocks if b["id"] == item.get("id")), None)
            if block is not None and block.get("start") and block.get("days"):
                return block["id"], block["days"][0], hhmm_to_minutes(block["start"])
        return None

    def _undo_from_notice(self) -> None:
        self._notice_step = None
        self.session.undo()
        self._focus_week()

    def _say_when_saved(self, words: str) -> None:
        """`words` say what the save now on its way changes, once it lands, with Undo. A change that
        started no save says nothing."""
        self._change_saving = words if self.session.busy else None

    def _show_change(self) -> None:
        # Not while a block is held: nothing new appears beside the hours until the release.
        if self._change_saved is None or self.hand.busy:
            return
        words, self._change_saved = self._change_saved, None
        self._set_notice(words, "Undo", self._undo_from_notice)
        self._notice_step = self.session.last_step()

    def _told(self, act) -> None:
        """Do what the student asked, and once it is done say what it did in the toast: the first thing
        the session says, bar words ending in "…", which say it is still going. Asked for, even a
        routine "Saved." is the answer."""
        self._telling = True
        act()
        if not self.session.busy:
            # Done at once, or a dialog closed without doing anything.
            self._telling = False

    def _on_planned(self, said: str) -> None:
        # The answer to Plan my homework, so no later status is taken for it.
        self._telling = False
        self._set_notice(said, "Undo", self._undo_from_notice)
        self._notice_step = self.session.last_step()
        self._focus_week(self._first_placed())

    def _on_plan_conflicts(self, lost: list) -> None:
        if not lost:
            return
        self._notice_ids = {item["block_id"] for item in lost}
        # Every homework that lost its time is named. Find a new time moves all of them, and the notice
        # showed only the first.
        said = [item["message"] for item in lost[:NOTICE_LINES]]
        if len(lost) > NOTICE_LINES:
            said.append(f"And {len(lost) - NOTICE_LINES} more.")
        self._set_notice("\n".join(said), "Find a new time", self._find_new_time)

    def _find_new_time(self) -> None:
        ids = getattr(self, "_notice_ids", set())
        if ids:
            self.session.solve(only=ids)

    def _add_from_chip(self, category: str) -> None:
        self.session.arm_category(category)
        self._sync_add_button()
        if category in FLEX_CATEGORIES:
            self._commit_homework(HomeworkDialog(self, today=self._today(), category=category))
            return
        self._commit_block(self._new_event(category))

    def _create_by_drag(self, span: Span) -> None:
        before = {item["id"] for item in self.session.blocks}
        self._create_range(span.day, span.start, span.end)
        made = [item for item in self.session.blocks if item["id"] not in before]
        if made:
            self._say_when_saved(added_words(made[0]))

    def _create_range(self, day: int, start_min: int, end_min: int) -> None:
        start = minutes_to_hhmm(start_min)
        duration = end_min - start_min
        category = self.session.armed_category
        if category in FLEX_CATEGORIES:
            self._commit_homework(
                HomeworkDialog(
                    self,
                    category=category,
                    estimate_min=duration,
                    due=sunday_due(self.session.week_start),
                ),
                days=[day],
            )
            return
        self._commit_block(
            BlockDialog(
                self,
                day=day,
                start=start,
                duration_min=duration,
                category=category,
                from_range=True,
            )
        )

    def _due_point(self, block_id: str) -> tuple[int, int] | None:
        """The day and minute a homework session is due, for the calendar to refuse a drag past it."""
        block = next((item for item in self.session.blocks if item["id"] == block_id), None)
        assignment = self.session.assignments.get((block or {}).get("assignment_id") or "")
        if not assignment:
            return None
        return due_point(assignment.get("due"), self.session.week_start)

    def _delete_homework(self, assignment_id: str, ask: bool = True) -> None:
        """Homework and its times in every week, gone in one step that Undo brings back."""
        assignment = self.session.assignments.get(assignment_id)
        if assignment is None:
            return
        title = assignment.get("title") or "this homework"
        words = f"Delete {title}? Its times on the calendar go too, in every week. You can undo this."
        if ask and not confirm(self, "Delete homework", words, "Delete"):
            return
        if self.session.delete_homework(assignment_id):
            self._say_when_saved(f"Deleted {title}.")

    def _edit_homework(self, assignment_id: str) -> None:
        assignment = self.session.assignments.get(assignment_id)
        if assignment is None:
            return
        sessions = [block for block in self.session.blocks if block.get("assignment_id") == assignment_id]
        waiting = any(not block.get("start") and not block.get("completed") for block in sessions)
        pinned = any(block.get("pinned") for block in sessions)
        dialog = HomeworkDialog(self, assignment, waiting=waiting, pinned=pinned)
        self._commit_homework(dialog)

    def _choose_time(self, assignment_id: str) -> None:
        """A time for this homework's first session that needs one, picked rather than dragged."""
        waiting = [
            item
            for item in self.session.blocks
            if item.get("assignment_id") == assignment_id
            and not item.get("start")
            and not item.get("completed")
        ]
        if not waiting:
            return
        block = waiting[0]
        due = self._due_point(block["id"])
        days = list(block["days"])
        clock = clock_parts(self.session.now_ms())
        today = clock["day"] if monday_of(clock["iso"]) == self.session.week_start else None
        dialog = ChooseTimeDialog(
            self, block, self.session.week_start, days, self.session.blocks, due, today, clock["minute"]
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        day, start = dialog.choice()
        if self.session.place_session(block["id"], day, start):
            self.session.save()

    def _judge_span(self, block_id: str, from_day: int, day: int, start: int, end: int) -> HandVerdict:
        """Whether a block can go where it is being dragged, and the words for it. One rule for the
        calendar and every design: another block there is allowed, and said, as in Daily Scheduler;
        time FlexWeek does not plan in, and homework ending after it is due, are not."""
        block = next((item for item in self.session.blocks if item["id"] == block_id), None)
        if block is None:
            return HandVerdict(False, "")
        problem = self.session.span_drop_problem(block_id, day, start, end, from_day)
        if problem is not None:
            return HandVerdict(False, problem)
        clash = span_clash(self.session.blocks, block_id, day, start, end)
        return HandVerdict(True, span_words(Span(day, start, end)) + (f" · beside {clash}" if clash else ""))

    def _move_block(self, block_id: str, from_day: int, day: int, start: int, end: int) -> None:
        """A block let go at a time, on the calendar or in a design. Homework that needed a time gets
        this one; a block that repeats moves only the day it was dragged from; anything else moves.
        Whatever moves by hand is pinned, so no plan moves it back."""
        if self.session.busy:
            self._move_waiting = (block_id, from_day, day, start, end)
            return
        block = next((item for item in self.session.blocks if item["id"] == block_id), None)
        if block is None:
            return
        verdict = self._judge_span(block_id, from_day, day, start, end)
        if not verdict.ok:
            if verdict.words:
                self.session._say(verdict.words)
            return
        origin = from_day if from_day in block["days"] else day
        if not block.get("start"):
            changed = self.session.place_session(block_id, day, start)
        elif is_series(block):
            changed = self.session.move_occurrence(block_id, origin, day, start, end)
        else:
            changed = self.session.apply_times(block_id, start, end, day)
        if changed:
            self.session.save()
            self._say_when_saved(moved_words(block, origin, day, start, end))

    def _edit_block(self, block_id: str) -> None:
        if QApplication.activeModalWidget() is not None:
            # One editor at a time: a click that lands while one is opening opens nothing more.
            return
        if self.session.planner_view == "day":
            self.session.select_block(block_id, date.fromisoformat(self.session.selected_day).weekday())
        block = next((item for item in self.session.blocks if item["id"] == block_id), None)
        if block is None:
            return
        assignment_id = block.get("assignment_id")
        if assignment_id and assignment_id in self.session.assignments:
            self._edit_homework(assignment_id)
            return
        if block.get("kind") != "locked":
            return
        dialog = BlockDialog(
            self,
            block,
            occurrence_day=self.session.selected_occurrence_day,
        )
        self._commit_block(dialog)

    def _block_menu(self, block_id: str, day: int, at: QPoint) -> None:
        """A block's right-click menu: Open, Duplicate, Finished for homework, and Delete, each the
        path its button or key already takes. `day` is -1 for homework with no time yet."""
        block = next((item for item in self.session.blocks if item["id"] == block_id), None)
        if block is None:
            return
        on = day if day >= 0 else None
        self.session.select_block(block_id, on)
        assignment = self.session.assignments.get(block.get("assignment_id") or "")
        menu = Menu(self)
        menu.setObjectName("blockMenu")
        menu.set_colours(self.more_menu.colours())
        menu.add("Open", "pencil", keys="Enter", name="blockMenuOpen")
        if block.get("start"):
            menu.add("Duplicate", "copy-plus", keys="Ctrl+D", name="blockMenuDuplicate")
            menu.add("Copy", "copy", keys="Ctrl+C", name="blockMenuCopy")
        if assignment is not None and not assignment.get("completed"):
            menu.add("Finished", "circle-check", name="blockMenuFinished")
        menu.addSeparator()
        menu.add("Delete", "trash", keys="Del", danger=True, name="blockMenuDelete")
        chosen = menu.exec(at)
        menu.deleteLater()
        picked = chosen.objectName() if chosen is not None else ""
        if picked == "blockMenuOpen":
            self._edit_block(block_id)
        elif picked == "blockMenuDuplicate":
            self._duplicate_selected()
        elif picked == "blockMenuCopy":
            self.session.select_block(block_id, on)
            self._copy_selected()
        elif picked == "blockMenuFinished" and assignment is not None:
            self._finish_homework(assignment["id"])
        elif picked == "blockMenuDelete":
            self._delete_from_block_menu(block, assignment, on)

    def _delete_from_block_menu(self, block: dict, assignment: dict | None, on: int | None) -> None:
        if assignment is None:
            one_day = is_series(block) and on is not None
            name = (block.get("title") or "this event") + (f" on {DAY_FULL[on]}" if one_day else "")
            if confirm(self, "Delete event", f"Delete {name}? You can undo this.", "Delete"):
                self._delete_block(block, "occurrence" if one_day else "series", on)
            return
        if not block.get("start"):
            self._delete_homework(assignment["id"])
            return
        title = assignment.get("title") or "this homework"
        sessions = [
            item
            for item in self.session.blocks
            if item.get("assignment_id") == assignment["id"] and item.get("start")
        ]
        if len(sessions) <= 1:
            self._delete_homework(assignment["id"])
            return
        day_name = DAY_FULL[on] if on is not None else "this day"
        if confirm(self, "Delete", f"Delete {title} on {day_name}? You can undo this.", "This time"):
            self._delete_block(block, "occurrence", on)

    def _spot_menu(self, day: int, minute: int, at: QPoint) -> None:
        """What an empty spot in the hours offers: fixed time at the step under the pointer, homework
        due that day, and the copied blocks pasted there. Each opens the sheet the Add and Paste
        buttons open, with the day and time filled in."""
        menu = Menu(self)
        menu.setObjectName("spotMenu")
        menu.set_colours(self.more_menu.colours())
        menu.add(f"Add fixed time at {clock_text(minute)}", "clock", name="spotMenuFixed")
        menu.add("Add homework due this day", "book-open", name="spotMenuHomework")
        paste = menu.add("Paste", "clipboard-paste", name="spotMenuPaste")
        session = self.session
        if session.clipboard is None or session.busy:
            # Greyed as in More, with its reason: on the row when nothing is copied, else on hover.
            paste.setEnabled(False)
            waiting = session.busy or session.dirty or session.pending_save is not None
            paste.setToolTip(WAIT_TIP if waiting else GREYED_TIPS["pasteBlock"])
        chosen = menu.exec(at)
        menu.deleteLater()
        picked = chosen.objectName() if chosen is not None else ""
        if picked == "spotMenuFixed":
            self._add_fixed_at(day, minute)
        elif picked == "spotMenuHomework":
            self._add_homework_due(date_for_day(session.week_start, day))
        elif picked == "spotMenuPaste":
            self._told(lambda: self._paste_at(day, minute))

    def _show_preview(
        self,
        title: str,
        summary: str,
        rows: list[dict] | None,
        *,
        label: str,
        snapshot_label: str | None = None,
        attempt_key: str | None = None,
        existing: list[dict] | None = None,
        destination: str | None = None,
        done: str | None = None,
    ) -> None:
        """`done` is the verb that says what saving the rows did, as in "Pasted Piano"."""
        if not rows:
            return
        dialog = PreviewDialog(
            self,
            title,
            summary,
            rows,
            existing if existing is not None else self.session.blocks,
        )
        if not self._run_sheet(dialog):
            return
        chosen = [row for row in dialog.rows() if row.get("checked")]
        what = chosen[0]["block"]["title"] if len(chosen) == 1 else f"{len(chosen)} blocks"
        said = f"{done} {what}." if done and chosen else None
        self.session.confirm_preview(
            dialog.rows(),
            label=label,
            snapshot_label=snapshot_label,
            attempt_key=attempt_key,
            existing=existing,
            destination=destination,
            said=said,
        )

    def _copy_selected(self) -> None:
        self.session.copy_selected()

    def _paste_clipboard(self) -> None:
        self._paste_preview(self.session.paste_destination(), self.session.paste_proposals())

    def _paste_at(self, day: int, minute: int) -> None:
        start = minutes_to_hhmm(minute)
        self._paste_preview((day, start), self.session.paste_proposals(day, start))

    def _paste_preview(self, dest: tuple[int, str | None] | None, rows: list[dict] | None) -> None:
        clip = self.session.clipboard
        label = "pasting " + clip["label"] if clip else "pasting"
        key = None
        if clip and self.session.account is not None:
            key = (
                f"paste|{self.session.account['id']}|{self.session.week_start}|"
                f"{dest[0] if dest else ''}|{(dest[1] if dest else '') or ''}|"
                f"{clip['fingerprint']}"
            )
        self._show_preview(
            "Preview paste",
            "Nothing changes until you save this preview.",
            rows,
            label=label,
            attempt_key=key,
            done="Pasted",
        )

    def _duplicate_selected(self) -> None:
        chosen = next(
            (item for item in self.session.blocks if item["id"] == self.session.selected_block_id), None
        )
        rows = self.session.duplicate_selected()
        self._show_preview(
            "Preview paste",
            "Nothing changes until you save this preview.",
            rows,
            label="duplicating " + (chosen or {}).get("title", "a block"),
            done="Duplicated",
        )

    def _copy_day(self) -> None:
        self.session.copy_day()

    def _open_routines(self) -> None:
        dialog = RoutineDialog(self, self.session.routines, self.session.blocks, self.session.week_start)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.action == "save":
            self.session.save_routine(dialog.name.text(), dialog.selected_block_ids())
            return
        if dialog.action == "delete" and dialog.routine_id:
            self.session.delete_routine(dialog.routine_id)
            return
        if dialog.action == "apply" and dialog.routine_id:
            routine = self.session.routines.get(dialog.routine_id)
            dest = dialog.destination
            rows = self.session.apply_routine_rows(dialog.routine_id, dest, dialog.days)
            name = routine["name"] if routine else "routine"
            key = None
            if routine and self.session.account is not None:
                key = (
                    f"routine|{self.session.account['id']}|{dialog.routine_id}|"
                    f"{routine['revision']}|{dest}|" + ",".join(str(day) for day in dialog.days)
                )

            def show(existing: list[dict]) -> None:
                self._show_preview(
                    "Apply " + name,
                    "Uncheck holidays or adjust one-off times before saving.",
                    rows,
                    label="the " + name + " routine",
                    snapshot_label=restore_point_label("Before applying " + name + " to " + dest),
                    attempt_key=key,
                    existing=existing,
                    destination=dest,
                )

            if dest == self.session.week_start:
                show(self.session.blocks)
                return

            def ok(data: dict) -> None:
                show(list(data.get("blocks") or []))

            def err(error: object) -> None:
                self.session._say(getattr(error, "message", str(error)))

            self.session.client.request("GET", f"/api/week?week_start={dest}", None, ok, err)
            return

    def _sync_unfinished_badge(self, items: list[dict]) -> None:
        count = len(items)
        self.unfinished_badge.setText(
            f"Unfinished homework from earlier weeks · {count} item{'s' if count != 1 else ''}"
        )
        self.unfinished_badge.setVisible(bool(items))

    def _collapse_unfinished(self) -> None:
        self._unfinished_introduced = True
        items = self.session.unfinished()
        if items:
            self._sync_unfinished_badge(items)

    def _open_unfinished_from_badge(self) -> None:
        items = self.session.unfinished()
        if not items:
            self.unfinished_badge.hide()
            return
        self.unfinished_badge.hide()
        self.unfinished_panel.set_items(items)

    def _copy_last_week_fixed(self) -> None:
        rows = self.session.copy_last_week_fixed_rows()
        if not rows:
            try:
                previous = monday_of(
                    (date.fromisoformat(self.session.week_start) - timedelta(days=7)).isoformat()
                )
            except ValueError:
                self.session._say("There is nothing to copy from last week yet.")
                return

            def ok(data: dict) -> None:
                blocks = list(data.get("blocks") or [])
                self.session._drafts[previous] = {
                    "blocks": blocks,
                    "revision": data.get("revision", 0),
                    "assignments": self.session.assignments,
                    "trace": None,
                    "dirty": True,
                }
                rows = self.session.copy_last_week_fixed_rows()
                if rows:
                    self._show_preview(
                        "Copy last week's fixed times",
                        "Uncheck anything you do not want before saving.",
                        rows,
                        label="last week's fixed times",
                        existing=self.session.blocks,
                    )
                else:
                    self.session._say("There is nothing to copy from last week yet.")

            def err(error: object) -> None:
                self.session._say(getattr(error, "message", str(error)))

            self.session.client.request("GET", f"/api/week?week_start={previous}", None, ok, err)
            return
        self._show_preview(
            "Copy last week's fixed times",
            "Uncheck anything you do not want before saving.",
            rows,
            label="last week's fixed times",
            existing=self.session.blocks,
        )

    def _show_unfinished(self) -> None:
        items = self.session.unfinished()
        if not items:
            self.session._say(NOTHING_UNFINISHED)
        self.unfinished_badge.hide()
        self.unfinished_panel.set_items(items)

    def _plan_unfinished(self, assignment_id: str) -> None:
        item = self.session.assignments.get(assignment_id)
        rows = self.session.plan_unfinished(assignment_id)
        self._show_preview(
            "Plan unfinished homework",
            (item["title"] + " keeps its original deadline and progress.") if item else "",
            rows,
            label="unfinished homework",
            attempt_key=(
                f"unfinished|{self.session.account['id']}|{self.session.week_start}|"
                f"{assignment_id}|{self.session.remaining_for(assignment_id)}"
                if self.session.account
                else None
            ),
        )

    def _open_late(self) -> None:
        now = datetime.fromtimestamp(self.session.now_ms() / 1000)
        refusal = running_late_refusal(
            week_start=self.session.week_start,
            now=now,
            dirty=self.session.dirty,
            conflict=self.session.conflict,
            block_count=len(self.session.blocks),
        )
        if refusal:
            self.session._say(refusal)
            return
        # Rounded up: a start in the quarter hour that has already begun was a time gone by. After 23:45
        # there is no quarter left today, so it stays the last one.
        ahead, minute = next_slot(now.hour * 60 + now.minute)
        if ahead:
            minute = DAY_END_MIN - SLOT_MIN
        starting = now.replace(hour=minute // 60, minute=minute % 60, second=0, microsecond=0)
        from_start = late_from_start(minute)
        dialog = LateDialog(self, f"Starting from {hhmm_text(from_start)} today ({DAY_FULL[now.weekday()]}).")
        dialog.preview_requested.connect(
            lambda: self.session.preview_running_late(dialog.chosen_minutes(), starting)
        )
        self._late_dialog = dialog
        self.session.status.connect(dialog.error.setText)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        with contextlib.suppress(RuntimeError, TypeError):
            self.session.status.disconnect(dialog.error.setText)
        preview = self.session.late_preview
        self._late_dialog = None
        if accepted:
            self._commit_late(preview)
        else:
            self.session.late_preview = None
            if preview is not None:
                # The preview's "N tasks move" stood under the week as if something had moved.
                self.session._say("")

    def _commit_late(self, preview: dict | None) -> None:
        block = None if preview is None else preview.get("block")
        moved = len(((preview or {}).get("trace") or {}).get("moves") or [])
        if not self.session.accept_running_late() or not isinstance(block, dict):
            return
        self.session.select_block(block["id"], (block.get("days") or [0])[0])
        # "Is now locked" waits for the save that stores it. Said at once, it stood on screen for six
        # seconds even when that save failed and the late start was never kept.
        self._late_waiting = (block["id"], late_locked_line(block, moved))

    def _on_save_finished(self, stored: bool, said: str) -> None:
        change, self._change_saving = self._change_saving, None
        if stored and change is not None:
            self._change_saved = change
            self._show_change()
        elif stored and self._notice_step is not None and self.session.last_step() is not self._notice_step:
            # A later change, or an Undo, has taken the notice's step off the top: its Undo would now
            # take back something else.
            self.toast.hide()
            self._notice_step = None
        if self._late_waiting is None:
            return
        block_id, message = self._late_waiting
        if not stored:
            # "Not saved. …", which the toast has already said.
            self._late_waiting = None
        elif any(item["id"] == block_id for item in self.session.blocks):
            # A save already in flight when Running late was accepted finishes without the late start;
            # the wait is for the one that carries it.
            self._late_waiting = None
            self.session._say(message)

    def _open_spread(self, assignment_id: str) -> None:
        item = self.session.assignments.get(assignment_id)
        if item is None or item.get("completed"):
            return
        due_date = item["due"][:10]
        today = date.today().isoformat()
        base = self.session.selected_day if self.session.selected_day > today else today
        from_date = base if base <= due_date else due_date
        dialog = SpreadDialog(self, item, from_date)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._pending_spread_ui = True
        self.session.preview_spread(assignment_id, dialog.session_min(), dialog.from_iso())

    def _open_availability(self) -> None:
        if self.session.preferences is None:
            self.session._say("Still loading your settings…")
            return
        subjects = sorted(
            {str(item["course"]).strip() for item in self.session.assignments.values() if item.get("course")}
        )
        dialog = AvailabilityDialog(self, self.session.preferences, subjects)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.session.save_availability(
            dialog.protected(), dialog.study_windows(), dialog.day_cutoff(), dialog.work_windows()
        )

    def _show_recover(self, shown: bool) -> None:
        for widget in (self.recovery_code, self.new_recovery_password, self.recover_button):
            widget.setVisible(shown)

    def _recover_account(self) -> None:
        self.session.keep_signed_in = self.keep_signed_in.isChecked()
        self.session.recover(
            self.username.text().strip(),
            self.recovery_code.text().strip(),
            self.new_recovery_password.text(),
        )

    def _start_focus(self, block_id: str, day: object) -> None:
        if self.session.start_focus(block_id or None, day if isinstance(day, int) else None):
            self._open_focus_screen()

    def _quick_focus(self) -> None:
        """The focus screen, ready: nothing starts until Start, as with F (decision 19 of 0.17)."""
        self._open_focus_screen()

    def _start_quick_focus(self) -> None:
        if self.session.start_quick_focus():
            self._open_focus_screen()

    def _confirm_replace_focus(self, current: str, incoming: str) -> None:
        answer = QMessageBox.question(
            self,
            "Replace timer",
            f"Stop the timer for {current} and start {incoming} instead?",
        )
        if answer == QMessageBox.StandardButton.Yes and self.session.confirm_replace_focus():
            self._open_focus_screen()

    def _build_focus_screen(self) -> None:
        self.focus_screen = FocusScreen()
        screen = self.focus_screen
        screen.back_requested.connect(self._close_focus_screen)
        screen.start_requested.connect(self._start_quick_focus)
        screen.pause_requested.connect(self.session.toggle_focus_pause)
        screen.skip_requested.connect(lambda: self.session.advance_focus(False))
        screen.stop_requested.connect(self._stop_focus)
        screen.finished_requested.connect(self._finish_focus_homework)
        screen.break_requested.connect(self.session.take_focus_break)
        self._stack.addWidget(screen)

    def _open_focus_screen(self) -> None:
        if self.session.account is None:
            return
        self.focus_screen.set_state(self.session)
        self._show_page("focusPage")
        self.focus_screen.setFocus()

    def _close_focus_screen(self) -> None:
        if self._stack.currentWidget() is self.focus_screen:
            self._show_page("weekPage")
            self._focus_week()

    def _stop_focus(self) -> None:
        self.session.reset_focus()
        self._close_focus_screen()

    def _finish_focus_homework(self) -> None:
        if self.session.finish_focused_homework():
            self._close_focus_screen()

    def _commands(self) -> list[Command]:
        """What the command bar offers: the actions a student reaches for most, then each homework."""
        manual = (self.session.preferences or {}).get("planning_style") == "manual"
        plan = SUGGEST_LABEL if manual else PLAN_LABEL
        made = [
            Command("addHomework", "Add homework", MORE_TIPS["addHomework"], "Add", "book-open"),
            Command("addFixed", "Add fixed time", MORE_TIPS["addFixed"], "Add", "clock"),
            Command("schoolHours", "School hours", MORE_TIPS["schoolHours"], "Add", "school"),
            Command("day", "Day", "One day as a list", "Go to", "list", "D"),
            Command("week", "Week", "The week you are planning", "Go to", "calendar-days", "W"),
            Command("month", "Month", "The month as a calendar", "Go to", "calendar", "M"),
            Command("myDay", "My day", "Watch today", "Go to", "sun", "T"),
            Command("focus", "Focus screen", "The focus timer on its own, large.", "Go to", "timer", "F"),
            Command("settingsGear", "Settings", "", "Go to", "settings"),
            Command("helpButton", "Help", MORE_TIPS["helpButton"], "Go to", "circle-question-mark"),
            Command("solveButton", plan, SUGGEST_TIP if manual else PLAN_TIP, "Homework", "sparkles"),
            # Settings' pages by what they hold: "look" found nothing (Grok Bot's 0.17.0 audit, X1).
            Command("settings:0", "Look and colours", "Look, accent and design", "Settings", "palette"),
            Command("customise", "Customise look…", "Make a look of your own", "Settings", "swatch-book"),
            Command("settings:1", "Planning settings", "How homework gets a time", "Settings", "calendar"),
            Command("settings:2", "Focus settings", "The focus timer's lengths", "Settings", "timer"),
            Command("settings:3", "Alerts", "Reminders, alarms and sounds", "Settings", "bell"),
            Command("settings:4", "This computer", "Account, setup and updates", "Settings", "laptop"),
        ]
        homework = sorted(
            self.session.assignments.values(),
            key=lambda item: (bool(item.get("completed")), item.get("due") or "", item.get("title") or ""),
        )
        made.extend(
            Command(
                "homework:" + item["id"],
                item.get("title") or "Homework",
                "Open this homework",
                "Homework",
                "book-open",
            )
            for item in homework
        )
        return made

    def _open_command_bar(self) -> None:
        if self.session.account is not None:
            self.command_bar.open(self._commands())

    def _run_command(self, key: str) -> None:
        """As the button or the click the command stands for: a button greyed while FlexWeek is busy
        does nothing here either."""
        if key != "focus":
            self._close_focus_screen()
        if key.startswith("homework:"):
            self._edit_homework(key.removeprefix("homework:"))
        elif key in {"day", "week", "month"}:
            self._choose_view(key)
        elif key == "myDay":
            self._enter_day()
        elif key == "focus":
            self._open_focus_screen()
        elif key.startswith("settings:") or key == "customise":
            self._open_settings_at(0 if key == "customise" else int(key.removeprefix("settings:")))
            if key == "customise" and self._settings is not None:
                self._settings._open_customise()
        else:
            button = self.findChild(QPushButton, key)
            if button is not None:
                button.click()

    def _on_focus(self) -> None:
        self.focus_panel.set_state(self.session)
        self.focus_screen.set_state(self.session)
        self._sync_chrome()
        self._refresh_layout()

    def _present_alerts(self, notices: list) -> None:
        prefs = self.session.preferences or {}
        if notices and prefs.get("reminder_sound", True) is not False:
            # Reminders ring the chosen alarm sound. A focus notice keeps its own two tones until the
            # student picks a sound, then uses theirs. A Spotify sound never starts music for these.
            tone = prefs.get("alarm_tone")
            short = FALLBACK if tone in (None, "spotify") else str(tone)
            focus = [notice for notice in notices if notice.get("kind") == "focus"]
            if len(focus) < len(notices):
                self._bell.once(short, prefs.get("alert_volume", 80))
            elif prefs.get("end_chime"):
                own = str(focus[0].get("tone") or FALLBACK)
                self._bell.once(own if tone is None else short, prefs.get("alert_volume", 80))
        tray = self._tray_icon if self._tray_icon is not None and self._tray_icon.supportsMessages() else None
        reminders = []
        for notice in notices:
            title = notice.get("title") or "FlexWeek"
            body = notice.get("body") or ""
            words = title + (" — " + body if body else "")
            if tray is not None:
                tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 8000)
            if notice.get("kind") == "reminder":
                reminders.append(words)
            elif tray is None:
                self.session._say(words)
        if reminders:
            # A desktop can hide a tray message, and FlexWeek cannot tell that it did, so the window
            # says it as well, wherever the student is.
            self._reminder_said = "; ".join(reminders)
            self._say_in_toast(self._reminder_said)
        if notices and prefs.get("reminder_dnd_override"):
            # A tray message is gone in eight seconds and a machine may suppress it outright. This
            # one sits in the window until it is dealt with, which is what the setting promises.
            self.alert_strip.add(notices)

    def _on_alarm(self, alarm: object) -> None:
        if not isinstance(alarm, dict):
            return
        if self._alarm_dialog is not None:
            return
        url = self.session.spotify_url(alarm.get("spotify_url"))
        dialog = AlarmRingDialog(self, alarm, url)
        self._alarm_dialog = dialog
        self._ring(alarm, url)
        try:
            dialog.exec()
        finally:
            # Whatever closed the dialog, including the window shutting, the noise stops with it,
            # Spotify included.
            self._bell.stop()
            self._spotify.stop()
        snoozed = dialog.snoozed
        self._alarm_dialog = None
        self.session.finish_alarm(snoozed)

    def _ring(self, alarm: dict, url: str) -> None:
        """Play the alarm's own sound. "spotify" means the linked song or playlist in the student's
        Spotify app. Whatever it cannot be sure will play gets the tone too: a silent alarm is not an
        alarm."""
        prefs = self.session.preferences or {}
        tone = str(alarm.get("sound") or prefs.get("alarm_tone") or FALLBACK)
        if tone == "spotify" and not url:
            url = self.session.spotify_url(prefs.get("default_spotify_url") or "")
        if tone == "spotify" and url and self._spotify.play(url) in (LISTENING, STARTING):
            # Listening: the tone waits for `late`, and stops when Spotify is heard.
            return
        self._bell.start(FALLBACK if tone == "spotify" else tone, prefs.get("alert_volume", 80))

    def _spotify_late(self) -> None:
        if self._alarm_dialog is not None:
            self._bell.start(FALLBACK, (self.session.preferences or {}).get("alert_volume", 80))

    def _spotify_heard(self, words: str) -> None:
        if self._alarm_dialog is not None:
            self._bell.stop()
            self._alarm_dialog.show_playing(words)

    def _check_updates(self, *, asked: bool) -> None:
        """Look for a newer release. Asked for by the student, or once a day on its own.

        A check that finds nothing says nothing unless the student asked, because an app that
        interrupts to report that it is already up to date is an app people turn off.
        """
        if self._updater.busy:
            return
        if not asked and not due_for_check(self._updates, self.session.now_ms()):
            return
        self._update_asked = asked
        self._updates["last_ms"] = self.session.now_ms()
        self._save_look()
        if asked:
            self.session._say("Checking for updates…")
        self._updater.check()

    def _on_update_found(self, update: object) -> None:
        if not isinstance(update, dict):
            return
        if not self._update_asked and update["version"] == self._updates.get("skip"):
            return
        dialog = UpdateDialog(self, update, VERSION)
        self._update_dialog = dialog
        dialog.install.clicked.connect(lambda: self._updater.download(update))
        dialog.exec()
        if dialog.skip_this:
            self._updates["skip"] = update["version"]
            self._save_look()
        self._update_dialog = None

    def _on_update_progress(self, got: int, total: int) -> None:
        if self._update_dialog is not None:
            self._update_dialog.show_progress(got, total)

    def _on_update_problem(self, why: str) -> None:
        if self._update_dialog is not None:
            self._update_dialog.show_problem(why)
        elif self._update_asked:
            self.session._say(why)

    def _on_update_ready(self, path: str) -> None:
        """The download is verified and on disk. Putting it in place replaces the running app, so
        the app is closed either way: on Windows the installer takes over, and on Linux the files
        under it have just been swapped."""
        problem = apply_update(path)
        if problem is not None:
            if self._update_dialog is not None:
                self._update_dialog.show_problem(problem + " Open the release page to update by hand.")
            return
        if self._update_dialog is not None:
            self._update_dialog.accept()
        self.session._say("Update installed. FlexWeek will close so the new version can start.")
        QTimer.singleShot(UPDATE_QUIT_MS, self.quit_app)

    def _no_update(self) -> None:
        if self._update_asked:
            self.session._say(f"FlexWeek {VERSION} is the latest version.")

    def _update_unreachable(self, why: str) -> None:
        """A check nobody asked for fails quietly and tries again tomorrow. One the student asked for
        says so; saying nothing left "Checking for updates…" on screen as if it were still going."""
        if not self._update_asked:
            return
        self.session._say(why)
        self._set_notice(why, "Open release page", lambda: QDesktopServices.openUrl(QUrl(RELEASE_PAGE)))

    def _open_spotify(self) -> None:
        url = self.session.spotify_url()
        if not url:
            self.session._say("This item has no Spotify share link.")
            return
        open_in_app(url)

    def _open_settings_at(self, section: int) -> None:
        """Settings, open at one of its SECTIONS."""
        self._open_settings()
        if self._settings is not None and 0 <= section < len(SECTIONS):
            self._settings.nav.setCurrentRow(section)

    def _open_settings(self) -> None:
        """Settings fill the window in place of the week. Every change shows the moment it is made;
        there is no OK. The look and layout live on this device and are written at once. The
        account's choices are saved a moment after the last change, so typing "45" saves once rather
        than twice, and going back to the week saves whatever is left."""
        if self.session.preferences is None:
            self.session._say("Still loading your settings…")
            return
        if self._settings is not None:
            self._show_page("settingsPage")
            return
        page = SettingsPage(
            self, self.session.preferences, self._look, self.session.reminder_limits, self._layout,
            saved_looks=self._saved_looks,
        )
        page.motion_level = self._motion
        page.account_requested.connect(self._open_account)
        page.availability_requested.connect(self._open_availability)
        page.updates_requested.connect(lambda: self._check_updates(asked=True))
        page.setup_requested.connect(self._run_setup_again)
        page.closed.connect(self._close_settings)
        stored = page.updates()
        login = bool(stored["start_at_login"])

        def save() -> None:
            nonlocal stored
            wanted = page.updates()
            if wanted != stored and self.session.save_preferences(wanted):
                stored = wanted

        def apply() -> None:
            nonlocal login
            look, layout = page.look_choice(), page.layout_choice()
            if look != self._look or layout != self._layout or page.saved_looks != self._saved_looks:
                self._look = look
                self.session.look = look
                self._layout = layout
                self._saved_looks = list(page.saved_looks)
                self._save_look()
                self._on_week()
            wanted = page.updates()
            if self.session.preferences is not None:
                # Pack and accent belong to the account but are seen like the look: at once. The save
                # that follows stores them.
                live = (
                    "theme_pack",
                    "accent",
                    "accent_chips",
                    "motion",
                    "alarm_tone",
                    "planning_style",
                    "drag_step_min",
                    "clock_24h",
                )
                shown = {key: wanted[key] for key in live}
                self.session.preferences = {**self.session.preferences, **shown}
            if bool(wanted["start_at_login"]) != login:
                login = bool(wanted["start_at_login"])
                self._apply_start_at_login(login)
            self._apply_appearance()
            self._sync_chrome()
            saver.start()

        def finish(keep: bool) -> None:
            saver.stop()
            with contextlib.suppress(RuntimeError, TypeError):
                self.session.status.disconnect(page.say)
            if keep:
                save()

        saver = QTimer(page)
        saver.setSingleShot(True)
        saver.setInterval(SETTINGS_SAVE_MS)
        saver.timeout.connect(save)
        page.changed.connect(apply)
        self.session.status.connect(page.say)
        self._settings = page
        self._settings_finish = finish
        self._stack.addWidget(page)
        self._show_page("settingsPage")
        page.nav.setFocus()

    def _close_settings(self, *, save: bool = True, show_week: bool = True) -> None:
        """Back from Settings: what is not saved yet is saved, and the page is let go, so the next
        Settings opens on what the account holds then."""
        page, finish = self._settings, self._settings_finish
        if page is None or finish is None:
            return
        self._settings, self._settings_finish = None, None
        finish(save and self.session.account is not None)
        if show_week and self.session.account is not None:
            self._show_page("weekPage")
        self._stack.removeWidget(page)
        page.deleteLater()

    def _apply_start_at_login(self, wanted: bool) -> None:
        """The setting used to be stored on the account and obeyed by nothing. It is applied to this
        machine, since starting at login is a property of the machine rather than of the account."""
        if autostart.sync(wanted) is None and wanted:
            self.session._say("This machine does not support starting at login.")

    def _open_restore(self) -> None:
        dialog = RestoreDialog(
            self, self.session.restore_points, self.session.restore_preview, self.session.storage_info
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.action == "create":
            self.session.create_restore_point(dialog.create_label)
        elif dialog.action == "preview" and dialog.selected_id:
            self.session.preview_restore_point(dialog.selected_id, lambda: self._told(self._open_restore))
        elif dialog.action == "restore" and dialog.selected_id:
            answer = QMessageBox.question(
                self,
                "Restore",
                "Restore this snapshot? FlexWeek saves a restore point first.",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.session.apply_restore_point(dialog.selected_id)

    def _log_out(self) -> None:
        where = (
            "your FlexWeek server"
            if (self.session.storage_info or {}).get("mode") == "hosted"
            else "this computer"
        )
        if confirm(self, "Sign out", SIGN_OUT_QUESTION.format(where=where), "Sign out", danger=False):
            self.session.logout()

    def _open_help(self) -> None:
        HelpDialog(self).exec()

    def _open_about(self) -> None:
        AboutDialog(self, self.session.storage_info, str(self._look_path().parent)).exec()

    def _open_account(self) -> None:
        dialog = AccountDialog(self, self.session.recovery_remaining, self.session.storage_info)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        password = dialog.current_password.text()
        if dialog.action == "password":
            self.session.change_password(password, dialog.new_password.text())
        elif dialog.action == "codes":
            self.session.replace_recovery_codes(password)
        elif dialog.action == "delete":
            name = (self.session.account or {}).get("username") or "this account"
            where = (
                "your FlexWeek server"
                if (self.session.storage_info or {}).get("mode") == "hosted"
                else "this computer"
            )
            question = (
                f"Delete the account {name}? Every week, all your homework and your settings are removed "
                f"from {where}. This can't be undone."
            )
            if confirm(self, "Delete account", question, f"Delete {name}"):
                self.session.delete_account(password)
        elif dialog.action == "export":
            self.session.export_account(password, self._write_account_file)
        elif dialog.action == "import":
            path, _ = QFileDialog.getOpenFileName(self, "Import account", "", "JSON (*.json)")
            if not path:
                return
            try:
                snapshot = json.loads(Path(path).read_text())
            except (OSError, UnicodeDecodeError, ValueError) as error:
                self.session._say("Could not read that file. " + str(error))
                return
            if not isinstance(snapshot, dict):
                self.session._say("Choose a FlexWeek account transfer file.")
                return
            self.session.preview_account_import(snapshot, self._confirm_transfer)
        elif dialog.action == "week":
            self._write_json("flexweek-" + self.session.week_start + ".json", self.session.week_file())
        elif dialog.action == "day":
            destination = self.session.paste_destination()
            if destination is None:
                self.session._say("Select a day first.")
                return
            day = destination[0]
            self._write_json("flexweek-day.json", self.session.day_file(day))
        elif dialog.action == "import-week":
            path, _ = QFileDialog.getOpenFileName(self, "Import week or day", "", "JSON (*.json)")
            if not path:
                return
            try:
                raw = Path(path).read_text()
            except (OSError, UnicodeDecodeError) as error:
                self.session._say("Could not read that file. " + str(error))
                return
            parsed = parse_import_payload(raw)
            if parsed.get("error"):
                self.session._say(parsed["error"])
                return
            if parsed.get("format") == EXPORT_FORMAT and self.session.blocks:
                answer = QMessageBox.question(
                    self,
                    "Replace week",
                    "Replace blocks in "
                    + week_label(self.session.week_start)
                    + " with the import? Other weeks stay untouched.",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                self.session.import_week_file(raw, replace=True)
            else:
                self.session.import_week_file(raw)

    def _confirm_transfer(self) -> None:
        preview = self.session.transfer_preview
        if preview is None:
            return
        dialog = TransferPreviewDialog(self, preview)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.session.apply_account_import()

    def _write_account_file(self, snapshot: dict) -> None:
        name = "flexweek-account-" + snapshot.get("username", "account") + ".json"
        self._write_json(name, snapshot)

    def _write_json(self, name: str, payload: dict) -> None:
        import json

        path, _ = QFileDialog.getSaveFileName(self, "Save FlexWeek file", name, "JSON (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(payload, indent=2) + "\n")
        except OSError as error:
            self.session._say("Could not write that file. " + str(error))

    def _look_path(self) -> Path:
        root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        return root / "flexweek-look.json"

    def _load_look(self) -> None:
        import json

        path = self._look_path()
        if not path.is_file():
            return
        try:
            stored = json.loads(path.read_text())
        except OSError, ValueError:
            stored = None
        self._look = sanitize_look(stored)
        self._layout = sanitize_layout(stored.get("layout") if isinstance(stored, dict) else None)
        self._updates = sanitize_updates(stored.get("updates") if isinstance(stored, dict) else None)
        self._zoom = sanitize_zoom(stored.get("zoom") if isinstance(stored, dict) else None)
        self._saved_looks = sanitize_saved(stored.get("saved_looks") if isinstance(stored, dict) else None)
        rail = stored.get("rail") if isinstance(stored, dict) else None
        self.rail.set_month_shown(not (isinstance(rail, dict) and rail.get("month") is False))

    def _save_look(self) -> None:
        import json

        path = self._look_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            body = {
                **self._look,
                "layout": self._layout,
                "updates": self._updates,
                "zoom": self._zoom,
                "saved_looks": self._saved_looks,
                "rail": {"month": self.rail.month_shown},
            }
            path.write_text(json.dumps(body) + "\n")
        except OSError:
            self.session._say("Could not save the look for this device.")

    def _page_palette(self, palette: dict) -> dict | None:
        """The colours of the design on screen when it wears a colourway of its own, for its page
        only; None when the page wears the look, as Today's app and a design in Match my look do."""
        layout_id = self._layout["day"] if self._day_mode else self._layout["main"]
        if layout_id not in VIEW_CLASSES:
            return None
        colour = options_for(self._layout, layout_id)["colour"]
        if colour == MATCH:
            return None
        return palette_from_tokens(tokens_for(layout_id, colour, palette), palette)

    def _apply_appearance(self) -> None:
        """Dress the window in the student's look. The top bar, the frame, dialogs and Today's app
        always wear the look and its accent; a design's colourway colours only the design's own page
        (decision 3 of 0.17). When the design dressed the chrome, three accents were on screen before
        a student had placed any homework."""
        pack, system_dark, accent = self._look_inputs()
        # Blocks and month cells are painted per item, which a stylesheet cannot reach.
        palette = resolved_palette(pack, system_dark, self._look, accent)
        art = control_art(palette)
        sheet = pack_stylesheet(pack, system_dark, self._look, accent, palette, art)
        page = self._page_palette(palette)
        page_sheet = ""
        if page is not None:
            page_sheet = pack_stylesheet(pack, system_dark, self._look, accent, page, control_art(page))
        chips = bool((self.session.preferences or {}).get("accent_chips"))
        chosen_motion = (self.session.preferences or {}).get("motion")
        self._motion = motion_level(chosen_motion, look_motion(self._look))
        dressed = (sheet, repr(self._look), repr(palette), chips, self._motion)
        # Every change to the week comes through here. Restyling the whole window each time, when the
        # look had not changed, cost about 26 ms a change and repainted everything on screen.
        if dressed != self._dressed:
            self._dressed = dressed
            self.setStyleSheet(sheet)
            self._keep_bar_whole()
            apply_ui_effects(self._motion)
            self.toast.motion = self._motion
            self.command_bar.motion = self._motion
            self._dress_overlays(palette)
            self.week_table.set_look(self._look, palette)
            self.day_view.set_look(self._look, palette)
            self.rail.set_look(self._look, palette)
            self.month_grid.set_palette(palette)
            self.add_menu.set_palette(palette, chips)
            self._dress_entry(palette)
            self.setup_page.set_palette(palette)
        if page_sheet != self._page_sheet:
            # The planner holds the design's page and nothing of the chrome.
            self._page_sheet = page_sheet
            self.planner.setStyleSheet(page_sheet)
        self._sync_add_button()
        self._refresh_layout()

    def _dress_entry(self, palette: dict) -> None:
        """The eye in the muted text colour, and the sign-in and recovery cards lifted off the page
        with the large shadow, unless the look's shadows are flat or drawn as hard edges."""
        for field in (self.password, self.new_recovery_password):
            field.set_colour(palette["muted"])
        knobs = effective_look(self._look)
        soft = knobs["depth"] == "soft"
        for card in self._entry_cards:
            # As wide as its words: a card sized for Normal text cut Large text's lines short.
            card.setFixedWidth(round(AUTH_CARD_WIDTH * text_scale(self._look)))
            if soft:
                lift(card, SHADOW_LARGE, palette["axis"] == "dark")
            else:
                card.setGraphicsEffect(None)

    def _dress_overlays(self, palette: dict) -> None:
        """What a style sheet cannot reach in the focus screen, the toast, Ctrl+K and the menus: the
        ring's colours, icons in the text's colour, and shadows, which a look without depth goes
        without (decisions 6 and 19 to 22 of 0.17)."""
        knobs = effective_look(self._look)
        lifted = knobs["depth"] == "soft"
        dark = palette.get("axis") == "dark"
        corner = look_measures(self._look)["card_radius"]
        self.focus_screen.set_palette(palette, text_scale(self._look))
        self.toast.set_look(toast_colours(palette)["action"], SHADOW_SMALL if lifted else None, dark)
        self.command_bar.set_look(palette, SHADOW_LARGE if lifted else None, dark)
        colours = menu_colours(palette, lifted=lifted, corner=corner)
        for menu in (self.more_menu, self.add_menu):
            menu.set_colours(colours)

    def _install_tray(self) -> None:
        tray = QSystemTrayIcon(self._icon, self)
        menu = QMenu(self)
        show = menu.addAction("Show FlexWeek")
        show.triggered.connect(self.restore_window)
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_app)
        tray.setContextMenu(menu)
        tray.setToolTip("FlexWeek")
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray_icon = tray

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason != QSystemTrayIcon.ActivationReason.Context:
            self.restore_window()

    def restore_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._quitting = True
        if self._tray_icon is not None:
            self._tray_icon.hide()
        QApplication.quit()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        """Qt gives a right-click's context menu to the widget under the pointer only when the pointer
        did not move between the press and the release. A hand or a touchpad nearly always moves a few
        pixels, and the menu then came to the window instead, so a block's or free time's menu opened about
        one time in ten. It goes on to the widget the pointer is over."""
        target = QApplication.widgetAt(event.globalPos())
        by_mouse = event.reason() == QContextMenuEvent.Reason.Mouse
        if not by_mouse or target is None or target is self or self._relaying:
            super().contextMenuEvent(event)
            return
        self._relaying = True
        try:
            relayed = QContextMenuEvent(
                QContextMenuEvent.Reason.Mouse, target.mapFromGlobal(event.globalPos()), event.globalPos()
            )
            QApplication.sendEvent(target, relayed)
        finally:
            self._relaying = False
        event.setAccepted(relayed.isAccepted())

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        tray = self._tray_icon
        prefs = self.session.preferences or {}
        stay = prefs.get("tray_notifications", True) is not False
        if tray is not None and tray.isVisible() and not self._quitting and stay:
            self.hide()
            event.ignore()
            if not self._tray_hinted:
                self._tray_hinted = True
                tray.showMessage(
                    "FlexWeek is still running",
                    "It stays in the tray so reminders and alarms still work.",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
            return
        super().closeEvent(event)

    def _week_surfaces(self) -> list[HoursCanvas]:
        page = self.planner.currentWidget()
        if page is None or self._stack.currentWidget() is not self._week_page:
            return []
        return [hours for hours in page.findChildren(HoursCanvas) if hours.isVisible()]

    def _focus_week(self, placed: tuple[str, int, int] | None = None) -> None:
        """Keyboard focus back on the week: on `placed` (a block's id, day and start) when it is shown,
        else on the hours. Left alone it falls to whatever button comes next in the top bar, and a stray
        Space or Enter then turns the page. The ring is drawn when the student was last on the keyboard,
        never after a click."""
        surfaces = self._week_surfaces()
        if not surfaces:
            return
        shown = next(
            (hours for hours in surfaces if placed and hours.track_for(placed[1], placed[2])), surfaces[0]
        )
        shown.take_focus(self._last_input.keyboard, placed)

    def _focus_top_bar(self) -> None:
        """Esc in the hours: the keyboard goes up to the button for the view shown, which does nothing
        when pressed by mistake."""
        name = {"day": "viewDay", "month": "viewMonth"}.get(self.session.planner_view, "viewWeek")
        button = self.findChild(QPushButton, name)
        if button is not None:
            button.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _watch_field(self, _old: QWidget | None, now: QWidget | None) -> None:
        """A box on the week page that takes keys of its own is watched, so Ctrl+Z and Ctrl+Y reach the
        week through it while it has nothing typed to undo."""
        if (
            isinstance(now, EDITABLE)
            and not now.property("undoWatched")
            and self._week_page.isAncestorOf(now)
        ):
            now.setProperty("undoWatched", True)
            now.installEventFilter(self)

    @staticmethod
    def _undo_passes(box: QWidget, event: QKeyEvent) -> bool:
        """Whether Ctrl+Z or Ctrl+Y in `box` belongs to the week: the box has no typed text of its own
        to undo or redo."""
        control = event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)
        if not control or event.key() not in (Qt.Key.Key_Z, Qt.Key.Key_Y):
            return False
        line = box.findChild(QLineEdit) if isinstance(box, (QAbstractSpinBox, QComboBox)) else box
        if isinstance(line, QLineEdit):
            return not (line.isUndoAvailable() or line.isRedoAvailable())
        if isinstance(line, QPlainTextEdit):
            return not (line.document().isUndoAvailable() or line.document().isRedoAvailable())
        return True

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.session.account is None or QApplication.activeModalWidget() is not None:
            super().keyPressEvent(event)
            return
        if self._settings is not None and self._stack.currentWidget() is self._settings:
            # The week's keys do nothing to a week that is not on screen; Esc is Settings' own.
            super().keyPressEvent(event)
            return
        if self._on_recovery():
            super().keyPressEvent(event)
            return
        focus = QApplication.focusWidget()
        key = event.key()
        mods = event.modifiers()
        if isinstance(focus, EDITABLE) and not self._undo_passes(focus, event):
            super().keyPressEvent(event)
            return
        if key == Qt.Key.Key_Escape and not mods and isinstance(focus, HoursCanvas) and not self._day_mode:
            self._focus_top_bar()
            event.accept()
            return
        planning = self._stack.currentWidget() in (self.focus_screen, self.findChild(QWidget, "weekPage"))
        if self._stack.currentWidget() is self.focus_screen:
            if key == Qt.Key.Key_Escape:
                self._close_focus_screen()
                event.accept()
                return
            if key in (Qt.Key.Key_W, Qt.Key.Key_D, Qt.Key.Key_M, Qt.Key.Key_T) and not mods:
                self._close_focus_screen()
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            if key == Qt.Key.Key_K and planning:
                self._open_command_bar()
                event.accept()
                return
            if key == Qt.Key.Key_Z:
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    self._told(self.session.redo)
                else:
                    self._told(self.session.undo)
                event.accept()
                return
            if key == Qt.Key.Key_Y:
                self._told(self.session.redo)
                event.accept()
                return
            if key == Qt.Key.Key_C:
                self._told(self._copy_selected)
                event.accept()
                return
            if key == Qt.Key.Key_V:
                self._told(self._paste_clipboard)
                event.accept()
                return
            if key == Qt.Key.Key_D:
                self._told(self._duplicate_selected)
                event.accept()
                return
            if key == Qt.Key.Key_S:
                self._told(self.session.save)
                event.accept()
                return
            if key in ZOOM_KEYS:
                for hours in self._hours_shown():
                    hours.zoom_by(ZOOM_KEYS[key])
                event.accept()
                return
        if key == Qt.Key.Key_Delete:
            if self.session.delete_selected():
                self.session.save()
            event.accept()
            return
        if key == Qt.Key.Key_T:
            self._enter_day()
            event.accept()
            return
        if key == Qt.Key.Key_F and planning:
            self._open_focus_screen()
            event.accept()
            return
        if self._day_mode and key in (Qt.Key.Key_B, Qt.Key.Key_Escape):
            self._leave_day()
            event.accept()
            return
        if key == Qt.Key.Key_W:
            self._choose_view("week")
            event.accept()
            return
        if key == Qt.Key.Key_D:
            self._choose_view("day")
            event.accept()
            return
        if key == Qt.Key.Key_M:
            self._choose_view("month")
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(watched, event)
        if isinstance(watched, EDITABLE):
            # Only Ctrl+Z and Ctrl+Y, and only past a box with nothing of its own to undo.
            if watched.property("undoWatched") and self._undo_passes(watched, event):
                self.keyPressEvent(event)
                return True
            return super().eventFilter(watched, event)
        key = event.key()
        mods = event.modifiers()
        control = bool(mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        if not control and key in (
            Qt.Key.Key_W,
            Qt.Key.Key_D,
            Qt.Key.Key_M,
            Qt.Key.Key_T,
            Qt.Key.Key_F,
            Qt.Key.Key_Delete,
        ):
            self.keyPressEvent(event)
            return True
        if control and key in (
            Qt.Key.Key_C,
            Qt.Key.Key_V,
            Qt.Key.Key_D,
            Qt.Key.Key_Z,
            Qt.Key.Key_Y,
            Qt.Key.Key_S,
            Qt.Key.Key_K,
        ):
            self.keyPressEvent(event)
            return True
        return super().eventFilter(watched, event)
