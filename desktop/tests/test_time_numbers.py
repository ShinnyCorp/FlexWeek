"""Dates, recovery codes and planner times remain readable at the minimum window size."""

from __future__ import annotations

import importlib.util

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


def test_plan_is_never_cut_when_the_bar_wraps(qapp: QApplication, window: NativeWindow) -> None:
    """#83: one order at every width, so a wrapped bar says "Plan" (Jonathan, 2026-10-04); whatever
    it says is whole, and a wide window gives the words back."""
    for width in (1280, 1000, 810, 1280):
        window.resize(width, 800)
        for _ in range(4):
            qapp.processEvents()
        assert window.solve_button.text() in ("Plan my homework", "Plan homework", "Plan")
        assert window.solve_button.fontMetrics().horizontalAdvance(window.solve_button.text()) < (
            window.solve_button.width() - window.solve_button.iconSize().width()
        )
    assert window.solve_button.text() == "Plan my homework", "1280 pixels has room for the words"


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


def crossed_by_now(canvas, block_id: str, day: int) -> tuple[int, list[bool]]:
    """A block painted without the time now, then with it on the line of pixels through the most of
    the block's words: how many pixels of the block's plain colour the line changed, and, along the
    line where it is at full strength, whether each pixel of a word still differs from the line.
    The hours are painted whole and the canvas holds the clock, so the line is all that differs."""
    from collections import Counter

    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor

    from desktop.native.hours.geometry import Axis

    track = canvas.track_for(day)
    drawn, rect = next((item, rect) for item, rect in canvas.drawn(track) if item.block_id == block_id)
    # Inside the block's edge and its category's bar, where there is only its colour and its words.
    box = track.transform.mapRect(rect).toRect().adjusted(10, 4, -4, -4)
    down = track.axis is Axis.DOWN
    lines = range(box.top(), box.bottom() + 1) if down else range(box.left(), box.right() + 1)
    along = range(box.left(), box.right() + 1) if down else range(box.top(), box.bottom() + 1)

    def row(image, line: int) -> list[int]:
        return [image.pixel(*((at, line) if down else (line, at))) for at in along]

    canvas.set_week(canvas.occurrences, day, None)
    bare = canvas.grab().toImage()
    plain = Counter(pixel for line in lines for pixel in row(bare, line)).most_common(1)[0][0]
    through = max(lines, key=lambda line: sum(pixel != plain for pixel in row(bare, line)))
    middle = box.center()
    point = QPointF(middle.x(), through) if down else QPointF(through, middle.y())
    minute = round(track.minute_at(point))
    assert drawn.span.start < minute < drawn.span.end
    canvas.set_week(canvas.occurrences, day, minute)
    lit = canvas.grab().toImage()

    def pairs(line: int) -> list[tuple[int, int]]:
        """Each pixel along this line of them, without the time now and with it."""
        return list(zip(row(bare, line), row(lit, line), strict=True))

    def strength(line: int) -> int:
        """How far the now line's own colour on this line of pixels is from the block's."""
        changed = [new for old, new in pairs(line) if old == plain and new != old]
        if not changed:
            return 0
        colour, fill = QColor(Counter(changed).most_common(1)[0][0]), QColor(plain)
        return sum(abs(a - b) for a, b in zip(colour.getRgb()[:3], fill.getRgb()[:3], strict=True))

    shown = sum(old == plain and new != old for line in lines for old, new in pairs(line))
    strongest = pairs(max(lines, key=strength))
    line_colour = Counter(new for old, new in strongest if old == plain).most_common(1)[0][0]
    return shown, [new != line_colour for old, new in strongest if old != plain]


@pytest.mark.parametrize("design", DESIGNS)
def test_now_crosses_a_block_over_its_colour_and_under_its_words(
    qapp: QApplication, window: NativeWindow, design: str,
) -> None:
    """During School the line for now shows on School, so a student sees how far into it they are,
    and School's words are written over the line. Painted before the block the line was hidden from
    08:00 to 14:30; painted after it, it ran through "School"."""
    window._layout = sanitize_layout({"main": design})
    window._apply_appearance()
    window._on_week()
    for _ in range(4):
        qapp.processEvents()
    shown, words = crossed_by_now(hours(window).canvas, "school", 3)
    assert shown >= 10, "the line for now is hidden by the block"
    assert len(words) >= 3, "the line does not cross the block's words"
    assert sum(words) >= len(words) / 2, (
        f"the line for now is drawn over the block's words: {sum(words)} of {len(words)} pixels of them show"
    )


SHARED_NOW = ("classic", "timeline", "bento", "retro", "clay")


