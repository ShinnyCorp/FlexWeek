"""A 12-hour clock (0.16 decision 13, review row R25).

Every time on screen is written by one function, `clock_text`, which reads the student's Clock choice
in Settings > This computer. What is saved and sent stays HH:MM. Each formatter is checked on both
clocks, then a walk of the week asks whether "16:00" is still written anywhere once 4:00 PM is chosen.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QTimeEdit, QWidget

from desktop.native import settings
from desktop.native.hours.canvas import Drawn
from desktop.native.hours.geometry import Span
from desktop.native.hours.hand import span_words
from desktop.native.hours.month import MonthChip
from desktop.native.setup import QuarterTime, span_label
from desktop.native.weekmodel import (
    clock_text,
    range_label,
    set_clock_24h,
)
from desktop.native.widgets import BlockDialog, LateDialog, PreviewDialog, Segmented
from desktop.native.window import NativeWindow
from desktop.native.work_windows import WorkWindowsEditor
from desktop.tests.window_support import (  # noqa: F401
    host,
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
    window,
)

TWELVE = False


@pytest.fixture()
def twelve() -> None:
    set_clock_24h(TWELVE)


def test_set_clock_says_whether_it_changed() -> None:
    assert set_clock_24h(True) is False
    assert set_clock_24h(TWELVE) is True
    assert set_clock_24h(TWELVE) is False
    assert set_clock_24h(True) is True


BLOCK = {"id": "soccer", "title": "Soccer practice", "start": "16:00", "duration_min": 90, "days": [3]}


def test_the_hours_words(twelve: None) -> None:
    drawn = Drawn("soccer", "Soccer practice", "sport", False, Span(3, 16 * 60, 17 * 60 + 30), 0, 1)
    # Decision 14 of 0.17: as short as a range still reads.
    assert drawn.detail == "4–5:30 PM · 1 h 30 min"
    assert range_label(11 * 60, 12 * 60 + 30) == "11 AM–12:30 PM"
    assert range_label(23 * 60, 24 * 60) == "11 PM–12 AM"
    assert span_words(Span(3, 16 * 60, 17 * 60 + 30)) == "Thu 4:00 PM–5:30 PM · 1 h 30 min"
    assert MonthChip("b", "Soccer practice", "sport", block_id="soccer", start=16 * 60).words == (
        "4:00 PM Soccer practice"
    )
    assert MonthChip("d", "Essay", "assignments", due=True, due_time="21:00").words == "Due 9:00 PM Essay"


def test_running_late_rows_on_the_12_hour_clock(qapp: QApplication, twelve: None) -> None:  # noqa: F811
    dialog = LateDialog(None, "")
    dialog.show_trace(
        {"moves": [{"block_id": "essay", "from_start": "16:00", "to_start": "17:30"}]}, {"essay": "Essay"}
    )
    assert dialog.changes.item(0).text() == "Essay: from 4:00 PM to 5:30 PM"


def test_setup_summaries_and_its_time_box(qapp: QApplication, twelve: None) -> None:  # noqa: F811
    assert span_label("15:30", 90) == "3:30 PM–5:00 PM"
    box = QuarterTime("16:00")
    assert box.text() == "4:00 PM"
    assert box.hhmm() == "16:00"


def test_editors_show_12_hour_times_and_keep_hh_mm(
    qapp: QApplication,  # noqa: F811
    host: QWidget,  # noqa: F811
    twelve: None,
) -> None:
    editor = BlockDialog(host, {**BLOCK, "kind": "locked", "category": "sport", "days": [3]})
    assert [box.text() for box in editor.findChildren(QTimeEdit)][:2] == ["4:00 PM", "5:30 PM"]
    rows = [{"block": {**BLOCK, "kind": "locked"}, "day": 3, "fixed": True, "checked": True}]
    preview = PreviewDialog(host, "Paste", "", rows, [])
    start = preview.findChild(QComboBox, "previewStart0")
    assert (start.currentText(), start.currentData()) == ("4:00 PM", "16:00")
    start.setCurrentIndex(start.findData("17:15"))
    assert preview.rows()[0]["block"]["start"] == "17:15"
    windows = WorkWindowsEditor([{"days": [0], "start": "15:45", "end": "24:00"}], parent=host)
    row = windows.findChild(QWidget, "workWindowRow")
    assert row.findChild(QComboBox, "workWindowStart").currentText() == "3:45 PM"
    assert row.findChild(QComboBox, "workWindowEnd").currentText() == "12:00 AM"
    assert windows.windows() == [{"days": [0], "start": "15:45", "end": "24:00"}]


def test_settings_offers_the_clock_under_this_computer_and_saves_it(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    dialog = settings.SettingsPage(window, window.session.preferences or {}, window._look, window._layout)
    clock = dialog.findChild(Segmented, "prefClock")
    assert [clock.itemText(index) for index in range(clock.count())] == ["24-hour", "12-hour"]
    assert clock.currentText() == "12-hour", "a new account starts on the 12-hour clock"
    assert dialog.updates()["clock_24h"] is False
    clock.setCurrentIndex(0)
    assert dialog.updates()["clock_24h"] is True
    clock.setCurrentIndex(1)
    assert dialog.updates()["clock_24h"] is False
    dialog.close()


def visible_words(shown: NativeWindow) -> list[str]:
    return [label.text() for label in shown.findChildren(QLabel) if label.isVisibleTo(shown) and label.text()]


def canvas_words(shown: NativeWindow) -> list[str]:
    hours = shown.planner.currentWidget().hours_surfaces()[0]
    return [drawn.detail for track in hours.tracks for drawn, _rect in hours.drawn(track)]


def test_the_week_says_4_pm_everywhere_once_the_12_hour_clock_is_chosen(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    session = window.session
    session.add_block({**BLOCK, "kind": "locked", "category": "sport"})
    session.save()
    settled(qapp, window)
    window.resize(1280, 800)
    session.preferences = {**(session.preferences or {}), "clock_24h": True}
    window._sync_chrome()
    qapp.processEvents()
    assert any("16:00–17:30" in words for words in canvas_words(window))
    session.preferences = {**(session.preferences or {}), "clock_24h": False}
    window._sync_chrome()
    qapp.processEvents()
    drawn = canvas_words(window)
    assert "4–5:30 PM · 1 h 30 min" in drawn
    said = visible_words(window) + drawn
    assert [words for words in said if "16:00" in words or "17:30" in words] == []
    # The saved block is untouched.
    assert session.blocks[0]["start"] == "16:00"
    assert window.session.preferences["clock_24h"] is False


def test_the_clock_saved_to_the_account_is_the_one_the_window_writes(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    for chosen, written in ((False, "4:00 PM"), (True, "16:00")):
        assert window.session.save_preferences({"clock_24h": chosen})
        wait_until(qapp, lambda: not window.session.busy)
        # 12-hour is the default, so the server leaves it out.
        assert window.session.preferences.get("clock_24h", False) is chosen
        assert clock_text(16 * 60) == written
