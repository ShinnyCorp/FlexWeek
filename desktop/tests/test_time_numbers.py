"""Dates, recovery codes and planner times remain readable at the minimum window size."""

from __future__ import annotations

import importlib.util
from datetime import datetime

import pytest

from desktop.tests.test_hours_open import DESIGNS

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtWidgets import QApplication, QPushButton

    from desktop.native.layouts.registry import sanitize_layout
    from desktop.native.look import sanitize_look
    from desktop.native.window import NativeWindow
    from desktop.tests.test_hours_open import hours, wait_until
    from desktop.tests.test_hours_open import qapp as qapp
    from desktop.tests.test_hours_open import window as window


@pytest.mark.parametrize("design", DESIGNS)
@pytest.mark.parametrize("preset", ["default", "paper"])
def test_the_week_title_uses_the_same_short_date_at_every_width(
    qapp: QApplication, window: NativeWindow, design: str, preset: str,
) -> None:
    session = window.session
    session.load_week("2026-09-28")
    wait_until(qapp, lambda: not session.busy)
    window._layout = sanitize_layout({"main": design})
    window._look = sanitize_look({"preset": preset})
    window._apply_appearance()
    window._on_week()
    for width in (1280, 1000, 810):
        window.resize(width, 800)
        for _ in range(4):
            qapp.processEvents()
        assert window.week_title.text() == "28 Sep – 4 Oct"
        assert window.week_title.full_text() == "28 Sep – 4 Oct"
        if design == "retro":
            assert window._views["retro"]._windows["week"].bar.text() == "Week.exe - 28 Sep – 4 Oct"


def test_recovery_codes_use_the_bundled_mono_face(window: NativeWindow) -> None:
    assert window.recovery_list.font().family() == "JetBrains Mono"


def test_plan_keeps_its_words_when_the_bar_wraps(qapp: QApplication, window: NativeWindow) -> None:
    for width in (1280, 1000, 810, 1280):
        window.resize(width, 800)
        for _ in range(4):
            qapp.processEvents()
        assert window.solve_button.text() == "Plan my homework"
        assert window.solve_button.fontMetrics().horizontalAdvance(window.solve_button.text()) < (
            window.solve_button.width() - window.solve_button.iconSize().width()
        )


