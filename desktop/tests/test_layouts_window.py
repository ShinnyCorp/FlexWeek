"""Layouts in the real window, against a real local backend: My day puts planning away and brings it
back, a day screen's buttons reach the behaviour the product already has, the choice survives a
restart, and Settings holds Main view and Day screen with their three levels.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import time
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QPoint, QRect, QStandardPaths, Qt
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QLabel,
        QPushButton,
        QRadioButton,
        QWidget,
    )

    from desktop.native.calendar import sunday_due
    from desktop.native.layouts.one_thing import OneThingView
    from desktop.native.layouts.registry import LAYOUTS, sanitize_layout
    from desktop.native.layouts.views import VIEW_CLASSES
    from desktop.native.motion import EASE_MS, PAGE_IN_MS, PAGE_OUT_MS, duration
    from desktop.native.settings import SettingsPage
    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer
    from desktop.tests.logic_support import past_setup

PASSWORD = "a-long-test-password"


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    application = QApplication.instance() or QApplication(["flexweek-layouts-window-test"])
    yield application


def wait_until(qapp: QApplication, predicate: Callable[[], bool], timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was still false")


def settled(qapp: QApplication, window: NativeWindow) -> None:
    wait_until(qapp, lambda: not window.session.busy and not window.session.dirty)


def look_file() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(root) / "flexweek-look.json"


@pytest.fixture()
def window(qapp: QApplication, tmp_path: Path) -> Iterator[NativeWindow]:
    """Signed in on this week with school, dinner and an essay planned for Thursday evening, and the
    clock held at Thursday 19:00 so the tests do not depend on the day they run."""
    look_file().unlink(missing_ok=True)
    server = LocalServer(tmp_path / "flexweek.db")
    server.start()
    made = NativeWindow(server.origin)
    made.show()
    try:
        made.username.setText("layout_student")
        made.password.setText(PASSWORD)
        made.findChild(QPushButton, "createAccount").click()
        wait_until(qapp, lambda: made._stack.currentWidget().objectName() == "recoveryPage")
        made.recovery_ack.setChecked(True)
        made.recovery_continue.click()
        past_setup(qapp, made)
        wait_until(qapp, lambda: made.session.preferences is not None)
        session = made.session
        thursday = datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=19)
        session.now_ms = lambda: int(thursday.timestamp() * 1000)
        session.add_block(
            {
                "id": "school",
                "title": "School",
                "kind": "locked",
                "category": "class",
                "start": "08:00",
                "duration_min": 390,
                "days": [0, 1, 2, 3, 4],
            }
        )
        session.add_homework(
            {
                "id": "essay",
                "title": "History essay",
                "due": sunday_due(session.week_start),
                "estimate_min": 60,
                "revision": 0,
            }
        )
        session.save()
        settled(qapp, made)
        work = next(block for block in session.blocks if block.get("assignment_id") == "essay")
        work.update({"start": "18:45", "days": [3], "duration_min": 60})
        session.add_block(work)
        session.save()
        settled(qapp, made)
        yield made
    finally:
        with contextlib.suppress(RuntimeError):
            made.session.client.reset()
        made.hide()
        qapp.processEvents()
        server.stop()
        look_file().unlink(missing_ok=True)


def click(window: NativeWindow, name: str) -> None:
    window.findChild(QPushButton, name).click()


def one_thing(window: NativeWindow) -> None:
    """One thing as the day screen. Day dial is the default since 0.16; these tests are about One
    thing's own buttons."""
    window._layout = sanitize_layout({**window._layout, "day": "one"})


def faded_in() -> None:
    """A new page fades through; a picture of it is what the student sees once it has."""
    QTest.qWait(duration(PAGE_OUT_MS + PAGE_IN_MS, "extra") + 100)


def test_my_day_puts_planning_away_and_back_brings_it_back(qapp: QApplication, window: NativeWindow) -> None:
    one_thing(window)
    assert window.planner.currentWidget() is window.week_table
    click(window, "viewMyDay")
    assert isinstance(window.planner.currentWidget(), OneThingView)
    assert window.solve_button.isVisible() is True
    assert window.findChild(QPushButton, "viewMyDay").isChecked() is True
    assert window.findChild(QPushButton, "viewWeek").isChecked() is False
    click(window, "oneBack")
    assert window.planner.currentWidget() is window.week_table
    assert window.solve_button.isVisible() is True
    assert window.findChild(QPushButton, "viewWeek").isChecked() is True


def test_the_day_screen_reads_the_real_week_at_the_real_minute(
    qapp: QApplication, window: NativeWindow
) -> None:
    one_thing(window)
    click(window, "viewMyDay")
    view = window.planner.currentWidget()
    said = tuple(view.findChild(QLabel, name).text() for name in ("oneLabel", "oneTitle", "oneLine"))
    assert said == ("Now", "History essay", "18:45–19:45")


def test_homework_finished_finishes_it_the_way_the_product_does(
    qapp: QApplication, window: NativeWindow
) -> None:
    one_thing(window)
    click(window, "viewMyDay")
    click(window, "oneFinished")
    settled(qapp, window)
    assert window.session.assignments["essay"]["completed"] is True
    assert window.session.can_undo() is True
    view = window.planner.currentWidget()
    assert view.findChild(QLabel, "oneTitle").text() == "All homework finished"


def test_start_focus_keeps_the_timer_in_view_on_a_day_screen(
    qapp: QApplication, window: NativeWindow
) -> None:
    one_thing(window)
    click(window, "viewMyDay")
    assert window.focus_panel.isVisible() is False
    click(window, "oneFocus")
    wait_until(qapp, lambda: window.session.focus is not None)
    assert window.session.focus["title"] == "History essay"
    assert window._stack.currentWidget() is window.focus_screen
    QTest.keyClick(window.focus_screen, Qt.Key.Key_Escape)
    assert window._stack.currentWidget().objectName() == "weekPage"
    assert window.focus_panel.isVisible() is True
    assert window.solve_button.isVisible() is True


