"""Times and words on blocks: a short block keeps its start with its name."""

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
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from desktop.native.hours.canvas import (
        TEXT_LEFT,
        TEXT_RIGHT,
        TEXT_TOP,
        BlockPainter,
        Drawn,
        Started,
        block_layout,
    )
    from desktop.native.hours.geometry import Span
    from desktop.native.look import resolved_palette
    from desktop.native.weekmodel import clock_label


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    yield QApplication.instance() or QApplication(["flexweek-week-words-test"])


def _fonts(look: dict | None = None) -> tuple[QFont, QFont]:
    painter = BlockPainter(resolved_palette("system", False, look), look)
    return painter.fonts(QFont("Inter", 12))


def _math(
    *, short: bool = False, started: bool = False, large: bool = False
) -> tuple[Drawn, QFont, QFont, QRectF, QRectF]:
    look = {"preset": "default", "knobs": {"text": "large"}} if large else None
    title, small = _fonts(look)
    # A column of the week beside the rail at 1280, 45 minutes at 48 pixels an hour.
    rect = QRectF(0, 0, 128, 45 * 48 / 60 - 3)
    room = rect.adjusted(TEXT_LEFT, TEXT_TOP, -TEXT_RIGHT, -1)
    tight = QRectF(room.left(), 1, room.width(), rect.height() - 1)
    span = Span(1, 17 * 60, 17 * 60 + 45)
    kind = Started if started else Drawn
    drawn = kind(
        "math",
        "Math worksheet",
        "assignments",
        True,
        span,
        0,
        1,
        short=short,
    )
    return drawn, title, small, room, tight


def said(drawn: Drawn, title: QFont, small: QFont, room: QRectF, tight: QRectF) -> list[str]:
    return [line.text for line in block_layout(drawn, title, small, room, tight=tight, book=drawn.work)]


def test_a_short_block_says_its_name_then_its_start(qapp: QApplication) -> None:
    """A 45-minute Math worksheet at 17:00. Today's app, Paper and Timeline wrote the name only;
    Clay and Retro already wrote the start. Every design writes the name, then the start."""
    start = clock_label(17 * 60)
    for short, started, large in (
        (False, False, False),
        (False, False, True),
        (True, False, False),
        (False, True, False),
        (True, True, False),
    ):
        drawn, title, small, room, tight = _math(short=short, started=started, large=large)
        words = said(drawn, title, small, room, tight)
        assert any("Math" in line for line in words), (short, started, large, words)
        assert start in words, (short, started, large, words)