def test_narrow_week_blocks_still_include_their_times(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from desktop.native.hours import canvas
    from desktop.native.weekmodel import clock_label

    window._layout = sanitize_layout({"main": "classic"})
    window._look = sanitize_look({"preset": "default"})
    window._apply_appearance()
    window._on_week()
    window.findChild(QPushButton, "viewWeek").click()
    written: list[str] = []
    original = canvas._paint_layout

    def record(painter, lay, *args, **kwargs) -> None:
        written.extend(line.text for line in lay)
        original(painter, lay, *args, **kwargs)

    monkeypatch.setattr(canvas, "_paint_layout", record)
    for width in (1280, 1000, 810):
        window.resize(width, 800)
        for _ in range(4):
            qapp.processEvents()
        assert window.width() == width
        scroll = hours(window)
        assert scroll.canvas is window.week_table.hours
        scroll.canvas.reveal(0, 480, 540)
        qapp.processEvents()
        written.clear()
        assert not scroll.canvas.grab().isNull()
        assert any(words.startswith(clock_label(480)) for words in written), (width, written)


@pytest.mark.parametrize("design", ["classic", "timeline", "clay"])
def test_now_is_painted_before_the_block_words(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch, design: str,
) -> None:
    session = window.session
    held = datetime.fromisoformat(session.week_start).replace(hour=10, minute=20)
    session.now_ms = lambda: int(held.timestamp() * 1000)
    window._layout = sanitize_layout({"main": design})
    window._apply_appearance()
    window._on_week()
    for _ in range(4):
        qapp.processEvents()
    scroll = hours(window)
    wrote: list[str] = []
    painter = scroll.canvas.painter
    block, now = painter.block, painter.now

    def draw_block(*args: object) -> None:
        if args[2].span.day == 0 and args[2].block_id == "school":
            wrote.append("school")
        block(*args)

    def draw_now(*args: object) -> None:
        wrote.append("now")
        now(*args)

    monkeypatch.setattr(painter, "block", draw_block)
    monkeypatch.setattr(painter, "now", draw_now)
    assert not scroll.canvas.grab().isNull()
    assert "school" in wrote and "now" in wrote
    assert wrote.index("now") < wrote.index("school")


def test_day_names_its_date_once(qapp: QApplication, window: NativeWindow) -> None:
    window.findChild(QPushButton, "viewDay").click()
    wait_until(qapp, lambda: not window.session.busy)
    assert window.day_view.agenda.heading.text() == "Agenda"
    assert window.day_view.name.text() == "Hours"


def test_my_day_labels_do_not_have_ticks_that_read_as_minus_signs(
    qapp: QApplication, window: NativeWindow,
) -> None:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPainter, QPixmap

    from desktop.native.layouts.dial import DialFace

    class Lines(QPainter):
        count = 0

        def drawLine(self, *args: object) -> None:  # noqa: N802
            self.count += 1
            super().drawLine(*args)

    dial = DialFace(0, False, parent=window)
    dial.set_day((), 0, window._scene_for("dial").tokens, 10 * 60, 1.0)
    picture = QPixmap(500, 500)
    painted = Lines(picture)
    try:
        dial._paint_ticks(painted, QPointF(250, 250), 100)
        assert painted.count == 12
    finally:
        painted.end()


def test_my_day_actions_leave_room_after_their_icons(qapp: QApplication, window: NativeWindow) -> None:
    session = window.session
    session.add_homework({"id": "essay", "title": "Essay", "due": "2026-10-04T23:59",
                          "estimate_min": 60, "revision": 0})
    block = next(item for item in session.blocks if item.get("assignment_id") == "essay")
    session.place_session(block["id"], 3, 19 * 60)
    session.save()
    wait_until(qapp, lambda: not session.busy and not session.dirty)
    window.findChild(QPushButton, "viewMyDay").click()
    for _ in range(4):
        qapp.processEvents()
    late = window.findChild(QPushButton, "dialLate")
    assert late is not None and late.isVisible()
    assert late.iconSize().width() >= late.iconSize().height() + 4
    painted = late.icon().pixmap(late.iconSize()).toImage()
    assert all(painted.pixelColor(x, y).alpha() == 0
               for x in range(painted.width() - 4, painted.width()) for y in range(painted.height()))


@pytest.mark.parametrize("large", [False, True])
def test_day_agenda_times_fit_in_twelve_hour_format(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch, large: bool,
) -> None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFontMetricsF, QPainter

    from desktop.native.hours import classic
    from desktop.native.weekmodel import clock_label, set_clock_24h

    window._look = sanitize_look({"knobs": {"text": "large" if large else "normal"}})
    window._apply_appearance()
    window.findChild(QPushButton, "viewDay").click()
    window.resize(810, 800)
    wait_until(qapp, lambda: not window.session.busy)
    set_clock_24h(False)
    checked: list[tuple[str, float, float]] = []
    wanted = {clock_label(value) for item in window.day_view.agenda.list.items
              for value in (item.start, item.end)}

    class Text(QPainter):
        def drawText(self, *args):  # noqa: N802
            if len(args) == 3 and isinstance(args[0], QRectF) and args[2] in wanted:
                checked.append((args[2], QFontMetricsF(self.font()).horizontalAdvance(args[2]),
                                args[0].width()))
            return super().drawText(*args)

    monkeypatch.setattr(classic, "QPainter", Text)
    try:
        window.day_view.agenda.list.grab()
        assert checked
        assert all(width <= room for _words, width, room in checked), checked
    finally:
        set_clock_24h(True)


@pytest.mark.parametrize("design", ["timeline", "clay"])
def test_the_now_pill_stays_outside_the_blocks(qapp: QApplication, design: str) -> None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont, QImage, QPainter

    from desktop.native.hours.geometry import LinearTrack
    from desktop.native.layouts.clay import ClayPainter
    from desktop.native.layouts.registry import MATCH, tokens_for
    from desktop.native.layouts.timeline import TimelinePainter
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import set_clock_24h

    tokens = tokens_for(design, MATCH, resolved_palette("light-frost", False, None))
    painting = TimelinePainter(tokens) if design == "timeline" else ClayPainter(tokens, full=True)
    boxes: list[QRectF] = []

    class Pills(QPainter):
        def drawRoundedRect(self, box, *args):  # noqa: N802
            boxes.append(QRectF(box))
            return super().drawRoundedRect(box, *args)

    track = LinearTrack(0, QRectF(120, 0, 600, 900))
    picture = QImage(800, 1000, QImage.Format.Format_ARGB32)
    paint = Pills(picture)
    paint.setFont(QFont("Inter", 12))
    set_clock_24h(True)
    try:
        painting.now(paint, track, 620)
        assert boxes
        assert all(box.right() <= track.area.left() for box in boxes), boxes
    finally:
        paint.end()


def test_clays_now_pill_takes_the_place_of_the_hour_label_under_it(qapp: QApplication) -> None:
    """The pill left of the hours lies where their labels are. At 10:20 on hours 40 pixels each, the
    10:00 label was written and the pill drawn over most of it; 11:00, clear of the pill, stays."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont, QImage, QPainter

    from desktop.native.hours.geometry import LinearTrack
    from desktop.native.layouts.clay import ClayPainter
    from desktop.native.layouts.registry import MATCH, tokens_for
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import set_clock_24h

    painting = ClayPainter(tokens_for("clay", MATCH, resolved_palette("light-frost", False, None)), full=True)
    painting.now_minute = 10 * 60 + 20
    pills: list[QRectF] = []
    labels: dict[str, QRectF] = {}

    class Marks(QPainter):
        def drawRoundedRect(self, box, *args):  # noqa: N802
            pills.append(QRectF(box))
            return super().drawRoundedRect(box, *args)

        def drawText(self, box, flags, words):  # noqa: N802
            labels[words] = QRectF(box)
            return super().drawText(box, flags, words)

    track = LinearTrack(0, QRectF(120, 20, 600, 480), first=8 * 60, last=20 * 60)
    picture = QImage(800, 520, QImage.Format.Format_ARGB32)
    paint = Marks(picture)
    paint.setFont(QFont("Inter", 12))
    set_clock_24h(True)
    try:
        painting.hour_labels(paint, track, 56)
        hours = dict(labels)
        painting.now(paint, track, painting.now_minute)
    finally:
        paint.end()
    assert len(pills) == 1 and "11:00" in hours
    under = [words for words, box in hours.items() if box.intersects(pills[0])]
    assert not under, f"the pill at {pills[0]} is drawn over {under}"


def test_running_school_has_no_agenda_now_row(qapp: QApplication, window: NativeWindow) -> None:
    from desktop.native.hours.classic import ClassicDay

    view = ClassicDay(window.hand, window)
    view.set_day(window.week_table._shown[0], 0, 0, 620)
    for _ in range(4):
        qapp.processEvents()
    assert all(row.item is not None for row in view.agenda.list.rows)
    school = next(row.item for row in view.agenda.list.rows if row.item.block_id == "school")
    assert school.start < 620 < school.end
    assert view.hours.now_min == 620
