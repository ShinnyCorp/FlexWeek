"""Lucide's icons (ISC licence, `desktop/assets/icons/LICENSE.txt`), tinted and drawn at any size.

Each file is Lucide's own SVG, drawn in `currentColor` at a 2-unit stroke on a 24-unit grid. An icon
is tinted to the colour asked, usually the text's, and drawn with 0.17's 1.75 stroke (decision 7).
No Unicode glyph stands in for an icon.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons"
STROKE = "1.75"
SIZES = (16, 20)


def names() -> tuple[str, ...]:
    return tuple(sorted(path.stem for path in ICON_DIR.glob("*.svg")))


@cache
def _source(name: str) -> str:
    return (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")


def svg(name: str, colour: str) -> bytes:
    """The icon's SVG in `colour`, at the system's stroke."""
    text = _source(name).replace("currentColor", colour)
    return text.replace('stroke-width="2"', f'stroke-width="{STROKE}"').encode("utf-8")


@cache
def pixmap(name: str, colour: str, size: int = 16, ratio: float = 1.0) -> QPixmap:
    """`name` drawn `size` pixels square in `colour`, sharp on a screen of device pixel `ratio`."""
    side = max(1, round(size * ratio))
    made = QPixmap(side, side)
    made.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg(name, colour)))
    painter = QPainter(made)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, side, side))
    painter.end()
    made.setDevicePixelRatio(ratio)
    return made


def icon(name: str, colour: str, disabled: str | None = None) -> QIcon:
    """A QIcon of `name` in `colour` at both of the system's sizes, and in `disabled` when greyed out."""
    made = QIcon()
    for size in SIZES:
        for ratio in (1.0, 2.0):
            made.addPixmap(pixmap(name, colour, size, ratio), QIcon.Mode.Normal)
            if disabled:
                made.addPixmap(pixmap(name, disabled, size, ratio), QIcon.Mode.Disabled)
    return made
