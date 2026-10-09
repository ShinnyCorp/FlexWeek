"""The hours end with their end label in every design, written the way the clock writes midnight."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None, reason="Desktop dependencies absent"
)

if importlib.util.find_spec("PySide6") is not None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from desktop.native.fonts import load_fonts
    from desktop.native.hours.canvas import BlockPainter
    from desktop.native.hours.classic import ClassicPainter
    from desktop.native.hours.geometry import Axis, LinearTrack
    from desktop.native.layouts.bento import BentoPainter
    from desktop.native.layouts.clay import ClayPainter
    from desktop.native.layouts.mission import MissionPainter
    from desktop.native.layouts.registry import MATCH, tokens_for
    from desktop.native.layouts.retro import RetroPainter, scheme
    from desktop.native.layouts.timeline import TimelinePainter
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import set_clock_24h


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-end-label-test"])


def painters() -> dict[str, BlockPainter]:
    palette = resolved_palette("light-frost", False, None)

    def tokens(design: str) -> dict[str, str]:
        return tokens_for(design, MATCH, palette)

    return {
        "plain": BlockPainter(tokens("clay")),
        "today": ClassicPainter(tokens("clay")),
        "bento": BentoPainter(tokens("bento")),
        "retro": RetroPainter(scheme(tokens("retro"))),
        "clay": ClayPainter(tokens("clay"), full=True),
        "timeline": TimelinePainter(tokens("timeline")),
        "mission": MissionPainter(tokens("mission")),
    }


def labels_of(painting: BlockPainter) -> list[str]:
    """The hour labels a design writes beside one day's hours, 06:00 to the end of the day."""
    words: list[str] = []
    across = isinstance(painting, MissionPainter)
    area = QRectF(160, 60, 800, 36) if across else QRectF(80, 10, 120, 1100)
    axis, first = (Axis.ACROSS, 0) if across else (Axis.DOWN, 6 * 60)
    track = LinearTrack(0, area, axis, first=first, last=24 * 60)

    class Wrote(QPainter):
        def drawText(self, *args) -> None:  # noqa: N802
            words.append(next(arg for arg in reversed(args) if isinstance(arg, str)))
            super().drawText(*args)

    picture = QImage(1200, 1200, QImage.Format.Format_ARGB32)
    paint = Wrote(picture)
    paint.setFont(QFont("Inter", 11))
    try:
        painting.hour_labels(paint, track, 56)
    finally:
        paint.end()
    return words


@pytest.mark.parametrize("twenty_four, midnight", [(True, "24:00"), (False, "12:00 AM")])
@pytest.mark.parametrize("design", ["plain", "today", "bento", "retro", "clay", "timeline", "mission"])
def test_the_last_hour_line_is_labelled_in_every_design_as_the_clock_writes_midnight(
    qapp: QApplication, design: str, twenty_four: bool, midnight: str
) -> None:
    load_fonts()
    set_clock_24h(twenty_four)
    try:
        written = labels_of(painters()[design])
    finally:
        set_clock_24h(True)
    assert midnight in written, (design, written)
