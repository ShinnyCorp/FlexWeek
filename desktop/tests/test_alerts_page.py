"""Settings > Alerts: reminders first, with their switch on top and their controls greyed while it is
off; alarms as their own group, each saying when it rings; one sound dropdown; plain words."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QLineEdit, QWidget

    from desktop.native.settings import SettingsPage
    from desktop.native.window import NativeWindow
    from desktop.server import LocalServer

ALERTS = 3
WEEKDAYS = [0, 1, 2, 3, 4]


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    QStandardPaths.setTestModeEnabled(True)
    yield QApplication.instance() or QApplication(["flexweek-alerts-page-test"])


def settings(qapp: QApplication, parent: QWidget | None = None, **preferences: Any) -> SettingsPage:
    dialog = SettingsPage(parent, {"reminders_enabled": True, "alarms": [], **preferences}, {}, {})
    dialog.show()
    dialog.nav.setCurrentRow(ALERTS)
    for _ in range(10):
        qapp.processEvents()
    return dialog


def page(dialog: SettingsPage) -> QWidget:
    return dialog.stack.widget(ALERTS).widget()


def top(widget: QWidget, dialog: SettingsPage) -> int:
    return widget.mapTo(page(dialog), widget.rect().topLeft()).y()


def test_reminders_come_first_with_their_switch_on_top(qapp: QApplication) -> None:
    dialog = settings(qapp)
    headings = sorted(
        (label for label in page(dialog).findChildren(QLabel, "prefsHeading") if label.isVisible()),
        key=lambda label: top(label, dialog),
    )
    assert [label.text() for label in headings][:2] == ["Reminders", "Alarms"]
    assert dialog.reminders.text() == "Remind me before each block starts"
    below = [dialog.lead, dialog.alarm_tone, dialog.reminder_sound, dialog.dnd_override]
    assert all(top(dialog.reminders, dialog) < top(widget, dialog) for widget in below)
    assert all(top(widget, dialog) < top(dialog.alarm_list, dialog) for widget in below)
    dialog.close()


def test_the_reminder_controls_are_greyed_while_reminders_are_off(qapp: QApplication) -> None:
    dialog = settings(qapp, reminders_enabled=False)
    controls = [dialog.lead, dialog.reminder_sound, dialog.alarm_tone, dialog.play_tone, dialog.dnd_override]
    assert [widget.isEnabled() for widget in controls] == [False] * len(controls)
    dialog.reminders.setChecked(True)
    assert [widget.isEnabled() for widget in controls] == [True] * len(controls)
    assert dialog.alarm_name.isEnabled() and dialog.volume.isEnabled(), "alarms do not depend on reminders"
    dialog.close()


def test_one_sound_dropdown_outside_the_new_alarm(qapp: QApplication) -> None:
    """There were two, both saying Chime: the sound, and a second one beside the volume for the Test
    button. Play plays the sound that is chosen, at the volume in the box."""
    dialog = settings(qapp, alert_volume=35, alarm_tone="low")
    combos = {box.objectName() for box in page(dialog).findChildren(QComboBox)}
    assert combos == {"prefAlarmTone", "alarmSound"}
    played: list = []
    dialog._tone_bell.once = lambda tone, volume: played.append((tone, volume)) or True
    dialog.volume.setValue(45)
    dialog.play_tone.click()
    assert played == [("low", 45)]
    dialog.close()


def test_a_sound_that_cannot_play_says_why(qapp: QApplication) -> None:
    dialog = settings(qapp)
    dialog._tone_bell.once = lambda _tone, _volume: False
    dialog.play_tone.click()
    assert dialog.save_state.text() == (
        "No sound played. Check that Volume is above 0 % and that your speakers or headphones are "
        "connected and not muted, then press Play again."
    )
    dialog.close()


@pytest.mark.parametrize(
    ("days", "words"),
    [
        (WEEKDAYS, "Wake up · Chime\nRings at 07:00, Monday to Friday"),
        ([5, 6], "Wake up · Chime\nRings at 07:00, Saturday and Sunday"),
        (list(range(7)), "Wake up · Chime\nRings at 07:00, every day"),
        ([0, 2, 4], "Wake up · Chime\nRings at 07:00, Mon, Wed and Fri"),
        ([3], "Wake up · Chime\nRings at 07:00, Thursday"),
    ],
)
def test_each_alarm_says_when_it_rings(qapp: QApplication, days: list[int], words: str) -> None:
    alarm = {"id": "a", "name": "Wake up", "time": "07:00", "days": days, "enabled": True, "sound": "chime"}
    dialog = settings(qapp, alarms=[alarm])
    assert dialog.alarm_list.item(0).text() == words
    assert dialog.alarm_empty.isHidden()
    dialog.close()


def test_no_alarms_says_so(qapp: QApplication) -> None:
    dialog = settings(qapp)
    assert not dialog.alarm_empty.isHidden() and dialog.alarm_empty.text() == "No alarms yet."
    assert dialog.alarm_list.isHidden()
    dialog.close()


def test_the_words_say_what_each_setting_does(qapp: QApplication) -> None:
    dialog = settings(qapp)
    # "80%", as it is written, not "80 %" (T20 of the 0.17.0 audit).
    assert dialog.volume.suffix() == "%"
    assert dialog.tray.text() == "Keep running when I close the window"
    assert dialog.findChild(QLabel, "prefTrayNote").text() == (
        "FlexWeek waits in the tray, so reminders and alarms still come."
    )
    assert dialog.dnd_override.text() == "Leave reminders on screen"
    dnd_note = dialog.findChild(QLabel, "prefDndNote").text()
    assert dnd_note == "Each one stays in the window until you press Got it."
    assert dialog.block_song_note.text() == (
        "When a block starts, its own Spotify link plays. With none, the default link plays if the"
        " sound is Spotify. Dismiss or snooze it as you would an alarm."
    )
    dialog.close()


def test_the_spotify_hints_fit_their_boxes_at_large_text(qapp: QApplication, tmp_path: Path) -> None:
    """At 1150x768 with large text the link's hint was cut off mid-address."""
    server = LocalServer(tmp_path / "alerts.db")
    server.start()
    window = NativeWindow(server.origin)
    try:
        window.resize(1150, 768)
        window.show()
        window._look = {**window._look, "knobs": {**(window._look.get("knobs") or {}), "text": "large"}}
        window._apply_appearance()
        dialog = settings(qapp, window, alarm_tone="spotify")
        cut = []
        for field in page(dialog).findChildren(QLineEdit):
            if field.isVisible() and field.placeholderText():
                need = field.fontMetrics().horizontalAdvance(field.placeholderText())
                if need + 24 > field.width():
                    cut.append((field.objectName(), field.placeholderText(), need, field.width()))
        assert cut == []
        dialog.close()
    finally:
        window.hide()
        qapp.processEvents()
        server.stop()


def test_a_new_alarm_starts_at_seven_names_its_spotify_field_and_offers_remove_only_with_alarms(
    qapp: QApplication,
) -> None:
    """T21 of the 0.17.0 audit: a new alarm started at 00:00, its Spotify field had no label, and
    Remove alarm showed with no alarm to remove."""
    dialog = settings(qapp)
    assert dialog.alarm_time.time().toString("HH:mm") == "07:00"
    form = dialog.alarm_spotify.parentWidget().layout()
    label = form.labelForField(dialog.alarm_spotify)
    assert isinstance(label, QLabel) and label.text() == "Spotify link" and label.isVisible()
    assert dialog.remove_alarm.isHidden(), "nothing to remove yet"
    dialog.alarm_name.setText("Wake up")
    dialog.findChild(QWidget, "addAlarm").click()
    assert [alarm["time"] for alarm in dialog.updates()["alarms"]] == ["07:00"]
    assert not dialog.remove_alarm.isHidden()
    dialog.alarm_list.setCurrentRow(0)
    dialog.remove_alarm.click()
    assert dialog.remove_alarm.isHidden()
    dialog.close()
