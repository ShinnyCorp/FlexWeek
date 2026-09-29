"""Reminders and a block's song, followed to what the student sees, with the clock held.

The reminder engine used to be checked by listening to the session's `alerts` signal, which proves a
notice was made, not that anyone saw it. These tests watch the tray message (through a stand-in tray,
since offscreen Qt has none), the toast under the top bar and the status line, and the song a block
with a Spotify link plays at its start (through a stand-in Spotify app: no test reaches the real one).
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import sqlite3
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QStandardPaths, QTimer
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton

    from desktop.native import spotify
    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer
    from desktop.tests.logic_support import past_setup

PASSWORD = "a-long-test-password"
TRACK = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
TRACK_ADDRESS = "spotify:track:4cOdK2wGLETKBW3PvgPWqT"
REMINDER = "Guitar practice starts soon — 18:45 · Thu"
# The preferences table as 0.14 left it, for an account made before reminders were on by default.
PREFERENCES_0_14 = """
    CREATE TABLE preferences (
        user_id INTEGER PRIMARY KEY REFERENCES users(id),
        theme TEXT NOT NULL DEFAULT 'system' CHECK(theme IN ('system', 'slate', 'nocturne')),
        reminders_enabled INTEGER NOT NULL DEFAULT 0 CHECK(reminders_enabled IN (0, 1)),
        reminder_lead_min INTEGER NOT NULL DEFAULT 5
            CHECK(reminder_lead_min >= 0 AND reminder_lead_min <= 120),
        reminder_sound INTEGER NOT NULL DEFAULT 1 CHECK(reminder_sound IN (0, 1)),
        reminder_dnd_override INTEGER NOT NULL DEFAULT 0 CHECK(reminder_dnd_override IN (0, 1)),
        timer_work_min INTEGER NOT NULL DEFAULT 30,
        timer_break_min INTEGER NOT NULL DEFAULT 15,
        timer_long_break_min INTEGER NOT NULL DEFAULT 30,
        timer_long_break_every INTEGER NOT NULL DEFAULT 4,
        auto_split_pomodoro INTEGER NOT NULL DEFAULT 0 CHECK(auto_split_pomodoro IN (0, 1)),
        default_spotify_url TEXT,
        alarms_json TEXT NOT NULL DEFAULT '[]',
        availability_json TEXT NOT NULL DEFAULT '{}',
        comfort_json TEXT NOT NULL DEFAULT '{}'
    )
"""
COLUMNS_0_14 = (
    "user_id, theme, reminders_enabled, reminder_lead_min, reminder_sound, reminder_dnd_override,"
    " timer_work_min, timer_break_min, timer_long_break_min, timer_long_break_every,"
    " auto_split_pomodoro, default_spotify_url, alarms_json, availability_json, comfort_json"
)


class Tray:
    """The system tray, as far as the window uses it for a notification."""

    def __init__(self) -> None:
        self.shown: list[tuple[str, str]] = []

    def supportsMessages(self) -> bool:  # noqa: N802
        return True

    def showMessage(self, title: str, body: str, *_rest: object) -> None:  # noqa: N802
        self.shown.append((title, body))

    def isVisible(self) -> bool:  # noqa: N802
        return True

    def hide(self) -> None:
        return None


class Bell:
    """The window's tone: what rang once, and what rang until stopped."""

    def __init__(self) -> None:
        self.once_rung: list[str] = []
        self.started: list[str] = []
        self.ringing = False

    def once(self, tone: str, _volume: object) -> bool:
        self.once_rung.append(tone)
        return True

    def start(self, tone: str, _volume: object) -> bool:
        self.started.append(tone)
        self.ringing = True
        return True

    def stop(self) -> None:
        self.ringing = False


class SpotifyApp:
    """The student's Spotify app on the session bus: what it was asked to play, and each pause."""

    def __init__(self) -> None:
        self.asked: list[str] = []
        self.paused = 0
        self.is_playing = False

    def reachable(self) -> bool:
        return True

    def running(self) -> bool:
        return True

    def play(self, address: str) -> None:
        self.asked.append(address)
        self.is_playing = True

    def playing(self) -> bool:
        return self.is_playing

    def pause(self) -> None:
        self.paused += 1
        self.is_playing = False

    def now_playing(self) -> tuple[str, str, str]:
        return "Practice mix", "Band", "track"


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-reminders-window-test"])


@pytest.fixture()
def spotify_app(monkeypatch: pytest.MonkeyPatch) -> SpotifyApp:
    player = SpotifyApp()
    monkeypatch.setattr(spotify, "system_remote", lambda: player)
    return player


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    return tmp_path / "reminders.db"


