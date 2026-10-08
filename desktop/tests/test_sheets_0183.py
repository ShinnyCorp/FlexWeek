"""Sheets for 0.18.3 batch B: #43, #51, #52, #53, #55.

Expected values are from the roadmap Done-when lines, mockup board 7, and Jonathan's three
calls: Accept late start filled (greyed until a preview), Preview outlined, Cancel bare; the
Spotify link under More details; New event renamed to Add fixed time, not a second entry.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from desktop.native.controller import plan_sentence
from desktop.native.fields import DayPicker, Stepper
from desktop.native.look import pack_stylesheet, resolved_palette
from desktop.native.settings import AboutDialog, HelpDialog
from desktop.native.widgets import (
    BlockDialog,
    ChooseTimeDialog,
    LateDialog,
    PlanReview,
    RoutineDialog,
    SchoolHoursDialog,
    control_art,
    day_range_words,
    guess_locked_category,
)
from desktop.native.window import NativeWindow
from desktop.tests.test_dialogs_look import WEEK, shown, soccer, styled
from desktop.tests.test_one_filled_button import filled
from desktop.tests.window_support import (  # noqa: F401
    free,
    qapp,
    server,
    settled,
    signed_out,
    still,
    wait_until,
    window,
)

WAITING = {"id": "w", "title": "Essay", "duration_min": 45, "days": [1, 2]}


def test_plan_sentence_and_the_panel_share_one_placed_wording() -> None:
    """#43: the toast and the panel both say Placed, in the toast's sentence."""
    assert plan_sentence(2, 1) == "Placed 2 homework blocks. 1 still needs a time."
    assert plan_sentence(1, 0) == "Placed 1 homework block."
    assert plan_sentence(0, 1) == "Nothing placed. 1 still needs a time."


def test_got_it_is_tinted_and_the_panel_uses_the_toast_sentence(qapp: QApplication) -> None:  # noqa: F811
    palette = resolved_palette("light-frost", False, None, "default")
    host = QWidget()
    host.setStyleSheet(pack_stylesheet("light-frost", False, None, "default", palette, control_art(palette)))
    host.show()
    panel = PlanReview(host)
    panel.set_trace(
        {
            "placed": [{"id": "essay"}],
            "unplaced": [{"id": "poster", "title": "Poster"}],
            "moves": [],
            "explanations": [],
        },
        {"essay": "Essay", "poster": "Poster"},
        WEEK,
        (2, 1),
    )
    qapp.processEvents()
    assert panel.heading.text() == plan_sentence(2, 1)
    got = panel.findChild(QPushButton, "planReviewDismiss")
    assert got.property("tonal") is True
    loud = filled(panel, palette["accent"])
    assert "Got it" not in loud
    free(panel)
    free(host)


def test_choose_a_time_has_day_pills_a_length_stepper_and_choose_this_time(
    qapp: QApplication,  # noqa: F811
) -> None:
    """#51."""
    parent, _palette = styled(qapp)
    dialog = shown(qapp, ChooseTimeDialog(parent, WAITING, WEEK, [1, 2], [], None, 1))
    assert not isinstance(dialog.day, QComboBox)
    assert isinstance(dialog.day, DayPicker)
    assert [button.text() for button in dialog.day.buttons] == [
        "Mon",
        "Tue",
        "Wed",
        "Thu",
        "Fri",
        "Sat",
        "Sun",
    ]
    assert dialog.day.days() == [1]
    assert not dialog.day.buttons[0].isEnabled()
    dialog.day.buttons[2].click()
    assert dialog.day.days() == [2]
    assert isinstance(dialog.length.parentWidget(), Stepper)
    assert dialog.length.value() == 45
    dialog.length.parentWidget().more.click()
    assert dialog.length.value() == 60
    ok = dialog.buttons.button(dialog.buttons.StandardButton.Ok)
    assert ok.text() == "Choose this time"
    free(dialog)
    free(parent)


