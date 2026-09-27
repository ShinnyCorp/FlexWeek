"""The app's own typeface, Inter, shipped beside the code so every computer draws the same app.

The four weights are registered with Qt before the window is made. When the files are missing, as in
a checkout someone trimmed, the font stacks in look.py fall through to the system's sans.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

from desktop.native.tokens import text_knob, type_pt

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FACES = ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf")
# Inter's figures are proportional; tabular ones keep a column of times from wobbling as they change.
TABULAR = "tnum"


@cache
def load_fonts() -> tuple[str, ...]:
    """Register the bundled faces, once. The families Qt took from them, or none."""
    families: set[str] = set()
    for face in FACES:
        ident = QFontDatabase.addApplicationFont(str(FONT_DIR / face))
        if ident >= 0:
            families.update(QFontDatabase.applicationFontFamilies(ident))
    return tuple(sorted(families))


def time_font(base: QFont) -> QFont:
    """`base` with every figure the same width, for a time written where it is read against others."""
    made = QFont(base)
    made.setFeature(QFont.Tag(TABULAR), 1)
    return made


def weighted(base: QFont, weight: int) -> QFont:
    """`base` at one of the type scale's weights (tokens.WEIGHT_*)."""
    made = QFont(base)
    made.setWeight(QFont.Weight(weight))
    return made


def caption(base: QFont) -> QFont:
    """The type scale's caption beside `base`, the body size at some Text knob. A design that sets
    its own size keeps its own proportion until its lane redraws it."""
    made = QFont(base)
    knob = text_knob(base.pointSizeF())
    made.setPointSizeF(type_pt("caption", knob) if knob else max(base.pointSizeF() * 0.86, 7))
    return made
