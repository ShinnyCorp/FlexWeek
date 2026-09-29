"""Make the bundled Newsreader, JetBrains Mono, Pixelify Sans and VT323 faces from the mock-up's fonts.

    python3 scripts/instance_fonts.py [family ...]   # needs fontTools (pip install fonttools); not the app's

The mock-up draws with the variable fonts in `docs/mockups/look-017/fonts/`. Qt registers a variable
font as one Regular face and ignores a stylesheet's `font-weight` on it, so a heading at 600 came out
at 400. The app bundles each weight as its own static face instead, named as Inter's four are, and
Qt picks the weight a stylesheet asks for. Every font here is under the OFL with no reserved name.

Pixelify Sans draws its 5 as an S and, at the caption size, its 2 as an 8, so Retro desktop's faces
take their figures and colon from VT323, scaled to Pixelify's cap height, as the mock-up's "Retro UI"
face does. VT323 is one static weight already and is copied as it is. Name families to make only
those; with none, all four are made.
"""

from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "mockups" / "look-017" / "fonts"
TARGET = ROOT / "desktop" / "assets" / "fonts"
WEIGHTS = {"Regular": 400, "Medium": 500, "SemiBold": 600, "Bold": 700}
# Newsreader's optical size: its text cut for the body, a display cut for headings, as a browser
# picks for 13 and 20 point type.
OPTICAL = {"Regular": 18, "Medium": 18, "SemiBold": 24, "Bold": 24}
FONTS = {
    "Newsreader": ("Newsreader.ttf", "Newsreader-OFL.txt"),
    "JetBrains Mono": ("JetBrainsMono.ttf", "JetBrainsMono-OFL.txt"),
    "Pixelify Sans": ("PixelifySans.ttf", "PixelifySans-OFL.txt"),
}
# Static already: copied under the name the app loads.
COPIED = {"VT323": ("VT323.ttf", "VT323-Regular.ttf", "VT323-OFL.txt")}
# The mock-up's `size-adjust: 128%` on VT323's figures, which brings its 560 cap height to Pixelify's 700.
FIGURES = "0123456789:"
FIGURES_SCALE = 1.28


def name(font: TTFont, family: str, style: str) -> None:
    """Inter's naming: a family per weight for old software, and the one family with its style."""
    compact = family.replace(" ", "")
    ribbi = style in {"Regular", "Bold"}
    table = font["name"]
    for ident in (1, 2, 3, 4, 6, 16, 17, 21, 22, 25):
        table.removeNames(nameID=ident)
    table.setName(family if ribbi else f"{family} {style}", 1, 3, 1, 0x409)
    table.setName(style if ribbi else "Regular", 2, 3, 1, 0x409)
    table.setName(f"{compact}-{style};FlexWeek static instance", 3, 3, 1, 0x409)
    table.setName(f"{family} {style}", 4, 3, 1, 0x409)
    table.setName(f"{compact}-{style}", 6, 3, 1, 0x409)
    table.setName(family, 16, 3, 1, 0x409)
    table.setName(style, 17, 3, 1, 0x409)
    bold = style == "Bold"
    os2 = font["OS/2"]
    os2.usWeightClass = WEIGHTS[style]
    os2.fsSelection = (os2.fsSelection & ~0b1100001) | (0b100000 if bold else 0b1000000)
    font["head"].macStyle = 1 if bold else 0


def borrow_figures(font: TTFont, donor: TTFont) -> None:
    """Put the donor's figures and colon in place of the font's own, scaled by FIGURES_SCALE, with the
    donor's hinting left behind, since it calls functions only the donor has."""
    scale = FIGURES_SCALE * font["head"].unitsPerEm / donor["head"].unitsPerEm
    ours, theirs = font.getBestCmap(), donor.getBestCmap()
    glyf = font["glyf"]
    for char in FIGURES:
        glyph = copy.deepcopy(donor["glyf"][theirs[ord(char)]])
        glyph.coordinates.scale((scale, scale))
        glyph.coordinates.toInt()
        glyph.program = Program()
        glyph.program.fromBytecode(b"")
        glyph.recalcBounds(glyf)
        glyf[ours[ord(char)]] = glyph
        advance = otRound(donor["hmtx"][theirs[ord(char)]][0] * scale)
        font["hmtx"][ours[ord(char)]] = (advance, glyph.xMin)


def main(wanted: list[str]) -> None:
    for family, (variable, licence) in FONTS.items():
        if wanted and family not in wanted:
            continue
        compact = family.replace(" ", "")
        for style, weight in WEIGHTS.items():
            font = TTFont(SOURCE / variable)
            axes = {axis.axisTag for axis in font["fvar"].axes}
            pinned = {"wght": weight}
            if "opsz" in axes:
                pinned["opsz"] = OPTICAL[style]
            static = instantiateVariableFont(font, pinned)
            if family == "Pixelify Sans":
                borrow_figures(static, TTFont(SOURCE / COPIED["VT323"][0]))
            name(static, family, style)
            static.save(TARGET / f"{compact}-{style}.ttf")
            print(TARGET / f"{compact}-{style}.ttf")
        shutil.copyfile(SOURCE / licence, TARGET / licence)
    for family, (source, target, licence) in COPIED.items():
        if wanted and family not in wanted:
            continue
        shutil.copyfile(SOURCE / source, TARGET / target)
        shutil.copyfile(SOURCE / licence, TARGET / licence)
        print(TARGET / target)


if __name__ == "__main__":
    main(sys.argv[1:])