def test_running_late_opens_the_products_own_running_late(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    one_thing(window)
    opened: list[str] = []
    monkeypatch.setattr(NativeWindow, "_open_late", lambda self: opened.append("late"))
    click(window, "viewMyDay")
    click(window, "oneLate")
    assert opened == ["late"]


def test_a_blocked_running_late_toasts_why(qapp: QApplication, window: NativeWindow) -> None:
    from desktop.native.widgets import TOAST_MS

    window.session.dirty = True
    window._open_late()
    saving = "Your last change is still saving. Try again in a moment."
    assert window.toast.isVisible() is True
    assert window.toast.text() == saving
    assert window.toast._timer.interval() == TOAST_MS

    window.session.dirty = False
    window.session.conflict = True
    window._open_late()
    conflict = "This week was changed somewhere else. Reload it first."
    assert window.toast.text() == conflict


def test_the_notice_sits_under_the_bar_on_one_line(qapp: QApplication, window: NativeWindow) -> None:
    """A notice short enough for one line stays on one line, and it never covers the bar. Sized from
    a wrapped label it broke after "locked. 2". It sits over the foot of the hours now, far below the
    bar at either text size."""
    said = "Running late: 16:30–17:00 is now locked. 2 moved."
    for text in ("normal", "large"):
        window._look = {**window._look, "knobs": {**(window._look.get("knobs") or {}), "text": text}}
        window._apply_appearance()
        settled(qapp, window)
        window.toast.show_message("OK")
        one_line = window.toast.height()
        window.toast.show_message(said)
        settled(qapp, window)
        bar_bottom = max(
            button.mapTo(window, button.rect().bottomLeft()).y()
            for button in (window.solve_button, window.more_button, window.settings_gear)
        )
        assert (text, window.toast.height()) == (text, one_line)
        assert window.toast.y() > bar_bottom, text


def accept_late(qapp: QApplication, window: NativeWindow) -> tuple[dict, str]:
    from desktop.native.reuse import late_locked_line

    now = datetime.fromtimestamp(window.session.now_ms() / 1000)
    window.session.preview_running_late(30, now)
    wait_until(qapp, lambda: window.session.late_preview is not None and not window.session.busy)
    preview = window.session.late_preview
    moved = len((preview.get("trace") or {}).get("moves") or [])
    window._commit_late(preview)
    return preview["block"], late_locked_line(preview["block"], moved)


def test_accepting_running_late_says_locked_once_it_is_saved(
    qapp: QApplication, window: NativeWindow
) -> None:
    block, said = accept_late(qapp, window)
    assert window.session.selected_block_id == block["id"]
    # "Locked" is not said before the save answers: until then the late start is not kept anywhere.
    assert not (window.toast.isVisible() and window.toast.text() == said)
    wait_until(qapp, lambda: window.toast.isVisible() and window.toast.text() == said)
    assert window.toast.text() == said
    assert window.session.dirty is False
    assert any(item["id"] == block["id"] for item in window.session.blocks)


def test_a_save_without_the_late_start_does_not_confirm_it(qapp: QApplication, window: NativeWindow) -> None:
    """A save already in flight when Running late was accepted stores the week without it."""
    window._late_waiting = ("b-late-not-stored-yet", "Running late: 19:00–19:30 is now locked.")
    window.session.save_finished.emit(True, "Saved.")
    qapp.processEvents()
    assert window.toast.isVisible() is False


def test_a_late_start_that_fails_to_save_says_so_instead(qapp: QApplication, window: NativeWindow) -> None:
    from desktop.tests.logic_support import fail_once

    fail_once(window.session, "POST", "/api/changes", 409)
    _block, said = accept_late(qapp, window)
    wait_until(qapp, lambda: window.toast.isVisible())
    assert window.toast.text() != said
    assert window.toast.text().startswith("Not saved.")
    assert window.session.conflict is True


def test_the_keyboard_reaches_my_day_and_back(qapp: QApplication, window: NativeWindow) -> None:
    """The week grid keeps letter keys for type-ahead, so T has to be taken the way W, D and M are."""
    one_thing(window)
    QTest.keyClick(window.week_table, Qt.Key.Key_T)
    day = window.planner.currentWidget()
    assert isinstance(day, OneThingView)
    QTest.keyClick(day, Qt.Key.Key_B)
    assert window.planner.currentWidget() is window.week_table
    QTest.keyClick(window.week_table, Qt.Key.Key_T)
    QTest.keyClick(window.planner.currentWidget(), Qt.Key.Key_Escape)
    assert window.planner.currentWidget() is window.week_table
    QTest.keyClick(window.week_table, Qt.Key.Key_T)
    QTest.keyClick(window.planner.currentWidget(), Qt.Key.Key_M)
    wait_until(qapp, lambda: window.planner.currentWidget() is window.month_grid)
    assert window.solve_button.isVisible() is True
    QTest.keyClick(window.month_grid.canvas, Qt.Key.Key_T)
    assert isinstance(window.planner.currentWidget(), OneThingView)


def test_the_view_buttons_leave_a_day_screen(qapp: QApplication, window: NativeWindow) -> None:
    click(window, "viewMyDay")
    click(window, "viewDay")
    assert window.planner.currentWidget() is window.day_view
    assert window.solve_button.isVisible() is True


def test_signing_out_of_a_day_screen_does_not_leave_the_next_student_in_one(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop.native import window as window_module

    monkeypatch.setattr(window_module, "confirm", lambda *_args, **_kwargs: True)
    click(window, "viewMyDay")
    click(window, "signOut")
    wait_until(qapp, lambda: window._stack.currentWidget().objectName() == "authPage")
    assert window._day_mode is False


def test_the_choice_is_saved_on_this_device_beside_the_look(qapp: QApplication, window: NativeWindow) -> None:
    window._look = {"preset": "paper", "knobs": {"corners": "rounded"}}
    window._layout = {"main": "classic", "day": "one", "options": {"one": {"colour": "paper"}}}
    window._save_look()
    stored = json.loads(look_file().read_text())
    assert stored["preset"] == "paper"
    assert stored["knobs"] == {"corners": "rounded"}
    assert stored["layout"] == {
        "main": "classic",
        "day": "one",
        "options": {"one": {"colour": "paper"}},
    }
    # Whether this computer checks for updates lives beside the look, because it is a property of
    # the computer rather than the account.
    assert set(stored["updates"]) == {"check", "last_ms", "skip"}
    window._look, window._layout = {}, {}
    window._load_look()
    assert window._look == {"preset": "paper", "knobs": {"corners": "rounded"}}
    assert window._layout["options"] == {"one": {"colour": "paper"}}
    click(window, "viewMyDay")
    faded_in()
    assert window.planner.currentWidget().grab().toImage().pixelColor(4, 4).name() == "#f7f1e3"


def test_a_look_file_from_before_layouts_still_loads(qapp: QApplication, window: NativeWindow) -> None:
    look_file().parent.mkdir(parents=True, exist_ok=True)
    look_file().write_text(json.dumps({"preset": "terminal", "knobs": {}}))
    window._load_look()
    assert window._look["preset"] == "terminal"
    assert window._layout == {"main": "classic", "day": "dial", "options": {}}
    look_file().write_text("not json")
    window._load_look()
    assert window._layout == {"main": "classic", "day": "dial", "options": {}}


def test_saving_the_look_from_settings_keeps_the_layout(qapp: QApplication, window: NativeWindow) -> None:
    window._layout = {"main": "classic", "day": "one", "options": {"one": {"daybar": "hide"}}}
    window._look = {"preset": "ink", "knobs": {}}
    window._save_look()
    assert json.loads(look_file().read_text())["layout"]["options"] == {"one": {"daybar": "hide"}}


def test_a_changed_look_repaints_a_design_that_matches_it(qapp: QApplication, window: NativeWindow) -> None:
    window._layout = {"main": "classic", "day": "one", "options": {"one": {"colour": "match"}}}
    click(window, "viewMyDay")
    faded_in()
    view = window.planner.currentWidget()
    before = view.grab().toImage().pixelColor(4, 4).name()
    window._look = {"preset": "terminal", "knobs": {}}
    window._apply_appearance()
    after = view.grab().toImage().pixelColor(4, 4).name()
    assert before != after
    assert after == view.scene.tokens["bg"]


def combo(dialog: SettingsPage, name: str) -> QComboBox:
    """A choice by name, whether a dropdown, a segmented control or the design cards: all three
    answer a dropdown's calls."""
    return dialog.findChild(QWidget, name)


def rows(dialog: SettingsPage, slot: str) -> list[str]:
    from desktop.native.widgets import Segmented

    return sorted(
        box.objectName()
        for box in dialog.findChildren(QWidget)
        if isinstance(box, (QComboBox, Segmented)) and box.objectName().startswith(f"layout{slot}-")
    )


def open_settings(window: NativeWindow) -> SettingsPage:
    """Settings as the gear opens it, in place of the week."""
    window._open_settings()
    page = window._settings
    assert page is not None and window._stack.currentWidget() is page
    return page


def prefs_layout(choice: dict | None = None) -> SettingsPage:
    return SettingsPage(None, {}, {}, {}, choice)


def test_every_view_says_what_it_is_for_before_its_style_name(qapp: QApplication) -> None:
    """ "Today's app" turned out to be the plain calendar; nothing in the menu said so. A student picks
    by what the view does, so that comes first and the style name after it."""
    dialog = prefs_layout()
    main = combo(dialog, "layoutMain")
    assert [main.itemText(index) for index in range(main.count())] == [
        "Calendar · Today's app",
        "Agenda · Timeline",
        "Dashboard · Mission control",
        "Dashboard · Bento",
        "Dashboard · Retro desktop",
        "Agenda · Clay deck",
    ]


def test_settings_shows_only_what_the_main_view_uses(qapp: QApplication) -> None:
    """Surface, Corners and Blocks stayed on screen for every design, though only Today's app reads
    them, so a student changed them in Bento and nothing happened. Look and Accent stay for every
    design: they dress the top bar and every window whatever the design (decision 3 of 0.17)."""
    from desktop.native.layouts.dialog import COLOUR_NOTE
    from desktop.native.settings import FINE_TUNE_LOOK, TODAYS_APP_KNOBS

    dialog = prefs_layout({"main": "classic", "day": "one", "options": {}})
    dialog.fine_tune.setChecked(True)
    dialog.show()
    qapp.processEvents()

    def note() -> QLabel | None:
        return dialog.findChild(QLabel, "layoutMainColourNote")

    def shown() -> dict[str, bool]:
        fields = {"look": dialog.look, "accent": dialog.accent, "chips": dialog.accent_chips}
        fields.update(dialog.knobs)
        return {name: field.isVisibleTo(dialog) for name, field in fields.items()} | {
            "note": note() is not None and note().isVisibleTo(dialog)
        }

    everything = shown()
    assert everything.pop("note") is False and all(everything.values())
    assert dialog.fine_tune.text() == FINE_TUNE_LOOK

    main = combo(dialog, "layoutMain")
    main.setCurrentIndex(main.findData("bento"))
    qapp.processEvents()
    # Bento arrives in Match my look, so there is nothing to say about colours of its own.
    matched = shown()
    assert {name for name, on in matched.items() if not on} == {"note", *TODAYS_APP_KNOBS}
    assert dialog.fine_tune.text() == FINE_TUNE_LOOK

    colour = combo(dialog, "layoutMain-colour")
    colour.setCurrentIndex(colour.findData(signature("bento")))
    qapp.processEvents()
    own = shown()
    assert {name for name, on in own.items() if not on} == set(TODAYS_APP_KNOBS)
    assert note().text() == COLOUR_NOTE
    assert dialog.fine_tune.text() == FINE_TUNE_LOOK

    main.setCurrentIndex(main.findData("classic"))
    qapp.processEvents()
    assert all(on for name, on in shown().items() if name != "note")
    dialog.close()


@pytest.mark.parametrize("main", ["timeline", "mission", "bento", "retro", "clay"])
def test_the_knobs_settings_hides_for_a_design_change_nothing_in_it(
    qapp: QApplication, window: NativeWindow, main: str
) -> None:
    """The reason Settings hides them. If a design starts reading one, show it again for that design."""
    from desktop.native.look import LOOK_DEFAULTS, LOOK_KNOBS, sanitize_look
    from desktop.native.settings import TODAYS_APP_KNOBS

    def view_with(knobs: dict[str, str], prefs: dict | None = None) -> QImage:
        window.session.preferences = {**base, **(prefs or {})}
        window._look = sanitize_look({"preset": "default", "knobs": knobs})
        # In its own colours: in Match my look a design wears the look, Surface included.
        colour = {main: {"colour": own_accent(main)}}
        window._layout = sanitize_layout({"main": main, "day": "one", "options": colour})
        window._apply_appearance()
        window._on_week()
        for _ in range(20):
            qapp.processEvents()
        return window.planner.currentWidget().grab().toImage()

    # Still pictures: with animations off, every picture is of the page as it settles.
    base = {**(window.session.preferences or {}), "motion": "off"}
    plain = view_with({})
    for knob in TODAYS_APP_KNOBS:
        other = next(value for value in LOOK_KNOBS[knob] if value != LOOK_DEFAULTS[knob])
        assert view_with({knob: other}) == plain, knob
    assert view_with({}, {"theme_pack": "dark-frost"}) == plain, "look"
    assert view_with({}, {"accent": "gold"}) == plain, "accent"


def test_a_custom_look_dresses_the_window_and_is_kept_with_the_saved_looks(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Customise end to end: Paper made a night look of the student's own, with Sea for the accent,
    School in green, square-ish corners, mono headings and larger text, worn by the whole window,
    saved by name in the look file and read back as it was."""
    from desktop.native.custom_look import save_look, wear
    from desktop.native.look import category_paint, oklch, sanitize_look
    from desktop.native.tokens import MARK

    custom = {
        "name": "Night study",
        "base": "paper",
        "accent": "sea",
        "colours": {"page": "#1e2430", "card": "#262d3b", "text": "#e8ecf2", "line": "#394255"},
        "categories": {"class": {"hue": 140}},
        "corners": 4,
        "heading_font": "mono",
        "text_scale": 1.2,
    }
    window._look = wear(sanitize_look(None), custom)
    window._saved_looks = save_look([], custom, "Night study")
    window._apply_appearance()
    window._on_week()
    settled(qapp, window)
    painter = window.week_table.hours.painter
    assert (painter.colours["window"], painter.colours["accent"]) == ("#1e2430", "#2dd4bf")
    # A dark page makes a dark look: School's green sunk into the card, its mark on the dark family.
    assert category_paint("class", painter.colours)[1] == oklch(*MARK["dark"], 140)
    title = window.findChild(QLabel, "weekTitle")
    assert title.font().family() == "JetBrains Mono"
    assert "font-size: 15.5pt" in window.styleSheet() and "border-radius: 4px" in window.styleSheet()
    picture = window.week_table.hours.grab().toImage()
    colours = {picture.pixelColor(x, y).name() for x in range(0, picture.width(), 40) for y in (5, 200)}
    # Today's app draws its hours on a sheet in the card's colour, beside the rail on the page.
    assert "#262d3b" in colours
    window._save_look()
    stored = json.loads(look_file().read_text())
    assert stored["custom"] == custom and stored["saved_looks"] == [custom]
    window._look, window._saved_looks = {}, []
    window._load_look()
    assert window._look["custom"] == custom and window._saved_looks == [custom]


def test_the_dialog_shows_style_first_and_fine_tune_on_request(qapp: QApplication) -> None:
    dialog = prefs_layout()
    assert [combo(dialog, "layoutDay").itemText(index) for index in range(2)] == [
        "Clock · Day dial",
        "Focus · One thing",
    ]
    pick = combo(dialog, "layoutDay")
    pick.setCurrentIndex(pick.findData("one"))
    assert rows(dialog, "Day") == ["layoutDay-colour"]
    dialog.findChild(QCheckBox, "layoutDayMore").setChecked(True)
    assert rows(dialog, "Day") == [
        "layoutDay-actions",
        "layoutDay-colour",
        "layoutDay-daybar",
        "layoutDay-lead",
    ]
    assert rows(dialog, "Main") == []


def test_the_dialog_stores_only_what_the_student_changed(qapp: QApplication) -> None:
    dialog = prefs_layout({"main": "classic", "day": "one"})
    assert dialog.layout_choice() == {"main": "classic", "day": "one", "options": {}}
    colour = combo(dialog, "layoutDay-colour")
    colour.setCurrentIndex(colour.findData("paper"))
    assert dialog.layout_choice()["options"] == {"one": {"colour": "paper"}}
    colour = combo(dialog, "layoutDay-colour")
    colour.setCurrentIndex(colour.findData("match"))
    assert dialog.layout_choice()["options"] == {}


def test_fine_tuning_already_in_use_is_not_hidden(qapp: QApplication) -> None:
    dialog = prefs_layout({"day": "one", "options": {"one": {"daybar": "hide"}}})
    assert dialog.findChild(QCheckBox, "layoutDayMore").isChecked() is True
    assert combo(dialog, "layoutDay-daybar").currentData() == "hide"


def test_trying_another_design_and_coming_back_loses_nothing(qapp: QApplication) -> None:
    dialog = prefs_layout({"day": "one", "options": {"one": {"colour": "paper"}}})
    pick = combo(dialog, "layoutDay")
    pick.setCurrentIndex(pick.findData("dial"))
    assert combo(dialog, "layoutDay-colour").currentData() == "match"
    pick.setCurrentIndex(pick.findData("one"))
    assert combo(dialog, "layoutDay-colour").currentData() == "paper"
    assert dialog.layout_choice()["options"] == {"one": {"colour": "paper"}}


def test_a_design_can_be_put_back_to_its_own_settings(qapp: QApplication) -> None:
    dialog = prefs_layout({"day": "one", "options": {"one": {"colour": "paper", "lead": "next"}}})
    dialog.findChild(QPushButton, "layoutDayReset").click()
    assert dialog.layout_choice()["options"] == {}
    assert dialog.findChild(QCheckBox, "layoutDayMore").isChecked() is False
    assert dialog.findChild(QPushButton, "layoutDayReset").text() == "Reset this layout's options"


def test_every_built_view_is_a_design_in_the_registry(qapp: QApplication) -> None:
    # Today's app is the week grid itself, so it is the one design with no view of its own.
    assert set(VIEW_CLASSES) == set(LAYOUTS) - {"classic"}
    assert all(view.layout_id == layout_id for layout_id, view in VIEW_CLASSES.items())


def test_my_day_opens_whichever_day_screen_was_picked(qapp: QApplication, window: NativeWindow) -> None:
    window._layout = {"main": "classic", "day": "dial", "options": {}}
    click(window, "viewMyDay")
    view = window.planner.currentWidget()
    assert type(view).__name__ == "DayDialView"
    assert view.findChild(QLabel, "dialTitle").text() == "History essay"
    click(window, "dialBack")
    assert window.planner.currentWidget() is window.week_table


def test_timelines_pages_are_its_paper_in_the_real_window(qapp: QApplication, window: NativeWindow) -> None:
    """The window's stylesheet paints every plain widget in the page colour. Under the hours, beside
    the zoom above them and behind Day's notes are plain widgets of Qt's own: drawn offscreen alone
    they showed the pages; in the window they would be grey bands on white paper."""
    window._layout = {"main": "timeline", "day": "one", "options": {}}
    window._on_week()
    faded_in()
    view = window.planner.currentWidget()
    paper = view.scene.tokens["surface"]
    assert paper != view.scene.tokens["bg"], "the page and the paper differ, or this checks nothing"
    hours = view.hours_surfaces()[0]
    header = view.findChild(QWidget, "timelineWeekHeader")
    between = round(hours.track_for(3).point_for(12 * 60 + 30).y())
    image = view.grab().toImage()
    # Left of the hour labels at half past twelve, where no label is; under the scroll bar at the
    # right edge, clear of its handle; and right of the zoom.
    assert image.pixelColor(hours.mapTo(view, QPoint(3, between))).name() == paper
    assert image.pixelColor(hours.mapTo(view, QPoint(hours.width() - 10, between))).name() == paper
    assert image.pixelColor(header.mapTo(view, QPoint(round(hours.gutter) - 3, 3))).name() == paper
    click(window, "viewDay")
    settled(qapp, window)
    faded_in()
    notes = view.findChild(QWidget, "timelineNotesPage")
    image = view.grab().toImage()
    assert image.pixelColor(notes.mapTo(view, QPoint(notes.width() - 3, 3))).name() == paper


def test_a_sticky_notes_small_print_is_regular_in_the_real_window(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window's stylesheet sets every button's font at 600; a note is a button, and its length
    and due date came out as bold as its title."""
    from PySide6.QtGui import QPainter

    from desktop.native.layouts import timeline

    written: list[tuple[str, int]] = []

    class Seen(QPainter):
        def drawText(self, *args) -> None:  # noqa: N802
            written.append((next(arg for arg in args if isinstance(arg, str)), self.font().weight()))
            super().drawText(*args)

    monkeypatch.setattr(timeline, "QPainter", Seen)
    session = window.session
    session.add_homework(
        {"id": "poster", "title": "Science poster", "due": sunday_due(session.week_start), "estimate_min": 60,
         "revision": 0}
    )
    session.save()
    settled(qapp, window)
    window._layout = {"main": "timeline", "day": "one", "options": {}}
    window._on_week()
    qapp.processEvents()
    view = window.planner.currentWidget()
    view.findChild(QPushButton, "timelineWaiting0").grab()
    assert ("Science", 600) in written
    assert [weight for words, weight in written if words == "1 h"] == [400]


def test_timelines_names_and_figures_take_the_looks_heading_face(
    qapp: QApplication, window: NativeWindow
) -> None:
    """In Match my look, as the mock-up draws them: Paper's serif headings are Newsreader."""
    from desktop.native.look import sanitize_look

    window._look = sanitize_look({"preset": "paper"})
    window._layout = {"main": "timeline", "day": "one", "options": {}}
    window._apply_appearance()
    window._on_week()
    qapp.processEvents()
    view = window.planner.currentWidget()
    found = [*view.findChildren(QLabel, "timelineDayName"), *view.findChildren(QLabel, "timelineStat")]
    assert found and {item.font().family() for item in found} == {"Newsreader"}


def test_the_dials_list_is_one_card_in_the_real_window(qapp: QApplication, window: NativeWindow) -> None:
    """The window's stylesheet paints every styled widget in the page colour. Drawn offscreen alone the
    list's last row was on its card; in the window it sat on a grey band."""
    window._layout = {"main": "classic", "day": "dial", "options": {}}
    click(window, "viewMyDay")
    faded_in()
    view = window.planner.currentWidget()
    closing = view.findChild(QWidget, "dialNone")
    # Right of its words, where only the background is drawn.
    spot = closing.mapTo(view, QPoint(closing.width() - 8, closing.height() // 2))
    assert view.grab().toImage().pixelColor(spot).name() == view.scene.tokens["surface"]


def test_summaries_speak_minutes_not_session_counts(qapp: QApplication, window: NativeWindow) -> None:
    import re

    from PySide6.QtWidgets import QListWidget

    sessions = re.compile(r"\b0 sessions?\b")

    def labels() -> list[str]:
        found = [lab.text() for lab in window.findChildren(QLabel) if lab.text()]
        for box in window.findChildren(QListWidget):
            found.extend(box.item(index).text() for index in range(box.count()))
        return found

    window.focus_panel.set_state(window.session)

    window._layout = {"main": "bento", "day": "one", "options": {}}
    window._on_week()
    qapp.processEvents()
    shown = labels()
    assert "This week" in shown
    assert not any(sessions.search(text) for text in shown)

    # Timeline's week in figures: the minutes of homework planned, and how many homework are done.
    window._layout = {"main": "timeline", "day": "one", "options": {}}
    window._on_week()
    qapp.processEvents()
    shown = labels()
    assert {"1 h", "homework planned", "0 of 1", "done"} <= set(shown)
    assert not any(sessions.search(text) for text in shown)

    click(window, "viewMyDay")
    click(window, "oneFinished")
    settled(qapp, window)
    click(window, "viewWeek")
    window._layout = {"main": "timeline", "day": "one", "options": {}}
    window._on_week()
    qapp.processEvents()
    shown = labels()
    assert {"1 h", "homework planned", "1 of 1", "done"} <= set(shown)
    assert not any(sessions.search(text) for text in shown)


def test_every_main_view_has_add_on_the_top_bar(qapp: QApplication, window: NativeWindow) -> None:
    """Add is the top bar's in every design (decision 11 of 0.17); a design draws no second one."""
    for spec in LAYOUTS.values():
        if spec.role != "plan":
            continue
        window._layout = {"main": spec.id, "day": "one", "options": {}}
        window._on_week()
        qapp.processEvents()
        assert window.findChild(QPushButton, "addButton").isVisible(), spec.id


def more_actions(window: NativeWindow) -> dict[str, bool]:
    """The items, without the section headings. addSection makes a separator that carries text.
    Undo, copy and save is a submenu, so its entries are included under their own names."""
    menu = window.more_button.menu()
    menu.aboutToShow.emit()
    offered: dict[str, bool] = {}
    for action in menu.actions():
        if action.isSeparator() or not action.text() or not action.isVisible():
            continue
        submenu = action.menu()
        if submenu is None:
            offered[action.text()] = action.isEnabled()
            continue
        offered[action.text()] = action.isEnabled()
        for inner in submenu.actions():
            if inner.text() and not inner.isSeparator() and inner.isVisible():
                offered[inner.text()] = inner.isEnabled()
    return offered


def more_sections(window: NativeWindow) -> list[str]:
    """The heading rows. Fusion never drew `addSection` titles, so the menu uses a label row instead."""
    from PySide6.QtWidgets import QWidgetAction

    menu = window.more_button.menu()
    menu.aboutToShow.emit()
    return [
        action.defaultWidget().text()
        for action in menu.actions()
        if isinstance(action, QWidgetAction) and isinstance(action.defaultWidget(), QLabel)
    ]


def test_plan_and_more_stay_on_the_bar_in_every_layout(qapp: QApplication, window: NativeWindow) -> None:
    """A design of its own used to hide Plan my homework and More behind Tools. That rule is gone:
    the same two buttons stay in the top bar in every layout, every view, and My day."""
    assert window.findChild(QPushButton, "toolsButton") is None
    sections = None
    items = None
    for main in ("classic", "bento", "timeline"):
        window._layout = {"main": main, "day": "one", "options": {}}
        window._on_week()
        assert window.solve_button.isVisible() is True
        assert window.more_button.isVisible() is True
        assert window.more_button.text() == "More"
        if sections is None:
            sections, items = more_sections(window), set(more_actions(window))
        else:
            assert more_sections(window) == sections
            assert set(more_actions(window)) == items
    window._layout = {"main": "bento", "day": "one", "options": {}}
    window._on_week()
    qapp.processEvents()
    assert window.planner.height() > window.height() * 0.8
    offered = more_actions(window)
    assert more_sections(window) == ["Planning"]
    assert not {"Add homework", "Add fixed time", "School hours"} & set(offered), "adding is under Add"
    wanted = {"Running late", "Routines", "Reload", "Undo", "Redo", "Undo, copy and save", "Log out"}
    assert wanted <= set(offered)
    assert "Settings" not in offered
    assert "Account" not in offered
    assert (offered["Undo"], offered["Redo"]) == (True, False)


def test_a_more_item_does_what_its_button_does(qapp: QApplication, window: NativeWindow) -> None:
    window._layout = {"main": "bento", "day": "one", "options": {}}
    window._on_week()
    before = len(window.session.blocks)
    menu = window.more_button.menu()
    menu.aboutToShow.emit()
    advanced = next(action.menu() for action in menu.actions() if action.text() == "Undo, copy and save")
    next(action for action in advanced.actions() if action.text() == "Undo").trigger()
    settled(qapp, window)
    assert len(window.session.blocks) != before or window.session.can_redo() is True


def test_day_and_month_follow_the_week_layout(qapp: QApplication, window: NativeWindow) -> None:
    window._layout = {"main": "bento", "day": "one", "options": {}}
    click(window, "viewDay")
    assert type(window.planner.currentWidget()).__name__ == "BentoView"
    assert window.planner.currentWidget().scene.surface == "day"
    assert (window.solve_button.isVisible(), window.more_button.isVisible()) == (True, True)
    click(window, "viewMonth")
    settled(qapp, window)
    shown = window.planner.currentWidget()
    assert type(shown).__name__ == "BentoView"
    assert shown.scene.surface == "month"
    click(window, "viewWeek")
    assert (window.solve_button.isVisible(), window.more_button.isVisible()) == (True, True)
    click(window, "viewMyDay")
    assert type(window.planner.currentWidget()).__name__ == "OneThingView"
    assert (window.solve_button.isVisible(), window.more_button.isVisible()) == (True, True)


def test_todays_app_keeps_the_clock_day_and_chip_month(qapp: QApplication, window: NativeWindow) -> None:
    window._layout = {"main": "classic", "day": "one", "options": {}}
    click(window, "viewDay")
    assert window.planner.currentWidget() is window.day_view
    assert window.solve_button.isVisible() is True
    click(window, "viewMonth")
    settled(qapp, window)
    assert window.planner.currentWidget() is window.month_grid


def test_bentos_buttons_reach_the_products_own_add_and_plan(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bento draws no Add of its own since 0.17: the top bar's is the one it uses."""
    asked: list[str] = []
    monkeypatch.setattr(NativeWindow, "_add_homework", lambda self: asked.append("add"))
    monkeypatch.setattr(type(window.session), "solve", lambda self: asked.append("plan"))
    window._layout = {"main": "bento", "day": "one", "options": {}}
    window._on_week()
    assert window.planner.currentWidget().findChild(QPushButton, "bentoAdd") is None
    click(window, "addButton")
    click(window, "solveButton")
    click(window, "viewMyDay")
    assert asked == ["add", "plan"]
    assert type(window.planner.currentWidget()).__name__ == "OneThingView"


def test_every_layout_leaves_the_window_fitting_a_laptop(qapp: QApplication, window: NativeWindow) -> None:
    # A busy Thursday: with two blocks every view is short, and three designs only outgrew the screen
    # once the day had a realistic number of rows.
    for index, (title, start) in enumerate(
        (
            ("Soccer", "15:30"),
            ("Dinner", "18:00"),
            ("Chores", "17:15"),
            ("Reading", "20:00"),
            ("Club", "07:00"),
        )
    ):
        window.session.add_block(
            {"id": f"busy{index}", "title": title, "kind": "locked", "category": "extra",
             "start": start, "duration_min": 30, "days": [3]}
        )  # fmt: skip
    for index in range(3):
        window.session.add_homework(
            {"id": f"wait{index}", "title": f"Waiting {index}", "due": sunday_due(window.session.week_start),
             "estimate_min": 45, "revision": 0}
        )  # fmt: skip
    sizes = {}
    for layout_id, spec in LAYOUTS.items():
        if layout_id not in VIEW_CLASSES:
            continue
        window._day_mode = spec.role == "day"
        window._layout = {
            "main": layout_id if spec.role == "plan" else "classic",
            "day": "dial",
            "options": {},
        }
        if spec.role == "day":
            window._layout["day"] = layout_id
        window._on_week()
        qapp.processEvents()
        assert type(window.planner.currentWidget()).layout_id == layout_id
        sizes[layout_id] = (window.minimumSizeHint().width(), window.minimumSizeHint().height())
    assert {name: size for name, size in sizes.items() if size[0] > 1366 or size[1] > 768} == {}


def test_the_dialog_fits_a_laptop_with_every_level_open(qapp: QApplication) -> None:
    busiest = {
        "main": "timeline",
        "day": "dial",
        "options": {"timeline": {"finished": "hide"}, "dial": {"list": "hide"}},
    }
    dialog = prefs_layout(busiest)
    for name in ("layoutMainMore", "layoutDayMore"):
        assert dialog.findChild(QCheckBox, name).isChecked() is True
    dialog.show()
    qapp.processEvents()
    assert dialog.height() <= 768
    assert dialog.width() <= 1366
    assert dialog.sizeHint().height() <= 768
    assert dialog.sizeHint().width() <= 1366


def test_fine_tune_and_reset_show_only_when_a_design_has_something_for_them(qapp: QApplication) -> None:
    """Today's app has nothing to change, Bento only styles, and Timeline also fine-tunes."""
    dialog = prefs_layout()
    dialog.show()
    qapp.processEvents()

    def offered() -> tuple[bool, bool]:
        return (
            dialog.findChild(QCheckBox, "layoutMainMore").isVisible(),
            dialog.findChild(QPushButton, "layoutMainReset").isVisible(),
        )

    assert offered() == (False, False)
    pick = combo(dialog, "layoutMain")
    pick.setCurrentIndex(pick.findData("bento"))
    assert offered() == (False, True)
    pick.setCurrentIndex(pick.findData("timeline"))
    assert offered() == (True, True)
    pick.setCurrentIndex(pick.findData("classic"))
    assert offered() == (False, False)


def preference_puts(window: NativeWindow) -> list[dict]:
    """Every preferences save the session sends, with what it sent."""
    sent: list[dict] = []
    real = window.session.client.request

    def spy(method, path, payload, on_success, on_error):  # type: ignore[no-untyped-def]
        if method == "PUT" and path == "/api/preferences":
            sent.append(dict(payload))
        return real(method, path, payload, on_success, on_error)

    window.session.client.request = spy  # type: ignore[method-assign]
    return sent


def test_a_settings_change_shows_before_settings_closes(qapp: QApplication, window: NativeWindow) -> None:
    """No OK: picking Bento changes the view behind Settings while it is still open, and so does an
    accent, and going back keeps both."""
    page = open_settings(window)
    pick = combo(page, "layoutMain")
    pick.setCurrentIndex(pick.findData("bento"))
    assert type(window.planner.currentWidget()).__name__ == "BentoView"
    assert window._stack.currentWidget() is page, "the change leaves Settings on screen"
    page.accent.setCurrentIndex(page.accent.findData("sea"))
    assert (window.session.preferences or {}).get("accent") == "sea"
    page.close_page()
    assert window._settings is None
    assert window._stack.currentWidget().objectName() == "weekPage"
    assert window._layout["main"] == "bento"


def test_settings_is_a_page_the_gear_opens_and_done_or_esc_closes(
    qapp: QApplication, window: NativeWindow
) -> None:
    """R11: Settings fills the window in place of the week, and the week's keys leave it alone."""
    from desktop.native.settings import SettingsPage

    window.findChild(QPushButton, "settingsGear").click()
    page = window._settings
    assert isinstance(page, SettingsPage) and window._stack.currentWidget() is page
    assert page.width() == window._stack.width()
    view = window.session.planner_view
    QTest.keyClick(page.nav, Qt.Key.Key_M)
    assert window.session.planner_view == view and window._stack.currentWidget() is page
    page.done.click()
    assert window._settings is None and window._stack.currentWidget().objectName() == "weekPage"
    page = open_settings(window)
    QTest.keyClick(page.nav, Qt.Key.Key_Escape)
    assert window._settings is None and window._stack.currentWidget().objectName() == "weekPage"


def test_settings_saves_once_after_a_burst_and_closing_saves_it_at_once(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Typing 2, 25, 45 is one save of 45, sent as Settings closes rather than lost with it."""
    sent = preference_puts(window)
    page = open_settings(window)
    for value in (2, 25, 45):
        page.work.setValue(value)
    page.close_page()
    assert [payload["timer_work_min"] for payload in sent] == [45]
    wait_until(qapp, lambda: not window.session.busy)
    # What the server sent back, not what the page showed: the timers are not shown ahead of the save.
    assert (window.session.preferences or {})["timer_work_min"] == 45


def test_the_drag_step_is_chosen_in_settings_kept_by_the_account_and_given_to_the_hand(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Five minutes until the student says otherwise. Fifteen, picked in Settings, moves the hand at
    once, is saved with the account and read back from it; five again is the default once more."""
    assert window.hand.step == 5

    def stored() -> dict:
        got: dict = {}
        window.session.client.request(
            "GET", "/api/preferences", None, got.update, lambda error: got.update(error=error)
        )
        wait_until(qapp, lambda: bool(got))
        return got

    for choice in (15, 5):
        page = open_settings(window)
        page.findChild(QPushButton, f"prefDragStep-{choice}").click()
        assert window.hand.step == choice, "applied while Settings is open"
        page.close_page()
        wait_until(qapp, lambda: not window.session.busy)
        assert stored().get("drag_step_min", 5) == choice
        assert window.hand.step == choice


def test_a_pause_saves_without_closing_settings(qapp: QApplication, window: NativeWindow) -> None:
    sent = preference_puts(window)
    page = open_settings(window)
    page.volume.setValue(35)
    wait_until(qapp, lambda: bool(sent))
    assert [payload["alert_volume"] for payload in sent] == [35]
    page.close_page()
    # Nothing changed after that save, so closing sends nothing more.
    assert [payload["alert_volume"] for payload in sent] == [35]


def test_settings_fits_its_width_in_every_layout_and_text_size(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Settings scrolls down, never sideways. When a page was wider than its room the extra was cut
    off: every dropdown lost its arrow and the layout blurbs stopped mid-word. At large text the
    list beside it cut "Appearance & layout" short. Measured in the real window at its narrowest,
    because the pack's padding and font are the cause."""
    # The smallest window 0.16 is for (decision 14 of its plan).
    window.resize(800, 700)
    choices = [{"main": main, "day": "one"} for main in LAYOUTS if LAYOUTS[main].role == "plan"]
    choices += [{"main": "classic", "day": day} for day in LAYOUTS if LAYOUTS[day].role == "day"]
    too_wide, cut_names = [], []
    for text in ("normal", "large"):
        window._look = {**window._look, "knobs": {**(window._look.get("knobs") or {}), "text": text}}
        window._apply_appearance()
        for choice in choices:
            window._layout = sanitize_layout(choice)
            page = open_settings(window)
            for name in ("prefFineTune", "layoutMainMore", "layoutDayMore"):
                box = page.findChild(QCheckBox, name)
                if box is not None:
                    box.setChecked(True)
            settled(qapp, window)
            # Section by section, as a student opens them: one never shown still has the default
            # font and reports a width it will not have once it is on screen.
            for index in range(page.stack.count()):
                page.nav.setCurrentRow(index)
                settled(qapp, window)
                area = page.stack.currentWidget()
                need, room = area.widget().minimumSizeHint().width(), area.viewport().width()
                if need > room:
                    too_wide.append((text, choice["main"], choice["day"], index, need, room))
            page.nav.setCurrentRow(0)
            settled(qapp, window)
            if page.nav.sizeHintForColumn(0) > page.nav.viewport().width():
                cut_names.append((text, choice["main"], choice["day"]))
            page.close_page()
    assert too_wide == []
    assert cut_names == []


def chrome_colour(window: NativeWindow) -> str:
    """What the top bar is actually painted with. A checked button blends, so this is only ever
    compared against another rendering, never against a token."""
    button = window.findChild(QPushButton, "signOut")
    return button.grab().toImage().pixelColor(button.width() // 2, button.height() // 2).name()


def signature(layout_id: str) -> str:
    """A design's own first colourway, which a student has to pick now that Match my look is first."""
    return LAYOUTS[layout_id].colourways[0][0]


def own_accent(layout_id: str) -> str:
    """A design's first colourway with an accent of its own. One that wears the student's accent, as
    Clay's does, changes with it."""
    return next(value for value, _, tokens in LAYOUTS[layout_id].colourways if "accent" in tokens)


def test_the_chrome_follows_the_look_whatever_design_is_on_screen(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Decision 3 of 0.17: the top bar and the frame wear the look and its accent in every design and
    every view, and a design's colourway colours only its own page. When the design dressed the
    chrome, a student saw three accents before placing any homework."""
    from desktop.native.layouts.registry import tokens_for
    from desktop.native.look import resolved_palette

    window._layout = {"main": "classic", "day": "one", "options": {}}
    window._on_week()
    qapp.processEvents()
    look_pixels = chrome_colour(window)
    pack, system_dark, accent = window._look_inputs()
    plain = resolved_palette(pack, system_dark, window._look, accent)

    for layout_id in ("bento", "mission", "clay"):
        colour = own_accent(layout_id)
        window._layout = {"main": layout_id, "day": "one", "options": {layout_id: {"colour": colour}}}
        window._on_week()
        for view in ("week", "day", "month"):
            window.session.set_view(view)
            qapp.processEvents()
            page = window.planner.currentWidget().scene.tokens
            assert page["accent"] == tokens_for(layout_id, colour, plain)["accent"] != plain["accent"]
            assert chrome_colour(window) == look_pixels, (layout_id, view)
        window.session.set_view("week")

    window._layout = {"main": "classic", "day": "one", "options": {}}
    window._on_week()
    qapp.processEvents()
    assert chrome_colour(window) == look_pixels


def test_a_day_screen_colours_its_own_page_and_leaves_the_chrome_to_the_look(
    qapp: QApplication, window: NativeWindow
) -> None:
    from desktop.native.layouts.registry import tokens_for
    from desktop.native.look import resolved_palette

    window._layout = {"main": "classic", "day": "one", "options": {}}
    window._on_week()
    qapp.processEvents()
    look_pixels = chrome_colour(window)
    pack, system_dark, accent = window._look_inputs()
    plain = resolved_palette(pack, system_dark, window._look, accent)
    colour = signature("one")
    window._layout = {"main": "classic", "day": "one", "options": {"one": {"colour": colour}}}
    click(window, "viewMyDay")
    qapp.processEvents()
    assert window.planner.currentWidget().scene.tokens["bg"] == tokens_for("one", colour, plain)["bg"]
    assert chrome_colour(window) == look_pixels


def test_no_chrome_button_spreads_across_the_window(qapp: QApplication, window: NativeWindow) -> None:
    """A button that fills the window reads as a banner, not a button. Seen at 439px on a day
    screen with focus running, and full width on the Day view."""
    window._layout = {"main": "bento", "day": "one", "options": {}}
    window._on_week()
    block = next(b for b in window.session.blocks if b.get("assignment_id"))
    window.session.start_focus(block["id"], 3)
    wait_until(qapp, lambda: window.session.focus is not None)
    qapp.processEvents()
    shown = [b for b in window.focus_panel.findChildren(QPushButton) if b.isVisible()]
    assert shown
    # "Not stretched" means each button is its own natural width, not a share of the window.
    stretched = [
        f"{b.objectName()} {b.width()}px vs {b.sizeHint().width()}px natural"
        for b in shown
        if b.width() > b.sizeHint().width() + 8
    ]
    assert stretched == []
    window.session.reset_focus()
    wait_until(qapp, lambda: window.session.focus is None)

    window._layout = {"main": "classic", "day": "one", "options": {}}
    click(window, "viewDay")
    qapp.processEvents()
    assert window.planner.currentWidget() is window.day_view
    assert window.day_view.hours.isVisible()
    stretched = [
        f"{button.objectName()} {button.width()}px vs {button.sizeHint().width()}px natural"
        for button in window.day_view.findChildren(QPushButton)
        if button.isVisible() and button.width() > button.sizeHint().width() + 8
    ]
    assert stretched == []


def test_every_dialog_fits_a_laptop_screen(qapp: QApplication, window: NativeWindow) -> None:
    """Settings stood 1056px tall and Account claimed 1338px wide. Both are opened on a 1366x768
    laptop, so both have to fit one."""
    from PySide6.QtWidgets import QDialog

    sizes: dict[str, tuple[int, int]] = {}
    original = QDialog.exec

    def measure(dialog: QDialog) -> int:
        dialog.show()
        qapp.processEvents()
        dialog.adjustSize()
        qapp.processEvents()
        sizes[measure.name] = (dialog.width(), dialog.height())
        dialog.hide()
        return QDialog.DialogCode.Rejected

    QDialog.exec = measure
    try:
        for name, call in (
            ("Add homework", window._add_homework),
            ("Add fixed time", window._add_fixed),
            ("Account", window._open_account),
        ):
            measure.name = name
            call()
    finally:
        QDialog.exec = original
    assert sorted(sizes) == ["Account", "Add fixed time", "Add homework"], sizes
    # A settings or account dialog is a panel, not a window. 1338x260 technically fitted a 1366
    # screen, which is why a screen-sized bound caught nothing; 700 square is the real rule.
    wrong = {name: size for name, size in sizes.items() if size[0] > 700 or size[1] > 768 or size[0] < 320}
    assert wrong == {}
    short = {
        name: size for name, size in sizes.items() if name == "Add homework" and size[1] < 400
    }
    assert short == {}


def test_the_focus_timer_reads_as_one_status_line(qapp: QApplication, window: NativeWindow) -> None:
    """Over a design of its own the timer arrived as loose text: the homework, then the phase, then
    the countdown, each on its own row."""
    from PySide6.QtWidgets import QLabel

    window._layout = {"main": "bento", "day": "one", "options": {}}
    window._on_week()
    block = next(b for b in window.session.blocks if b.get("assignment_id"))
    window.session.start_focus(block["id"], 3)
    wait_until(qapp, lambda: window.session.focus is not None)
    qapp.processEvents()
    parts = [window.focus_panel.findChild(QLabel, name) for name in ("focusTask", "focusPhase", "focusTime")]
    assert all(part is not None and part.isVisible() for part in parts)
    tops = {part.mapTo(window.focus_panel, part.rect().topLeft()).y() for part in parts}
    assert max(tops) - min(tops) < 8, f"the status is stacked, not one line: {sorted(tops)}"
    lefts = [part.mapTo(window.focus_panel, part.rect().topLeft()).x() for part in parts]
    assert lefts == sorted(lefts), "the parts should read left to right"
    window.session.reset_focus()
    wait_until(qapp, lambda: window.session.focus is None)


def test_a_real_solve_explains_itself_once(qapp: QApplication, window: NativeWindow) -> None:
    """Driven through the real solver, not a fixture trace. The panel opens when there is something
    to say, and a later week load must not reopen it."""
    # Ten hours due at the start of the week: there is no room before that deadline, so the solver
    # has something to say. Given a comfortable week it says nothing, which is the point of it.
    window.session.add_homework(
        {
            "id": "poster",
            "title": "Science fair poster",
            "due": f"{window.session.week_start}T08:00",
            "estimate_min": 600,
            "revision": 0,
        }
    )
    window.session.save()
    settled(qapp, window)
    window.session.solve()
    wait_until(qapp, lambda: window.session.trace is not None and not window.session.busy)
    qapp.processEvents()
    assert window.session.trace is not None
    said = [window.plan_review.list.item(i).text() for i in range(window.plan_review.list.count())]
    trace = window.session.trace
    assert trace.get("unplaced"), "the fixture should give the solver something it cannot place"
    assert said, "the solver had something to say and the panel showed nothing"
    assert any("Science fair poster" in line for line in said)
    assert window.plan_review.isVisible() is True

    # Reading the week again is not a new plan.
    window.plan_review.hide()
    window._on_week()
    qapp.processEvents()
    assert window.plan_review.isVisible() is False


def test_the_plan_bar_counts_what_the_toast_counts(qapp: QApplication, window: NativeWindow) -> None:
    """Decision 18 of 0.17. The bar counted every block the solver's trace calls placed, School and
    homework already placed included, and said 2 placed under a toast that said 0. Both now say the
    homework this plan gave a time and the homework it could not."""
    import re

    session = window.session
    session.add_block({"id": "school", "title": "School", "kind": "locked", "category": "class",
                       "start": "08:00", "duration_min": 390, "days": [0, 1, 2, 3, 4]})
    due = f"{(date.fromisoformat(session.week_start) + timedelta(days=6)).isoformat()}T23:59"
    session.add_homework({"id": "essay", "title": "History essay", "due": due, "estimate_min": 60,
                          "revision": 0})
    # Ten hours due at the week's start: there is no room for it, so the bar has something to say.
    session.add_homework({"id": "poster", "title": "Science fair poster",
                          "due": f"{session.week_start}T08:00", "estimate_min": 600, "revision": 0})
    session.save()
    settled(qapp, window)
    session.solve()
    wait_until(qapp, lambda: session.trace is not None and not session.busy)
    qapp.processEvents()
    assert len(session.trace.get("placed") or []) > 1, "the trace also lists School"
    said = window.toast.text()
    planned = re.match(r"Planned (\d+) homework blocks?\. (\d+) still needs? a time\.", said)
    assert planned, said
    assert window.plan_review.isVisible()
    assert window.plan_review.heading.text() == f"Placed {planned[1]} · {planned[2]} without a time"


def test_a_commitment_over_planned_homework_offers_find_a_new_time(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Mutation that turns this red: plan_conflicts is never connected to the notice."""
    window.session.add_block(
        {
            "id": "club",
            "title": "Club",
            "kind": "locked",
            "start": "18:00",
            "duration_min": 120,
            "days": [3],
        }
    )
    qapp.processEvents()
    assert window.toast.button.isVisible()
    assert window.toast.button.text() == "Find a new time"
    assert "History essay" in window.toast.text()


def test_a_conflict_is_said_once_on_the_notice_not_again_in_a_toast(
    qapp: QApplication, window: NativeWindow
) -> None:
    window.session.add_block(
        {"id": "club", "title": "Club", "kind": "locked", "start": "18:00", "duration_min": 120, "days": [3]}
    )
    qapp.processEvents()
    assert window.toast.button.isVisible()
    assert window.toast.button.text() == "Find a new time", "said once, with its button"


def test_every_homework_that_lost_its_time_is_named_on_the_notice(
    qapp: QApplication, window: NativeWindow
) -> None:
    """The notice showed the first note only, so a second assignment that lost its time went unnamed
    while Find a new time moved it too."""
    notes = [
        {"block_id": "a", "message": "Math worksheet no longer fits Monday at 15:15: Club is there now."},
        {"block_id": "b", "message": "English essay no longer fits Monday at 15:45: Club is there now."},
    ]
    window._on_plan_conflicts(notes)
    qapp.processEvents()
    shown = window.toast.text()
    assert "Math worksheet" in shown and "English essay" in shown


def test_the_plan_notice_counts_homework_blocks(qapp: QApplication, window: NativeWindow) -> None:
    """Mutation that turns this red: plan_sentence says 'Placed 4 of 4'."""
    # The essay began at 18:45, before the clock's 19:00, so Replan all leaves it; this needs a time.
    due = sunday_due(window.session.week_start)
    window.session.add_homework({"id": "math", "title": "Math", "due": due, "estimate_min": 60})
    window.session.save()
    settled(qapp, window)
    window.session.solve(everything=True)
    wait_until(qapp, lambda: not window.session.busy)
    qapp.processEvents()
    assert window.toast.text().startswith("Planned ")
    assert " of " not in window.toast.text()


def test_the_week_toolbar_keeps_only_what_is_reached_for(qapp: QApplication, window: NativeWindow) -> None:
    """Twelve buttons competed for one row while nine more hid in an overflow menu, and a strip of
    eight category chips sat above them. The row keeps adding, planning, saving and starting a
    timer; everything else sits under the heading for its job.

    Retry save is not here: it appears only when a save has actually failed."""
    from PySide6.QtWidgets import QPushButton

    page = window._stack.currentWidget()
    shown = [
        button.objectName()
        for button in page.findChildren(QPushButton)
        # The calendar's own controls, such as zooming its hours or paging the rail's month, belong to
        # it, not to the toolbar.
        if button.isVisible()
        and button.objectName()
        and not window.planner.isAncestorOf(button)
        and not window.rail.isAncestorOf(button)
    ]
    assert window.findChild(QPushButton, "weekZoomIn").isVisible()
    assert shown == [
        "prevWeek",
        "nextWeek",
        "todayWeek",
        "viewDay",
        "viewWeek",
        "viewMonth",
        "viewMyDay",
        "addButton",
        "addArrow",
        "solveButton",
        "moreButton",
        "settingsGear",
    ]

    menu = window.findChild(QPushButton, "moreButton").menu()
    menu.aboutToShow.emit()
    sections = more_sections(window)
    items = more_actions(window)
    assert sections == ["Planning"]
    wanted = {"Undo", "Redo", "Duplicate", "Running late", "Routines", "Undo, copy and save", "Log out"}
    assert wanted <= set(items)
    assert "Settings" not in items
    assert "Account" not in items
    assert "Replan all my homework" in items


def test_today_jumps_the_planner_to_this_week(qapp: QApplication, window: NativeWindow) -> None:
    from datetime import date

    from desktop.native.calendar import monday_of

    click(window, "nextWeek")
    settled(qapp, window)
    assert window.session.week_start != monday_of(date.today().isoformat())
    click(window, "todayWeek")
    settled(qapp, window)
    assert window.session.week_start == monday_of(date.today().isoformat())


def test_the_week_title_sits_beside_its_arrows_and_is_whole_when_there_is_room(
    qapp: QApplication, window: NativeWindow
) -> None:
    """The title was given 96 of the 217 pixels "21 – 27 September" needs, and Qt laid the arrows
    out as if it had none, so it read "21 – 27 S" under the arrows at every width, half an empty bar
    beside it. The arrows and Today now come first (decision 11 of 0.17), and the title after them."""
    for width in (1280, 1024):
        window.resize(width, 768)
        qapp.processEvents()
        title, today = window.week_title, window.findChild(QPushButton, "todayWeek")
        title_left = title.mapTo(window, title.rect().topLeft()).x()
        today_right = today.mapTo(window, today.rect().topRight()).x()
        assert today_right < title_left, (width, today_right, title_left)
    window.resize(1280, 768)
    qapp.processEvents()
    shown = window.week_title.text()
    assert not shown.endswith("…"), shown
    assert window.week_title.fontMetrics().horizontalAdvance(shown) <= window.week_title.width()


def test_a_week_across_two_months_shortens_to_month_abbreviations_not_an_ellipsis(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Beside 0.17's top bar at 1280 px "28 September – 4 October" does not fit, and cut short it read
    "28 Septemb…": no end date at all. The short form keeps the whole range. Wider, the whole words
    come back; narrower, the controls go under the title, which then has room again."""
    window.session.load_week("2026-09-28")
    wait_until(qapp, lambda: not window.session.busy and window.session.week_start == "2026-09-28")
    seen = {}
    for width in (1440, 1280, 1150, 1024):
        window.resize(width, 768)
        qapp.processEvents()
        seen[width] = window.week_title.text()
        assert window.week_title.accessibleName() == "28 September – 4 October", width
    assert seen[1440] == "28 September – 4 October"
    assert seen[1280] == "28 Sep – 4 Oct"
    assert set(seen.values()) <= {"28 September – 4 October", "28 Sep – 4 Oct"}, seen


def test_the_top_bar_keeps_the_gear_on_a_1024_window(qapp: QApplication, window: NativeWindow) -> None:
    """The gear stays inside a 1024 pixel window. test_window_screens goes on down to the narrowest."""
    window.resize(1024, 768)
    window.show()
    qapp.processEvents()
    gear = window.findChild(QPushButton, "settingsGear")
    today = window.findChild(QPushButton, "todayWeek")
    assert today is not None and today.isVisible()
    assert gear is not None and gear.isVisible()
    right = gear.mapTo(window, gear.rect().topRight()).x()
    assert right <= window.width(), (right, window.width(), window.minimumSizeHint().width())


def test_the_gear_opens_settings(qapp: QApplication, window: NativeWindow) -> None:
    gear = window.findChild(QPushButton, "settingsGear")
    assert gear is not None
    assert gear.text() == "" and not gear.icon().isNull()
    assert gear.toolTip() == "Settings"
    assert gear.accessibleName() == "Settings"
    click(window, "settingsGear")
    assert window._stack.currentWidget().objectName() == "settingsPage"
    window._settings.close_page()


def test_an_update_check_that_fails_says_so_only_when_asked(qapp: QApplication, window: NativeWindow) -> None:
    """GitHub refused the check (403, its hourly limit for a shared address) and the app said nothing,
    so "Checking for updates…" stayed on screen as if the check were still going."""
    from desktop.native.updater import CHECK_FAILED

    window._update_asked = False
    window._updater.unreachable.emit(CHECK_FAILED)
    qapp.processEvents()
    assert window.toast.isVisible() is False, "a daily check that fails stays quiet"

    window._update_asked = True
    window._updater.unreachable.emit(CHECK_FAILED)
    qapp.processEvents()
    assert window.toast.button.isVisible() is True
    assert window.toast.text() == CHECK_FAILED
    assert window.toast.button.text() == "Open release page"


def test_more_hides_spotify_until_there_is_a_link(qapp: QApplication, window: NativeWindow) -> None:
    assert "Open Spotify link" not in more_actions(window)
    window.session.preferences = {
        **(window.session.preferences or {}),
        "default_spotify_url": SPOTIFY_TRACK,
    }
    assert "Open Spotify link" in more_actions(window)


def test_advanced_shortcuts_still_act(qapp: QApplication, window: NativeWindow) -> None:
    before = len(window.session.blocks)
    QTest.keyClick(window.week_table, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    settled(qapp, window)
    assert len(window.session.blocks) != before or window.session.can_redo() is True
    window.session.select_block("school", 0)
    QTest.keyClick(window.week_table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert (window.session.clipboard or {}).get("kind") == "block"
    window.session.clipboard = None
    QTest.keyClick(window.week_table, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    # Ctrl+S is how Save is reached now that it lives under Advanced.
    window.session.dirty = True
    QTest.keyClick(window.week_table, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    settled(qapp, window)
    assert window.session.dirty is False or window.session.busy is True


def test_settings_holds_account_availability_and_updates(qapp: QApplication, window: NativeWindow) -> None:
    from desktop.native.settings import SettingsPage
    from desktop.native.version import VERSION

    prefs = window.session.preferences or {}
    dialog = SettingsPage(window, prefs, window._look, window.session.reminder_limits)
    assert dialog.findChild(QPushButton, "prefsAccount") is not None
    assert dialog.findChild(QPushButton, "prefsAvailability") is not None
    assert dialog.findChild(QLabel, "prefsVersion").text() == f"FlexWeek {VERSION}"
    assert dialog.findChild(QPushButton, "prefsCheckUpdates") is not None
    asked: list[str] = []
    dialog.account_requested.connect(lambda: asked.append("account"))
    dialog.availability_requested.connect(lambda: asked.append("availability"))
    dialog.updates_requested.connect(lambda: asked.append("updates"))
    dialog.findChild(QPushButton, "prefsAccount").click()
    dialog.findChild(QPushButton, "prefsAvailability").click()
    dialog.findChild(QPushButton, "prefsCheckUpdates").click()
    assert asked == ["account", "availability", "updates"]
    dialog.close()


def test_the_clipboard_line_only_appears_when_it_has_something_to_say(
    qapp: QApplication, window: NativeWindow
) -> None:
    window._on_week()
    qapp.processEvents()
    assert window.clipboard_summary.isVisible() is False
    block = next(b for b in window.session.blocks if b.get("kind") == "locked")
    window.session.select_block(block["id"], 0)
    window.session.copy_selected()
    window._on_week()
    qapp.processEvents()
    assert window.clipboard_summary.isVisible() is True
    assert window.clipboard_summary.text().startswith("Copied: ")


class RingRecorder:
    """Stands in for the window's Bell so the ringing decision is visible without a sound card."""

    def __init__(self) -> None:
        self.started: list[tuple[str, object]] = []
        self.stops = 0
        self.ringing = False

    def start(self, tone: str, volume: object) -> bool:
        self.started.append((tone, volume))
        self.ringing = True
        return True

    def once(self, tone: str, volume: object) -> bool:
        self.started.append((tone, volume))
        return True

    def stop(self) -> None:
        self.stops += 1
        self.ringing = False


SPOTIFY_TRACK = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"


def no_spotify(monkeypatch: pytest.MonkeyPatch, opened: list) -> None:
    """Nothing in a test may hand a URL to the real desktop, which would open a browser."""
    from PySide6.QtGui import QDesktopServices

    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        staticmethod(lambda url: bool(opened.append(url.toString())) or True),
    )


def test_an_alarm_rings_with_the_sound_it_was_given(qapp: QApplication, window: NativeWindow) -> None:
    window._bell = RingRecorder()
    window.session.preferences = {**(window.session.preferences or {}), "alert_volume": 45}
    window._ring({"name": "Practice", "sound": "glass"}, "")
    assert window._bell.started == [("glass", 45)]


def test_an_alarm_set_to_spotify_plays_the_track_instead_of_a_tone(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list = []
    no_spotify(monkeypatch, opened)
    window._bell = RingRecorder()
    window._ring({"name": "Wake up", "sound": "spotify"}, SPOTIFY_TRACK)
    # In the Spotify app, by its own address. A track starts there by itself, so no tone over it.
    assert opened == ["spotify:track:4cOdK2wGLETKBW3PvgPWqT"]
    assert window._bell.started == []


def test_a_spotify_alarm_with_no_link_still_makes_a_noise(qapp: QApplication, window: NativeWindow) -> None:
    """A best-effort link that is not there must not turn the alarm into a silent dialog."""
    window._bell = RingRecorder()
    window._ring({"name": "Wake up", "sound": "spotify"}, "")
    assert [tone for tone, _volume in window._bell.started] == ["chime"]


def test_a_spotify_alarm_falls_back_to_a_tone_when_the_link_will_not_open(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtGui import QDesktopServices

    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda _url: False))
    window._bell = RingRecorder()
    window._ring({"name": "Wake up", "sound": "spotify"}, SPOTIFY_TRACK)
    assert [tone for tone, _volume in window._bell.started] == ["chime"]


def test_answering_an_alarm_stops_the_noise(qapp: QApplication, window: NativeWindow) -> None:
    from PySide6.QtCore import QTimer

    window._bell = RingRecorder()
    QTimer.singleShot(0, lambda: window._alarm_dialog and window._alarm_dialog.accept())
    window._on_alarm({"id": "a1", "name": "Practice", "time": "07:00", "sound": "low"})
    assert [tone for tone, _volume in window._bell.started] == ["low"]
    assert window._bell.ringing is False
    assert window._bell.stops >= 1


def test_a_reminder_makes_its_sound_when_the_student_asked_for_one(
    qapp: QApplication, window: NativeWindow
) -> None:
    window._bell = RingRecorder()
    window.session.preferences = {
        **(window.session.preferences or {}),
        "reminder_sound": True,
        "alert_volume": 60,
    }
    window._present_alerts([{"title": "Essay starts soon", "body": "19:00 · Thu"}])
    assert window._bell.started == [("chime", 60)]


def test_a_reminder_is_silent_when_the_student_turned_sound_off(
    qapp: QApplication, window: NativeWindow
) -> None:
    window._bell = RingRecorder()
    window.session.preferences = {**(window.session.preferences or {}), "reminder_sound": False}
    window._present_alerts([{"title": "Essay starts soon", "body": "19:00 · Thu"}])
    assert window._bell.started == []


def test_the_end_of_session_chime_answers_to_its_own_setting(
    qapp: QApplication, window: NativeWindow
) -> None:
    """The setting saved a value and played nothing. A focus notice is not a reminder: it uses the
    tone the phase carries and only sounds when the student asked for an end-of-session chime."""
    window._bell = RingRecorder()
    window.session.preferences = {
        **(window.session.preferences or {}),
        "reminder_sound": True,
        "end_chime": True,
        "alert_volume": 70,
    }
    window._present_alerts([{"title": "Focus session", "body": "Essay", "kind": "focus", "tone": "bright"}])
    assert window._bell.started == [("bright", 70)]


def test_no_chime_at_the_end_of_a_session_when_that_setting_is_off(
    qapp: QApplication, window: NativeWindow
) -> None:
    window._bell = RingRecorder()
    window.session.preferences = {
        **(window.session.preferences or {}),
        "reminder_sound": True,
        "end_chime": False,
    }
    window._present_alerts([{"title": "Break", "body": "Essay", "kind": "focus", "tone": "soft"}])
    assert window._bell.started == []


def test_a_reminder_still_rings_when_the_end_of_session_chime_is_off(
    qapp: QApplication, window: NativeWindow
) -> None:
    """The two settings are separate, so gating one on the other would silence reminders."""
    window._bell = RingRecorder()
    window.session.preferences = {
        **(window.session.preferences or {}),
        "reminder_sound": True,
        "end_chime": False,
        "alert_volume": 80,
    }
    window._present_alerts([{"title": "Essay starts soon", "body": "19:00 · Thu"}])
    assert window._bell.started == [("chime", 80)]


def test_open_on_day_is_honoured_instead_of_always_coming_up_on_the_week(
    qapp: QApplication, window: NativeWindow
) -> None:
    """The setting could be saved from the desktop but only the web read it."""
    window._day_mode = False
    window._opened_on_preference = False
    window.session.preferences = {**(window.session.preferences or {}), "preferred_view": "day"}
    window._on_week()
    qapp.processEvents()
    assert window._day_mode is True


def test_open_on_is_a_starting_point_not_a_lock(qapp: QApplication, window: NativeWindow) -> None:
    """Every week refresh runs through the same path, so applying it more than once would drag the
    student back to the day screen whenever the week reloaded."""
    window._day_mode = False
    window._opened_on_preference = False
    window.session.preferences = {**(window.session.preferences or {}), "preferred_view": "day"}
    window._on_week()
    qapp.processEvents()
    window._leave_day()
    qapp.processEvents()
    assert window._day_mode is False
    window._on_week()
    qapp.processEvents()
    assert window._day_mode is False


def menu_swatches(window: NativeWindow) -> dict:
    """The colour beside each type in the Add menu, read back off its icon."""
    from PySide6.QtGui import QAction

    from desktop.native.calendar import CATEGORIES

    faces = {}
    for key in CATEGORIES:
        action = window.add_menu.findChild(QAction, f"addMenu-{key}")
        assert action is not None, key
        image = action.icon().pixmap(12, 12).toImage()
        faces[key] = image.pixelColor(6, 6).name()
    return faces


def test_the_add_menu_says_which_type_each_entry_makes(qapp: QApplication, window: NativeWindow) -> None:
    """The chip strip carried the category colours and took a whole row to do it. The colours moved
    into the Add menu with it."""
    from desktop.native.calendar import CATEGORIES

    window.session.preferences = {**(window.session.preferences or {}), "accent_chips": False}
    window._on_week()
    qapp.processEvents()
    assert len(set(menu_swatches(window).values())) == len(CATEGORIES)


def test_accent_chips_paints_every_type_in_the_accent(qapp: QApplication, window: NativeWindow) -> None:
    window.session.preferences = {**(window.session.preferences or {}), "accent_chips": True}
    window._on_week()
    qapp.processEvents()
    assert len(set(menu_swatches(window).values())) == 1


class FakeUpdater:
    """Stands in for the real one so no test reaches the network."""

    def __init__(self) -> None:
        self.checks = 0
        self.downloads: list[dict] = []
        self.busy = False

    def check(self) -> None:
        self.checks += 1

    def download(self, update: dict) -> None:
        self.downloads.append(update)


def test_the_app_checks_for_updates_once_a_day_not_every_week_refresh(
    qapp: QApplication, window: NativeWindow
) -> None:
    """_on_week runs on every save, solve and week change. Checking there without a cadence would
    ask GitHub dozens of times a session."""
    fake = FakeUpdater()
    window._updater = fake
    window._updates = {"check": True, "last_ms": 0, "skip": ""}
    window._on_week()
    qapp.processEvents()
    assert fake.checks == 1
    window._on_week()
    window._on_week()
    qapp.processEvents()
    assert fake.checks == 1, "a week refresh asked GitHub again"


def test_turning_update_checks_off_is_obeyed(qapp: QApplication, window: NativeWindow) -> None:
    fake = FakeUpdater()
    window._updater = fake
    window._updates = {"check": False, "last_ms": 0, "skip": ""}
    window._on_week()
    qapp.processEvents()
    assert fake.checks == 0


def test_asking_for_a_check_ignores_the_cadence(qapp: QApplication, window: NativeWindow) -> None:
    """Check for updates has to check, whatever the daily timer says."""
    fake = FakeUpdater()
    window._updater = fake
    window._updates = {"check": True, "last_ms": window.session.now_ms(), "skip": ""}
    window._check_updates(asked=True)
    assert fake.checks == 1


def test_a_skipped_version_stays_quiet_until_asked(qapp: QApplication, window: NativeWindow) -> None:
    window._updates = {"check": True, "last_ms": 0, "skip": "9.9.9"}
    window._update_asked = False
    shown: list = []
    window._on_update_found({"version": "9.9.9", "asset": "x", "url": "u", "checksum_url": "c", "notes": ""})
    assert shown == []
    assert window._update_dialog is None


def test_no_button_appears_twice_on_the_week_page(qapp: QApplication, window: NativeWindow) -> None:
    """Moving Quick focus into the action row left the focus panel's own copy on screen, so the same
    button was offered twice a few pixels apart. The action row is not the only place a button can
    come from, so this counts them across the whole page rather than inside one container."""
    from PySide6.QtWidgets import QPushButton

    window._day_mode = False
    window._on_week()
    qapp.processEvents()
    page = window._stack.currentWidget()
    labels = [b.text() for b in page.findChildren(QPushButton) if b.isVisible() and b.text()]
    repeated = sorted({text for text in labels if labels.count(text) > 1})
    assert repeated == [], f"offered twice: {repeated}"


def test_the_add_button_says_what_a_drag_will_make(qapp: QApplication, window: NativeWindow) -> None:
    """The armed type was legible because eight chips sat on screen with one of them lit. With the
    chips gone, the button that opens the menu has to carry it."""
    from PySide6.QtWidgets import QPushButton

    # arm_category, not _add_from_chip: that one also opens the Add dialog, which blocks.
    window.session.arm_category("exercise")
    window._sync_add_button()
    qapp.processEvents()
    button = window.findChild(QPushButton, "addButton")
    assert button is not None
    assert "sport" in button.text().lower()
    assert not button.icon().isNull(), "no colour beside the armed type"


def test_the_week_saves_itself_without_anyone_pressing_save(qapp: QApplication, window: NativeWindow) -> None:
    """Save left the bar, so this is the only thing that writes a student's week. If it stops
    working, work is lost silently, which is the worst failure this app has."""
    from desktop.native.calendar import sunday_due

    before = window.session.revision
    window.session.add_homework(
        {
            "id": "auto",
            "title": "Autosaved essay",
            "due": sunday_due(window.session.week_start),
            "estimate_min": 30,
            "revision": 0,
        }
    )
    assert window.session.dirty is True
    # The clock the debounce reads is the session's, so move it rather than sleeping.
    window._changed_ms = 0
    window._last_try_ms = 0
    window._autosave_tick()
    wait_until(qapp, lambda: not window.session.busy and window.session.revision > before)
    assert window.session.dirty is False


def test_autosave_waits_until_the_student_stops_changing_things(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Dragging a block emits a change per step. Saving on each one would post continuously."""
    window.session.dirty = True
    window.session.pending_save = None
    window._changed_ms = window.session.now_ms()
    posted = []
    window.session.save = lambda *a, **k: posted.append(1)
    window._autosave_tick()
    assert posted == [], "saved while the student was still changing things"


def test_autosave_keeps_its_hands_off_a_conflict(qapp: QApplication, window: NativeWindow) -> None:
    """A 409 means another window wrote this week. Answering that is the student's decision, and a
    timer that retried would overwrite whichever copy lost the race."""
    window.session.dirty = True
    window.session.conflict = True
    window._changed_ms = 0
    posted = []
    window.session.save = lambda *a, **k: posted.append(1)
    window._autosave_tick()
    assert posted == []


def test_autosave_does_not_pile_requests_on_a_busy_session(qapp: QApplication, window: NativeWindow) -> None:
    window.session.dirty = True
    window.session.conflict = False
    window.session.busy = True
    window._changed_ms = 0
    posted = []
    window.session.save = lambda *a, **k: posted.append(1)
    window._autosave_tick()
    window.session.busy = False
    assert posted == []


def _dialog_shows(dialog: QDialog, widget) -> bool:
    top = widget.mapTo(dialog, widget.rect().topLeft())
    return 0 <= top.y() < dialog.height() - 8


def _squeeze(qapp: QApplication, dialog: QDialog) -> None:
    """The audit's desktop gave Settings and the homework editor their minimum height, 154 pixels
    on 0.14.1, not the height they asked for. Offscreen they open at their size hint, which hid it."""
    dialog.resize(dialog.width(), 10)
    qapp.processEvents()


@pytest.mark.parametrize("size", [(1024, 768), (1280, 800)])
@pytest.mark.parametrize("pack", ["light-frost", "dark-frost"])
def test_settings_and_homework_open_tall_enough_to_read(
    qapp: QApplication, window: NativeWindow, size: tuple[int, int], pack: str
) -> None:
    from desktop.native.widgets import HomeworkDialog

    window.resize(*size)
    window.session.preferences = {**window.session.preferences, "theme_pack": pack}
    window._apply_appearance()
    qapp.processEvents()
    # Settings is a page of the window now, so it is as tall as the window, with Done in view.
    prefs = open_settings(window)
    for _ in range(30):
        qapp.processEvents()
    assert prefs.height() == window._stack.height(), (pack, size, prefs.width(), prefs.height())
    assert _dialog_shows(prefs, prefs.done)
    prefs.close_page()

    homework = HomeworkDialog(window)
    homework.setStyleSheet(window.styleSheet())
    homework.show()
    qapp.processEvents()
    _squeeze(qapp, homework)
    assert homework.height() >= 400, (pack, size, homework.width(), homework.height())
    for field in (homework.title, homework.due, homework.estimate):
        assert _dialog_shows(homework, field)
    buttons = homework.findChild(QDialogButtonBox, "dialogButtons")
    assert buttons is not None and _dialog_shows(homework, buttons)
    homework.close()

    edited = HomeworkDialog(window, window.session.assignments["essay"])
    edited.setStyleSheet(window.styleSheet())
    edited.show()
    qapp.processEvents()
    _squeeze(qapp, edited)
    assert edited.height() >= 400
    assert _dialog_shows(edited, edited.title)
    assert _dialog_shows(edited, edited.findChild(QDialogButtonBox, "dialogButtons"))
    edited.close()


def test_bento_month_hides_the_week_up_next_card(qapp: QApplication, window: NativeWindow) -> None:
    window._layout = {"main": "bento", "day": "one", "options": {}}
    window._on_week()
    qapp.processEvents()
    view = window.planner.currentWidget()
    scroll = view.findChild(QWidget, "bentoScroll")
    assert scroll is not None and scroll.isVisible()
    click(window, "viewMonth")
    settled(qapp, window)
    view = window.planner.currentWidget()
    scroll = view.findChild(QWidget, "bentoScroll")
    assert scroll is not None
    assert scroll.isVisible() is False
    hero = view.findChild(QLabel, "bentoHeroTitle")
    if hero is not None:
        assert hero.isVisible() is False
    board = view.findChild(QWidget, "layoutMonthBoard")
    assert board is not None and board.isVisible()


@pytest.mark.parametrize("layout_id", ["timeline", "mission", "bento", "retro", "clay"])
def test_month_hides_the_whole_week_surface(qapp: QApplication, window: NativeWindow, layout_id: str) -> None:
    """Mutation that turns this red: LayoutView._week_host returns None."""
    window._layout = {"main": layout_id, "day": "one", "options": {}}
    window._day_mode = False
    window.session.set_view("week")
    window._on_week()
    qapp.processEvents()
    view = window.planner.currentWidget()
    host = view._week_host()
    assert host is not None and host.isVisible()
    click(window, "viewMonth")
    settled(qapp, window)
    view = window.planner.currentWidget()
    host = view._week_host()
    assert host is not None
    assert host.isVisible() is False
    board = view.findChild(QWidget, "layoutMonthBoard")
    assert board is not None and board.isVisible()


def test_retros_start_opens_mores_menu_up_from_the_taskbar(qapp: QApplication, window: NativeWindow) -> None:
    """Start is the app's own menu, More's, opening up over the taskbar as Windows 98's did; it asks
    for nothing More does not already offer."""
    from desktop.native.look import MENU_EDGE

    window._layout = sanitize_layout({"main": "retro", "day": "one"})
    window._day_mode = False
    window.session.set_view("week")
    window._on_week()
    qapp.processEvents()
    start = window.planner.currentWidget().findChild(QPushButton, "retroStart")
    start.click()
    wait_until(qapp, window.more_menu.isVisible)
    corner = start.mapToGlobal(start.rect().topLeft())
    panel = window.more_menu.geometry().adjusted(MENU_EDGE, MENU_EDGE, -MENU_EDGE, -MENU_EDGE)
    assert panel.bottom() <= corner.y() + 1, (panel, corner)
    window.more_menu.close()


def test_finishing_from_my_day_offers_undo_on_the_notice(qapp: QApplication, window: NativeWindow) -> None:
    """Mutation that turns this red: _finish_homework never calls _set_notice."""
    one_thing(window)
    click(window, "viewMyDay")
    click(window, "oneFinished")
    settled(qapp, window)
    assert window.session.assignments["essay"]["completed"] is True
    assert window.toast.button.isVisible()
    assert window.toast.text() == "Finished History essay."
    assert window.toast.button.text() == "Undo"


FREE_TODAY = (
    "done for today",
    "nothing else today",
    "all clear",
    "the rest of the day is yours",
    "a free day",
    "0 min left today",
    "nothing on this day",
    "no homework tonight",
)

SCREENS = (
    ("classic", "week"),
    ("timeline", "week"),
    ("mission", "week"),
    ("bento", "week"),
    ("retro", "week"),
    ("clay", "week"),
    ("one", "day"),
    ("dial", "day"),
)


def visible_copy(root: QWidget) -> str:
    bits = []
    for child in [root, *root.findChildren(QWidget)]:
        if not child.isVisible():
            continue
        if isinstance(child, (QLabel, QPushButton)):
            text = child.text().strip()
            if text:
                bits.append(text)
    return "\n".join(bits)


@pytest.mark.parametrize(("layout_id", "surface"), SCREENS)
def test_unplaced_homework_due_today_is_named_on_every_screen(
    qapp: QApplication, window: NativeWindow, layout_id: str, surface: str
) -> None:
    """Math worksheet due tonight with no time. No screen may say the day is free, and each names it.

    Mutation that turns this red: WeekModel.due_today_unplaced always returns ().
    """
    session = window.session
    thursday = datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=16)
    session.now_ms = lambda: int(thursday.timestamp() * 1000)
    session.blocks = [item for item in session.blocks if item.get("assignment_id") != "essay"]
    session._touch("clearing the placed essay")
    due = (datetime.fromisoformat(session.week_start) + timedelta(days=3)).strftime("%Y-%m-%dT21:00")
    session.add_homework(
        {
            "id": "math",
            "title": "Math worksheet",
            "due": due,
            "estimate_min": 45,
            "revision": 0,
        }
    )
    session.save()
    settled(qapp, window)
    if surface == "day":
        window._layout = {"main": "classic", "day": layout_id, "options": {}}
        window._day_mode = True
    else:
        window._layout = {"main": layout_id, "day": "one", "options": {}}
        window._day_mode = False
        session.set_view("week")
    window._on_week()
    qapp.processEvents()
    said = visible_copy(window).lower()
    assert "math worksheet" in said, said
    for phrase in FREE_TODAY:
        assert phrase not in said, f"{layout_id} still says {phrase!r} in:\n{said}"


def _fades(host: QWidget) -> list[QLabel]:
    from desktop.native.motion import FADE_NAME

    return [label for label in host.findChildren(QLabel, FADE_NAME) if label.isVisible()]


def at_level(window: NativeWindow, level: str) -> None:
    window.session.preferences = {**(window.session.preferences or {}), "motion": level}
    window._apply_appearance()
    faded_in()


def test_a_new_view_is_live_at_once_while_the_old_one_fades(qapp: QApplication, window: NativeWindow) -> None:
    at_level(window, "normal")
    title = window.week_title
    week_title = title.full_text()
    click(window, "viewMonth")
    month = window._planner_widget("month")
    assert window.planner.currentWidget() is month
    assert title.full_text() != week_title
    over_title = [picture for picture in _fades(window) if picture.geometry().topLeft() == title.pos()]
    assert len(_fades(window)) == 2 and len(over_title) == 1, "the page and, over the new title, the old one"
    assert title.graphicsEffect().opacity == 0, "and the new title comes in with the page, not a frame early"
    effect = month.graphicsEffect()
    assert effect.opacity == 0, "Month starts under the week, which is still there"
    assert effect.offset.x() > 0, "and comes in from the right, where its segment is"
    faded_in()
    assert title.graphicsEffect() is None
    assert _fades(window) == [] and month.graphicsEffect() is None
    click(window, "viewDay")
    assert window.planner.currentWidget().graphicsEffect().offset.x() < 0, "Day comes in from the left"


def test_my_day_changes_its_chrome_and_its_page_in_the_same_frame(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Decision 29 of 0.17: the planning chrome and the rail went at once while the old week still
    faded, so for a moment neither page was on screen as it is."""
    at_level(window, "normal")
    page = window._week_page
    top = window._top_bar.geometry().bottom() + 1
    under_bar = QRect(0, top, page.width(), page.height() - top)
    before = page.grab(under_bar).toImage()
    assert window.rail.isVisible()
    click(window, "viewMyDay")
    assert not window.rail.isVisible() and not window.plan_chrome.isVisible()
    assert page.grab(under_bar).toImage() == before, "the first frame is still the week, rail and all"
    assert window.planner.currentWidget().graphicsEffect().opacity == 0
    faded_in()
    assert _fades(window) == []
    assert page.grab(under_bar).toImage() != before


def test_settings_slide_in_over_the_week_and_away_again(qapp: QApplication, window: NativeWindow) -> None:
    at_level(window, "normal")
    window._open_settings()
    settings = window._settings
    assert window._stack.currentWidget() is settings
    assert settings.graphicsEffect().offset.x() == window._stack.width(), "from the right edge"
    (week,) = _fades(window._stack)
    faded_in()
    assert _fades(window) == [] and settings.graphicsEffect() is None
    settings.close_page()
    assert window._stack.currentWidget().objectName() == "weekPage", "the week is live at once"
    (leaving,) = _fades(window._stack)
    faded_in()
    assert _fades(window) == []


def test_the_next_week_slides_in_as_the_last_one_drifts_away(
    qapp: QApplication, window: NativeWindow
) -> None:
    at_level(window, "normal")
    start = window.session.week_start
    click(window, "nextWeek")
    assert window._travel_direction == -1
    wait_until(qapp, lambda: window.session.week_start != start and not window.session.busy)
    QTest.qWait(duration(EASE_MS, "normal") + 200)
    assert _fades(window) == []


def test_animations_off_turns_every_fade_off(qapp: QApplication, window: NativeWindow) -> None:
    # The fixture's first homework swaps the new account's empty week for the hours, with a fade.
    at_level(window, "off")
    assert window._motion == "off"
    click(window, "viewMonth")
    assert _fades(window) == []
    assert window.planner.currentWidget().graphicsEffect() is None
    dialog = SettingsPage(None, window.session.preferences, window._look, {}, window._layout)
    assert combo(dialog, "prefMotion").currentData() == "off"
    assert dialog.updates()["motion"] == "off"


def test_homework_moved_by_hand_to_another_day_is_saved_pinned(
    qapp: QApplication, window: NativeWindow
) -> None:
    """The server accepts the pin, and it survives a reload."""
    work = next(block for block in window.session.blocks if block.get("assignment_id") == "essay")
    assert window.session.apply_times(work["id"], 19 * 60, 20 * 60, 4)
    window.session.save()
    settled(qapp, window)
    window.session.load_week(window.session.week_start, discard=True)
    settled(qapp, window)
    moved = next(block for block in window.session.blocks if block["id"] == work["id"])
    assert (moved["days"], moved["start"], moved.get("pinned")) == ([4], "19:00", True)


def _rung(window: NativeWindow, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    heard: list[tuple[str, str]] = []
    monkeypatch.setattr(window._bell, "once", lambda tone, _volume: heard.append(("once", tone)) or True)
    monkeypatch.setattr(window._bell, "start", lambda tone, _volume: heard.append(("start", tone)) or True)
    return heard


def test_a_reminder_rings_the_chosen_alarm_sound(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    heard = _rung(window, monkeypatch)
    window.session.preferences = {**(window.session.preferences or {}), "alarm_tone": "glass"}
    window._present_alerts([{"kind": "reminder", "title": "Math worksheet", "body": "in 10 min"}])
    assert heard == [("once", "glass")]


def test_a_spotify_sound_never_starts_music_for_a_reminder(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    heard = _rung(window, monkeypatch)
    window.session.preferences = {**(window.session.preferences or {}), "alarm_tone": "spotify"}
    window._present_alerts([{"kind": "reminder", "title": "Math worksheet", "body": "in 10 min"}])
    assert heard == [("once", "chime")]


def test_a_focus_ending_keeps_its_own_tone_until_a_sound_is_chosen(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    heard = _rung(window, monkeypatch)
    base = {**(window.session.preferences or {}), "end_chime": True}
    window.session.preferences = {key: value for key, value in base.items() if key != "alarm_tone"}
    window._present_alerts([{"kind": "focus", "title": "Break", "tone": "bright"}])
    window.session.preferences = {**window.session.preferences, "alarm_tone": "low"}
    window._present_alerts([{"kind": "focus", "title": "Break", "tone": "bright"}])
    assert heard == [("once", "bright"), ("once", "low")]


def test_an_alarm_with_no_sound_of_its_own_rings_the_chosen_one(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    heard = _rung(window, monkeypatch)
    window.session.preferences = {**(window.session.preferences or {}), "alarm_tone": "soft"}
    window._ring({"name": "Wake up"}, "")
    window._ring({"name": "Practice", "sound": "bright"}, "")
    assert heard == [("start", "soft"), ("start", "bright")]


def test_settings_picks_the_alarm_sound_and_new_alarms_start_with_it(qapp: QApplication) -> None:
    dialog = SettingsPage(None, {"alarm_tone": "low"}, {}, {}, None)
    tone = combo(dialog, "prefAlarmTone")
    assert tone.currentData() == "low"
    assert combo(dialog, "alarmSound").currentData() == "low"
    tone.setCurrentIndex(tone.findData("glass"))
    assert combo(dialog, "alarmSound").currentData() == "glass"
    assert dialog.updates()["alarm_tone"] == "glass"
    dialog.show()
    # On the Alerts page, which is not the page on screen, so the row's own state is what counts.
    assert dialog.tone_note.isHidden() is True
    tone.setCurrentIndex(tone.findData("spotify"))
    assert dialog.tone_note.isHidden() is False
    played: list[str] = []
    tone.setCurrentIndex(tone.findData("bright"))
    dialog._tone_bell.once = lambda name, _volume: played.append(name) or True
    dialog.play_tone.click()
    assert played == ["bright"]
    dialog.close()


def _press(dialog: QDialog, name: str) -> int:
    """What a student does in the homework editor: press one button, which closes it."""
    dialog.findChild(QPushButton, name).click()
    return QDialog.DialogCode.Accepted


def _waiting_math(qapp: QApplication, window: NativeWindow) -> dict:
    due = sunday_due(window.session.week_start)
    window.session.add_homework({"id": "math", "title": "Math worksheet", "due": due, "estimate_min": 60})
    window.session.save()
    settled(qapp, window)
    return next(block for block in window.session.blocks if block.get("assignment_id") == "math")


def _hours(window: NativeWindow):
    hours = window.week_table.hours
    if not hours.tracks:
        hours.resize(980, 640)
        hours.relayout()
    return hours


def _drop(qapp: QApplication, window: NativeWindow, block_id: str, hhmm: str, day: int) -> None:
    from PySide6.QtCore import QEvent, QPoint, QPointF
    from PySide6.QtGui import QMouseEvent

    click(window, "viewWeek")
    window.move(0, 0)
    window.resize(760, 720)
    for _ in range(5):
        qapp.processEvents()
    hours = _hours(window)
    minute = int(hhmm[:2]) * 60 + int(hhmm[3:])
    hours.reveal(day, max(minute - 60, 0), minute + 90)
    qapp.processEvents()
    chip = next(
        widget
        for widget in window.findChildren(QPushButton)
        if widget.property("block_id") == block_id and widget.property("tray") and widget.isVisible()
    )
    start = chip.mapToGlobal(chip.rect().center())
    end = hours.point_for(day, minute)

    def send(widget, kind: QEvent.Type, at, held: bool) -> None:
        buttons = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
        event = QMouseEvent(
            kind,
            QPointF(widget.mapFromGlobal(at)),
            QPointF(at),
            Qt.MouseButton.LeftButton,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(widget, event)

    send(chip, QEvent.Type.MouseButtonPress, start, True)
    for step in range(1, 9):
        moved = QPoint(
            start.x() + (end.x() - start.x()) * step // 8,
            start.y() + (end.y() - start.y()) * step // 8,
        )
        send(hours, QEvent.Type.MouseMove, moved, True)
    send(hours, QEvent.Type.MouseButtonRelease, end, False)
    qapp.processEvents()


def _drag_on_the_week(
    qapp: QApplication,
    window: NativeWindow,
    day: int,
    hhmm: str,
    to_day: int,
    to: str,
    between: Callable[[], None] | None = None,
) -> None:
    """Press on the week's hours, move and let go, as a mouse does. `between` runs while it is held."""
    from PySide6.QtCore import QEvent, QPoint, QPointF
    from PySide6.QtGui import QMouseEvent

    click(window, "viewWeek")
    window.move(0, 0)
    window.resize(760, 720)
    for _ in range(5):
        qapp.processEvents()
    hours = _hours(window)
    start_min = int(hhmm[:2]) * 60 + int(hhmm[3:])
    end_min = int(to[:2]) * 60 + int(to[3:])
    hours.reveal(day, max(min(start_min, end_min) - 60, 0), max(start_min, end_min) + 90)
    qapp.processEvents()

    def point(on: int, when: str):
        return hours.point_for(on, int(when[:2]) * 60 + int(when[3:]))

    def send(kind: QEvent.Type, at, held: bool) -> None:
        buttons = Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
        event = QMouseEvent(
            kind,
            QPointF(hours.mapFromGlobal(at)),
            QPointF(at),
            Qt.MouseButton.LeftButton,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(hours, event)

    start, end = point(day, hhmm), point(to_day, to)
    send(QEvent.Type.MouseButtonPress, start, True)
    middle = QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2)
    send(QEvent.Type.MouseMove, middle, True)
    send(QEvent.Type.MouseMove, end, True)
    if between is not None:
        between()
        qapp.processEvents()
    send(QEvent.Type.MouseButtonRelease, end, False)
    qapp.processEvents()


def test_homework_dropped_on_the_calendar_gets_that_time_and_keeps_it(
    qapp: QApplication, window: NativeWindow
) -> None:
    waiting = _waiting_math(qapp, window)
    assert not waiting.get("start")
    _drop(qapp, window, waiting["id"], "16:00", 2)
    settled(qapp, window)
    placed = next(block for block in window.session.blocks if block["id"] == waiting["id"])
    assert (placed["days"], placed["start"], placed.get("pinned")) == ([2], "16:00", True)
    window.session.undo()
    settled(qapp, window)
    back = next(block for block in window.session.blocks if block["id"] == waiting["id"])
    assert not back.get("start"), "the drop is one Undo step"
    window.session.redo()
    settled(qapp, window)
    window.session.solve(everything=True)
    settled(qapp, window)
    replanned = next(block for block in window.session.blocks if block["id"] == waiting["id"])
    assert (replanned["days"], replanned["start"]) == ([2], "16:00"), "Replan all leaves it where it was put"


def test_a_drop_over_school_sits_beside_it_and_no_plan_moves_it_off(
    qapp: QApplication, window: NativeWindow
) -> None:
    """As in Daily Scheduler: two blocks at one time is allowed, side by side, and said. It was put
    there by hand, so the planner that makes way for School leaves it where it is."""
    waiting = _waiting_math(qapp, window)
    _drop(qapp, window, waiting["id"], "10:00", 1)
    settled(qapp, window)
    placed = next(block for block in window.session.blocks if block["id"] == waiting["id"])
    assert (placed["days"], placed["start"], placed.get("pinned")) == ([1], "10:00", True)
    tuesday = {
        item.block_id: item.columns
        for item, _rect in _hours(window).drawn(_hours(window).track_for(1, 10 * 60))
    }
    assert tuesday == {"school": 2, waiting["id"]: 2}, "side by side, each marked"
    window.session.solve(everything=True)
    settled(qapp, window)
    replanned = next(block for block in window.session.blocks if block["id"] == waiting["id"])
    assert (replanned["days"], replanned["start"]) == ([1], "10:00")


def test_a_block_held_on_the_week_goes_back_when_the_student_switches_to_day(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Switching away while holding a block is letting go of it, as Escape is: nothing moves and
    nothing is saved, whatever lies under the pointer on the view that comes up."""
    settled(qapp, window)
    revision = window.session.revision
    _drag_on_the_week(qapp, window, 2, "10:00", 2, "11:00", between=lambda: window._choose_view("day"))
    settled(qapp, window)
    assert window.session.planner_view == "day"
    assert not window.hand.busy
    assert window.session.revision == revision, "a save was made"
    school = [block for block in window.session.blocks if block["title"] == "School"]
    assert [(tuple(block["days"]), block["start"]) for block in school] == [((0, 1, 2, 3, 4), "08:00")]


def test_dragging_one_day_of_school_moves_that_day_only(qapp: QApplication, window: NativeWindow) -> None:
    _drag_on_the_week(qapp, window, 2, "10:00", 2, "11:00")
    settled(qapp, window)
    school = [block for block in window.session.blocks if block["title"] == "School"]
    assert sorted((tuple(block["days"]), block["start"]) for block in school) == [
        ((0, 1, 3, 4), "08:00"),
        ((2,), "09:00"),
    ]
    window.session.undo()
    settled(qapp, window)
    school = [block for block in window.session.blocks if block["title"] == "School"]
    assert [(block["days"], block["start"]) for block in school] == [([0, 1, 2, 3, 4], "08:00")], (
        "one Undo step"
    )


def test_a_block_moved_on_the_week_while_a_save_is_under_way_is_not_lost(
    qapp: QApplication, window: NativeWindow
) -> None:
    waiting = _waiting_math(qapp, window)
    assert window.session.place_session(waiting["id"], 2, 16 * 60)
    window.session.save()
    settled(qapp, window)
    window.session.add_homework(
        {"id": "poster", "title": "Poster", "due": sunday_due(window.session.week_start), "estimate_min": 30}
    )
    window.session.save()
    assert window.session.busy
    _drag_on_the_week(qapp, window, 2, "16:30", 3, "17:30")
    settled(qapp, window)
    wait_until(
        qapp, lambda: next(b for b in window.session.blocks if b["id"] == waiting["id"])["days"] == [3]
    )
    settled(qapp, window)
    moved = next(block for block in window.session.blocks if block["id"] == waiting["id"])
    assert (moved["days"], moved["start"]) == ([3], "17:00")
    assert "poster" in window.session.assignments, "the save under way went through too"


def test_choose_a_time_places_homework_without_dragging(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """For the keyboard, and for the designs with no grid to drop on."""
    from PySide6.QtCore import QTime

    from desktop.native.widgets import ChooseTimeDialog, HomeworkDialog

    waiting = _waiting_math(qapp, window)
    seen: list[str] = []

    def pick(dialog: ChooseTimeDialog) -> int:
        # The clock is held at Thursday, so that is where it opens, not on Monday.
        seen.append(f"opened on {dialog.day.currentData()}")
        dialog.day.setCurrentIndex(dialog.day.findData(1))
        dialog.start.setTime(QTime(10, 0))
        seen.append(dialog.beside.text())
        ok = dialog.buttons.button(dialog.buttons.StandardButton.Ok)
        seen.append("ok" if ok.isEnabled() else "refused")
        dialog.start.setTime(QTime(16, 7))
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ChooseTimeDialog, "exec", pick)
    monkeypatch.setattr(HomeworkDialog, "exec", lambda dialog: _press(dialog, "homeworkChooseTime"))
    window._edit_homework("math")
    settled(qapp, window)
    assert seen == [
        "opened on 3",
        "School is at that time too. Both will show, side by side.",
        "ok",
    ]
    placed = next(block for block in window.session.blocks if block["id"] == waiting["id"])
    assert (placed["days"], placed["start"], placed.get("pinned")) == ([1], "16:07", True), "the time picked"
    hours = _hours(window)
    shown = next(
        item for item, _rect in hours.drawn(hours.track_for(1, 16 * 60)) if item.block_id == waiting["id"]
    )
    assert "Pinned" in shown.detail


def test_let_flexweek_move_it_takes_the_pin_away(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from desktop.native.widgets import HomeworkDialog

    waiting = _waiting_math(qapp, window)
    assert window.session.place_session(waiting["id"], 2, 17 * 60)
    window.session.save()
    settled(qapp, window)
    monkeypatch.setattr(HomeworkDialog, "exec", lambda dialog: _press(dialog, "homeworkUnpin"))
    window._edit_homework("math")
    settled(qapp, window)
    released = next(block for block in window.session.blocks if block["id"] == waiting["id"])
    assert released.get("pinned") is None and released["start"] == "17:00"


def _add_through_the_editor(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> dict:
    from desktop.native.widgets import HomeworkDialog

    def fill(dialog: HomeworkDialog) -> int:
        dialog.title.setText("Chemistry lab")
        dialog.accept()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(HomeworkDialog, "exec", fill)
    window._add_homework()
    for _ in range(3):
        settled(qapp, window)
        QTest.qWait(50)
    return next(item for item in window.session.assignments.values() if item["title"] == "Chemistry lab")


def test_plan_it_as_i_add_it_gives_new_homework_a_time_in_one_undo_step(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.session.preferences = {**(window.session.preferences or {}), "planning_style": "auto"}
    added = _add_through_the_editor(qapp, window, monkeypatch)
    sessions = [block for block in window.session.blocks if block.get("assignment_id") == added["id"]]
    assert sessions and all(block.get("start") for block in sessions), "placed without pressing Plan"
    window.session.undo()
    settled(qapp, window)
    assert added["id"] not in window.session.assignments, "one Undo takes back the homework and its time"
    assert not any(block.get("assignment_id") == added["id"] for block in window.session.blocks)


def test_by_default_new_homework_waits_for_plan_my_homework(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    added = _add_through_the_editor(qapp, window, monkeypatch)
    sessions = [block for block in window.session.blocks if block.get("assignment_id") == added["id"]]
    assert sessions and not any(block.get("start") for block in sessions)
    assert window.solve_button.text() == "Plan my homework"


def test_placing_by_hand_turns_plan_into_suggest_times(qapp: QApplication, window: NativeWindow) -> None:
    dialog = SettingsPage(window, window.session.preferences, window._look, {}, window._layout)
    dialog.findChild(QRadioButton, "prefPlanning-manual").setChecked(True)
    assert dialog.updates()["planning_style"] == "manual"
    window.session.preferences = {**(window.session.preferences or {}), "planning_style": "manual"}
    window._sync_chrome()
    assert window.solve_button.text() == "Suggest times"


def test_a_study_window_can_be_kept_for_one_subject(qapp: QApplication) -> None:
    from PySide6.QtCore import QTime

    from desktop.native.widgets import AvailabilityDialog

    dialog = AvailabilityDialog(None, {}, ["Math", "Reading"])
    dialog.study_start.setTime(QTime(15, 30))
    dialog.study_end.setTime(QTime(17, 0))
    dialog.study_subject.setCurrentIndex(dialog.study_subject.findData("Math"))
    dialog.findChild(QPushButton, "studyAdd").click()
    kept = {"days": [0, 1, 2, 3, 4], "start": "15:30", "duration_min": 90, "subject": "Math"}
    assert dialog.study_windows() == [kept]
    assert dialog.study_list.item(0).text().endswith("Math only")
    dialog.study_end.setTime(QTime(15, 0))
    dialog.findChild(QPushButton, "studyAdd").click()
    assert len(dialog.study_windows()) == 1
    assert "ends after it starts" in dialog.error.text()


def test_a_change_to_the_week_does_not_restyle_the_window_when_the_look_is_the_same(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every change to the week re-dressed the whole window, about 26 ms a time, for nothing."""
    dressed: list[str] = []
    original = window.setStyleSheet
    monkeypatch.setattr(window, "setStyleSheet", lambda sheet: (dressed.append(sheet), original(sheet)))
    window._on_week()
    window._on_week()
    assert dressed == []
    window.session.preferences = {**window.session.preferences, "theme_pack": "dark-frost"}
    window._on_week()
    assert len(dressed) == 1, "a new look is still put on at once"


def test_a_short_busy_spell_takes_no_clicks_but_does_not_grey_the_top_bar(
    qapp: QApplication, window: NativeWindow
) -> None:
    """Grok Bot's 0.17.0 audit (T7): Plan my homework greyed the whole top bar for one frame. A plan
    takes a few milliseconds; the bar greys only once the session has been busy BUSY_LOOK_MS, and takes
    no click from the first moment."""
    from desktop.native.window import BUSY_LOOK_MS

    session = window.session
    plan = window.findChild(QPushButton, "solveButton")
    pressed: list[bool] = []
    plan.clicked.connect(lambda: pressed.append(True))
    session.busy = True
    session.busy_changed.emit(True)
    assert plan.isEnabled(), "not greyed at once"
    QTest.mouseClick(plan, Qt.MouseButton.LeftButton)
    assert pressed == [], "but it takes no click while busy"
    session.busy = False
    session.busy_changed.emit(False)
    QTest.qWait(BUSY_LOOK_MS + 100)
    assert plan.isEnabled(), "a short spell never greys it"
    session.busy = True
    session.busy_changed.emit(True)
    QTest.qWait(BUSY_LOOK_MS + 100)
    assert not plan.isEnabled(), "a long one does"
    session.busy = False
    session.busy_changed.emit(False)
    assert plan.isEnabled(), "and it comes back at once"
