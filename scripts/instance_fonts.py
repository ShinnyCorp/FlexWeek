"""Make the bundled Newsreader and JetBrains Mono faces from the mock-up's variable fonts.

    python3 scripts/instance_fonts.py      # needs fontTools (pip install fonttools); not the app's

The mock-up draws with the variable fonts in `docs/mockups/look-017/fonts/`. Qt registers a variable
font as one Regular face and ignores a stylesheet's `font-weight` on it, so a heading at 600 came out
at 400. The app bundles each weight as its own static face instead, named as Inter's four are, and
Qt picks the weight a stylesheet asks for. Both fonts are under the OFL with no reserved name.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fontTools.ttLib import TTFont
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
}


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


def main() -> None:
    for family, (variable, licence) in FONTS.items():
        compact = family.replace(" ", "")
        for style, weight in WEIGHTS.items():
            font = TTFont(SOURCE / variable)
            axes = {axis.axisTag for axis in font["fvar"].axes}
            pinned = {"wght": weight}
            if "opsz" in axes:
                pinned["opsz"] = OPTICAL[style]
            static = instantiateVariableFont(font, pinned)
            name(static, family, style)
            static.save(TARGET / f"{compact}-{style}.ttf")
            print(TARGET / f"{compact}-{style}.ttf")
        shutil.copyfile(SOURCE / licence, TARGET / licence)


if __name__ == "__main__":
    main()