@pytest.fixture()
def opened(qapp: QApplication) -> Iterator[list]:
    """Every window and server a test opens, closed after it whatever happens."""
    things: list = []
    yield things
    for thing in reversed(things):
        if isinstance(thing, NativeWindow):
            with contextlib.suppress(RuntimeError):
                thing.session.client.reset()
            thing.hide()
        else:
            thing.stop()
    qapp.processEvents()


def wait_until(qapp: QApplication, predicate: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def settled(qapp: QApplication, window: NativeWindow) -> None:
    wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)
    for _ in range(5):
        qapp.processEvents()


def serve(database: Path, opened: list) -> LocalServer:
    server = LocalServer(database)
    server.start()
    opened.append(server)
    return server


def launch(qapp: QApplication, server: LocalServer, name: str, opened: list, *, create: bool) -> NativeWindow:
    """The app opened on this server: a new account past setup, or a sign-in to an existing one."""
    window = NativeWindow(server.origin)
    opened.append(window)
    window.resize(1280, 860)
    window.show()
    window.username.setText(name)
    window.password.setText(PASSWORD)
    if create:
        window.findChild(QPushButton, "createAccount").click()
        wait_until(qapp, lambda: window._stack.currentWidget().objectName() == "recoveryPage")
        window.recovery_ack.setChecked(True)
        window.recovery_continue.click()
        past_setup(qapp, window)
    else:
        if window.sign_in_button.isHidden():
            window.findChild(QPushButton, "authSwitch").click()
        window.keep_signed_in.setChecked(False)
        window.sign_in_button.click()
        wait_until(qapp, lambda: window.session.preferences is not None and not window.session.busy)
    window._tray_icon = Tray()
    window._bell = Bell()
    return window


class Clock:
    """Thursday of the week on screen, at the minute a test says."""

    def __init__(self, window: NativeWindow) -> None:
        self.thursday = datetime.fromisoformat(window.session.week_start) + timedelta(days=3)
        self.now = self.thursday
        window.session.now_ms = lambda: int(self.now.timestamp() * 1000)

    def at(self, hour: int, minute: int) -> None:
        self.now = self.thursday.replace(hour=hour, minute=minute)


def hold(window: NativeWindow, hour: int, minute: int) -> Clock:
    clock = Clock(window)
    clock.at(hour, minute)
    return clock


def choose(qapp: QApplication, window: NativeWindow, **preferences: object) -> None:
    window.session.save_preferences(preferences)
    wait_until(
        qapp,
        lambda: not window.session.busy
        and all((window.session.preferences or {}).get(key) == value for key, value in preferences.items()),
    )


def add_practice(qapp: QApplication, window: NativeWindow, **extra: object) -> None:
    window.session.add_block(
        {
            "id": "practice",
            "title": "Guitar practice",
            "kind": "locked",
            "category": "class",
            "start": "18:45",
            "duration_min": 30,
            "days": [3],
            **extra,
        }
    )
    window.session.save()
    settled(qapp, window)


def tick(qapp: QApplication, window: NativeWindow, clock: Clock, minute: int) -> None:
    """What the window's poll does every 30 seconds, at 18:mm on the held clock."""
    clock.at(18, minute)
    window.session.check_alerts()
    for _ in range(3):
        qapp.processEvents()


def seen(window: NativeWindow) -> dict:
    return {
        "tray": list(window._tray_icon.shown),
        "toast": window.toast.text() if window.toast.isVisible() else "",
    }


def answer_alarm(qapp: QApplication, window: NativeWindow, button: str, heard: list) -> None:
    """Press a button on the alarm when it rings, noting what it said and what was playing."""
    tries = [0]

    def act() -> None:
        tries[0] += 1
        with contextlib.suppress(RuntimeError):
            dialog = window._alarm_dialog
            if dialog is None or not dialog.isVisible():
                if tries[0] < 100:
                    QTimer.singleShot(20, act)
                return
            words = [label.text() for label in dialog.findChildren(QLabel) if label.text()]
            heard.append(words)
            dialog.findChild(QPushButton, button).click()

    QTimer.singleShot(0, act)


def test_a_block_saved_inside_its_lead_reminds_at_once_and_only_once(
    qapp: QApplication, database: Path, opened: list
) -> None:
    """Timmy's test: at 18:38 a block for 18:45 with a 10-minute lead. Its lead began at 18:35, so the
    reminder was due before the block existed, and a check that only looks back two minutes never
    found it. It comes at the first check after the save, and never again."""
    window = launch(qapp, serve(database, opened), "timmy", opened, create=True)
    clock = hold(window, 18, 38)
    choose(qapp, window, reminders_enabled=True, reminder_lead_min=10)
    add_practice(qapp, window)
    tick(qapp, window, clock, 38)
    assert seen(window) == {
        "tray": [("Guitar practice starts soon", "18:45 · Thu")],
        "toast": REMINDER,
    }
    assert window._bell.once_rung == ["chime"]
    for minute in range(39, 49):
        tick(qapp, window, clock, minute)
    assert window._tray_icon.shown == [("Guitar practice starts soon", "18:45 · Thu")]
    assert window._bell.once_rung == ["chime"]


