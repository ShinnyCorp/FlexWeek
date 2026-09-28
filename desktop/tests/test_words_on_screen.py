"""One word for one thing, everywhere (0.15 rows 13, 16, 17).

The Next line said "in 20m" where every design said "in 20 min". A finished block said "Done" where
every button and notice says "Finished". The tray was "Needs a time" in one place and "Not placed
yet" in the next. The strip under Next had no word saying what it was, and cancelling Running late
left its preview's sentence behind.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from desktop.native.focus import now_and_next, now_next_line
from desktop.native.hours.canvas import Drawn
from desktop.native.hours.geometry import Span
from desktop.native.layouts.registry import sanitize_layout
from desktop.native.weekmodel import LEFTOVER
from desktop.native.widgets import LateDialog
from desktop.native.window import NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
    window,
)


def test_the_next_line_says_min_like_every_design() -> None:
    blocks = [
        {"title": "Soccer practice", "start": "16:00", "duration_min": 90, "days": [3], "completed": False}
    ]
    assert now_next_line(now_and_next(blocks, 3, 15 * 60 + 40), 15 * 60 + 40) == (
        "Next: Soccer practice at 16:00 (in 20 min)"
    )
    assert now_next_line(now_and_next(blocks, 3, 14 * 60 + 30), 14 * 60 + 30) == (
        "Next: Soccer practice at 16:00 (in 1 h 30 min)"
    )
    assert now_next_line(now_and_next(blocks, 3, 16 * 60 + 10), 16 * 60 + 10) == (
        "Now: Soccer practice · 1 h 20 min left"
    )


def test_running_late_says_where_each_block_goes_in_words(qapp: QApplication) -> None:  # noqa: F811
    """Its rows read "16:00 → 17:30" and "unscheduled → 18:00"."""
    dialog = LateDialog(None, "Starting from 16:00 today (Thursday).")
    trace = {
        "moves": [
            {"block_id": "essay", "from_start": "16:00", "to_start": "17:30"},
            {"block_id": "maths", "from_start": None, "to_start": "18:00"},
            {"block_id": "club", "from_start": "19:00", "to_start": None},
        ]
    }
    dialog.show_trace(trace, {"essay": "History essay", "maths": "Maths", "club": "Club"})
    rows = [dialog.changes.item(index).text() for index in range(dialog.changes.count())]
    assert rows == [
        "History essay: from 16:00 to 17:30",
        "Maths: placed at 18:00",
        "Club: moves off 19:00 and is not placed",
    ]


def test_a_finished_block_says_finished() -> None:
    block = Drawn("essay", "History essay", "", True, Span(3, 19 * 60, 20 * 60), 0, 1, done=True)
    assert block.detail == "19:00–20:00 · 1 h · Finished"


def test_the_tray_is_not_placed_yet_everywhere(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    assert LEFTOVER["needs_time"] == "Not placed yet"
    session = window.session
    session.add_homework({"id": "essay", "title": "History essay", "estimate_min": 60, "revision": 0,
                          "due": session.week_start[:10] + "T23:59"})
    session.save()
    settled(qapp, window)
    window._on_week()
    qapp.processEvents()
    assert window.findChild(QLabel, "classicWaitingLabel").text() == "Not placed yet"
    trays = (("timeline", "timelineTrayLabel"), ("clay", "clayTrayLabel"))
    for main, name in trays:
        window._layout = sanitize_layout({"main": main, "day": "one"})
        window._on_week()
        qapp.processEvents()
        labels = [label.text() for label in window.findChildren(QLabel, name) if label.isVisibleTo(window)]
        assert labels and all(text.startswith("Not placed yet") for text in labels), (main, labels)
    # Retro's Notepad says it on the homework's own line, as the mock-up writes it.
    window._layout = sanitize_layout({"main": "retro", "day": "one"})
    window._on_week()
    qapp.processEvents()
    line = window.findChild(QPushButton, "retroNoteWaiting0")
    assert line.isVisibleTo(window) and line.lines[-1].endswith("not placed yet"), line.lines


def test_the_strip_under_next_says_what_it_is(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    session = window.session
    session.add_homework({"id": "essay", "title": "History essay", "estimate_min": 60, "revision": 0,
                          "due": session.week_start[:10] + "T23:59"})
    session.save()
    settled(qapp, window)
    essay = next(block for block in session.blocks if block.get("assignment_id") == "essay")
    session.add_block({**essay, "start": "19:00", "days": [0], "pinned": True})
    session.save()
    settled(qapp, window)
    panel = window.rail
    assert panel.tasks.isVisibleTo(window)
    label = panel.findChild(QLabel, "focusTasksLabel")
    assert label.text() == "Start a focus timer"
    assert label.isVisibleTo(window)
    assert panel.tasks.toolTip() == "Double-click homework to start a focus timer for it."


def test_cancelling_running_late_takes_its_preview_off_the_screen(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = window.session
    thursday = datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=15, minutes=40)
    session.now_ms = lambda: int(thursday.timestamp() * 1000)
    session.add_homework({"id": "essay", "title": "History essay", "estimate_min": 60, "revision": 0,
                          "due": (thursday.date() + timedelta(days=2)).isoformat() + "T23:59"})
    session.save()
    settled(qapp, window)

    def run(dialog: LateDialog) -> int:
        dialog.show()
        dialog.preview_requested.emit()
        wait_until(qapp, lambda: session.late_preview is not None and not session.busy)
        assert window.toast.text().endswith("tasks no longer fit")
        dialog.reject()
        return dialog.result()

    monkeypatch.setattr(LateDialog, "exec", run)
    window._open_late()
    qapp.processEvents()
    assert session.late_preview is None
    assert not window.toast.isVisible()
