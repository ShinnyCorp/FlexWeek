"""Add and Edit homework, the form's own findings (#36 of the 0.17.2 audit, 0.18.3 batch B): the due
starts tomorrow and at the end of the school day, the length hint speaks only when it is wrong, Edit says
where the homework is placed, and empty lists stay out of the way."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate, QPoint, QTime
from PySide6.QtGui import QTextLayout
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from desktop.native.widgets import STACKED_GAP, HomeworkDialog, OverlayBar, use_app_style
from desktop.tests.test_dialogs_look import styled
from desktop.tests.window_support import free, qapp  # noqa: F401

TODAY = "2026-09-14"
LATE_EVENING = datetime(2026, 9, 14, 22, 41)
SCHOOL = {
    "id": "school",
    "kind": "locked",
    "category": "class",
    "days": [0, 1, 2, 3, 4],
    "start": "08:00",
    "duration_min": 390,
}


def host(*blocks: dict, now: datetime = LATE_EVENING) -> QWidget:
    """A parent whose session has this week's blocks and a clock, as the window's session does."""
    parent = QWidget()
    parent.session = SimpleNamespace(  # type: ignore[attr-defined]
        now_ms=lambda: int(now.timestamp() * 1000), blocks=list(blocks), week_start=TODAY
    )
    return parent


def styled_host(qapp: QApplication, *blocks: dict) -> QWidget:  # noqa: F811
    """`host`, dressed in the app's look, so widths and gaps are the ones a student sees."""
    parent, _palette = styled(qapp)
    parent.session = host(*blocks).session  # type: ignore[attr-defined]
    return parent


def session(day: int, start: str | None, **more: object) -> dict:
    return {
        "id": f"s{day}{start}",
        "title": "History essay",
        "kind": "flexible",
        "assignment_id": "essay",
        "duration_min": 60,
        "days": [day],
        **({"start": start} if start else {}),
        **more,
    }


def essay(**more: object) -> dict:
    return {
        "id": "essay",
        "title": "History essay",
        "due": "2026-09-25",
        "estimate_min": 60,
        "category": "assignments",
        "revision": 0,
        **more,
    }


def opened(parent: QWidget, assignment: dict | None = None) -> HomeworkDialog:
    dialog = HomeworkDialog(parent, assignment, TODAY)
    dialog.show()
    QApplication.processEvents()
    return dialog


# Defaults