def test_a_block_saved_before_its_lead_reminds_when_the_lead_begins(
    qapp: QApplication, database: Path, opened: list
) -> None:
    """Without a tray to carry it, the window alone says it."""
    window = launch(qapp, serve(database, opened), "early_bird", opened, create=True)
    window._tray_icon = None
    clock = hold(window, 18, 20)
    choose(qapp, window, reminders_enabled=True, reminder_lead_min=10)
    add_practice(qapp, window)
    for minute in range(20, 35):
        tick(qapp, window, clock, minute)
        assert window._bell.once_rung == [], f"reminded at 18:{minute}"
    tick(qapp, window, clock, 35)
    assert window.toast.isVisible() and window.toast.text() == REMINDER
    for minute in range(36, 50):
        tick(qapp, window, clock, minute)
    assert window._bell.once_rung == ["chime"]


def test_a_new_account_reminds_without_being_asked(qapp: QApplication, database: Path, opened: list) -> None:
    """Setup skipped, nothing chosen: blocks still remind, at the lead the account starts with."""
    window = launch(qapp, serve(database, opened), "new_student", opened, create=True)
    assert window.session.preferences["reminders_enabled"] is True
    lead = int(window.session.preferences["reminder_lead_min"])
    clock = hold(window, 18, 20)
    add_practice(qapp, window)
    tick(qapp, window, clock, 45 - lead)
    assert window._tray_icon.shown == [("Guitar practice starts soon", "18:45 · Thu")]


def make_it_0_14(database: Path, reminders: bool) -> None:
    """The account as 0.14 left it: its preferences in 0.14's table, with reminders as given."""
    with sqlite3.connect(database) as db:
        db.execute("ALTER TABLE preferences RENAME TO preferences_now")
        db.execute(PREFERENCES_0_14)
        db.execute(f"INSERT INTO preferences({COLUMNS_0_14}) SELECT {COLUMNS_0_14} FROM preferences_now")
        db.execute("DROP TABLE preferences_now")
        db.execute("UPDATE preferences SET reminders_enabled = ?", (int(reminders),))


def an_account_from_0_14(qapp: QApplication, database: Path, opened: list) -> None:
    server = serve(database, opened)
    window = launch(qapp, server, "old_student", opened, create=True)
    window.session.client.reset()
    window.hide()
    server.stop()
    opened.remove(server)
    make_it_0_14(database, reminders=False)


def test_an_account_from_0_14_with_reminders_off_reminds_after_the_update(
    qapp: QApplication, database: Path, opened: list
) -> None:
    """Its reminders were off only because setup never asked, so the update turns them on."""
    an_account_from_0_14(qapp, database, opened)
    window = launch(qapp, serve(database, opened), "old_student", opened, create=False)
    assert window.session.preferences["reminders_enabled"] is True
    clock = hold(window, 18, 30)
    choose(qapp, window, reminder_lead_min=10)
    add_practice(qapp, window)
    tick(qapp, window, clock, 35)
    assert window._tray_icon.shown == [("Guitar practice starts soon", "18:45 · Thu")]


def test_reminders_turned_off_after_the_update_stay_off(
    qapp: QApplication, database: Path, opened: list
) -> None:
    """The update happens once. After it, the student's own choice stands, restart after restart."""
    an_account_from_0_14(qapp, database, opened)
    server = serve(database, opened)
    first = launch(qapp, server, "old_student", opened, create=False)
    assert first.session.preferences["reminders_enabled"] is True
    choose(qapp, first, reminders_enabled=False, reminder_lead_min=10)
    first.session.client.reset()
    first.hide()
    server.stop()
    opened.remove(server)
    window = launch(qapp, serve(database, opened), "old_student", opened, create=False)
    assert window.session.preferences["reminders_enabled"] is False
    clock = hold(window, 18, 30)
    add_practice(qapp, window)
    for minute in range(30, 50):
        tick(qapp, window, clock, minute)
    assert window._tray_icon.shown == []
    assert window._bell.once_rung == []


