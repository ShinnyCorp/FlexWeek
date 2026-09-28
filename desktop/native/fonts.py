"""The app's own typefaces, shipped beside the code so every computer draws the same app.

Inter for the words, Newsreader for the Serif font's headings and JetBrains Mono for the Mono font
(0.17's knobs), each in four weights, registered with Qt before the window is made. Newsreader and
JetBrains Mono are static cuts of the mock-up's variable fonts (scripts/instance_fonts.py), since
Qt draws a variable font at one weight whatever a stylesheet asks. When the files are missing, as in
a checkout someone trimmed, the font stacks in look.py fall through to the system's faces.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
STYLES = ("Regular", "Medium", "SemiBold", "Bold")
# Each family and the file name its faces start with.
FAMILIES = {"Inter": "Inter", "Newsreader": "Newsreader", "JetBrains Mono": "JetBrainsMono"}
FACES = {family: tuple(f"{stem}-{style}.ttf" for style in STYLES) for family, stem in FAMILIES.items()}
# Inter's figures are proportional; tabular ones keep a column of times from wobbling as they change.
TABULAR = "tnum"


@cache
def load_fonts() -> tuple[str, ...]:
    """Register the bundled faces, once. The families Qt took from them, or none."""
    families: set[str] = set()
    for faces in FACES.values():
        for face in faces:
            ident = QFontDatabase.addApplicationFont(str(FONT_DIR / face))
            if ident >= 0:
                families.update(QFontDatabase.applicationFontFamilies(ident))
    return tuple(sorted(families))


def time_font(base: QFont) -> QFont:
    """`base` with every figure the same width, for a time written where it is read against others."""
    made = QFont(base)
    made.setFeature(QFont.Tag(TABULAR), 1)
    return made