@pytest.mark.parametrize("design", SHARED_NOW)
def test_the_now_line_runs_under_a_blocks_words_without_a_gap(
    qapp: QApplication, window: NativeWindow, monkeypatch: pytest.MonkeyPatch, design: str,
) -> None:
    """With now on the row of School's name, the line runs through the block under the words and
    icon, with no 3 px hole round them. Drawn over the name it read as crossing it out; a gap round
    the words read as the line being cut. On a row of School with no words the line is whole from
    one side of the block to the other. Mission still clips its own ticks (lane 3)."""
    from collections import Counter

    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QFontMetricsF, QPainter

    from desktop.native.hours import canvas as canvas_module
    from desktop.native.hours.geometry import Axis

    laid: list[tuple[str, QRectF]] = []

    class Laid(QPainter):
        """Where the hours write words and draw icons, in the canvas's own pixels."""

        def drawText(self, *args):  # noqa: N802
            if isinstance(args[0], QRectF) and isinstance(args[-1], str):
                flags = getattr(args[1], "value", args[1])
                ink = QFontMetricsF(self.font()).boundingRect(args[0], int(flags), args[-1])
                laid.append((args[-1], self.transform().mapRect(ink)))
            return super().drawText(*args)

        def drawPixmap(self, *args):  # noqa: N802
            if isinstance(args[0], QPointF):
                size = args[1].deviceIndependentSize()
                laid.append(("", self.transform().mapRect(QRectF(args[0], size))))
            return super().drawPixmap(*args)

    monkeypatch.setattr(canvas_module, "QPainter", Laid)
    window._layout = sanitize_layout({"main": design})
    window._apply_appearance()
    window._on_week()
    for _ in range(4):
        qapp.processEvents()
    canvas, day = hours(window).canvas, 3
    track = canvas.track_for(day)
    rect = next(rect for item, rect in canvas.drawn(track) if item.block_id == "school")
    block = track.transform.mapRect(rect)
    # Inside the block's own edge and rounded corners.
    inside = block.adjusted(6, 4, -4, -4).toRect()
    canvas.set_week(canvas.occurrences, day, None)
    laid.clear()
    bare = canvas.grab().toImage()
    words = [(text, box) for text, box in laid if block.contains(box.center())]
    name = next(box for text, box in words if text == "School")
    assert any(text == "" for text, _box in words), "School has no icon under the line"

    def lit_at(point: QPointF):
        minute = round(track.minute_at(point))
        canvas.set_week(canvas.occurrences, day, minute)
        return canvas.grab().toImage()

    down = track.axis is Axis.DOWN
    lit = lit_at(name.center())
    line = round(name.center().y() if down else name.center().x())
    along = range(inside.left(), inside.right() + 1) if down else range(inside.top(), inside.bottom() + 1)

    def sample(image, pos: int, shift: int = 0) -> int:
        y = line + shift
        return image.pixel(*((pos, y) if down else (y, pos)))

    plain = Counter(sample(bare, pos) for pos in along).most_common(1)[0][0]
    holes = [
        pos
        for pos in along
        if sample(bare, pos) == plain
        and all(sample(lit, pos, shift) == sample(bare, pos, shift) for shift in range(-3, 4))
    ]
    assert holes == [], "the now line stops short of the block's words"
    ink = [pos for pos in along if sample(bare, pos) != plain]
    assert ink, "no words on the now line"
    changed = [
        sample(lit, pos) for pos in along if sample(bare, pos) == plain and sample(lit, pos) != plain
    ]
    assert changed, "the now line does not show on the block"
    line_colour = Counter(changed).most_common(1)[0][0]
    assert sum(sample(lit, pos) != line_colour for pos in ink) >= len(ink) / 2, (
        "the now line is drawn over the words"
    )
    taken = [box.adjusted(-8, -8, 8, 8) for _text, box in words]
    first, last = (inside.top(), inside.bottom()) if down else (inside.left(), inside.right())
    clear = next(
        at for at in range(last - 4, first, -1)
        if not any((box.top() <= at <= box.bottom()) if down else (box.left() <= at <= box.right())
                   for box in taken)
    )
    middle = inside.center()
    lit = lit_at(QPointF(middle.x(), clear) if down else QPointF(clear, middle.y()))
    across = range(inside.left(), inside.right() + 1) if down else range(inside.top(), inside.bottom() + 1)
    gaps = [
        at for at in across
        if not any(
            lit.pixel(*((at, clear + d) if down else (clear + d, at)))
            != bare.pixel(*((at, clear + d) if down else (clear + d, at)))
            for d in range(-3, 4)
        )
    ]
    assert gaps == [], "the line for now is broken where the block has no words"


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


def test_clays_now_pill_stays_outside_the_blocks(qapp: QApplication) -> None:
    """Timeline's pill has its own test over every day (test_layout_timeline.py)."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont, QImage, QPainter

    from desktop.native.hours.geometry import LinearTrack
    from desktop.native.layouts.clay import ClayPainter
    from desktop.native.layouts.registry import MATCH, tokens_for
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import set_clock_24h

    painting = ClayPainter(tokens_for("clay", MATCH, resolved_palette("light-frost", False, None)), full=True)
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