def test_new_homework_is_due_tomorrow_even_at_22_41(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    assert dialog.due.value() == "2026-09-15"
    free(dialog)
    free(parent)


def test_a_due_given_by_the_caller_is_kept(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = HomeworkDialog(parent, today=TODAY, due="2026-09-18")
    assert dialog.due.value() == "2026-09-18"
    free(dialog)
    free(parent)


def test_the_due_time_starts_at_the_end_of_the_school_day(qapp: QApplication) -> None:  # noqa: F811
    parent = host(SCHOOL)
    dialog = opened(parent)
    dialog.due.timed.setChecked(True)
    assert dialog.due.time.time() == QTime(14, 30), "08:00 plus 390 minutes"
    free(dialog)
    free(parent)


def test_with_no_school_saved_the_due_time_starts_at_15_00(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    dialog.due.timed.setChecked(True)
    assert dialog.due.time.time() == QTime(15, 0)
    free(dialog)
    free(parent)


def test_a_saved_due_time_is_not_replaced_by_the_school_day(qapp: QApplication) -> None:  # noqa: F811
    parent = host(SCHOOL)
    dialog = opened(parent, essay(due="2026-09-25T09:15"))
    assert dialog.due.time.time() == QTime(9, 15)
    free(dialog)
    free(parent)


def test_the_title_hint_is_the_example_setup_gives(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = HomeworkDialog(parent, today=TODAY, category="study")
    assert dialog.title.placeholderText() == "e.g. History essay"
    free(dialog)
    free(parent)


# The length hint


def test_the_multiple_of_15_hint_shows_only_for_a_value_that_is_wrong(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    hint = dialog.estimate_hint
    assert not hint.isVisible(), "60 is fine: nothing to say"
    dialog.estimate.setValue(50)
    dialog.estimate.editingFinished.emit()
    assert hint.isVisible()
    assert hint.property("problem") is True, "in the error colour"
    dialog.stepper.chips[3].click()  # 60
    assert dialog.estimate.value() == 60
    assert not hint.isVisible(), "choosing 60 takes it away"
    free(dialog)
    free(parent)


def wrapped_lines(label: QLabel, width: int) -> list[str]:
    layout = QTextLayout(label.text(), label.font())
    layout.beginLayout()
    lines = []
    while (line := layout.createLine()).isValid():
        line.setLineWidth(width)
        lines.append(label.text()[line.textStart() : line.textStart() + line.textLength()])
    layout.endLayout()
    return lines


def test_the_hint_never_leaves_a_word_alone_on_a_line(qapp: QApplication) -> None:  # noqa: F811
    parent = styled_host(qapp)
    dialog = opened(parent)
    dialog.estimate.setValue(50)
    dialog.estimate.editingFinished.emit()
    hint = dialog.estimate_hint
    for width in range(140, 420, 4):
        last = wrapped_lines(hint, width)[-1]
        assert len(last.split()) > 1, f"{last!r} stands alone at {width} px"
    free(dialog)
    free(parent)


def test_an_off_grid_length_cannot_be_saved(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    dialog.title.setText("Essay")
    dialog.estimate.setValue(50)
    dialog.accept()
    assert dialog.result() != dialog.DialogCode.Accepted
    assert dialog.estimate_hint.isVisible()
    free(dialog)
    free(parent)


# The due row


def test_the_year_shows_only_when_it_is_not_this_year(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    assert dialog.due.date.text() == "Tue 15 Sep"
    dialog.due.date.setDate(QDate(2027, 1, 8))
    assert dialog.due.date.text() == "Fri 8 Jan 2027"
    dialog.due.date.setDate(QDate(2026, 12, 1))
    assert dialog.due.date.text() == "Tue 1 Dec"
    free(dialog)
    free(parent)


def test_the_due_by_switch_sits_a_pixel_further_from_the_date_than_a_form_gap(qapp: QApplication) -> None:  # noqa: F811
    parent = styled_host(qapp)
    dialog = opened(parent)
    date_bottom = dialog.due.date.mapTo(dialog.due, QPoint(0, dialog.due.date.height())).y()
    switch_top = dialog.due.timed.mapTo(dialog.due, QPoint(0, 0)).y()
    assert switch_top - date_bottom == STACKED_GAP + 1
    free(dialog)
    free(parent)


# Edit says where it is placed


def placed_line(dialog: HomeworkDialog) -> QLabel:
    return dialog.placed_line


def test_edit_says_where_the_homework_is_placed(qapp: QApplication) -> None:  # noqa: F811
    parent = host(session(4, "15:30"))
    dialog = opened(parent, essay())
    line = placed_line(dialog)
    assert line.isVisible() and line.text() == "Placed Fri 15:30"
    free(dialog)
    free(parent)


def test_edit_counts_every_time_it_is_placed(qapp: QApplication) -> None:  # noqa: F811
    parent = host(
        session(5, "10:00"), session(4, "15:30"), session(2, None), session(1, "09:00", completed=True)
    )
    dialog = opened(parent, essay())
    assert placed_line(dialog).text() == "Placed Fri 15:30 and Sat 10:00 · 2 times"
    free(dialog)
    free(parent)


def test_nothing_is_said_when_it_is_not_placed_or_new(qapp: QApplication) -> None:  # noqa: F811
    parent = host(session(2, None))
    unplaced = opened(parent, essay())
    assert not placed_line(unplaced).isVisible()
    free(unplaced)
    free(parent)
    other = host(session(4, "15:30"))
    new = opened(other)
    assert not placed_line(new).isVisible()
    free(new)
    free(other)


# More details


def test_the_toggle_names_what_it_will_do(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    toggle = dialog.more_details
    assert toggle.text() == "More details"
    toggle.click()
    assert toggle.text() == "Fewer details"
    toggle.click()
    assert toggle.text() == "More details"
    free(dialog)
    free(parent)


def test_notes_has_a_label(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    dialog.more_details.click()
    found = dialog._details.findChildren(QLabel)
    labels = [label.text() for label in found if label.objectName() == "fieldLabel"]
    assert "Notes" in labels
    free(dialog)
    free(parent)


def test_empty_lists_say_so_in_one_grey_line_and_give_way_to_entries(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(parent)
    dialog.more_details.click()
    none_links, none_steps = dialog.no_links, dialog.no_steps
    assert none_links.text() == "No links yet" and none_steps.text() == "No steps yet"
    assert none_links.isVisible() and none_steps.isVisible()
    assert not dialog.links.isVisible() and not dialog.checks.isVisible()
    dialog.link_label.setText("Notes")
    dialog.link_url.setText("https://example.org/notes")
    dialog.findChild(QPushButton, "addHomeworkLink").click()
    dialog.check_text.setText("Read chapter 4")
    dialog.findChild(QPushButton, "addHomeworkCheck").click()
    assert dialog.links.isVisible() and dialog.checks.isVisible()
    assert not none_links.isVisible() and not none_steps.isVisible()
    free(dialog)
    free(parent)


def test_homework_with_entries_opens_with_the_lists_not_the_grey_lines(qapp: QApplication) -> None:  # noqa: F811
    parent = host()
    dialog = opened(
        parent,
        essay(
            links=[{"label": "Sources", "url": "https://example.org/a"}],
            checklist=[{"id": "c1", "text": "Outline", "done": False}],
        ),
    )
    assert dialog.links.isVisible() and dialog.checks.isVisible()
    assert not dialog.no_links.isVisible()
    assert not dialog.no_steps.isVisible()
    free(dialog)
    free(parent)


# The scroll bar


def test_the_content_keeps_16_px_from_the_scroll_bar(qapp: QApplication) -> None:  # noqa: F811
    use_app_style(qapp)
    parent = styled_host(qapp)
    dialog = opened(parent)
    dialog.more_details.click()
    scroll = dialog._scroll
    scroll.setFixedHeight(160)
    QApplication.processEvents()
    bar = scroll.verticalScrollBar()
    assert bar.maximum() > 0, "the body is taller than 160 px, so the bar shows"
    pill_left = bar.mapTo(scroll, QPoint(bar.width() - OverlayBar.WIDE - OverlayBar.EDGE, 0)).x()
    content_right = dialog.title.mapTo(scroll, QPoint(dialog.title.width(), 0)).x()
    assert pill_left - content_right == 16
    free(dialog)
    free(parent)
