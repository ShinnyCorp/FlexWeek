"""Settings in the words a student looks for, in the order they look (0.15 rows 15, 18, 19, 29).

Appearance & layout opened on an implementation note, then Animations, then a box inside a box with
the style rows in a grey table. The version said 0.14.3. Account and Availability sat together
under This computer, and "Long break after 4" did not say four of what.

Since 0.16 Settings is a page of the window, in cards (design review R11): a switch for on or off, a
segmented control for two or three choices, and the designs as pictures.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QWidget,
)

from desktop.native.layouts.registry import sanitize_layout
from desktop.native.settings import SettingsPage
from desktop.native.update import WINDOWS_SETUP, available
from desktop.native.version import VERSION
from desktop.native.widgets import Segmented, Switch
from desktop.native.window import NativeWindow
from desktop.tests.window_support import qapp, server, signed_out, window  # noqa: F401


def prefs(window: NativeWindow, layout: dict | None = None) -> SettingsPage:  # noqa: F811
    """Settings as the gear opens it, in place of the week."""
    if layout is not None:
        window._layout = sanitize_layout(layout)
    window._open_settings()
    dialog = window._settings
    assert dialog is not None and window._stack.currentWidget() is dialog
    for _ in range(5):
        QApplication.processEvents()
    return dialog


def inside(card_of: QWidget, within: QWidget) -> QPoint:
    """A point on the card that holds `card_of`, clear of its edge and of anything on it."""
    card = card_of
    while card.objectName() != "settingsCard":
        card = card.parentWidget()
    return card.mapTo(within, QPoint(card.width() - 6, card.height() // 2))


def page(dialog: SettingsPage, row: int) -> QWidget:
    return dialog.stack.widget(row).widget()


def label_for(widget: QWidget) -> str:
    form = widget.parentWidget().layout()
    assert isinstance(form, QFormLayout)
    label = form.labelForField(widget)
    return label.text() if isinstance(label, QLabel) else ""


def top(widget: QWidget, within: QWidget) -> int:
    return widget.mapTo(within, widget.rect().topLeft()).y()


def test_this_build_says_0_15_0_and_is_not_offered_0_14_3(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    assert VERSION == "0.15.0"
    release = {
        "tag_name": "v0.14.3",
        "assets": [
            {"name": name, "browser_download_url": f"https://example.invalid/{name}"}
            for name in (WINDOWS_SETUP, WINDOWS_SETUP + ".sha256")
        ],
    }
    assert available(release, "windows") is None
    assert available({**release, "tag_name": "v0.15.1"}, "windows")["version"] == "0.15.1"
    dialog = prefs(window)
    assert dialog.findChild(QLabel, "prefsVersion").text() == "FlexWeek 0.15.0"
    dialog.close_page()


def test_appearance_opens_on_main_view_and_ends_with_animations_and_fine_tune(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    dialog = prefs(window, {"main": "timeline", "day": "one", "options": {}})
    appearance = page(dialog, 0)
    assert appearance.findChildren(QGroupBox) == [], "no box inside the page's box"
    shown = sorted(
        (label for label in appearance.findChildren(QLabel) if label.isVisibleTo(dialog) and label.text()),
        key=lambda label: top(label, appearance),
    )
    assert [label.text() for label in shown[:3]] == [
        "Appearance & layout",
        "Main view",
        "A design is how FlexWeek lays out your week. Your blocks and homework are the same in every one.",
    ]
    assert not any("has its own colours" in label.text() for label in shown)
    order = [
        appearance.findChild(QWidget, "layoutMain"),
        appearance.findChild(QComboBox, "layoutMain-colour"),
        appearance.findChild(QWidget, "layoutDay"),
        dialog.motion,
        dialog.fine_tune,
    ]
    tops = [top(widget, appearance) for widget in order]
    assert tops == sorted(tops), tops
    # What the note said, where it applies: under the colours it is about.
    colour = appearance.findChild(QComboBox, "layoutMain-colour")
    note = appearance.findChild(QLabel, "layoutMainColourNote")
    assert note.text() == "Pick Match my look to use your own Look and Accent."
    assert note.isVisibleTo(dialog)
    assert 0 < top(note, appearance) - top(colour, appearance) < 3 * colour.height()
    colour.setCurrentIndex(colour.findData("match"))
    qapp.processEvents()
    assert not note.isVisibleTo(dialog)
    dialog.close_page()


def test_the_style_rows_sit_on_the_page_not_in_a_grey_table(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    dialog = prefs(window, {"main": "timeline", "day": "one", "options": {}})
    appearance = page(dialog, 0)
    colour = appearance.findChild(QComboBox, "layoutMain-colour")
    heading = appearance.findChild(QLabel, "layoutMainHeading")
    picture = appearance.grab().toImage()
    edge = heading.mapTo(appearance, QPoint(0, 0)).x() - 6
    beside_colour = picture.pixelColor(edge, top(colour, appearance) + colour.height() // 2)
    beside_heading = picture.pixelColor(edge, top(heading, appearance) + heading.height() // 2)
    assert beside_colour == beside_heading, "the style rows are painted on a band of their own"
    dialog.close_page()


def test_focus_says_what_the_long_break_counts(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    dialog = prefs(window)
    assert label_for(dialog.long_every) == "Long break after"
    assert dialog.long_every.text() == "4 focus sessions"
    assert label_for(dialog.long_break) == "Long break minutes"
    dialog.close_page()


def test_account_has_its_own_row_and_availability_is_under_planning(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    dialog = prefs(window)
    account = dialog.findChild(QPushButton, "prefsAccount")
    availability = dialog.findChild(QPushButton, "prefsAvailability")
    assert account.text() == "Manage account…"
    assert label_for(account) == "Account"
    assert page(dialog, 4).isAncestorOf(account)
    assert availability.text() == "Availability…"
    assert page(dialog, 1).isAncestorOf(availability), "Availability is about when to plan"
    asked: list[str] = []
    # The window's own answer is a dialog that waits for a click; only the request is under test.
    dialog.availability_requested.disconnect(window._open_availability)
    dialog.availability_requested.connect(lambda: asked.append("availability"))
    availability.click()
    assert asked == ["availability"]
    dialog.close_page()


def test_play_that_hears_nothing_says_what_to_do(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It said "No sound card" and nothing else, and at volume 0 it blamed the computer."""
    dialog = prefs(window)
    next_step = (
        "No sound played. Check that Volume is above 0 % and that your speakers or headphones are "
        "connected and not muted, then press Play again."
    )
    dialog.volume.setValue(0)
    dialog.play_tone.click()
    assert dialog.save_state.text() == next_step
    dialog.save_state.setText("")
    monkeypatch.setattr(dialog._tone_bell, "once", lambda _tone, _volume: False)
    dialog.volume.setValue(80)
    dialog.play_tone.click()
    assert dialog.save_state.text() == next_step
    dialog.close_page()


