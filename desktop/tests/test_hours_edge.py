"""A homework block's edge says who chose its time (finding 32 of the 0.17.2 audit): dashed when
FlexWeek planned it and the next plan may move it, solid when the student placed it and no plan will.
Read off the pixels of the shared block painter, so every design that draws its hours through it has it."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from desktop.native.hours.canvas import BlockPainter, Drawn
    from desktop.native.hours.geometry import Span
    from desktop.native.look import category_paint, resolved_palette

RECT = QRectF(20, 20, 140, 100)
PALETTE = resolved_palette("light-frost", False, None, "default")
CATEGORY = "assignments"
LOOKS = {"filled or edged": None, "outlined": {"preset": "default", "knobs": {"blocks": "outline"}}}


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-edge-test"])


def block(*, work: bool = True, **more: bool) -> Drawn:
    return Drawn("essay", "History essay", CATEGORY, work, Span(3, 17 * 60, 18 * 60 + 30), 0, 1, **more)


def top_edge(drawn: Drawn, look: dict | None) -> list[QColor]:
    """The pixels along the block's top edge, clear of its rounded corners and its left strip."""
    image = QImage(200, 140, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    BlockPainter(PALETTE, look).body(painter, RECT, drawn)
    painter.end()
    y = int(RECT.top()) + 1
    return [image.pixelColor(x, y) for x in range(int(RECT.left()) + 16, int(RECT.right()) - 16)]


def share(pixels: list[QColor], wanted: str) -> float:
    """How much of the line is `wanted`, give or take the last bits of each channel."""
    goal = QColor(wanted).getRgb()[:3]
    near = [p for p in pixels if all(abs(a - b) <= 6 for a, b in zip(p.getRgb()[:3], goal, strict=True))]
    return len(near) / len(pixels)


def runs(pixels: list[QColor], wanted: str) -> int:
    """How many times the line changes between `wanted` and anything else: a dash is two changes."""
    goal = QColor(wanted).getRgb()[:3]
    marked = [all(abs(a - b) <= 6 for a, b in zip(p.getRgb()[:3], goal, strict=True)) for p in pixels]
    return sum(one != two for one, two in zip(marked, marked[1:], strict=False))


def mark_colour() -> str:
    mark = category_paint(CATEGORY, PALETTE)[1]
    assert mark
    return mark


@pytest.mark.parametrize("look", LOOKS.values(), ids=LOOKS.keys())
def test_homework_flexweek_planned_has_a_dashed_edge(qapp: QApplication, look: dict | None) -> None:  # noqa: F811
    mark = mark_colour()
    edge = top_edge(block(), look)
    assert 0.25 < share(edge, mark) < 0.9, "dashes of the category's mark"
    assert runs(edge, mark) >= 6, "with gaps between them"


@pytest.mark.parametrize("look", LOOKS.values(), ids=LOOKS.keys())
def test_homework_the_student_placed_has_a_solid_edge(qapp: QApplication, look: dict | None) -> None:  # noqa: F811
    mark = mark_colour()
    edge = top_edge(block(pinned=True), look)
    assert share(edge, mark) > 0.97 and runs(edge, mark) == 0


def test_homework_being_carried_has_no_gaps_in_its_edge(qapp: QApplication) -> None:  # noqa: F811
    """The ring that marks the carried block is solid, as the edge it will have once dropped."""
    edge = top_edge(block(held=True), None)
    assert len({pixel.name() for pixel in edge}) == 1


@pytest.mark.parametrize("drawn", [block(work=False), block(done=True), block(pinned=True, done=True)])
def test_a_fixed_block_and_finished_homework_have_neither_edge(
    qapp: QApplication,  # noqa: F811
    drawn: Drawn,
) -> None:
    assert share(top_edge(drawn, None), mark_colour()) < 0.03
