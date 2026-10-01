"""Lucide's icons (ISC licence, `desktop/assets/icons/LICENSE.txt`), tinted and drawn at any size.

Each file is Lucide's own SVG, drawn in `currentColor` at a 2-unit stroke on a 24-unit grid. An icon
is tinted to the colour asked, usually the text's, and drawn with 0.17's 1.75 stroke (decision 7).
No Unicode glyph stands in for an icon.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QObject, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton

ICON_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons"
STROKE = "1.75"
SIZES = (16, 20)


def names() -> tuple[str, ...]:
    return tuple(sorted(path.stem for path in ICON_DIR.glob("*.svg")))


@cache
def _source(name: str) -> str:
    return (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")


def svg(name: str, colour: str, stroke: str = STROKE, fill: str = "none") -> bytes:
    """The icon's SVG in `colour`, at the system's stroke unless given another, its shapes filled
    with `fill` if given: Retro desktop's icons are drawn white inside, as Windows 98's were."""
    text = _source(name).replace("currentColor", colour).replace('fill="none"', f'fill="{fill}"')
    return text.replace('stroke-width="2"', f'stroke-width="{stroke}"').encode("utf-8")


@cache
def pixmap(
    name: str, colour: str, size: int = 16, ratio: float = 1.0, stroke: str = STROKE, fill: str = "none"
) -> QPixmap:
    """`name` drawn `size` pixels square in `colour`, sharp on a screen of device pixel `ratio`."""
    side = max(1, round(size * ratio))
    made = QPixmap(side, side)
    made.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg(name, colour, stroke, fill)))
    painter = QPainter(made)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, side, side))
    painter.end()
    made.setDevicePixelRatio(ratio)
    return made


def icon(name: str, colour: str, disabled: str | None = None, gap: int = 0) -> QIcon:
    """A QIcon of `name` in `colour` at both of the system's sizes, and in `disabled` when greyed out."""
    made = QIcon()
    for size in SIZES:
        for ratio in (1.0, 2.0):
            made.addPixmap(_with_gap(pixmap(name, colour, size, ratio), gap), QIcon.Mode.Normal)
            if disabled:
                made.addPixmap(_with_gap(pixmap(name, disabled, size, ratio), gap), QIcon.Mode.Disabled)
    return made


def _with_gap(source: QPixmap, gap: int) -> QPixmap:
    if not gap:
        return source
    ratio = source.devicePixelRatioF()
    made = QPixmap(source.width() + round(gap * ratio), source.height())
    made.setDevicePixelRatio(ratio)
    made.fill(Qt.GlobalColor.transparent)
    painter = QPainter(made)
    painter.drawPixmap(0, 0, source)
    painter.end()
    return made


# The dynamic property a tinted button keeps its icon's name in.
NAME = "iconName"


class _Tint(QObject):
    """Draws each tinted button's icon in the colour its stylesheet gives its words, again whenever the
    stylesheet changes, as it does with the look."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            _apply(watched)
        return False


_TINT: _Tint | None = None


def _apply(button: QObject) -> None:
    name = button.property(NAME)
    if not isinstance(button, QAbstractButton) or not name:
        return
    colours = button.palette()
    words = colours.color(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText).name()
    greyed = colours.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText).name()
    gap = button.property("iconGap") or 0
    made = (name, words, greyed, str(gap))
    if button.property("iconTint") != "|".join(made):
        button.setProperty("iconTint", "|".join(made))
        button.setIcon(icon(name, words, greyed, gap))


def tint(button: QAbstractButton, name: str | None, *, gap: int = 0) -> None:
    """Show Lucide's `name` on `button` in its own text colour, which follows the look; None takes the
    icon off, for a button that draws another."""
    global _TINT
    if _TINT is None:
        _TINT = _Tint()
    button.setProperty(NAME, name or "")
    button.setProperty("iconGap", gap)
    if gap:
        button.setIconSize(QSize(16 + gap, 16))
    button.setProperty("iconTint", "")
    button.removeEventFilter(_TINT)
    if name:
        button.installEventFilter(_TINT)
        button.ensurePolished()
        _apply(button)
    else:
        button.setIcon(QIcon())
