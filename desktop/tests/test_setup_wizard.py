"""First-run setup: each page kept as the student leaves it, every page skippable, and setup never
back once it is finished or skipped, unless the student runs it again from Settings."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
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
    from PySide6.QtCore import QPoint, QStandardPaths, Qt, QTime, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QComboBox, QDateTimeEdit, QLabel, QPushButton, QWidget

    from desktop.native.calendar import monday_of, sunday_due
    from desktop.native.layouts.registry import EXPERIMENTAL, sanitize_layout
    from desktop.native.look import pack_stylesheet
    from desktop.native.setup import (
        COLOURS,
        DONE,
        FIRST,
        HOMEWORK,
        LOOK,
        REMINDERS,
        STYLE,
        WEEK,
        QuarterTime,
        SetupPage,
        SetupState,
    )
    from desktop.native.widgets import AvailabilityDialog
    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer

PASSWORD = "a-long-test-password"
SPOTIFY = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-setup-test"])


def look_file() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(root) / "flexweek-look.json"


@pytest.fixture()
def server(qapp: QApplication, tmp_path: Path) -> Iterator[LocalServer]:
    # Setup writes the look for this computer. Left behind, it would dress every later test's window.
    look_file().unlink(missing_ok=True)
    running = LocalServer(tmp_path / "setup.db")
    running.start()
    yield running
    running.stop()
    look_file().unlink(missing_ok=True)


def wait_until(qapp: QApplication, predicate: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def page(window: NativeWindow) -> str:
    return window._stack.currentWidget().objectName()


def written(qapp: QApplication, window: NativeWindow) -> None:
    """Everything setup kept has reached the server."""
    wait_until(
        qapp,
        lambda: (
            not window.session.busy
            and not window._setup_prefs
            and window._setup_work_windows is None
            and not window._setup_week
            and not window.session.dirty
        ),
    )
    # A plan started by the last save, and the save after it.
    for _ in range(10):
        qapp.processEvents()
    wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)


def close(qapp: QApplication, window: NativeWindow) -> None:
    with contextlib.suppress(RuntimeError):
        window.session.client.reset()
    qapp.processEvents()
    window.close()


def new_account(qapp: QApplication, server: LocalServer, name: str) -> NativeWindow:
    window = NativeWindow(server.origin)
    window.resize(1180, 760)
    window.show()
    window.username.setText(name)
    window.password.setText(PASSWORD)
    window.findChild(QPushButton, "createAccount").click()
    wait_until(qapp, lambda: page(window) == "recoveryPage")
    window.recovery_ack.setChecked(True)
    window.recovery_continue.click()
    wait_until(qapp, lambda: page(window) == "setupPage" and not window.session.busy)
    wait_until(qapp, lambda: window.session.preferences is not None)
    return window


def sign_in(qapp: QApplication, server: LocalServer, name: str) -> NativeWindow:
    """A fresh launch: a new window, signed in to an account that already exists."""
    window = NativeWindow(server.origin)
    window.resize(1180, 760)
    window.show()
    wait_until(qapp, lambda: page(window) == "authPage")
    if window._making_account:
        window.findChild(QPushButton, "authSwitch").click()
    window.username.setText(name)
    window.password.setText(PASSWORD)
    window.keep_signed_in.setChecked(False)
    window.sign_in_button.click()
    wait_until(qapp, lambda: window.session.preferences is not None and not window.session.busy)
    for _ in range(10):
        qapp.processEvents()
    return window


def locked(window: NativeWindow) -> dict[str, tuple[str, str, tuple[int, ...], int]]:
    return {
        block["id"]: (block["title"], block["start"], tuple(block["days"]), block["duration_min"])
        for block in window.session.blocks
        if block.get("kind") == "locked"
    }


def test_a_new_account_goes_from_its_recovery_codes_to_setup(qapp: QApplication, server: LocalServer) -> None:
    window = new_account(qapp, server, "setup_first")
    setup = window.setup_page
    assert setup.step == STYLE
    assert not setup.back.isVisible()
    assert setup.skip.isVisible() and setup.next.text() == "Next"
    assert setup.rail_items[0].property("current") is True
    assert not setup.rail_items[1].isEnabled(), "a step not reached yet cannot be jumped to"
    close(qapp, window)


def test_every_page_is_kept_when_the_student_leaves_it(qapp: QApplication, server: LocalServer) -> None:
    window = new_account(qapp, server, "setup_walk")
    setup = window.setup_page
    setup.style_cards["dashboard"].chosen.emit()
    setup.next.click()
    written(qapp, window)
    stored = json.loads(look_file().read_text())
    assert stored["layout"]["main"] == "bento", "the look belongs to this computer"
    assert stored["layout"]["options"]["bento"]["colour"] == "indigo"
    assert window.session.preferences["theme_pack"] == "light-frost"
    assert window.session.preferences["setup"]["step"] == WEEK

    assert setup.step == WEEK
    setup.school_times.set_span("08:00", 390)
    setup.activities[0].name.setText("Soccer")
    setup.activities[0].days.set_days([1, 3])
    setup._add_activity(title="Band", days=[0], start="16:00", minutes=60)
    setup.cutoff.setCurrentIndex(setup.cutoff.findData("22:00"))
    setup.next.click()
    written(qapp, window)
    assert locked(window) == {
        "school": ("School", "08:00", (0, 1, 2, 3, 4), 390),
        "activity-1": ("Soccer", "15:30", (1, 3), 90),
        "activity-2": ("Band", "16:00", (0,), 60),
    }
    assert window.session.revision == 1
    assert window.session.preferences["day_cutoff"] == "22:00"

    setup.planning_buttons["auto"].setChecked(True)
    assert setup.drag_buttons[5].isChecked(), "five minutes unless the student picks fifteen"
    setup.drag_buttons[15].setChecked(True)
    setup.work_editor.set_windows([{"days": [0, 1, 2, 3, 4], "start": "19:00", "end": "21:00"}])
    setup.next.click()
    written(qapp, window)
    assert window.session.preferences["planning_style"] == "auto"
    assert window.session.preferences["drag_step_min"] == 15
    assert window.hand.step == 15
    assert window.session.preferences["work_windows"] == [
        {"days": [0, 1, 2, 3, 4], "start": "19:00", "end": "21:00"}
    ]
    assert not window.session.preferences.get("study_windows"), "setup no longer asks for study times"

    assert setup.reminders.isChecked(), "setup turns reminders on unless the student says no"
    setup.lead.setValue(15)
    setup.tone_buttons["glass"].setChecked(True)
    setup.next.click()
    written(qapp, window)
    prefs = window.session.preferences
    assert (prefs["reminders_enabled"], prefs["reminder_lead_min"], prefs["alarm_tone"]) == (
        True,
        15,
        "glass",
    )

    # Wednesday morning, so there is time to plan it whatever day the test runs.
    wednesday = datetime.fromisoformat(window.session.week_start) + timedelta(days=2, hours=9)
    window.session.now_ms = lambda: int(wednesday.timestamp() * 1000)
    setup.homework_rows[0].name.setText("History essay")
    setup.homework_rows[0].minutes.setValue(90)
    setup.next.click()
    written(qapp, window)
    essay = next(item for item in window.session.assignments.values() if item["title"] == "History essay")
    assert essay["estimate_min"] == 90
    assert essay["due"] == sunday_due(monday_of(window.session.week_start))[:10], "that Sunday, no time"
    sessions = [block for block in window.session.blocks if block.get("assignment_id") == essay["id"]]
    assert sessions and all(block.get("start") for block in sessions), "Plan it for me gave it a time"

    assert setup.step == DONE
    summary = setup.summary_text()
    assert summary[0] == "Dashboard · Bento in Indigo"
    assert "Soccer Tue, Thu 15:30–17:00" in summary[1] and "Band Mon 16:00–17:00" in summary[1]
    assert summary[4] == "History essay"
    setup.next.click()
    written(qapp, window)
    assert page(window) == "weekPage"
    assert window._layout["main"] == "bento"
    assert window.session.preferences["setup"]["finished_at"]
    close(qapp, window)

    again = sign_in(qapp, server, "setup_walk")
    assert page(again) == "weekPage", "setup does not come back once it is finished"
    assert again.session.preferences["alarm_tone"] == "glass"
    close(qapp, again)


def test_skipping_every_page_keeps_nothing_and_setup_never_returns(
    qapp: QApplication, server: LocalServer
) -> None:
    window = new_account(qapp, server, "setup_skipper")
    setup = window.setup_page
    visited = []
    while setup.step != DONE:
        visited.append(setup.step)
        if setup.step == HOMEWORK:
            assert any(
                "Homework can be planned at any time of day." in label.text()
                for label in setup.pages[HOMEWORK].findChildren(QLabel)
            )
            setup.work_editor.set_windows(
                [{"days": [0, 1, 2, 3, 4], "start": "15:30", "end": "18:00"}]
            )
        setup.skip.click()
    assert visited == [STYLE, WEEK, HOMEWORK, REMINDERS, FIRST]
    setup.next.click()
    written(qapp, window)
    assert page(window) == "weekPage"
    assert window.session.blocks == [] and window.session.assignments == {}
    prefs = window.session.preferences
    assert prefs["reminders_enabled"] is True, "a skipped page changes nothing, and reminders start on"
    assert prefs.get("planning_style", "suggest") == "suggest"
    assert not prefs.get("work_windows"), "skipping does not keep hours entered on that page"
    assert prefs["setup"]["finished_at"]
    assert not look_file().exists() or json.loads(look_file().read_text())["layout"]["main"] == "classic"
    close(qapp, window)

    again = sign_in(qapp, server, "setup_skipper")
    assert page(again) == "weekPage", "an empty week does not bring setup back"
    close(qapp, again)


def test_a_work_window_chosen_in_setup_reaches_the_account(
    qapp: QApplication, server: LocalServer
) -> None:
    window = new_account(qapp, server, "setup_work_hours")
    setup = window.setup_page
    setup.skip.click()
    setup.skip.click()
    assert setup.step == HOMEWORK
    chosen = {"days": [0, 1, 2, 3, 4], "start": "15:30", "end": "18:00", "subject": "Math"}
    setup.work_editor.set_windows([chosen])
    setup.next.click()
    written(qapp, window)
    assert window.session.preferences["work_windows"] == [chosen]
    close(qapp, window)

    again = sign_in(qapp, server, "setup_work_hours")
    assert again.session.preferences["work_windows"] == [chosen]
    close(qapp, again)


def test_settings_saves_work_windows_with_existing_availability(
    qapp: QApplication, server: LocalServer
) -> None:
    window = new_account(qapp, server, "settings_work_hours")
    window.setup_page.skip_all.click()
    written(qapp, window)
    protected = [{"days": [0], "start": "19:00", "duration_min": 60, "kind": "meal"}]
    study = [{"days": [1], "start": "17:00", "duration_min": 60, "subject": "Math"}]
    assert window.session.save_availability(protected, study, "22:00", [])
    wait_until(qapp, lambda: not window.session.busy and window.session.preferences["study_windows"] == study)

    chosen = {"days": [5, 6], "start": "10:00", "end": "16:00"}
    sent: list[tuple[list[dict], list[dict], str | None, list[dict]]] = []
    save = window.session.save_availability

    def record(
        kept_protected: list[dict], kept_study: list[dict], cutoff: str | None, hours: list[dict]
    ) -> bool:
        sent.append((kept_protected, kept_study, cutoff, hours))
        return save(kept_protected, kept_study, cutoff, hours)

    window.session.save_availability = record

    def choose() -> None:
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, AvailabilityDialog)
        dialog.work_editor.set_windows([chosen])
        dialog.accept()

    QTimer.singleShot(0, choose)
    window._open_availability()
    wait_until(
        qapp,
        lambda: not window.session.busy and window.session.preferences["work_windows"] == [chosen],
    )
    prefs = window.session.preferences
    assert sent == [(protected, study, "22:00", [chosen])]
    assert prefs["protected"] == protected
    assert prefs["study_windows"] == study
    assert prefs["day_cutoff"] == "22:00"
    close(qapp, window)


def test_setup_refuses_a_work_window_that_ends_before_it_starts(qapp: QApplication) -> None:
    setup = opened(qapp)
    setup._show(HOMEWORK)
    setup.work_editor.set_windows([{"days": [0], "start": "15:00", "end": "16:00"}])
    row = setup.work_editor.findChild(QWidget, "workWindowRow")
    row.findChild(QComboBox, "workWindowEnd").setCurrentText("14:45")
    setup.next.click()
    assert setup.step == HOMEWORK
    assert row.findChild(QLabel, "validationError").text() == "End must be after Start."
    setup.close()


def test_skip_setup_is_remembered(qapp: QApplication, server: LocalServer) -> None:
    window = new_account(qapp, server, "setup_skip_all")
    window.setup_page.skip_all.click()
    written(qapp, window)
    assert page(window) == "weekPage"
    assert window.session.preferences["setup"]["finished_at"]
    close(qapp, window)
    again = sign_in(qapp, server, "setup_skip_all")
    assert page(again) == "weekPage"
    close(qapp, again)


def test_a_skip_before_the_accounts_preferences_arrive_is_still_written(
    qapp: QApplication, server: LocalServer
) -> None:
    """A new account opens setup before its preferences have loaded. A skip in that moment waits for
    them, and is written when they come, rather than forgotten."""
    window = new_account(qapp, server, "setup_quick")
    window.session.preferences = None
    window.setup_page.skip_all.click()
    assert page(window) == "weekPage"
    assert window._setup_prefs, "nothing to write it into yet"
    window.session._fetch_preferences()
    written(qapp, window)
    assert window.session.preferences["setup"]["finished_at"]
    close(qapp, window)
    again = sign_in(qapp, server, "setup_quick")
    assert page(again) == "weekPage"
    close(qapp, again)


def test_a_quit_resumes_on_the_step_it_left_with_earlier_answers_kept(
    qapp: QApplication, server: LocalServer
) -> None:
    window = new_account(qapp, server, "setup_quitter")
    setup = window.setup_page
    setup.style_cards["retro"].chosen.emit()
    setup.next.click()
    setup.school_times.set_span("07:45", 435)
    setup.next.click()
    assert setup.step == HOMEWORK
    written(qapp, window)
    close(qapp, window)

    again = sign_in(qapp, server, "setup_quitter")
    wait_until(qapp, lambda: page(again) == "setupPage")
    resumed = again.setup_page
    assert resumed.step == HOMEWORK
    assert again._layout["main"] == "retro", "the look chosen before the quit is the one on screen"
    resumed.back.click()
    assert resumed.step == WEEK
    assert resumed.school_times.span() == ("07:45", 435)
    close(qapp, again)


def test_a_new_account_starts_at_the_beginning_not_where_the_last_one_left(
    qapp: QApplication, server: LocalServer
) -> None:
    first = new_account(qapp, server, "setup_before")
    first.setup_page.skip.click()
    first.setup_page.skip.click()
    written(qapp, first)
    first.session.logout()
    wait_until(qapp, lambda: page(first) == "authPage")
    if not first._making_account:
        first.findChild(QPushButton, "authSwitch").click()
    first.username.setText("setup_after")
    first.password.setText(PASSWORD)
    first.findChild(QPushButton, "createAccount").click()
    wait_until(qapp, lambda: page(first) == "recoveryPage")
    first.recovery_ack.setChecked(True)
    first.recovery_continue.click()
    wait_until(qapp, lambda: page(first) == "setupPage" and not first.session.busy)
    assert first.setup_page.step == STYLE
    assert first.setup_page.homework_rows[0].name.text() == ""
    close(qapp, first)


def test_an_account_from_before_setup_with_work_in_it_is_not_asked(
    qapp: QApplication, server: LocalServer
) -> None:
    """Setup kept its place only from this version. An account already in use has nothing to record,
    and must not be walked through setup the first time it opens this version."""
    window = new_account(qapp, server, "setup_veteran")
    window.session.add_homework(
        {"id": "essay", "title": "Essay", "due": sunday_due(window.session.week_start), "estimate_min": 60}
    )
    window.session.save()
    wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)
    assert "setup" not in window.session.preferences
    close(qapp, window)
    again = sign_in(qapp, server, "setup_veteran")
    assert page(again) == "weekPage"
    close(qapp, again)


def test_run_setup_again_opens_filled_in_with_the_current_choices(
    qapp: QApplication, server: LocalServer
) -> None:
    window = new_account(qapp, server, "setup_rerun")
    setup = window.setup_page
    setup.style_cards["night"].chosen.emit()
    setup.next.click()
    setup.activities[0].name.setText("Soccer")
    setup.activities[0].days.set_days([1, 3])
    setup.next.click()
    setup.skip.click()
    setup.reminders.setChecked(False)
    setup.next.click()
    setup.skip_all.click()
    written(qapp, window)
    assert page(window) == "weekPage"

    window._open_settings()
    assert page(window) == "settingsPage"
    window._settings.findChild(QPushButton, "prefsRunSetup").click()
    wait_until(qapp, lambda: page(window) == "setupPage")
    assert setup.step == STYLE
    assert setup.style_cards["night"].is_selected(), "the style in use shows as picked"
    assert [row.name.text() for row in setup.activities] == ["Soccer"]
    assert setup.activities[0].days.days() == [1, 3]
    assert not setup.reminders.isChecked(), "reminders are as the student left them, not on again"
    written(qapp, window)
    setup.skip_all.click()
    written(qapp, window)
    assert page(window) == "weekPage"
    assert window._layout["main"] == "timeline"
    close(qapp, window)


def test_back_then_next_does_not_add_the_first_homework_twice(
    qapp: QApplication, server: LocalServer
) -> None:
    window = new_account(qapp, server, "setup_twice")
    setup = window.setup_page
    for _ in range(4):
        setup.skip.click()
    assert setup.step == FIRST
    setup.homework_rows[0].name.setText("Chem lab report")
    setup.next.click()
    written(qapp, window)
    setup.back.click()
    setup.homework_rows[0].name.setText("Chem lab report")
    setup.homework_rows[0].minutes.setValue(120)
    setup.next.click()
    written(qapp, window)
    titles = [item["title"] for item in window.session.assignments.values()]
    assert titles == ["Chem lab report"]
    assert next(iter(window.session.assignments.values()))["estimate_min"] == 120
    close(qapp, window)


def test_a_first_homework_due_at_a_set_time_keeps_it_and_one_without_has_none(
    qapp: QApplication, server: LocalServer
) -> None:
    window = new_account(qapp, server, "setup_due_time")
    setup = window.setup_page
    for _ in range(4):
        setup.skip.click()
    assert setup.step == FIRST
    oral = setup.homework_rows[0]
    oral.name.setText("French oral")
    oral.due.timed.setChecked(True)
    oral.due.time.setTime(QTime(9, 0))
    setup.add_homework.click()
    setup.homework_rows[1].name.setText("Reading log")
    setup.next.click()
    written(qapp, window)
    sunday = sunday_due(window.session.week_start)[:10]
    dues = {item["title"]: item["due"] for item in window.session.assignments.values()}
    assert dues == {"French oral": f"{sunday}T09:00", "Reading log": sunday}
    close(qapp, window)


def test_a_test_reminder_rings_the_chosen_sound_and_gives_the_spotify_app_the_link(
    qapp: QApplication, server: LocalServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = new_account(qapp, server, "setup_tester")
    setup = window.setup_page
    for _ in range(3):
        setup.skip.click()
    assert setup.step == REMINDERS
    rung: list[str] = []
    opened: list[str] = []
    monkeypatch.setattr(window._bell, "once", lambda tone, _volume: rung.append(tone) or True)

    monkeypatch.setattr("desktop.native.spotify.open_address", lambda address: opened.append(address) or True)
    setup.tone_buttons["bright"].setChecked(True)
    setup.test.click()
    assert rung == ["bright"]
    assert setup.test_result.text().startswith("Sent.")
    setup.tone_buttons["spotify"].setChecked(True)
    setup.test.click()
    assert opened == [], "no link yet, so nothing to open"
    assert "Spotify link" in setup.test_result.text()
    setup.spotify.setText(SPOTIFY)
    setup.test.click()
    assert opened == ["spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"], "the playlist, in the Spotify app"
    assert rung[-1] == "chime", "a reminder never starts music; it chimes"
    close(qapp, window)


# The page on its own


def state(**changes: object) -> SetupState:
    base = SetupState(
        pack="system",
        look={"preset": "default", "knobs": {}},
        layout=sanitize_layout(None),
        preferences={},
        blocks=[],
        week_start=monday_of("2026-09-23"),
    )
    for key, value in changes.items():
        setattr(base, key, value)
    return base


def opened(qapp: QApplication, **changes: object) -> SetupPage:
    setup = SetupPage()
    setup.motion = "off"
    setup.resize(1100, 720)
    setup.open(state(**changes))
    setup.show()
    qapp.processEvents()
    return setup


def test_two_activities_keep_their_own_days_and_an_untouched_row_adds_nothing(qapp: QApplication) -> None:
    setup = opened(qapp)
    setup._show(WEEK)
    assert [block["id"] for block in setup.week_blocks()] == ["school"], "the empty row is not an activity"
    setup.activities[0].name.setText("Soccer")
    setup.activities[0].days.set_days([1, 3])
    setup._add_activity(title="", days=[0], start="16:00", minutes=60)
    setup._add_activity(title="Band", days=[], start="17:00", minutes=60)
    made = {block["title"]: block["days"] for block in setup.week_blocks() if block["id"] != "school"}
    assert made == {"Soccer": [1, 3], "Sport or club": [0]}, "a row with days but no name still counts"
    setup.close()


def test_a_look_tried_and_skipped_is_put_back(qapp: QApplication) -> None:
    setup = opened(qapp)
    shown: list[dict] = []
    kept: list[object] = []
    setup.previewed.connect(shown.append)
    setup.left.connect(lambda _step, _to, answer: kept.append(answer))
    setup.style_cards["night"].chosen.emit()
    assert shown[-1]["pack"] == "dark-frost" and shown[-1]["layout"]["main"] == "timeline"
    setup.skip.click()
    assert kept == [None]
    assert shown[-1]["pack"] == "system" and shown[-1]["layout"]["main"] == "classic"
    setup.close()


def test_choose_my_own_look_goes_through_look_and_colours(qapp: QApplication) -> None:
    setup = opened(qapp)
    kept: list[tuple[int, object]] = []
    setup.left.connect(lambda step, _to, answer: kept.append((step, answer)))
    own = setup.findChild(QPushButton, "setupOwnLook")
    # Words, not an arrow drawn after them.
    assert own.text() == "Choose my own look instead"
    own.click()
    assert setup.step == LOOK
    setup.look_cards["timeline"].chosen.emit()
    setup.next.click()
    assert setup.step == COLOURS
    setup.colours.buttons()[1].click()
    setup.text_size.buttons()[2].click()
    setup.next.click()
    assert setup.step == WEEK
    step, answer = kept[-1]
    assert step == COLOURS and isinstance(answer, dict)
    assert answer["layout"]["main"] == "timeline"
    assert answer["layout"]["options"]["timeline"]["colour"] == "night"
    assert answer["look"]["knobs"]["text"] == "large"
    setup.back.click()
    assert setup.step == COLOURS, "Back from the week returns to the look the student built"
    setup.close()


def test_a_spotify_alarm_needs_a_spotify_link(qapp: QApplication) -> None:
    setup = opened(qapp)
    setup._show(REMINDERS)
    setup.tone_buttons["spotify"].setChecked(True)
    assert setup.spotify.isEnabled()
    setup.spotify.setText("https://example.com/song")
    setup.next.click()
    assert setup.step == REMINDERS
    assert setup.error.text() == (
        "Paste a link that starts with https://open.spotify.com, or pick another sound."
    )
    setup.spotify.setText(SPOTIFY)
    setup.next.click()
    assert setup.step == FIRST
    assert setup.error.text() == ""
    setup.close()


def test_school_has_to_end_after_it_starts(qapp: QApplication) -> None:
    setup = opened(qapp)
    setup._show(WEEK)
    setup.school_times.set_span("15:00", 0)
    setup.next.click()
    assert setup.step == WEEK and "School" in setup.error.text()
    setup.school_days.set_days([])
    setup.next.click()
    assert setup.step == HOMEWORK, "no school days means no school, so its hours do not matter"
    setup.close()


def test_first_homework_takes_up_to_three(qapp: QApplication) -> None:
    setup = opened(qapp)
    setup._show(FIRST)
    assert len(setup.homework_rows) == 1
    setup.add_homework.click()
    setup.add_homework.click()
    assert len(setup.homework_rows) == 3
    assert not setup.add_homework.isEnabled()
    setup._add_homework_row()
    assert len(setup.homework_rows) == 3, "a fourth is refused however it is asked for"
    due = setup.homework_rows[0].due
    assert due.date.calendarPopup()
    assert due.value() == sunday_due(monday_of("2026-09-23"))[:10], "due that Sunday, with no time"
    setup.close()


def test_a_time_steps_a_quarter_hour_and_a_typed_one_keeps_its_minute(qapp: QApplication) -> None:
    """School that starts at 08:05 starts at 08:05. It was moved to 08:00 without a word."""
    field = QuarterTime("08:00")
    field.setCurrentSection(QDateTimeEdit.Section.MinuteSection)
    field.stepBy(1)
    assert field.hhmm() == "08:15"
    field.stepBy(-2)
    assert field.hhmm() == "07:45"
    field.setTime(QTime(8, 7))
    field.editingFinished.emit()
    assert field.hhmm() == "08:07"
    field.stepBy(1)
    assert field.hhmm() == "08:15", "the arrows go on to the quarter hour either side"
    field.setTime(QTime(8, 7))
    field.stepBy(-1)
    assert field.hhmm() == "08:00"


def test_a_style_card_is_picked_from_the_keyboard(qapp: QApplication) -> None:
    setup = opened(qapp)
    card = setup.style_cards["dashboard"]
    card.setFocus(Qt.FocusReason.TabFocusReason)
    QTest.keyClick(card, Qt.Key.Key_Space)
    assert card.is_selected()
    assert not setup.style_cards["plain"].is_selected()
    setup.close()


def test_a_step_already_seen_can_be_jumped_to_from_the_rail(qapp: QApplication) -> None:
    setup = opened(qapp)
    setup.skip.click()
    setup.skip.click()
    assert setup.step == HOMEWORK
    setup.rail_items[1].click()
    assert setup.step == WEEK
    assert not setup.rail_items[4].isEnabled(), "a step not reached yet is shown out of reach"
    setup._jump(FIRST)
    assert setup.step == WEEK, "and stays out of reach"
    setup.close()


@pytest.mark.parametrize("size", ["small", "normal", "large"])
def test_time_labels_sit_level_with_their_fields(qapp: QApplication, size: str) -> None:
    host = QWidget()
    host.setStyleSheet(pack_stylesheet("light-frost", False, {"preset": "default", "knobs": {"text": size}}))
    setup = SetupPage(host)
    setup.motion = "off"
    setup.open(state())
    host.resize(1100, 760)
    setup.resize(1100, 760)
    host.show()
    setup._show(WEEK)
    qapp.processEvents()
    row = setup.school_times
    for label, field in zip(
        [child for child in row.children() if child.objectName() == "setupFieldLabel"],
        (row.start, row.end),
        strict=True,
    ):
        label_mid = label.mapTo(row, QPoint(0, label.height() // 2)).y()
        field_mid = field.mapTo(row, QPoint(0, field.height() // 2)).y()
        assert abs(label_mid - field_mid) <= 3, (size, label.text())
    host.close()


def _top(widget: QWidget, within: QWidget) -> int:
    return widget.mapTo(within, QPoint(0, 0)).y()


def test_the_experimental_styles_and_designs_come_after_their_heading(qapp: QApplication) -> None:
    """Decision 3 of 0.16: Plain calendar and Night owl first, Dashboard and Retro under
    "Experimental styles"; on the next page Today's app and Timeline first, the other four after."""
    setup = opened(qapp)
    style_page = setup.pages[STYLE]
    heading = next(label for label in style_page.findChildren(QLabel) if label.text() == EXPERIMENTAL)
    line = _top(heading, style_page)
    above = sorted(key for key, card in setup.style_cards.items() if _top(card, style_page) < line)
    below = sorted(key for key, card in setup.style_cards.items() if _top(card, style_page) > line)
    assert (above, below) == (["night", "plain"], ["dashboard", "retro"])
    setup._show(LOOK)
    qapp.processEvents()
    look_page = setup.pages[LOOK]
    heading = next(label for label in look_page.findChildren(QLabel) if label.text() == EXPERIMENTAL)
    line = _top(heading, look_page)
    above = [key for key, card in setup.look_cards.items() if _top(card, look_page) < line]
    assert above == ["classic", "timeline"]
    setup.close()