def test_a_sheets_text_field_uses_the_outlined_style_with_an_accent_focus_ring(
    qapp: QApplication,  # noqa: F811
) -> None:
    """#51: one outlined input style for every text and time field in sheets."""
    parent, palette = styled(qapp)
    dialog = shown(qapp, BlockDialog(parent, day=3, start="17:00"))
    field = dialog.findChild(QLineEdit, "blockTitle")
    field.ensurePolished()
    border = field.style().pixelMetric(field.style().PixelMetric.PM_DefaultFrameWidth, None, field)
    field.setFocus()
    qapp.processEvents()
    # Focus ring is the accent, not the hairline.
    picture = dialog.grab().toImage()
    # The ring is the 1 px accent border (a 2 px border grew homework and routines scroll).
    spot = field.mapTo(dialog, QPoint(0, field.height() // 2))
    colour = picture.pixelColor(spot)
    assert colour.name().lower() == QColor(palette["accent"]).name().lower() or abs(
        colour.hue() - QColor(palette["accent"]).hue()
    ) < 40
    assert border >= 1
    free(dialog)
    free(parent)


def test_add_fixed_time_is_titled_that_and_guesses_category_from_the_start(
    qapp: QApplication,  # noqa: F811
) -> None:
    """#52. Edit stays Edit event. New event is the old title, renamed."""
    parent, _palette = styled(qapp)
    added = shown(qapp, BlockDialog(parent, day=3, start="10:00"))
    assert added.windowTitle() == "Add fixed time"
    assert added.findChild(QLabel, "sheetTitle").text() == "Add fixed time"
    assert added.findChild(QLabel, "blockRepeatNote").text() == "Pick more days to repeat it."
    duration = next(label for label in added.findChildren(QLabel) if label.text() == "Duration")
    assert duration.isVisibleTo(added)
    assert added.category.currentData() == "class"
    added.start.setTime(added.start.time().addSecs(8 * 3600))
    qapp.processEvents()
    # 10:00 + 8 h = 18:00, a meal window.
    assert added.category.currentData() == "meals"
    added.category.setCurrentIndex(added.category.findData("extra"))
    added.start.setTime(added.start.time().addSecs(-6 * 3600))
    qapp.processEvents()
    assert added.category.currentData() == "extra", "a choice the student made is kept"
    assert added.findChild(QLineEdit, "blockSpotify") is None or not added.findChild(
        QLineEdit, "blockSpotify"
    ).isVisibleTo(added)
    added.more_details.setChecked(True)
    qapp.processEvents()
    assert added.spotify.isVisibleTo(added)
    free(added)
    edited = shown(qapp, BlockDialog(parent, soccer(), occurrence_day=3))
    assert edited.windowTitle() == "Edit event"
    free(edited)
    free(parent)


def test_category_guess_follows_school_meals_and_afternoon_activity() -> None:
    assert guess_locked_category("08:00") == "class"
    assert guess_locked_category("07:30") == "meals"
    assert guess_locked_category("12:15") == "meals"
    assert guess_locked_category("18:00") == "meals"
    assert guess_locked_category("16:00") == "extra"
    assert guess_locked_category("21:00") == "extra"


def test_day_ranges_collapse_three_or_more_in_a_row() -> None:
    assert day_range_words([0, 1, 2, 3, 4]) == "Mon–Fri"
    assert day_range_words([0, 2, 4]) == "Mon, Wed, Fri"
    assert day_range_words([0, 1]) == "Mon, Tue"
    assert day_range_words([4, 5, 6]) == "Fri–Sun"


def test_running_late_buttons_are_filled_outlined_and_bare(qapp: QApplication) -> None:  # noqa: F811
    """Jonathan's call: Accept late start filled, Preview outlined, Cancel bare."""
    parent, palette = styled(qapp)
    late = shown(qapp, LateDialog(parent, "School"))
    preview = late.findChild(QPushButton, "latePreview")
    cancel = next(button for button in late.findChildren(QPushButton) if button.text() == "Cancel")
    assert preview.property("outlined") is True
    assert preview.property("quiet") is not True
    assert cancel.property("quiet") is True
    assert late.accept_button.isEnabled() is False
    loud = filled(late, palette["accent"])
    assert loud == []
    late.show_trace({"moves": [], "unplaced": []}, {})
    qapp.processEvents()
    still(late)
    loud = filled(late, palette["accent"])
    assert loud == ["Accept late start"]
    free(late)
    free(parent)


def test_running_late_is_greyed_on_another_week_with_the_reason(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """#53: greyed while viewing next week, instead of refusing after the click."""
    window.findChild(QPushButton, "viewWeek").click()
    settled(qapp, window)
    late = window.findChild(QPushButton, "runningLate")
    assert late.isEnabled()
    window.session.load_week(
        (date.fromisoformat(window.session.week_start) + timedelta(days=7)).isoformat()
    )
    settled(qapp, window)
    assert late.isEnabled() is False
    assert late.toolTip() == "Open this week to use Running late."
    opened: list[str] = []
    window._open_late = lambda: opened.append("opened")  # type: ignore[method-assign]
    late.click()
    assert opened == []


def test_routines_heading_ranges_and_hidden_apply(
    qapp: QApplication,  # noqa: F811
) -> None:
    """#55."""
    parent, _palette = styled(qapp)
    empty = shown(qapp, RoutineDialog(parent, {}, [soccer()], WEEK))
    titles = [label.text() for label in empty.findChildren(QLabel) if label.objectName() == "cardTitle"]
    assert titles[0] == "Make a routine from this week"
    assert empty.findChild(QPushButton, "saveRoutine").text() != titles[0]
    assert empty.findChild(QPushButton, "applyRoutine").isHidden()
    assert empty.findChild(QPushButton, "deleteRoutine").isHidden()
    assert "Mon–Fri" in empty.choices.item(0).text() or "Tue, Thu" in empty.choices.item(0).text()
    free(empty)
    saved = {"r": {"id": "r", "name": "School week", "blocks": [soccer()]}}
    filled_sheet = shown(qapp, RoutineDialog(parent, saved, [soccer()], WEEK))
    assert filled_sheet.findChild(QPushButton, "applyRoutine").isVisibleTo(filled_sheet)
    free(filled_sheet)
    free(parent)


def test_help_routines_and_about_share_a_top_and_help_has_bottom_room(
    qapp: QApplication,  # noqa: F811
) -> None:
    """#55: one top offset, bottom padding so Help's last row is not on the edge."""
    parent, _palette = styled(qapp)
    help_sheet = shown(qapp, HelpDialog(parent))
    about = shown(qapp, AboutDialog(parent, {"mode": "local"}, "/nowhere"))
    routines = shown(qapp, RoutineDialog(parent, {}, [soccer()], WEEK))
    tops = {sheet.y() for sheet in (help_sheet, about, routines)}
    assert len(tops) == 1, tops
    card = help_sheet.card
    assert card.layout().contentsMargins().bottom() >= 16
    free(help_sheet)
    free(about)
    free(routines)
    free(parent)


def test_school_hours_labels_its_times_above_the_fields(qapp: QApplication) -> None:  # noqa: F811
    parent, _palette = styled(qapp)
    dialog = shown(qapp, SchoolHoursDialog(parent, None))
    words = [label.text() for label in dialog.findChildren(QLabel) if label.objectName() == "fieldLabel"]
    assert "Start" in words and "End" in words
    from_labels = [label for label in dialog.findChildren(QLabel) if label.text() == "from"]
    assert not any(label.isVisibleTo(dialog) for label in from_labels)
    free(dialog)
    free(parent)