def test_fine_tune_is_the_last_thing_on_appearance(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    dialog = prefs(window)
    appearance = page(dialog, 0)
    boxes = [box for box in appearance.findChildren(QCheckBox) if box.isVisibleTo(dialog)]
    assert max(boxes, key=lambda box: top(box, appearance)) is dialog.fine_tune
    dialog.close_page()


def test_reset_is_a_quiet_button_at_the_left_not_a_bar_across_the_page(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    dialog = prefs(window, {"main": "timeline", "day": "one", "options": {}})
    appearance = page(dialog, 0)
    reset = appearance.findChild(QPushButton, "layoutMainReset")
    assert reset.isVisibleTo(dialog)
    picture = appearance.grab().toImage()
    at = reset.mapTo(appearance, reset.rect().topLeft())
    card = inside(reset, appearance)
    filled = picture.pixelColor(at.x() + reset.width() // 2, at.y() + 4)
    assert filled == picture.pixelColor(card.x(), card.y()), "filled"
    assert reset.width() <= reset.sizeHint().width(), "as wide as its words, not the page"
    dialog.close_page()


def test_every_heading_on_appearance_stands_out_from_the_rows_under_it(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """The design first, since it decides what the rest offers; then its colours, the day screen,
    and what applies to every screen."""
    dialog = prefs(window, {"main": "classic", "day": "one", "options": {}})
    appearance = page(dialog, 0)
    names = ("prefsHeading", "layoutMainHeading", "layoutDayHeading")
    headings = sorted(
        (
            label
            for label in appearance.findChildren(QLabel)
            if label.objectName() in names and label.isVisibleTo(dialog)
        ),
        key=lambda label: top(label, appearance),
    )
    assert [label.text() for label in headings] == ["Main view", "Colours", "Day screen", "Every screen"]
    plain = appearance.findChild(QLabel, "settingsCardNote")
    for heading in headings:
        assert heading.font().bold() and not plain.font().bold(), heading.text()
    dialog.close_page()


def test_on_or_off_is_a_switch_and_two_or_three_choices_are_side_by_side(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """R11: toggles for on and off, segmented controls for two or three choices, and the drop-down
    kept for the lists too long to lay side by side."""
    dialog = prefs(window)
    boxes = [box for box in dialog.findChildren(QCheckBox) if not box.objectName().startswith("alarmDay")]
    assert boxes and all(isinstance(box, Switch) for box in boxes), [
        box.objectName() for box in boxes if not isinstance(box, Switch)
    ]
    spacing = dialog.knobs["density"]
    assert isinstance(spacing, Segmented)
    assert [button.text() for button in spacing.buttons()] == ["Comfortable", "Compact"]
    assert label_for(spacing) == "Spacing"
    for control in (dialog.motion, dialog.preferred_view, dialog.drag_step, *dialog.knobs.values()):
        assert isinstance(control, Segmented) and 2 <= control.count() <= 3, control.objectName()
    # A design's colours stay a list: each design adds its own, and Match my look comes last.
    for box in dialog.findChildren(QComboBox):
        assert box.count() > 3 or box.objectName().endswith("-colour"), box.objectName()
    # A click on a segment is a change, said and saved like any other.
    said: list[bool] = []
    dialog.changed.connect(lambda: said.append(True))
    spacing.buttons()[1].click()
    assert spacing.currentData() == "compact" and said
    assert dialog.look_choice()["knobs"].get("density") == "compact"
    dialog.close_page()


def test_every_main_view_is_a_picture_and_the_experimental_ones_come_under_their_heading(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    from desktop.native.widgets import ChoiceCard

    dialog = prefs(window)
    appearance = page(dialog, 0)
    picker = appearance.findChild(QWidget, "layoutMain")
    cards = picker.findChildren(ChoiceCard)
    heading = picker.findChild(QLabel, "settingsExperimental")
    assert heading.text() == "Experimental styles"
    above = [card.accessibleName() for card in cards if top(card, picker) < top(heading, picker)]
    below = [card.accessibleName() for card in cards if top(card, picker) > top(heading, picker)]
    assert above == ["Calendar · Today's app", "Agenda · Timeline"]
    assert below == [
        "Dashboard · Mission control",
        "Dashboard · Bento",
        "Dashboard · Retro desktop",
        "Agenda · Clay deck",
    ]
    for _ in range(40):
        qapp.processEvents()
    assert all(not card.picture.pixmap().isNull() for card in cards), "each card shows its design"
    cards[3].chosen.emit()
    assert dialog.layout_choice()["main"] == "bento"
    assert [card.is_selected() for card in cards] == [False, False, False, True, False, False]
    dialog.close_page()


@pytest.mark.parametrize(
    ("row", "name"),
    [(1, "prefsAvailability"), (4, "prefsAccount"), (4, "prefsRunSetup"), (4, "prefsCheckUpdates")],
)
def test_a_button_that_opens_something_else_is_plain_and_as_wide_as_its_words(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    row: int,
    name: str,
) -> None:
    """Stretched across the page and filled, each was louder than Done, the one answer Settings has."""
    dialog = prefs(window)
    dialog.nav.setCurrentRow(row)
    qapp.processEvents()
    on = page(dialog, row)
    button = on.findChild(QPushButton, name)
    picture = on.grab().toImage()
    at = button.mapTo(on, QPoint(button.width() // 2, 4))
    card = inside(button, on)
    assert picture.pixelColor(at.x(), at.y()) == picture.pixelColor(card.x(), card.y()), "filled"
    assert button.width() <= button.sizeHint().width(), "as wide as the page"
    dialog.close_page()
