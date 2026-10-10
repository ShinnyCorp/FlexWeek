"""Regression for fix-specs.md item 0c: changing Start drags End along while you type, and can wrap it.

Block editor (`widgets.py` BlockDialog, `self.start.timeChanged.connect(self._keep_length)`): End should
follow Start only once Start is settled, stop following once End was typed by hand in this sheet, and
clamp at 24:00 rather than wrap to the morning. Setup's rows and School hours carry no length, so for
them the guard is that Start never moves End. Keys go through the window system's path (see item 0's
tests).
"""

# ruff: noqa: F811  (pytest fixtures imported by name)
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import QLabel, QWidget

from desktop.native.widgets import BlockDialog, SchoolHoursDialog
from desktop.tests.test_regress_item0_time_boxes import _setup, _up, enter, press, type_text
from desktop.tests.window_support import free, qapp  # noqa: F401


@pytest.fixture()
def editor(qapp):
    host = QWidget()
    made: list[QWidget] = []

    def open_editor(start: str = "16:00", minutes: int = 60) -> BlockDialog:
        dialog = _up(qapp, BlockDialog(host, day=3, start=start, duration_min=minutes))
        dialog.title.setText("Club")
        made.append(dialog)
        return dialog

    yield open_editor
    for widget in made:
        widget.hide()
        free(widget)
    free(host)


def hhmm(field) -> str:
    minutes = field.minutes()
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def test_end_does_not_move_while_start_is_half_typed(editor) -> None:
    dialog = editor()
    ends = []
    enter(dialog.start, "tab-in")
    for char in "18:00":
        type_text(dialog.start, char)
        ends.append(hhmm(dialog.end))
    assert ends == ["17:00"] * 5, f"End while typing Start: {ends}"


def test_end_follows_a_settled_start(editor) -> None:
    """Guard: once Start is settled (Tab), End keeps the block's length."""
    dialog = editor()
    enter(dialog.start, "tab-in")
    type_text(dialog.start, "18:00")
    press(dialog.start, Qt.Key.Key_Tab)
    assert (hhmm(dialog.start), hhmm(dialog.end)) == ("18:00", "19:00")
    dialog.accept()
    assert dialog.block()["duration_min"] == 60


def test_start_never_moves_an_end_typed_by_hand(editor) -> None:
    """The spec's guard: End typed first, then Start retyped key by key: End unchanged."""
    dialog = editor()
    enter(dialog.end, "tab-in")
    type_text(dialog.end, "17:30")
    press(dialog.end, Qt.Key.Key_Tab)
    assert hhmm(dialog.end) == "17:30"
    enter(dialog.start, "tab-in")
    type_text(dialog.start, "15:00")
    press(dialog.start, Qt.Key.Key_Tab)
    assert (hhmm(dialog.start), hhmm(dialog.end)) == ("15:00", "17:30")


def test_end_is_clamped_at_midnight_with_a_message(editor) -> None:
    """The spec's guard: Start 16:00 to 23:30 on a 90 min block: End is 24:00 with a message, not 01:00."""
    dialog = editor(minutes=90)
    dialog.start.setTime(QTime(23, 30))
    assert dialog.end.minutes() == 24 * 60, f"End is {hhmm(dialog.end)}"
    said = [label.text() for label in dialog.findChildren(QLabel) if label.isVisible()]
    assert any("24:00" in text or "midnight" in text.lower() for text in said), said


def test_the_duration_line_says_end_moved(editor) -> None:
    dialog = editor()
    enter(dialog.start, "tab-in")
    type_text(dialog.start, "16:30")
    press(dialog.start, Qt.Key.Key_Tab)
    assert "End moved to 17:30" in dialog.duration_line.text()


@pytest.mark.parametrize("where", ["setup-school", "setup-activity", "school-hours"])
def test_setup_and_school_hours_start_never_moves_end(qapp, where) -> None:
    """Item 0c.5 guard: these carry no length, so retyping Start leaves End alone."""
    if where == "school-hours":
        host = QWidget()
        top = _up(qapp, SchoolHoursDialog(host))
        start, end = top.times.start, top.times.end
        owned = [top, host]
    else:
        box = _setup(qapp, "school-start" if where == "setup-school" else "activity-start")
        top, owned = box.top, box.owned
        start = box.field
        end = top.school_times.end if where == "setup-school" else top.activities[0].times.end
    try:
        before = hhmm(end)
        enter(start, "tab-in")
        type_text(start, "09:15")
        press(start, Qt.Key.Key_Tab)
        assert (hhmm(start), hhmm(end)) == ("09:15", before)
    finally:
        for widget in owned:
            widget.hide()
            free(widget)


def test_a_moved_end_keeps_the_blocks_length_for_the_next_start(editor) -> None:
    """Clamped at 24:00, End is 30 min after Start, but the block is still 90 min: Start back to 22:00
    puts End at 23:30, not 22:30."""
    dialog = editor(minutes=90)
    dialog.start.setTime(QTime(23, 30))
    assert hhmm(dialog.end) == "24:00"
    dialog.start.setTime(QTime(22, 0))
    assert hhmm(dialog.end) == "23:30"


def test_a_start_after_a_typed_end_says_end_needs_to_be_later(editor) -> None:
    dialog = editor()
    enter(dialog.end, "tab-in")
    type_text(dialog.end, "17:00")
    press(dialog.end, Qt.Key.Key_Tab)
    enter(dialog.start, "tab-in")
    type_text(dialog.start, "18:00")
    press(dialog.start, Qt.Key.Key_Tab)
    assert hhmm(dialog.end) == "17:00"
    assert dialog.duration_line.text() == "End needs to be later than Start (18:00)."


def test_end_moved_is_announced_once_politely(editor, monkeypatch) -> None:
    said: list[tuple[str, bool]] = []

    def record(widget, text, assertive=False) -> None:
        said.append((text, assertive))

    monkeypatch.setattr("desktop.native.widgets.announce", record)
    dialog = editor()
    dialog.start.setTime(QTime(16, 30))
    assert said == [("End moved to 17:30", False)]