def test_a_block_with_a_spotify_link_plays_it_at_its_start_and_dismiss_stops_it(
    qapp: QApplication, database: Path, opened: list, spotify_app: SpotifyApp
) -> None:
    window = launch(qapp, serve(database, opened), "guitarist", opened, create=True)
    clock = hold(window, 18, 30)
    choose(qapp, window, reminder_lead_min=10)
    add_practice(qapp, window, spotify_url=TRACK)
    tick(qapp, window, clock, 35)
    assert window._tray_icon.shown == [("Guitar practice starts soon", "18:45 · Thu")]
    assert spotify_app.asked == [], "the reminder before the start plays no music"
    heard: list = []
    answer_alarm(qapp, window, "alarmDismiss", heard)
    tick(qapp, window, clock, 45)
    assert heard and heard[0][:2] == ["Guitar practice", "18:45 · Starting now"]
    assert spotify_app.asked == [TRACK_ADDRESS]
    assert spotify_app.paused == 1, "dismissing stops the song"
    assert window._alarm_dialog is None and window.session.active_alarm is None
    assert window._tray_icon.shown == [("Guitar practice starts soon", "18:45 · Thu")], "one notice"
    for minute in range(46, 55):
        tick(qapp, window, clock, minute)
    assert spotify_app.asked == [TRACK_ADDRESS], "it plays once"


def test_a_snoozed_block_song_plays_again_five_minutes_later(
    qapp: QApplication, database: Path, opened: list, spotify_app: SpotifyApp
) -> None:
    window = launch(qapp, serve(database, opened), "snoozer", opened, create=True)
    clock = hold(window, 18, 44)
    add_practice(qapp, window, spotify_url=TRACK)
    tick(qapp, window, clock, 44)
    heard: list = []
    answer_alarm(qapp, window, "alarmSnooze", heard)
    tick(qapp, window, clock, 45)
    assert len(heard) == 1 and spotify_app.paused == 1
    for minute in range(46, 50):
        tick(qapp, window, clock, minute)
    assert spotify_app.asked == [TRACK_ADDRESS]
    answer_alarm(qapp, window, "alarmDismiss", heard)
    tick(qapp, window, clock, 50)
    assert len(heard) == 2 and spotify_app.asked == [TRACK_ADDRESS, TRACK_ADDRESS]
    assert spotify_app.paused == 2
    for minute in range(51, 58):
        tick(qapp, window, clock, minute)
    assert spotify_app.asked == [TRACK_ADDRESS, TRACK_ADDRESS]


def test_a_block_without_a_link_plays_nothing_at_its_start(
    qapp: QApplication, database: Path, opened: list, spotify_app: SpotifyApp
) -> None:
    window = launch(qapp, serve(database, opened), "quiet_one", opened, create=True)
    clock = hold(window, 18, 30)
    choose(qapp, window, reminder_lead_min=10)
    add_practice(qapp, window)
    rang: list = []
    window.session.alarm_due.connect(rang.append)
    for minute in range(30, 50):
        tick(qapp, window, clock, minute)
    assert rang == [] and window._bell.started == [] and spotify_app.asked == []
    assert window._tray_icon.shown == [("Guitar practice starts soon", "18:45 · Thu")]


def test_the_toast_keeps_a_reminder_until_something_more_important(
    qapp: QApplication, database: Path, opened: list
) -> None:
    """"Saved preferences." wrote over the reminder. A save's confirmation is less than a reminder, so
    it is not said at all; something the student has to read now is more."""
    window = launch(qapp, serve(database, opened), "status_reader", opened, create=True)
    clock = hold(window, 18, 30)
    choose(qapp, window, reminder_lead_min=10)
    add_practice(qapp, window)
    tick(qapp, window, clock, 35)
    assert window.toast.text() == REMINDER
    window.session.save_preferences({"alert_volume": 70})
    settled(qapp, window)
    assert window.session.message == "Saved preferences."
    assert window.toast.text() == REMINDER
    window.session.add_block(
        {"id": "dinner", "title": "Dinner", "kind": "locked", "category": "meals", "start": "19:30",
         "duration_min": 30, "days": [3]}
    )
    window.session.save()
    settled(qapp, window)
    assert window.toast.text() == REMINDER
    window.session.select_block(None, None)
    window.session.copy_selected()
    assert window.toast.text() == "Select a block before copying it."


def test_got_it_on_a_reminder_left_on_screen_takes_its_toast_away_too(
    qapp: QApplication, database: Path, opened: list
) -> None:
    window = launch(qapp, serve(database, opened), "handler", opened, create=True)
    clock = hold(window, 18, 30)
    choose(qapp, window, reminder_lead_min=10, reminder_dnd_override=True)
    add_practice(qapp, window)
    tick(qapp, window, clock, 35)
    assert window.alert_strip.isVisible() and window.toast.text() == REMINDER
    window.alert_strip.dismiss.click()
    assert not window.alert_strip.isVisible()
    assert not window.toast.isVisible()
