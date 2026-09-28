"""The countdown ring the focus screen and One thing's Countdown share (decision 19 of 0.17): what it
draws, read back from its pixels."""

from __future__ import annotations

import importlib.util
import math
import os
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication, QLabel

    from desktop.native.look import resolved_palette
    from desktop.native.ring import CountdownRing, RingColours, arc_angles, ring_colours

ARC, TRACK, NUMBER, MUTED = "#ff0000", "#00ff00", "#0000ff", "#ff00ff"
SIDE = 240


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-ring-test"])


def drawn(ring: CountdownRing) -> QImage:
    image = QImage(SIDE, SIDE, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    ring.render(image)
    return image


def made(qapp: QApplication, left: float, number: str = "", unit: str = "") -> CountdownRing:
    ring = CountdownRing()
    ring.setFixedSize(SIDE, SIDE)
    ring.set_colours(RingColours(ARC, TRACK, NUMBER, MUTED))
    ring.set_left(left)
    ring.set_number(number, unit)
    return ring


def on_ring(ring: CountdownRing, image: QImage, minutes_of_60: float) -> str:
    """The colour on the track's centre line at a clock position, 0 at the top, clockwise."""
    turn = 2 * math.pi * minutes_of_60 / 60
    radius = ring._radius()
    x = SIDE / 2 + radius * math.sin(turn)
    y = SIDE / 2 - radius * math.cos(turn)
    return image.pixelColor(round(x), round(y)).name()


def inked(image: QImage, colour: str, box: tuple[int, int, int, int]) -> int:
    left, top, right, bottom = box
    wanted = QColor(colour)
    return sum(
        1
        for x in range(left, right)
        for y in range(top, bottom)
        if image.pixelColor(x, y) == wanted
    )


def test_the_arc_is_the_time_left_from_the_top_clockwise_on_the_track(qapp: QApplication) -> None:
    ring = made(qapp, 20 / 60)
    image = drawn(ring)
    assert [on_ring(ring, image, minute) for minute in (5, 15)] == [ARC, ARC], "the first 20 minutes"
    assert [on_ring(ring, image, minute) for minute in (30, 45, 55)] == [TRACK] * 3, "the rest is track"
    full = drawn(made(qapp, 1.0))
    assert {on_ring(ring, full, minute) for minute in (5, 20, 35, 50)} == {ARC}, "all left: the whole ring"
    empty = drawn(made(qapp, 0.0))
    assert {on_ring(ring, empty, minute) for minute in (5, 20, 35, 50)} == {TRACK}, "none left: only track"
    assert arc_angles(0.25) == (90 * 16, -90 * 16), "Qt's angles: from twelve o'clock, clockwise"


def test_the_number_is_drawn_in_the_middle_and_its_unit_beside_it_muted(qapp: QApplication) -> None:
    ring = made(qapp, 0.5, "20", "min")
    image = drawn(ring)
    middle = (SIDE // 4, SIDE // 3, 3 * SIDE // 4, 2 * SIDE // 3)
    assert inked(image, NUMBER, middle) > 100, "the number"
    assert inked(image, MUTED, middle) > 10, "the unit"
    assert ring.number() == "20" and ring.accessibleName() == "20 min"
    plain = drawn(made(qapp, 0.5))
    assert inked(plain, NUMBER, middle) == 0, "no number, nothing in the middle"


def test_a_long_number_shrinks_to_stay_inside_the_ring(qapp: QApplication) -> None:
    ring = made(qapp, 0.5, "124:59")
    image = drawn(ring)
    inner = ring._inner()
    columns = [x for x in range(SIDE) if any(image.pixelColor(x, y) == QColor(NUMBER) for y in range(SIDE))]
    assert columns, "the number drew nothing"
    assert SIDE / 2 - inner < columns[0] and columns[-1] < SIDE / 2 + inner


def test_the_number_leaves_the_lines_above_and_below_it_their_room(qapp: QApplication) -> None:
    """One thing's two-line title over the number in a small ring pushed the lines out over the
    track. The number now takes only the height the owner's lines leave, and all of it stays inside."""
    ring = made(qapp, 0.5, "20", "min")
    title, when = QLabel("Soccer practice\nand the drive"), QLabel("16:00–17:30")
    title.setStyleSheet("font-size: 28pt;")
    ring.above.addWidget(title)
    ring.below.addWidget(when)
    for line in (title, when):
        line.ensurePolished()
    ring.lines_changed()
    ring.layout().activate()
    image = drawn(ring)
    rows = [y for y in range(SIDE) if any(image.pixelColor(x, y) == QColor(NUMBER) for x in range(SIDE))]
    assert rows, "the number drew nothing"
    assert title.geometry().bottom() < rows[0] and rows[-1] < when.geometry().top()
    top = (SIDE - ring.inside().height()) / 2
    assert top - 1 <= title.geometry().top() and when.geometry().bottom() <= SIDE - top + 1, "inside"
    assert [line.height() >= line.sizeHint().height() for line in (title, when)] == [True, True]


def test_the_scale_draws_marks_outside_the_track(qapp: QApplication) -> None:
    ring = made(qapp, 0.5)
    bare = drawn(ring)
    ring.set_scale(12, ("0", "15", "30", "45"))
    scaled = drawn(ring)
    outside = (SIDE // 2 - 3, 0, SIDE // 2 + 3, round(SIDE / 2 - ring._radius() - ring._stroke() / 2) - 1)
    assert inked(bare, MUTED, outside) == 0
    assert inked(scaled, MUTED, outside) > 0, "the mark at the top"


def test_the_ring_takes_the_accent_and_a_track_from_the_look() -> None:
    light = resolved_palette("light-frost", False, None)
    colours = ring_colours(light)
    assert (colours.arc, colours.number, colours.muted) == (light["accent"], light["text"], light["muted"])
    assert colours.track not in {light["window"], light["text"], light["accent"]}
    contrast = resolved_palette("system", False, {"preset": "high-contrast", "knobs": {}})
    assert ring_colours(contrast).arc == "#ffd400"
