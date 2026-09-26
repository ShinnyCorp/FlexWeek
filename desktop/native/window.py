"""Qt widgets window for the native FlexWeek desktop client."""

from __future__ import annotations

import contextlib
import json
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QKeyEvent,
    QPalette,
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
    QVBoxLayout,
    QWidget,
)

from backend.slots import minutes_to_hhmm
from desktop.native import autostart
from desktop.native.calendar import (
    CATEGORIES,
    DAY_FULL,
    FLEX_CATEGORIES,
    date_for_day,
    is_series,
    monday_of,
    span_clash,
    span_problem,
    sunday_due,
)
from desktop.native.client import PASSWORD_LENGTH_HINT, USERNAME_HINT, sign_in_problem, sign_up_problem
from desktop.native.controller import ROUTINE_STATUS, NativeSession
from desktop.native.files import EXPORT_FORMAT, parse_import_payload
from desktop.native.focus import phase_duration_ms
from desktop.native.fonts import load_fonts
from desktop.native.hours.chips import TrayChip
from desktop.native.hours.classic import ClassicDay, ClassicWeek
from desktop.native.hours.geometry import Span, drag_step
from desktop.native.hours.hand import Create, Hand, Move, MoveDate, Place, span_words
from desktop.native.hours.hand import Verdict as HandVerdict
from desktop.native.hours.month import MonthGrid
from desktop.native.hours.zoom import ZOOM_KEYS, HoursScroll, sanitize_zoom
from desktop.native.kept import KeptSession
from desktop.native.layouts.base import LayoutView, Scene
from desktop.native.layouts.registry import options_for, sanitize_layout, tokens_for
from desktop.native.layouts.views import VIEW_CLASSES
from desktop.native.look import (
    TEXT_PT,
    effective_look,
    pack_motion,
    pack_stylesheet,
    palette_from_tokens,
    resolved_palette,
    sanitize_look,
)
from desktop.native.motion import appear, apply_ui_effects, fade_away, hold_picture, motion_level, switch_page
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
    AboutDialog,
    AccountDialog,
    AlarmRingDialog,
    FocusPanel,
    HelpDialog,
    PrefsDialog,
    RestoreDialog,
    TransferPreviewDialog,
    UpdateDialog,
)
from desktop.native.setup import REMINDERS, SETUP_VERSION, STYLE, SetupPage, SetupState
from desktop.native.sound import Bell
from desktop.native.spotify import LISTENING, STARTING, SpotifyPlayer, open_in_app
from desktop.native.tones import FALLBACK
from desktop.native.update import RELEASE_PAGE, due_for_check, sanitize_updates
from desktop.native.updater import Updater, apply_update
from desktop.native.version import VERSION
from desktop.native.weekmodel import added_words, build_week, dated_words, moved_words
from desktop.native.widgets import (
    REPLAN_TIP,
    AddMenu,
    AlertStrip,
    AvailabilityDialog,
    BlockDialog,
    ChooseTimeDialog,
    EndsLayout,
    FittedButton,
    FittedLabel,
    FlowLayout,
    HomeworkDialog,
    LateDialog,
    PlanReview,
    PreviewDialog,
    RoutineDialog,
    SpreadDialog,
    Toast,
    UnfinishedPanel,
    add_heading,
    confirm,
    control_art,
    steady_wheel,
    swatch,
)