def test_the_day_screen_chips_are_one_choice_across_two_rows(qapp: QApplication) -> None:
    setup = opened(qapp)
    setup._show(LOOK)
    setup._show(COLOURS)
    qapp.processEvents()
    chips = setup.day_screen
    assert chips.experimental_heading.text() == "Experimental styles"
    assert chips.experimental_heading.isVisibleTo(setup)
    dial, one = chips.buttons()
    assert _top(dial, setup) < _top(chips.experimental_heading, setup) < _top(one, setup)
    one.click()
    assert chips.value() == "one" and not dial.isChecked()
    dial.click()
    assert chips.value() == "dial" and not one.isChecked()
    assert setup._layout["day"] == "dial"
    setup.close()


def test_the_planning_hours_presets_are_quiet_buttons_that_add_a_row(qapp: QApplication) -> None:
    """R21: drawn as filled pills they read as choices, and none showed as chosen."""
    setup = opened(qapp)
    setup._show(HOMEWORK)
    qapp.processEvents()
    editor = setup.work_editor
    note = editor.findChild(QLabel, "workWindowsPresetsNote")
    assert note.text() == "Each adds a row of hours you can change."
    after = editor.findChild(QPushButton, "workWindowPresetAfterschool")
    assert after.text() == "+ After school" and after.property("quiet") is True
    assert editor.add_button.property("quiet") is not True, "Add custom hours stays the filled one"
    after.click()
    assert editor.windows() == [{"days": [0, 1, 2, 3, 4], "start": "15:30", "end": "18:00"}]
    setup.close()


def test_the_alarm_sounds_are_a_form_with_play_in_its_own_column(qapp: QApplication) -> None:
    """R21: the Play buttons sat in a three-column grid beside their names and did not line up."""
    setup = opened(qapp)
    setup._show(REMINDERS)
    qapp.processEvents()
    body = setup.pages[REMINDERS]
    plays = [button for button in body.findChildren(QPushButton, "setupPlay") if button.isVisibleTo(setup)]
    tones = [key for key in setup.tone_buttons if key != "spotify"]
    assert len(plays) == len(tones)
    assert len({button.mapTo(body, QPoint(0, 0)).x() for button in plays}) == 1, "one column"
    for tone, play in zip(tones, plays, strict=True):
        radio = setup.tone_buttons[tone]
        assert play.accessibleName() == f"Play {radio.text()}"
        middle = radio.mapTo(body, QPoint(0, radio.height() // 2)).y()
        assert abs(play.mapTo(body, QPoint(0, play.height() // 2)).y() - middle) <= 2, tone
    setup.close()
