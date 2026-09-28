"""Week's side: the Next line, the focus list and Not placed yet beside the hours, as Day has; folded
into one line on a narrow window, where blocks say their names only; and the window's floor."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QPushButton

from desktop.native.calendar import sunday_due
from desktop.native.hours import canvas as canvas_module
from desktop.native.hours.canvas import BlockPainter, Drawn
from desktop.native.hours.classic import SIDE_PX
from desktop.native.hours.geometry import Span
from desktop.native.layouts.registry import sanitize_layout
from desktop.native.window import WINDOW_MIN_WIDTH, NativeWindow
from desktop.tests.window_support import (  # noqa: F401
    qapp,
    server,
    settled,
    signed_out,
    wait_until,
    window,
)


def seeded(qapp: QApplication, window: NativeWindow) -> None:  # noqa: F811
    """Thursday 15:40: Soccer practice next, the essay placed at 19:00, the worksheet with no time."""
    session = window.session
    thursday = datetime.fromisoformat(session.week_start) + timedelta(days=3, hours=15, minutes=40)
    session.now_ms = lambda: int(thursday.timestamp() * 1000)
    session.add_block({"id": "soccer", "title": "Soccer practice", "kind": "locked", "category": "sport",
                       "start": "16:00", "duration_min": 90, "days": [1, 3]})
    due = sunday_due(session.week_start)
    for key, title in (("essay", "History essay"), ("math", "Math worksheet")):
        session.add_homework({"id": key, "title": title, "due": due, "estimate_min": 60, "revision": 0})
    session.save()
    settled(qapp, window)
    essay = next(block for block in session.blocks if block.get("assignment_id") == "essay")
    session.add_block({**essay, "start": "19:00", "days": [3], "pinned": True})
    session.save()
    settled(qapp, window)
    window._layout = sanitize_layout({"main": "classic", "day": "one"})
    window._apply_appearance()
    session.set_view("week")
    window.resize(1280, 860)
    window._on_week()
    for _ in range(5):
        qapp.processEvents()


def test_week_keeps_next_the_focus_list_and_not_placed_yet_beside_its_hours(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """They stacked above Week's grid and took a quarter of a laptop's window before the day names."""
    seeded(qapp, window)
    side = window.week_table.side
    assert window.planner.currentWidget() is window.week_table
    assert side.isVisible() and not side.folded and side.width() == SIDE_PX
    hours = window.week_table.scroll
    assert side.geometry().left() >= hours.geometry().right(), "the side is to the right of the hours"
    assert side.next.isVisible() and side.next.text() == window.session.now_next_text()
    assert side.next.text().startswith("Next: Soccer practice")
    assert [side.tasks.item(row).text().split("  ")[0] for row in range(side.tasks.count())] == [
        "History essay"
    ]
    chips = [chip for chip in side.findChildren(QPushButton) if chip.property("tray") and chip.isVisible()]
    assert [chip.text() for chip in chips] == ["Math worksheet · 1 h"]
    # Above the hours only the top bar: no Next line, no focus list, no strip of chips.
    assert not window.focus_panel.isVisible()
    bar_bottom = window.solve_button.mapTo(window, QPoint(0, window.solve_button.height())).y()
    assert window.planner.mapTo(window, QPoint(0, 0)).y() - bar_bottom < 32


def test_high_contrast_cuts_no_chip_and_scrolls_the_focus_list_neither_way(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    """Switched to High contrast with the side already up, its larger text and thicker borders ran the
    chips' words off their edge and gave the focus list a sideways scroll bar and a row short."""
    from desktop.native.look import sanitize_look

    seeded(qapp, window)
    session = window.session
    session.add_homework(
        {"id": "poster", "title": "Science poster for the fair", "due": sunday_due(session.week_start),
         "estimate_min": 90, "revision": 0}
    )
    session.save()
    settled(qapp, window)
    window._look = sanitize_look({"preset": "high-contrast", "knobs": {}})
    window._apply_appearance()
    for _ in range(5):
        qapp.processEvents()
    side = window.week_table.side
    chips = [chip for chip in side.findChildren(QPushButton) if chip.property("tray") and chip.isVisible()]
    assert len(chips) == 2 and any("…" in chip.text() for chip in chips)
    for chip in chips:
        assert QPushButton.sizeHint(chip).width() <= chip.width(), chip.text()
    tasks = side.tasks
    assert tasks.count() and not tasks.horizontalScrollBar().isVisible()
    assert not tasks.verticalScrollBar().isVisible()
    assert tasks.viewport().height() >= tasks.count() * tasks.sizeHintForRow(0)


def chip_row(side) -> bool:
    """The folded line and every chip on one row."""
    chips = [chip for chip in side.findChildren(QPushButton) if chip.property("tray")]
    return bool(chips) and all(chip.geometry().top() == side.line.geometry().top() for chip in chips)


def test_a_narrow_window_folds_the_side_into_one_line_and_blocks_say_their_names(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    seeded(qapp, window)
    side, hours = window.week_table.side, window.week_table.scroll
    window.resize(1100, 860)
    for _ in range(5):
        qapp.processEvents()
    assert side.folded and window.week_table.hours.short_words
    assert side.geometry().bottom() < hours.geometry().top(), "the line sits above the hours"
    assert side.height() < 80 and chip_row(side), "one slim line"
    assert side.line.text() == f"{window.session.now_next_text()} · Not placed yet: 1"
    assert not side.tasks.isVisible() and not side.next.isVisible()
    chip = next(chip for chip in side.findChildren(QPushButton) if chip.property("tray"))
    assert chip.isVisible() and chip.text() == "Math worksheet · 1 h"
    frame = window.rect()
    assert frame.contains(chip.mapTo(window, chip.rect().bottomRight()))
    window.resize(1280, 860)
    for _ in range(5):
        qapp.processEvents()
    assert not side.folded and not window.week_table.hours.short_words
    assert side.geometry().left() >= hours.geometry().right() and chip.isVisible()


def test_the_window_is_never_narrower_than_800(
    qapp: QApplication,  # noqa: F811
    window: NativeWindow,  # noqa: F811
) -> None:
    assert WINDOW_MIN_WIDTH == 800
    window.resize(650, 720)
    for _ in range(3):
        qapp.processEvents()
    assert window.width() == 800


def written(monkeypatch: pytest.MonkeyPatch, drawn: Drawn, height: float) -> list[str]:
    """What the block's words put in lines, painted into a column 96 pixels wide."""
    said: list[str] = []
    real = canvas_module._write_lines

    def record(painter: QPainter, text: str, font, room: QRectF) -> None:
        said.append(text)
        real(painter, text, font, room)

    monkeypatch.setattr(canvas_module, "_write_lines", record)
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    rect = QRectF(0, 0, 96, height)
    BlockPainter({"error": "#dc2626", "accent": "#2563eb"}).words(painter, rect, drawn, QColor("#000"), rect)
    painter.end()
    return said


def test_a_short_block_word_gives_its_name_the_room_its_times_took(
    qapp: QApplication,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At 800 pixels "Soccer practice" read "Soccer …" above its times. Short of room its name is
    whole, over two lines, and the times are left to its editor."""
    soccer = Drawn("soccer", "Soccer practice", "sport", False, Span(3, 16 * 60, 17 * 60 + 30), 0, 1)
    assert any("16:00" in text for text in written(monkeypatch, soccer, 72))
    short = Drawn(**{**soccer.__dict__, "short": True})
    assert written(monkeypatch, short, 72) == ["Soccer practice"]
