"""One source per setting: the Spotify link, the reminder lead, the homework cutoff and the snooze
length each have one place that decides them, and every page that shows them reads it."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtWidgets import QApplication, QComboBox, QLabel

    from desktop.native.calendar import monday_of
    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.settings import SPOTIFY_TONE_NOTE, SettingsPage
    from desktop.native.setup import NOTES, REMINDERS, SetupPage, SetupState

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