WINDOW_SIZE = (1280, 800)
WINDOW_MIN_WIDTH = 640
# The longest the old week's picture waits for the next one before it fades anyway.
TRAVEL_WAIT_MS = 900
PLAN_LABEL = "Plan my homework"
# The widest an Undo notice's words go before they wrap, beside the status line.
NOTICE_MAX_WIDTH = 520
SUGGEST_LABEL = "Suggest times"
PLAN_TIP = (
    "Find a time for homework that has none, around your fixed times and before it is due. Homework "
    "that already has a time keeps it."
)
SUGGEST_TIP = "Give homework without a time a suggested time. Drag any of them somewhere else if you like."
NOTHING_UNFINISHED = "Nothing is unfinished: no homework from earlier weeks still needs time."
QUICK_FOCUS_TIP = (
    "Start a {minutes}-minute focus timer now, without picking homework. "
    "Change its length in Settings > Focus."
)
# Hover words for More and Advanced, by the object name of the button each action presses.
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
LOG_OUT_QUESTION = (
    "Log out of FlexWeek on this computer? Your plans stay saved in your account. You'll need your "
    "password to sign in again."
)
# What they say on a top bar with no room for the whole words.
PLAN_SHORT = "Plan"
SUGGEST_SHORT = "Suggest"
NAV_ARROW_PX = 34
AUTH_CARD_WIDTH = 380
# Long enough for the student to read that the update installed before the window goes.
UPDATE_QUIT_MS = 1200
# How long after the last change the week saves itself. Long enough that dragging a block does not
# post on every pixel, short enough that closing the laptop straight after a change keeps it.
AUTOSAVE_AFTER_MS = 1500
# A failed save keeps its payload and its operation id, so trying again writes the same thing once.
AUTOSAVE_RETRY_MS = 6000
AUTOSAVE_TICK_MS = 500
LAYOUT_TICK_MS = 20_000
# Space between the top bar and a notice under it.
TOAST_GAP = 8
# How long Settings waits after the last change before saving it to the account. Long enough that
# typing a number or clicking through a menu is one save.
SETTINGS_SAVE_MS = 600
# Homework named on a Find a new time notice before the rest is counted.
NOTICE_LINES = 3


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
        self._travel_picture: QLabel | None = None
        self._travel_direction = 0
        self._stack.setObjectName("nativeStack")
        self.setCentralWidget(self._stack)
        self._more_pairs = []
        self._layout = sanitize_layout(None)
        self._day_mode = False
        self._opened_on_preference = False
        self._views: dict[str, LayoutView] = {}
        self._making_account = False
        self._updates = sanitize_updates(None)
        self._zoom: dict[str, int] = {}
        self._shown: tuple | None = None
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
        # A block let go while a save is under way, moved once it is done: the save's reply replaces
        # the week, so a move made before it arrived would be lost.
        self._move_waiting: tuple[str, int, int, int, int] | None = None
        self._date_waiting: MoveDate | None = None
        # What a drag changed, said with Undo once its save lands: the words for the save on its way,
        # and words waiting for the pointer to let go, since the notice pushes the hours down.
        self._change_saving: str | None = None
        self._change_saved: str | None = None
        # The Undo step a change notice offers to take back.
        self._notice_step: dict | None = None
        # Something asked for is under way; the next thing the status line says is what it did.
        self._telling = False
        self._month_revealed: tuple | None = None
        self._changed_ms = 0
        self._last_try_ms = 0
        self._autosave = QTimer(self)
        self._autosave.setInterval(AUTOSAVE_TICK_MS)
        self._autosave.timeout.connect(self._autosave_tick)
        self._autosave.start()
        self._build_auth()
        self._build_recovery()
        self._build_week()
        self._build_setup()
        self.session.account_changed.connect(self._on_account)
        self.session.recovery_codes.connect(self._show_recovery)
        self.session.week_changed.connect(self._on_week)
        self.session.status.connect(self._on_status)
        self.session.status.connect(self._tell)
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
        # The reminder the status line is keeping, until something more important or "Got it".
        self._held_reminder: str | None = None
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
        self._making_account = not self._making_account
        self._sync_auth_mode()

    def _sync_auth_mode(self) -> None:
        """Sign in is the door, and creating an account is the small print under it: a student signs
        in many times and creates an account once."""
        making = self._making_account
        self.auth_heading.setText("Create your account" if making else "Sign in")
        self.auth_note.setText(
            "FlexWeek fits homework around school and sports. Your week is saved to your account."
            if making
            else "Welcome back."
        )
        self.create_button.setVisible(making)
        self.sign_in_button.setVisible(not making)
        self.password_hint.setVisible(making)
        self.username_hint.setVisible(making)
        self.auth_switch.setText(
            "Already have an account? Sign in" if making else "New here? Create an account"
        )
        self.sign_in_button.setDefault(not making)
        self.create_button.setDefault(making)

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
                switch_page(self._stack, page, self._motion)
                return

    def _build_auth(self) -> None:
        page = QWidget()
        page.setObjectName("authPage")
        # The first screen anyone sees. Left to a plain page layout it stretched every field and
        # button the full width of the window, so it read as an unstyled form with a lot of nothing
        # under it. The content sits in a card of its own, centred.
        outer = QVBoxLayout(page)
        outer.addStretch(1)
        middle = QHBoxLayout()
        middle.addStretch(1)
        card = QWidget()
        card.setObjectName("authCard")
        card.setMaximumWidth(AUTH_CARD_WIDTH)
        card.setMinimumWidth(AUTH_CARD_WIDTH)
        middle.addWidget(card)
        middle.addStretch(1)
        outer.addLayout(middle)
        outer.addStretch(1)
        layout = QVBoxLayout(card)
        brand = QLabel("FlexWeek")
        brand.setObjectName("authBrand")
        layout.addWidget(brand)
        self.auth_heading = QLabel()
        self.auth_heading.setObjectName("authHeading")
        layout.addWidget(self.auth_heading)
        self.auth_note = QLabel()
        self.auth_note.setObjectName("authNote")
        self.auth_note.setWordWrap(True)
        layout.addWidget(self.auth_note)
        self.username = QLineEdit()
        self.username.setObjectName("username")
        self.username.setMaxLength(32)
        self.username.setPlaceholderText("Username")
        layout.addWidget(self.username)
        self.username_hint = QLabel(USERNAME_HINT)
        self.username_hint.setObjectName("usernameHint")
        self.username_hint.setWordWrap(True)
        layout.addWidget(self.username_hint)
        self.password = QLineEdit()
        self.password.setObjectName("password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setMaxLength(128)
        self.password.setPlaceholderText("Password")
        password_row = QHBoxLayout()
        password_row.addWidget(self.password, 1)
        self.password_reveal = QPushButton("Show")
        self.password_reveal.setObjectName("passwordReveal")
        self.password_reveal.setCheckable(True)
        self.password_reveal.toggled.connect(self._toggle_password)
        password_row.addWidget(self.password_reveal)
        layout.addLayout(password_row)
        self.password_hint = QLabel(PASSWORD_LENGTH_HINT)
        self.password_hint.setObjectName("passwordHint")
        self.password_hint.setWordWrap(True)
        layout.addWidget(self.password_hint)
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
        forgot = QPushButton("Forgot password")
        forgot.setObjectName("forgotPassword")
        forgot.setFlat(True)
        forgot.setCursor(Qt.CursorShape.PointingHandCursor)
        forgot.clicked.connect(self._toggle_recover)
        layout.addWidget(forgot)
        self.auth_switch = QPushButton()
        self.auth_switch.setObjectName("authSwitch")
        self.auth_switch.setFlat(True)
        self.auth_switch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auth_switch.clicked.connect(self._toggle_auth_mode)
        layout.addWidget(self.auth_switch)
        self.recovery_code = QLineEdit()
        self.recovery_code.setObjectName("recoveryCode")
        self.recovery_code.setPlaceholderText("Recovery code")
        self.recovery_code.setVisible(False)
        layout.addWidget(self.recovery_code)
        self.new_recovery_password = QLineEdit()
        self.new_recovery_password.setObjectName("recoverPassword")
        self.new_recovery_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_recovery_password.setPlaceholderText("New password")
        self.new_recovery_password.setVisible(False)
        layout.addWidget(self.new_recovery_password)
        self.recover_button = QPushButton("Reset password")
        self.recover_button.setObjectName("recoverAccount")
        self.recover_button.setVisible(False)
        self.recover_button.clicked.connect(self._recover_account)
        layout.addWidget(self.recover_button)
        self.auth_status = QLabel()
        self.auth_status.setObjectName("authStatus")
        self.auth_status.setWordWrap(True)
        layout.addWidget(self.auth_status)
        self._stack.addWidget(page)

    def _build_recovery(self) -> None:
        page = QWidget()
        page.setObjectName("recoveryPage")
        outer = QVBoxLayout(page)
        outer.addStretch(1)
        middle = QHBoxLayout()
        middle.addStretch(1)
        card = QWidget()
        card.setObjectName("authCard")
        card.setMaximumWidth(AUTH_CARD_WIDTH)
        card.setMinimumWidth(AUTH_CARD_WIDTH)
        layout = QVBoxLayout(card)
        brand = QLabel("FlexWeek")
        brand.setObjectName("authBrand")
        layout.addWidget(brand)
        heading = QLabel("Save these recovery codes")
        heading.setObjectName("authHeading")
        layout.addWidget(heading)
        note = QLabel(
            "They are the only way to reset your password. FlexWeek cannot email you. "
            "Copy them somewhere you will still have if this computer is gone."
        )
        note.setWordWrap(True)
        note.setObjectName("authNote")
        layout.addWidget(note)
        self.recovery_list = QLabel()
        self.recovery_list.setObjectName("recoveryList")
        self.recovery_list.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.recovery_list)
        self.recovery_ack = QCheckBox("I have saved these codes")
        self.recovery_ack.setObjectName("recoveryAck")
        self.recovery_ack.toggled.connect(self._on_recovery_ack)
        layout.addWidget(self.recovery_ack)
        self.recovery_continue = QPushButton("Continue to my week")
        self.recovery_continue.setObjectName("recoveryContinue")
        self.recovery_continue.setEnabled(False)
        self.recovery_continue.clicked.connect(self._finish_recovery)
        layout.addWidget(self.recovery_continue)
        middle.addWidget(card)
        middle.addStretch(1)
        outer.addLayout(middle)
        outer.addStretch(1)
        self._stack.addWidget(page)

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
        # Where you are, said once and said large. Thirteen buttons of equal weight and no title at
        # all was the clutter: nothing told the eye where to land.
        self.week_title = FittedLabel()
        self.week_title.setObjectName("weekTitle")
        where.addWidget(self.week_title)
        self.prev_nav = QPushButton("‹")
        self.prev_nav.setObjectName("prevWeek")
        self.prev_nav.setToolTip("Previous week")
        self.prev_nav.clicked.connect(self._go_previous)
        self.next_nav = QPushButton("›")
        self.next_nav.setObjectName("nextWeek")
        self.next_nav.setToolTip("Next week")
        self.next_nav.clicked.connect(self._go_next)
        today = QPushButton("Today")
        today.setObjectName("todayWeek")
        today.setToolTip("Jump to today")
        today.clicked.connect(self._go_today)
        for arrow in (self.prev_nav, self.next_nav):
            arrow.setFixedWidth(NAV_ARROW_PX)
            where.addWidget(arrow)
        where.addWidget(today)
        # One control, not four loose buttons: switching view is one decision.
        for view, label, tip in (
            ("day", "Day", "One day as a list"),
            ("week", "Week", "The week you are planning"),
            ("month", "Month", "The month as a calendar"),
        ):
            button = QPushButton(label)
            button.setObjectName(f"view{view.title()}")
            button.setProperty("segment", "middle" if view == "week" else view)
            button.setCheckable(True)
            button.setToolTip(tip)
            button.clicked.connect(lambda checked=False, value=view: self._choose_view(value))
            self._bar_views.addWidget(button)
        my_day = QPushButton("My day")
        my_day.setObjectName("viewMyDay")
        my_day.setCheckable(True)
        my_day.setToolTip("Watch today")
        my_day.clicked.connect(self._enter_day)
        self._bar_views.addWidget(my_day)
        self.account_name = QLabel()
        self.account_name.setObjectName("accountName")
        self.account_name.setVisible(False)
        self._bar_views.addWidget(self.account_name)
        sign_out = QPushButton("Log out")
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
        self.add_menu.category_chosen.connect(self._add_from_chip)
        add_button = QPushButton("Add")
        add_button.setObjectName("addButton")
        add_button.setMenu(self.add_menu)
        # Kept so the shortcuts and the tests that press them still have something to press; the
        # calendar's own context menu reaches them too.
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
        solve = FittedButton(PLAN_LABEL, PLAN_SHORT)
        solve.setObjectName("solveButton")
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
        more = QPushButton("More")
        more.setObjectName("moreButton")
        overflow = QWidget(page)
        overflow.setObjectName("moreOverflow")
        overflow.hide()
        more_menu = QMenu(more)
        more_menu.setToolTipsVisible(True)
        self._more_pairs = []
        self._spotify_action = None
        self.quick_focus = QPushButton("Quick focus")
        self.quick_focus.setObjectName("quickFocusAction")
        self.quick_focus.clicked.connect(self.session.start_quick_focus)
        self._groups = (
            ("Adding", (add_homework, school_hours, add_fixed)),
            ("Planning", (late, unfinished, routines, self.quick_focus, spotify, replan)),
        )
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
                action = more_menu.addAction(button.text())
                action.triggered.connect(button.click)
                self._more_pairs.append((action, button))
                if button is spotify:
                    self._spotify_action = action
        advanced_menu = more_menu.addMenu("Advanced")
        advanced_menu.setToolTipsVisible(True)
        for button in self._advanced:
            if button.parent() is not overflow:
                button.setParent(overflow)
            action = advanced_menu.addAction(button.text())
            action.triggered.connect(lambda _=False, pressed=button: self._told(pressed.click))
            self._more_pairs.append((action, button))
        help_button = QPushButton("Help")
        help_button.setObjectName("helpButton")
        help_button.clicked.connect(self._open_help)
        about = QPushButton("About FlexWeek")
        about.setObjectName("aboutButton")
        about.clicked.connect(self._open_about)
        more_menu.addSeparator()
        for button in (help_button, about, sign_out):
            if button.parent() is not overflow:
                button.setParent(overflow)
            button.hide()
            action = more_menu.addAction(button.text())
            action.triggered.connect(button.click)
            self._more_pairs.append((action, button))
        more_menu.aboutToShow.connect(self._sync_more_menu)
        more.setMenu(more_menu)
        gear = QPushButton("⚙\ufe0e")
        gear.setObjectName("settingsGear")
        gear.setToolTip("Settings")
        gear.setAccessibleName("Settings")
        gear.clicked.connect(self._open_settings)
        # The week saves itself now, so Save is not a thing to press; it stays reachable under More
        # and on Ctrl+S for anyone who wants to be sure. Retry appears only when a save has failed.
        for shown in (solve, retry, more, gear):
            self._bar_views.addWidget(shown)
        self.solve_button = solve
        self.more_button = more
        self.settings_gear = gear
        for hidden in (add_button, add_homework, add_fixed, save, self.quick_focus):
            actions.addWidget(hidden)
        for hidden in (add_button, add_homework, add_fixed, save, self.quick_focus):
            hidden.setVisible(False)
        chrome.addLayout(actions)
        self.retry_button = retry
        self.clipboard_summary = QLabel("Nothing copied")
        self.clipboard_summary.setObjectName("clipboardSummary")
        chrome.addWidget(self.clipboard_summary)
        self.focus_panel = FocusPanel()
        self.focus_panel.start_requested.connect(self._start_focus)
        self.focus_panel.quick_requested.connect(self.session.start_quick_focus)
        self.focus_panel.pause_requested.connect(self.session.toggle_focus_pause)
        self.focus_panel.skip_requested.connect(lambda: self.session.advance_focus(False))
        self.focus_panel.reset_requested.connect(self.session.reset_focus)
        self.focus_panel.finished_requested.connect(self.session.finish_focused_homework)
        self.focus_panel.break_requested.connect(self.session.take_focus_break)
        self.focus_panel.more_requested.connect(self.session.add_focus_time)
        layout.addWidget(self.focus_panel)
        # Neither is inside the planning chrome, which a design of its own hides: More > Unfinished
        # and Plan can be pressed from any design, and what they show is the point of pressing them.
        self.unfinished_panel = UnfinishedPanel()
        self.unfinished_panel.plan_requested.connect(self._plan_unfinished)
        layout.addWidget(self.unfinished_panel)
        self.plan_review = PlanReview()
        self.plan_review.replan_requested.connect(lambda: self.session.solve(everything=True))
        layout.addWidget(self.plan_review)
        self.alert_strip = AlertStrip()
        self.alert_strip.handled.connect(self._release_status)
        layout.addWidget(self.alert_strip)
        self.planner = QStackedWidget()
        self.planner.setObjectName("plannerStack")
        # One pointer for every gesture on every surface: it follows a drag and reports one change.
        self.hand = Hand(self._hand_judge, self)
        self.hand.committed.connect(self._apply_change)
        self.hand.refused.connect(self.session._say)
        self.hand.opened.connect(self._edit_block)
        self.hand.selected.connect(self.session.select_block)
        self.hand.holding.connect(self._hold_renders)
        self.hand.date_judge = self._date_judge
        # Today's app, as Daily Scheduler draws it: a Week that scrolls and a full-width Day.
        self.week_table = ClassicWeek(self.hand)
        self.week_table.day_opened.connect(self._open_week_day)
        self.planner.addWidget(self.week_table)
        self.day_view = ClassicDay(self.hand)
        self.planner.addWidget(self.day_view)
        for hours in (self.week_table.scroll, self.day_view.scroll):
            hours.zoomed.connect(self._remember_zoom)
        self.month_grid = MonthGrid(hand=self.hand)
        self.month_grid.day_activated.connect(self.session.open_day)
        self.planner.addWidget(self.month_grid)
        for widget in (
            self.week_table.hours,
            self.day_view.hours,
            self.month_grid.canvas,
            self.focus_panel.tasks,
        ):
            widget.installEventFilter(self)
        # The calendar is the point of this page, so it takes whatever height the rest does not need.
        self.classic_waiting = QFrame()
        self.classic_waiting.setObjectName("classicWaiting")
        self.classic_waiting_row = QHBoxLayout(self.classic_waiting)
        self._waiting_shown: tuple = ()
        self.classic_waiting_row.setContentsMargins(8, 4, 8, 4)
        self.classic_waiting.hide()
        layout.addWidget(self.classic_waiting)
        self.action_notice = QFrame()
        self.action_notice.setObjectName("actionNotice")
        notice_row = QHBoxLayout(self.action_notice)
        notice_row.setContentsMargins(8, 4, 8, 4)
        self.action_notice_text = QLabel()
        self.action_notice_text.setObjectName("actionNoticeText")
        self.action_notice_text.setWordWrap(True)
        self.action_notice_button = QPushButton()
        self.action_notice_button.setObjectName("actionNoticeButton")
        self._notice_callback = lambda: None
        self.action_notice_button.clicked.connect(lambda: self._notice_callback())
        notice_row.addWidget(self.action_notice_text, 1)
        notice_row.addWidget(self.action_notice_button)
        self.action_notice.hide()
        layout.addWidget(self.planner, 1)
        self.week_status = QLabel()
        self.week_status.setObjectName("weekStatus")
        self.week_status.setWordWrap(True)
        # The notice shares the status line's row, under the hours, and the row keeps the notice's
        # height whether or not it shows. Over the hours, each drag's notice pushed the whole page
        # down under the pointer, and on a short window put the next drop where the hours scroll.
        foot = QWidget()
        foot.setObjectName("statusRow")
        foot_row = QHBoxLayout(foot)
        foot_row.setContentsMargins(0, 0, 0, 0)
        foot_row.addWidget(self.week_status, 1)
        foot_row.addWidget(self.action_notice)
        self._status_row = foot
        layout.addWidget(foot)
        self._stack.addWidget(page)
        self.toast = Toast(self, self._toast_top)

    def _toast_top(self) -> int:
        """Just under the top bar, however tall large text makes it."""
        page = self._top_bar.parentWidget()
        if page is None:
            return TOAST_GAP
        return page.mapTo(self, QPoint(0, self._top_bar.geometry().bottom())).y() + TOAST_GAP

    def _planner_widget(self, view: str) -> QWidget:
        """The chosen main view stands in for the week grid, and for Day and Month too.

        Today's app keeps the clock-order Day list and the chip Month. My day is still its own
        screen. A design of its own rebuilds Day and Month in that design, so the app is not two
        programs once you leave the week.
        """
        if self._day_mode:
            return self._layout_view(self._layout["day"])
        main = self._layout["main"]
        if main in VIEW_CLASSES and view in {"week", "day", "month"}:
            return self._layout_view(main)
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
            view.day_activated.connect(self.session.open_day)
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
        return Scene(
            week=build_week(session.week_start, session.blocks, session.assignments, session.trace),
            today=clock["day"] if monday_of(clock["iso"]) == session.week_start else None,
            minute=clock["minute"],
            options=options,
            tokens=tokens_for(layout_id, options["colour"], palette),
            scale=TEXT_PT[effective_look(self._look)["text"]] / TEXT_PT["normal"],
            surface=surface,
            month=session.month_data,
            iso_day=session.selected_day,
            dirty=session.dirty,
            unsaved_weeks=session.unsaved_weeks(),
        )

    def _chrome_palette(self, palette: dict) -> dict:
        """The colours of the design the student picked, for the whole window.

        This used to read whichever widget was on screen, which meant the design dressed the week and
        nothing else: pressing Day or Month dropped back to the pack's own blue, and the app looked
        like two different programs. A layout is a whole way of showing a week, not a skin for one
        page of it, so the choice decides the colours wherever you are in the planner.
        """
        layout_id = self._layout["day"] if self._day_mode else self._layout["main"]
        if layout_id not in VIEW_CLASSES:
            # Classic is the app's own look, which is the pack, so there is nothing to derive.
            return palette
        options = options_for(self._layout, layout_id)
        return palette_from_tokens(tokens_for(layout_id, options["colour"], palette), palette)

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
        self.focus_panel.show_now_next(self.session.now_next_text())

    def _sync_chrome(self) -> None:
        """Planning chips and the clipboard line step aside for a design of its own. Plan my
        homework and More stay in the top bar in every layout, every view, and My day. The hand
        drags in the step the student chose."""
        self.hand.step = drag_step((self.session.preferences or {}).get("drag_step_min"))
        manual = (self.session.preferences or {}).get("planning_style") == "manual"
        # A student who places homework by hand asks for ideas; the plan is theirs.
        self.solve_button.set_texts(*((SUGGEST_LABEL, SUGGEST_SHORT) if manual else (PLAN_LABEL, PLAN_SHORT)))
        self.solve_button.setToolTip(SUGGEST_TIP if manual else PLAN_TIP)
        self._keep_bar_whole()
        own = isinstance(self.planner.currentWidget(), LayoutView)
        self.plan_chrome.setVisible(not own)
        self.focus_panel.setVisible(not own or self.session.focus is not None)
        if own:
            # Picking what to focus on is planning. Left in, the picker took the height and the day
            # screen's title was cut off after its first line.
            self.focus_panel.tasks.hide()
            self.focus_panel.tasks_label.hide()
        # Quick focus is in the action row whenever there is one, so the panel's own copy would be
        # the same button twice; it belongs to the panel only where no action row is shown.
        self.focus_panel.quick.setVisible(own and self._day_mode)

    def _keep_bar_whole(self) -> None:
        """The window is never narrower than the top bar's buttons at their smallest, which large
        text, Suggest times and Retry save each widen."""
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

    def _enter_day(self) -> None:
        if self.session.account is None:
            return
        self._day_mode = True
        self._on_week()
        self._views[self._layout["day"]].setFocus()

    def _leave_day(self) -> None:
        self._day_mode = False
        self._on_week()

    def _on_account(self, account: object) -> None:
        if account is None:
            self._day_mode = False
            self._opened_on_preference = False
            self._making_account = False
            self._setup_active = False
            self._setup_checked = False
            self._setup_prefs = {}
            self._setup_work_windows = None
            self._setup_week = False
            self._sync_auth_mode()
            self.username.clear()
            self.password.clear()
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
            said += " Alarms play your Spotify link in the Spotify app, which it has just been given."
        self.setup_page.show_test_result(said)

    def _show_recovery(self, codes: list) -> None:
        self._allow_week_page = False
        self.recovery_list.setText("\n".join(str(code) for code in codes))
        self.recovery_ack.setChecked(False)
        self.recovery_continue.setEnabled(False)
        self._show_page("recoveryPage")

    def _on_week(self) -> None:
        if self.session.account is None:
            return
        if self.hand.busy and self._where() != self._shown:
            # Somewhere else was asked for while a block was held: another view, week, day or design.
            # The block goes back and nothing moves, as Escape does.
            self.hand.cancel()
        if not self.hand.busy:
            self._shown = self._where()
        if self.session.dirty:
            # Every change reaches here, so this is where the clock on "stopped changing" restarts.
            self._changed_ms = self.session.now_ms()
        if self._on_recovery() and not self._allow_week_page:
            return
        self._honour_preferred_view()
        self._check_updates(asked=False)
        self._fill_classic()
        self.month_grid.set_month(self.session.month_data, self.session.dirty)
        opened = (self.session.planner_view, self.session.selected_month, self.session.month_data is not None)
        if opened[0] == "month" and opened[2] and opened != self._month_revealed:
            # Once, when a month opens: after that it stays wherever the student scrolled it, through
            # saves and refreshes. After the month has been laid out, or there is nothing to measure.
            self._month_revealed = opened
            QTimer.singleShot(0, lambda day=self.session.selected_day: self.month_grid.reveal(day))
        elif opened[0] != "month":
            self._month_revealed = None
        self._sync_add_button()
        self._sync_classic_waiting()
        view = self.session.planner_view
        switch_page(self.planner, self._planner_widget(view), self._motion)
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
        self.week_title.set_full_text(
            planner_title(self.session, view), planner_title(self.session, view, short=True)
        )
        self._maybe_open_setup()
        if self._setup_prefs or self._setup_work_windows is not None or self._setup_week:
            # The account's preferences may only now have arrived, and what setup kept before they did,
            # a skip included, is written with them.
            QTimer.singleShot(0, self._flush_setup)
        if not self._setup_active:
            self._show_page("weekPage")
        can_retry = self.session.pending_save is not None and not self.session.conflict
        # Hidden, not merely greyed: a button that is never pressable is a permanent piece of
        # furniture that says a save failed when none has.
        self.retry_button.setVisible(can_retry)
        self.retry_button.setEnabled(can_retry)
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
        elif not items:
            self.unfinished_panel.hide()
        if self._late_dialog is not None and self.session.late_preview:
            titles = {block["id"]: block["title"] for block in self.session.blocks}
            self._late_dialog.show_trace(self.session.late_preview["trace"], titles)
        self.focus_panel.set_state(self.session)
        fresh = self.session.consume_plan_review()
        if fresh is not None:
            titles = {block["id"]: block["title"] for block in self.session.blocks}
            was_open = self.plan_review.isVisible()
            self.plan_review.set_trace(fresh, titles, self.session.week_start)
            if self.plan_review.isVisible() and not was_open:
                appear(self.plan_review, self._motion)
        self._sync_chrome()
        self._apply_appearance()
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
        self.auth_status.setText(message)
        if self._held_reminder is not None and message in ROUTINE_STATUS:
            return
        self._held_reminder = None
        self.week_status.setText(message)

    def _release_status(self) -> None:
        if self._held_reminder is not None:
            self._held_reminder = None
            self.week_status.setText(self.session.message)

    def _sync_more_menu(self) -> None:
        unfinished = self.findChild(QPushButton, "unfinishedOpen")
        if unfinished is not None:
            # Worked out as the menu opens: the busy flag turns every action back on when a save
            # ends, and left to that "Unfinished" was pressable with nothing to show.
            unfinished.setEnabled(not self.session.busy and bool(self.session.unfinished()))
        for action, button in self._more_pairs:
            action.setEnabled(button.isEnabled())
            action.setText(button.text())
            action.setToolTip(self._more_tip(button.objectName(), button.isEnabled()))
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
        names = (
            "createAccount",
            "signIn",
            "recoveryContinue",
            "addFixed",
            "addHomework",
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
        for name in names:
            button = self.findChild(QPushButton, name)
            if button is not None:
                button.setEnabled(not busy)
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

    def _on_recovery_ack(self, checked: bool) -> None:
        self.recovery_continue.setEnabled(checked and not self.session.busy)

    def _toggle_password(self, shown: bool) -> None:
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password)
        self.password_reveal.setText("Hide" if shown else "Show")

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
        fade_away(picture, self._motion, self._travel_direction)

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
        today = date.today()
        self.session.load_week(monday_of(today.isoformat()))
        if self.session.planner_view == "day" or self._day_mode:
            self.session.open_day(today.isoformat())

    def _shift_week(self, days: int) -> None:
        monday = date.fromisoformat(self.session.week_start) + timedelta(days=days)
        self.session.load_week(monday.isoformat())

    def _commit_block(self, dialog: BlockDialog) -> None:
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.deleted():
            gone = dialog.block()
            self.session.delete_block(gone["id"], scope=dialog.scope(), day=dialog.occurrence_day())
            self.session.save()
            # The question before deleting promised an undo; this is where it is.
            self._set_notice(f"Deleted {gone.get('title') or 'the event'}.", "Undo", self._undo_from_notice)
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
        if dialog.exec() != QDialog.DialogCode.Accepted:
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
        self._commit_block(BlockDialog(self, category=category))

    def _school_hours(self) -> None:
        """School for a student who skipped it at setup, when nothing on the menu said school: their
        School if they have one, otherwise School already filled in, Monday to Friday 08:00-14:30."""
        locked = [item for item in self.session.blocks if item.get("kind") == "locked"]
        school = next((item for item in locked if item["id"] == "school"), None) or next(
            (item for item in locked if item.get("category") == "class"), None
        )
        self._commit_block(BlockDialog(self, school) if school else BlockDialog(self, category="class"))

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
            button.setIcon(QIcon(swatch(info["mark"])) if info else QIcon())

    def _sync_classic_waiting(self) -> None:
        """Today's app's Week shows homework with no start above the hours, to drag onto them."""
        if self.hand.busy:
            # Rebuilding would delete the chip the pointer is holding. The release refreshes.
            return
        classic = (
            self._layout.get("main") == "classic"
            and not self._day_mode
            and self.session.planner_view == "week"
            and self.session.account is not None
        )
        week = (
            build_week(
                self.session.week_start, self.session.blocks, self.session.assignments, self.session.trace
            )
            if classic
            else None
        )
        waiting = week.waiting if week is not None else ()
        self.classic_waiting.setVisible(bool(waiting))
        # Every save comes through here. Chips made again for the same homework were shown a frame
        # after the old ones went, so the bar blinked empty on each save.
        if waiting == self._waiting_shown:
            return
        self._waiting_shown = waiting
        row = self.classic_waiting_row
        while row.count():
            item = row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        if not waiting:
            return
        kicker = QLabel("Not placed yet")
        kicker.setObjectName("classicWaitingLabel")
        row.addWidget(kicker)
        for index, item in enumerate(waiting):
            made = TrayChip(self.hand, item)
            made.setObjectName(f"classicWaiting{index}")
            made.clicked.connect(lambda _=False, key=item.block_id: self._edit_block(key))
            row.addWidget(made)
        row.addStretch(1)

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

    def _open_week_day(self, day: int) -> None:
        self.session.open_day(date_for_day(self.session.week_start, day))

    def _hand_judge(self, block_id: str, from_day: int, span) -> HandVerdict:
        return self._judge_span(block_id, from_day, span.day, span.start, span.end)

    def _apply_change(self, change: object) -> None:
        """What the pointer did, turned into the change the week keeps."""
        if isinstance(change, Move):
            span = change.span
            self._move_block(change.block_id, change.from_day, span.day, span.start, span.end)
        elif isinstance(change, Place):
            span = change.span
            self._move_block(change.block_id, -1, span.day, span.start, span.end)
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
            self._sync_classic_waiting()
            self._show_change()

    def _hold_status_row(self) -> None:
        """As tall as the notice, shown or not, so its coming and going never moves the hours."""
        button, label = self.action_notice_button, self.action_notice_text
        words, said = button.text(), label.text()
        # Measured with words in it: empty, the notice is a few pixels shorter.
        button.setText(words or "Undo")
        label.setText(said or "Moved History essay to Fri 18:00.")
        self._status_row.setMinimumHeight(self.action_notice.sizeHint().height())
        button.setText(words)
        label.setText(said)

    def _set_notice(self, text: str, button: str, callback) -> None:
        self._notice_step = None
        self.action_notice_text.setText(text)
        # A wrapping label asks for its narrowest width, and "Fri 18:00." went to a second line
        # beside an empty status line. Its words' width, up to a limit, keeps it on one.
        self.action_notice_text.setMinimumWidth(
            min(self.action_notice_text.fontMetrics().horizontalAdvance(text) + 8, NOTICE_MAX_WIDTH)
        )
        self.action_notice_button.setText(button)
        self._notice_callback = callback
        # The notice stays until the student acts on it. A toast of the same words on top of it
        # said everything twice.
        self.toast.hide()
        self.action_notice.show()
        appear(self.action_notice, self._motion)

    def _undo_from_notice(self) -> None:
        self.action_notice.hide()
        self._notice_step = None
        self._told(self.session.undo)

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
        the status line says, bar words ending in "…", which say it is still going. The status line
        alone, at the foot of the window, went unseen."""
        self._telling = True
        act()
        if not self.session.busy:
            # Done at once, or a dialog closed without doing anything.
            self._telling = False

    def _tell(self, message: str) -> None:
        if self._telling and message and not message.endswith("…"):
            self._telling = False
            self.toast.show_message(message)

    def _on_planned(self, said: str) -> None:
        self._set_notice(said, "Undo", self._undo_from_notice)
        self._notice_step = self.session.last_step()

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
        self.action_notice.hide()
        if ids:
            self.session.solve(only=ids)

    def _add_from_chip(self, category: str) -> None:
        self.session.arm_category(category)
        self._sync_add_button()
        if category in FLEX_CATEGORIES:
            self._commit_homework(HomeworkDialog(self, today=self._today(), category=category))
            return
        self._commit_block(BlockDialog(self, category=category))

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
        dialog = ChooseTimeDialog(self, block, self.session.week_start, days, self.session.blocks, due, today)
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
        problem = span_problem(self.session.blocks, block_id, day, start, end, self._due_point(block_id))
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
        if dialog.exec() != QDialog.DialogCode.Accepted:
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
        clip = self.session.clipboard
        rows = self.session.paste_proposals()
        label = "pasting " + clip["label"] if clip else "pasting"
        key = None
        if clip and self.session.account is not None:
            dest = self.session.paste_destination()
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

    def _show_unfinished(self) -> None:
        items = self.session.unfinished()
        if not items:
            self.session._say(NOTHING_UNFINISHED)
            self.toast.show_message(NOTHING_UNFINISHED)
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
            self.toast.show_message(refusal)
            return
        from_start = late_from_start(now.hour * 60 + now.minute)
        dialog = LateDialog(self, f"Starting from {from_start} today ({DAY_FULL[now.weekday()]}).")
        dialog.preview_requested.connect(
            lambda: self.session.preview_running_late(dialog.chosen_minutes(), now)
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
            self.action_notice.hide()
            self._notice_step = None
        if self._late_waiting is None:
            return
        block_id, message = self._late_waiting
        if not stored:
            self._late_waiting = None
            self.toast.show_message(said)
        elif any(item["id"] == block_id for item in self.session.blocks):
            # A save already in flight when Running late was accepted finishes without the late start;
            # the wait is for the one that carries it.
            self._late_waiting = None
            self.session._say(message)
            self.toast.show_message(message)

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

    def _toggle_recover(self) -> None:
        visible = not self.recovery_code.isVisible()
        self.recovery_code.setVisible(visible)
        self.new_recovery_password.setVisible(visible)
        self.recover_button.setVisible(visible)

    def _recover_account(self) -> None:
        self.session.keep_signed_in = self.keep_signed_in.isChecked()
        self.session.recover(
            self.username.text().strip(),
            self.recovery_code.text().strip(),
            self.new_recovery_password.text(),
        )

    def _start_focus(self, block_id: str, day: object) -> None:
        self.session.start_focus(block_id or None, day if isinstance(day, int) else None)

    def _confirm_replace_focus(self, current: str, incoming: str) -> None:
        answer = QMessageBox.question(
            self,
            "Replace timer",
            f"Stop the timer for {current} and start {incoming} instead?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.session.confirm_replace_focus()

    def _on_focus(self) -> None:
        self.focus_panel.set_state(self.session)
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
            # says it as well: for a moment under the top bar, and on the status line until it matters
            # less than what comes next.
            said = "; ".join(reminders)
            self.toast.show_message(said)
            self._held_reminder = said
            self.week_status.setText(said)
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

    def _open_settings(self) -> None:
        """Every change shows the moment it is made; there is no OK. The look and layout live on this
        device and are written at once. The account's choices are saved a moment after the last
        change, so typing "45" saves once rather than twice, and closing saves whatever is left."""
        if self.session.preferences is None:
            self.session._say("Still loading your settings…")
            return
        dialog = PrefsDialog(
            self, self.session.preferences, self._look, self.session.reminder_limits, self._layout
        )
        dialog.motion_level = self._motion
        dialog.account_requested.connect(self._open_account)
        dialog.availability_requested.connect(self._open_availability)
        dialog.updates_requested.connect(lambda: self._check_updates(asked=True))
        rerun: list[bool] = []
        dialog.setup_requested.connect(lambda: (rerun.append(True), dialog.reject()))
        stored = dialog.updates()
        login = bool(stored["start_at_login"])

        def save() -> None:
            nonlocal stored
            wanted = dialog.updates()
            if wanted != stored and self.session.save_preferences(wanted):
                stored = wanted

        def apply() -> None:
            nonlocal login
            look, layout = dialog.look_choice(), dialog.layout_choice()
            if look != self._look or layout != self._layout:
                self._look = look
                self.session.look = look
                self._layout = layout
                self._save_look()
                self._on_week()
            wanted = dialog.updates()
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
                )
                shown = {key: wanted[key] for key in live}
                self.session.preferences = {**self.session.preferences, **shown}
            if bool(wanted["start_at_login"]) != login:
                login = bool(wanted["start_at_login"])
                self._apply_start_at_login(login)
            self._apply_appearance()
            self._sync_chrome()
            saver.start()

        saver = QTimer(dialog)
        saver.setSingleShot(True)
        saver.setInterval(SETTINGS_SAVE_MS)
        saver.timeout.connect(save)
        dialog.changed.connect(apply)
        self.session.status.connect(dialog.save_state.setText)
        try:
            dialog.exec()
        finally:
            with contextlib.suppress(RuntimeError, TypeError):
                self.session.status.disconnect(dialog.save_state.setText)
        saver.stop()
        save()
        if rerun:
            self._run_setup_again()

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
        if confirm(self, "Log out", LOG_OUT_QUESTION, "Log out", danger=False):
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

    def _save_look(self) -> None:
        import json

        path = self._look_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            body = {**self._look, "layout": self._layout, "updates": self._updates, "zoom": self._zoom}
            path.write_text(json.dumps(body) + "\n")
        except OSError:
            self.session._say("Could not save the look for this device.")

    def _apply_appearance(self) -> None:
        pack, system_dark, accent = self._look_inputs()
        # Blocks and month cells are painted per item, which a stylesheet cannot reach.
        palette = resolved_palette(pack, system_dark, self._look, accent)
        design = self._chrome_palette(palette)
        art = control_art(design)
        sheet = pack_stylesheet(pack, system_dark, self._look, accent, design, art)
        chips = bool((self.session.preferences or {}).get("accent_chips"))
        self._motion = motion_level((self.session.preferences or {}).get("motion"), pack_motion(pack))
        dressed = (sheet, repr(self._look), repr(design), chips, self._motion)
        # Every change to the week comes through here. Restyling the whole window each time, when the
        # look had not changed, cost about 26 ms a change and repainted everything on screen.
        if dressed != self._dressed:
            self._dressed = dressed
            self.setStyleSheet(sheet)
            self._keep_bar_whole()
            self._hold_status_row()
            apply_ui_effects(self._motion)
            self.toast.motion = self._motion
            # Day, Month and the week grid are dressed by the same design as the main view, so moving
            # between them is moving around one app rather than between two.
            self.week_table.set_look(self._look, design)
            self.day_view.set_look(self._look, design)
            self.month_grid.set_palette(design)
            self.add_menu.set_palette(design, chips)
        self._sync_add_button()
        self._refresh_layout()

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

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.session.account is None or QApplication.activeModalWidget() is not None:
            super().keyPressEvent(event)
            return
        if self._on_recovery():
            super().keyPressEvent(event)
            return
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox)):
            super().keyPressEvent(event)
            return
        key = event.key()
        mods = event.modifiers()
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
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
        key = event.key()
        mods = event.modifiers()
        control = bool(mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        if not control and key in (
            Qt.Key.Key_W,
            Qt.Key.Key_D,
            Qt.Key.Key_M,
            Qt.Key.Key_T,
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
        ):
            self.keyPressEvent(event)
            return True
        return super().eventFilter(watched, event)
