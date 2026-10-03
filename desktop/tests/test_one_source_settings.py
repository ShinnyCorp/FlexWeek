"""One source per setting: the Spotify link, the reminder lead, the homework cutoff and the snooze
length each have one place that decides them, and every page that shows them reads it."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import os
from collections.abc import Iterator

import flexweek_engine  # type: ignore[import-untyped]
import pytest

from desktop.native import remind

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton

    from desktop.native.calendar import monday_of
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.settings import SPOTIFY_TONE_NOTE, AlarmRingDialog, SettingsPage
    from desktop.native.setup import NOTES, REMINDERS, WEEK, SetupPage, SetupState
    from desktop.native.widgets import AvailabilityDialog

ALERTS = 3
HINT = "Used by alarms and by blocks that start without a link of their own."
TRACK = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
TRACK_ADDRESS = "spotify:track:4cOdK2wGLETKBW3PvgPWqT"
NO_HOMEWORK_AFTER = ["No limit", "20:00", "20:30", "21:00", "21:30", "22:00", "22:30", "23:00"]


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-one-source-test"])


def settings(qapp: QApplication, **preferences: object) -> SettingsPage:
    dialog = SettingsPage(None, {"reminders_enabled": True, "alarms": [], **preferences}, {}, {})
    dialog.show()
    dialog.nav.setCurrentRow(ALERTS)
    for _ in range(10):
        qapp.processEvents()
    return dialog


def setup_page(qapp: QApplication, **changes: object) -> SetupPage:
    state = SetupState(
        pack="system",
        look={"preset": "default", "knobs": {}},
        layout=sanitize_layout(None),
        preferences={},
        blocks=[],
        week_start=monday_of("2026-09-23"),
    )
    for key, value in changes.items():
        setattr(state, key, value)
    page = SetupPage()
    page.motion = "off"
    page.resize(1100, 720)
    page.open(state)
    page.show()
    qapp.processEvents()
    return page


def texts(box: QComboBox) -> list[tuple[str, object]]:
    return [(box.itemText(row), box.itemData(row)) for row in range(box.count())]


# The Spotify link


def test_settings_names_the_link_as_the_default_and_says_who_uses_it(qapp: QApplication) -> None:
    dialog = settings(qapp, alarm_tone="spotify")
    label = dialog._alerts_form.labelForField(dialog.spotify)
    assert isinstance(label, QLabel) and label.text() == "Default Spotify link"
    assert HINT in dialog.tone_note.text()
    assert dialog.tone_note.isVisible()
    dialog.close()


def test_the_link_note_does_not_say_a_block_without_a_link_plays_nothing(qapp: QApplication) -> None:
    assert SPOTIFY_TONE_NOTE.startswith(HINT)
    assert "Reminders before a block and the end of a focus session play Chime." in SPOTIFY_TONE_NOTE


def test_setup_says_the_same_about_the_link_as_settings(qapp: QApplication) -> None:
    page = setup_page(qapp)
    page._show(REMINDERS)
    page.tone_buttons["spotify"].setChecked(True)
    assert page.spotify_label.text() == "Default Spotify link"
    assert page.spotify.accessibleName() == "Default Spotify link"
    assert page.spotify_note.text() == SPOTIFY_TONE_NOTE
    assert page.spotify_note.isVisible() and page.spotify_label.isVisible()
    page.tone_buttons["bright"].setChecked(True)
    assert not page.spotify_note.isVisible() and not page.spotify_label.isVisible()
    page.close()


def test_setup_does_not_say_one_sound_covers_everything(qapp: QApplication) -> None:
    words = NOTES[REMINDERS]
    assert "One sound" not in words
    assert "alarms and when a block starts" in words
    assert "Chime" in words


def test_play_previews_the_default_link_when_the_sound_is_spotify(qapp: QApplication) -> None:
    dialog = settings(qapp, alarm_tone="spotify", default_spotify_url=TRACK)
    asked: list[str] = []
    rung: list[str] = []
    dialog._spotify_player.play = lambda link: asked.append(link) or True
    dialog._tone_bell.once = lambda tone, _volume: rung.append(tone) or True
    dialog.play_tone.click()
    assert asked == [TRACK] and rung == []
    dialog.close()


def test_play_chimes_when_the_sound_is_spotify_and_there_is_no_link(qapp: QApplication) -> None:
    # A block start rings Chime then, so that is what Play lets the student hear.
    dialog = settings(qapp, alarm_tone="spotify")
    rung: list[str] = []
    dialog._tone_bell.once = lambda tone, _volume: rung.append(tone) or True
    dialog.play_tone.click()
    assert rung == ["chime"]
    dialog.close()


def test_play_says_it_previews_a_block_start(qapp: QApplication) -> None:
    dialog = settings(qapp)
    assert dialog.play_tone.toolTip() == "Hear what plays when a block starts"
    dialog.close()


# The reminder lead


@pytest.fixture()
def lead_of_seven(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(remind, "REMINDER_LEAD_DEFAULT_MIN", 7)
    return 7


def test_the_default_lead_is_the_engines_and_is_five() -> None:
    assert remind.REMINDER_LEAD_DEFAULT_MIN == flexweek_engine.REMINDER_LEAD_DEFAULT_MIN == 5
    assert remind.reminder_lead_min({}) == 5
    assert remind.reminder_lead_min({"reminder_lead_min": None}) == 5
    assert remind.reminder_lead_min({"reminder_lead_min": 12}) == 12


def test_setup_settings_and_the_summary_start_from_the_one_default(qapp: QApplication) -> None:
    first = setup_page(qapp)
    first._show(REMINDERS)
    assert first.lead.value() == 5
    first.close()
    later = setup_page(qapp, first_run=False, preferences={"reminders_enabled": True})
    later._show(REMINDERS)
    assert later.lead.value() == 5
    later.close()
    assert settings(qapp).lead.value() == 5
    summary = setup_page(qapp, preferences={"reminders_enabled": True})
    assert summary_reminders(summary).startswith("5 min before things start")
    summary.close()


def test_every_page_follows_the_default_when_it_changes(qapp: QApplication, lead_of_seven: int) -> None:
    first = setup_page(qapp)
    first._show(REMINDERS)
    assert first.lead.value() == lead_of_seven
    first.close()
    later = setup_page(qapp, first_run=False, preferences={"reminders_enabled": True})
    later._show(REMINDERS)
    assert later.lead.value() == lead_of_seven
    later.close()
    dialog = settings(qapp)
    assert dialog.lead.value() == lead_of_seven
    dialog.close()
    summary = setup_page(qapp, preferences={"reminders_enabled": True})
    assert summary_reminders(summary).startswith(f"{lead_of_seven} min before things start")
    summary.close()


def summary_reminders(page: SetupPage) -> str:
    page._fill_summary()
    return page.summary_text()[3]


# The homework cutoff


def test_setup_and_availability_offer_the_same_cutoffs(qapp: QApplication) -> None:
    setup_box = setup_page(qapp).cutoff
    availability = AvailabilityDialog(None, {})
    assert [words for words, _ in texts(setup_box)] == NO_HOMEWORK_AFTER
    assert texts(availability.cutoff) == texts(setup_box)
    assert texts(setup_box)[0] == ("No limit", None)
    assert texts(setup_box)[1:] == [(hhmm, hhmm) for hhmm in NO_HOMEWORK_AFTER[1:]]
    availability.close()


def test_the_availability_cutoff_says_what_it_is_for(qapp: QApplication) -> None:
    availability = AvailabilityDialog(None, {})
    availability.show()
    qapp.processEvents()
    assert availability.cutoff.accessibleName() == "No homework after"
    labels = [label for label in availability.findChildren(QLabel) if label.text() == "No homework after"]
    assert len(labels) == 1 and labels[0].isVisible()
    above = labels[0].mapTo(availability, labels[0].rect().topLeft()).y()
    assert above < availability.cutoff.mapTo(availability, availability.cutoff.rect().topLeft()).y()
    availability.close()


def test_a_cutoff_saved_off_the_list_is_kept_not_dropped(qapp: QApplication) -> None:
    # Availability used to offer every quarter hour, so a saved 22:15 is real and must survive a save.
    availability = AvailabilityDialog(None, {"day_cutoff": "22:15"})
    assert availability.day_cutoff() == "22:15"
    assert [words for words, _ in texts(availability.cutoff)] == [
        "No limit", "20:00", "20:30", "21:00", "21:30", "22:00", "22:15", "22:30", "23:00",
    ]  # fmt: skip
    availability.close()
    page = setup_page(qapp, preferences={"day_cutoff": "22:15"})
    page._show(WEEK)
    assert page.cutoff.currentData() == "22:15"
    page.close()


# The constants


def test_python_keeps_no_copy_of_the_engines_constants() -> None:
    tree = ast.parse(inspect.getsource(remind))
    assigned = {
        target.id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    for name in ("REMINDER_WINDOW_MIN", "REMINDER_LEAD_DEFAULT_MIN", "ALARM_SNOOZE_MIN", "ALARM_SNOOZE_MS"):
        value = assigned[name]
        assert isinstance(value, ast.Attribute), f"{name} is written down again, not read"
        assert isinstance(value.value, ast.Name) and value.value.id == "flexweek_engine", name
        assert getattr(remind, name) == getattr(flexweek_engine, name)


def test_the_snooze_button_and_the_snooze_length_agree(qapp: QApplication) -> None:
    dialog = AlarmRingDialog(None, {"name": "Wake up", "time": "06:45"}, "")
    button = dialog.findChild(QPushButton, "alarmSnooze")
    assert isinstance(button, QPushButton)
    snoozed_for = remind.snooze_until(1_000_000) - 1_000_000
    assert snoozed_for % 60_000 == 0
    assert button.text() == f"Snooze {snoozed_for // 60_000} minutes"
    dialog.close()
