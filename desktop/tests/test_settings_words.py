"""Settings in the words a student looks for, in the order they look (0.15 rows 15, 18, 19, 29).

Appearance & layout opened on an implementation note, then Animations, then a box inside a box with
the style rows in a grey table. The version said 0.14.3. Account and Availability sat together
under This computer, and "Long break after 4" did not say four of what.

Since 0.16 Settings is a page of the window, in cards (design review R11): a switch for on or off, a
segmented control for two or three choices, and the designs as pictures.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from desktop.native.layouts.registry import sanitize_layout
from desktop.native.look import look_menu_token
from desktop.native.settings import BUTTON_WIDTH, FINE_TUNE_LOOK, SettingsPage
from desktop.native.update import WINDOWS_SETUP, available
from desktop.native.version import VERSION
from desktop.native.widgets import Segmented, Switch
from desktop.native.window import NativeWindow
from desktop.tests.window_support import qapp, server, signed_out, still, window  # noqa: F401


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
    # A number is stepped by − and + around it, and the three are the form's field together.
    if widget.parentWidget().objectName() == "stepper":
        widget = widget.parentWidget()
    form = widget.parentWidget().layout()
    assert isinstance(form, QFormLayout)
    label = form.labelForField(widget)
    return label.text() if isinstance(label, QLabel) else ""


def top(widget: QWidget, within: QWidget) -> int:
    return widget.mapTo(within, widget.rect().topLeft()).y()


def test_every_field_in_a_forms_column_starts_at_the_same_left_edge(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """A segmented control's track starts where the text fields, steppers, dropdowns and buttons in its
    column do: at the widget's box, and as painted, since a track can be drawn inset from its box."""
    dialog = prefs(window)
    still(dialog)
    seen: list[str] = []
    for row in range(5):
        dialog.nav.setCurrentRow(row)
        for _ in range(5):
            qapp.processEvents()
        on = page(dialog, row)
        picture = on.grab().toImage()
        for form in on.findChildren(QFormLayout):
            fields = [
                item.widget()
                for at in range(form.rowCount())
                if (item := form.itemAt(at, QFormLayout.ItemRole.FieldRole)) is not None
                and item.widget() is not None
                and item.widget().isVisibleTo(dialog)
                and form.itemAt(at, QFormLayout.ItemRole.LabelRole) is not None
            ]
            if not fields:
                continue
            edges = {field.mapTo(on, QPoint(0, 0)).x() for field in fields}
            assert len(edges) == 1, (row, [(f.objectName(), f.mapTo(on, QPoint(0, 0)).x()) for f in fields])
            column = edges.pop()
            for field in fields:
                if not isinstance(field, (Segmented, QLineEdit, QComboBox, QPushButton)) and (
                    field.objectName() != "stepper"
                ):
                    continue
                middle = field.mapTo(on, QPoint(0, field.height() // 2)).y()
                card = picture.pixelColor(column - 3, middle)
                ink = next(x for x in range(column - 2, column + 12) if picture.pixelColor(x, middle) != card)
                assert ink == column, f"{field.objectName()} is drawn from {ink}, column {column}"
                seen.append(type(field).__name__)
    assert "Segmented" in seen and "QLineEdit" in seen and "QComboBox" in seen, seen
    dialog.close_page()


def test_this_build_says_0_18_4_and_is_not_offered_0_18_3(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    assert VERSION == "0.18.4"
    release = {
        "tag_name": "v0.18.3",
        "assets": [
            {"name": name, "browser_download_url": f"https://example.invalid/{name}"}
            for name in (WINDOWS_SETUP, WINDOWS_SETUP + ".sha256")
        ],
    }
    assert available(release, "windows") is None
    assert available({**release, "tag_name": "v0.18.5"}, "windows")["version"] == "0.18.5"
    dialog = prefs(window)
    assert dialog.findChild(QLabel, "prefsVersion").text() == "FlexWeek 0.18.4"
    dialog.close_page()


def test_appearance_opens_on_colours_then_the_designs_and_ends_with_animations(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Grok Bot's 0.17.0 audit (X1, A11): Colours sat under every design card and its fine-tuning
    under Every screen. Colours now comes first, with its fine-tuning in it."""
    dialog = prefs(window, {"main": "timeline", "day": "one", "options": {}})
    appearance = page(dialog, 0)
    assert appearance.findChildren(QGroupBox) == [], "no box inside the page's box"
    shown = sorted(
        (label for label in appearance.findChildren(QLabel) if label.isVisibleTo(dialog) and label.text()),
        key=lambda label: top(label, appearance),
    )
    assert [label.text() for label in shown[:3]] == ["Appearance & layout", "Colours", "Look"]
    assert not any("has its own colours" in label.text() for label in shown)
    notes = [label.text() for label in appearance.findChildren(QLabel, "settingsCardNote")]
    design_line = (
        "A design is how FlexWeek lays out your week. Your blocks and homework are the same in every one."
    )
    assert notes.count(design_line) == 1, "Main view says once what a design is"
    order = [
        dialog.look,
        dialog.fine_tune,
        appearance.findChild(QWidget, "layoutMain"),
        appearance.findChild(QComboBox, "layoutMain-colour"),
        appearance.findChild(QWidget, "layoutDay"),
        dialog.motion,
    ]
    tops = [top(widget, appearance) for widget in order]
    assert tops == sorted(tops), tops
    # What the note says, where it applies: under the colours it is about, once a design wears
    # colours of its own rather than the student's look.
    colour = appearance.findChild(QComboBox, "layoutMain-colour")
    note = appearance.findChild(QLabel, "layoutMainColourNote")
    assert colour.currentData() == "match"
    assert not note.isVisibleTo(dialog)
    colour.setCurrentIndex(colour.findData("paper"))
    qapp.processEvents()
    assert note.text() == (
        "Only the design's page takes these colours. The rest of FlexWeek keeps your Look and Accent."
    )
    assert note.isVisibleTo(dialog)
    assert 0 < top(note, appearance) - top(colour, appearance) < 3 * colour.height()
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


def test_the_look_is_fine_tuned_in_the_colours_card_under_a_name_of_its_own(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Grok Bot's 0.17.0 audit (A11, T33): the look's fine-tuning sat under Every screen, and "Fine-tune
    this look" and "Fine-tune this design" read as one toggle."""
    dialog = prefs(window)
    colours = dialog.colours_card
    assert dialog.fine_tune.parentWidget() is not None and colours.isAncestorOf(dialog.fine_tune)
    names = {box.text() for box in page(dialog, 0).findChildren(QCheckBox) if box.isVisibleTo(dialog)}
    assert FINE_TUNE_LOOK in names and "Fine-tune this design" not in names
    assert "Show more options for this design" in names
    dialog.close_page()


def test_reset_is_an_outlined_button_at_the_left_not_a_bar_across_the_page(
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
    assert [label.text() for label in headings] == ["Colours", "Main view", "Day screen", "Every screen"]
    plain = appearance.findChild(QLabel, "settingsCardNote")
    for heading in headings:
        assert heading.font().bold() and not plain.font().bold(), heading.text()
    dialog.close_page()


def test_on_or_off_is_a_switch_and_two_or_three_choices_are_side_by_side(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """R11: toggles for on and off, segmented controls for two or three choices, and the drop-down
    kept for the lists too long to lay side by side. Animations' four short levels are side by side
    too (decision 33 of 0.17)."""
    dialog = prefs(window)
    boxes = [box for box in dialog.findChildren(QCheckBox) if not box.objectName().startswith("alarmDay")]
    assert boxes and all(isinstance(box, Switch) for box in boxes), [
        box.objectName() for box in boxes if not isinstance(box, Switch)
    ]
    spacing = dialog.knobs["density"]
    assert isinstance(spacing, Segmented)
    assert [button.text() for button in spacing.buttons()] == ["Comfortable", "Compact"]
    assert label_for(spacing) == "Spacing"
    for control in (dialog.preferred_view, dialog.drag_step, *dialog.knobs.values()):
        assert isinstance(control, Segmented) and 2 <= control.count() <= 3, control.objectName()
    assert isinstance(dialog.motion, Segmented) and dialog.motion.count() == 4
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


def test_animations_has_four_levels_and_follows_the_look_until_one_is_chosen(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Decision 33 of 0.17: Normal, More, Reduce and Off, kept as the ids saved preferences and custom
    looks already use, and Paper starts at Reduce. Settings used to save whatever it showed, so the
    first change anywhere in Settings pinned the level and a look chosen after it could not set it."""
    dialog = prefs(window)
    motion = dialog.motion
    assert [button.text() for button in motion.buttons()] == ["Normal", "More", "Reduce", "Off"]
    assert [motion.itemData(index) for index in range(motion.count())] == ["normal", "extra", "reduce", "off"]
    assert dialog.updates()["motion"] is None, "never chosen: the look's own"
    dialog.look.setCurrentIndex(dialog.look.findData(look_menu_token("preset", "paper")))
    assert motion.currentData() == "reduce", "Paper starts at Reduce"
    assert dialog.updates()["motion"] is None
    motion.buttons()[1].click()
    assert dialog.updates()["motion"] == "extra"
    dialog.look.setCurrentIndex(dialog.look.findData(look_menu_token("preset", "ink")))
    assert motion.currentData() == "extra", "once chosen, the level stays whatever the look"
    dialog.close_page()


def test_every_main_view_is_a_picture_with_a_single_name_and_the_experimental_ones_say_so(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    from desktop.native.widgets import ChoiceCard

    dialog = prefs(window)
    appearance = page(dialog, 0)
    picker = appearance.findChild(QWidget, "layoutMain")
    cards = picker.findChildren(ChoiceCard)
    assert [card.accessibleName() for card in cards] == [
        "Today's app",
        "Timeline",
        "Mission control",
        "Bento",
        "Retro desktop",
        "Clay deck",
    ]
    tagged = [card.accessibleName() for card in cards if card.findChild(QLabel, "setupChoiceTag")]
    assert tagged == ["Mission control", "Bento", "Retro desktop", "Clay deck"]
    # The pictures are drawn once Settings would have slid in, one at a time.
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and any(card.picture.pixmap().isNull() for card in cards):
        qapp.processEvents()
        QTest.qWait(10)
    assert all(not card.picture.pixmap().isNull() for card in cards), "each card shows its design"
    cards[3].chosen.emit()
    assert dialog.layout_choice()["main"] == "bento"
    assert [card.is_selected() for card in cards] == [False, False, False, True, False, False]
    dialog.close_page()


@pytest.mark.parametrize(
    ("row", "name"),
    [(1, "prefsAvailability"), (4, "prefsAccount"), (4, "prefsRunSetup"), (4, "prefsCheckUpdates")],
)
def test_a_button_that_opens_something_else_is_outlined_and_as_wide_as_its_words(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    row: int,
    name: str,
) -> None:
    """Stretched across the page and filled, each was louder than Done, the one answer Settings has. Now
    each is outlined, not filled, and no wider than its words."""
    dialog = prefs(window)
    dialog.nav.setCurrentRow(row)
    qapp.processEvents()
    on = page(dialog, row)
    button = on.findChild(QPushButton, name)
    picture = on.grab().toImage()
    at = button.mapTo(on, QPoint(button.width() // 2, 4))
    card = inside(button, on)
    assert picture.pixelColor(at.x(), at.y()) == picture.pixelColor(card.x(), card.y()), "filled"
    # The three buttons of This computer share one width, 190 px (mockup 8).
    assert button.width() <= max(button.sizeHint().width(), BUTTON_WIDTH), "as wide as the page"
    dialog.close_page()
