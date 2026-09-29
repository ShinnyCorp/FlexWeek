"""The shared system's measures and its colour maths. No Qt.

Spacing, radii and shadows are 0.17's decisions 5 and 6 as data. The colour functions turn OKLCH, the
space the category family is chosen in (decision 9), into the sRGB hex a stylesheet takes, and back
into OKLab to measure how far apart two colours look.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SPACING = (4, 8, 12, 16, 24, 32)
RADIUS_CONTROL = 6
RADIUS_CARD = 10
RADIUS_SHEET = 16


@dataclass(frozen=True)
class Shadow:
    """A drop shadow as `QGraphicsDropShadowEffect` takes it: offset down, blur, and black's opacity on
    a light look and on a dark one, where a faint shadow would not show."""

    y: int
    blur: int
    opacity: float
    dark_opacity: float


SHADOW_SMALL = Shadow(1, 3, 0.08, 0.40)
SHADOW_LARGE = Shadow(12, 32, 0.16, 0.50)

# Decision 4: five sizes in points at Normal text, which Small and Large scale together, and two
# weights, with 700 only for display numbers.
TYPE_PT = {"caption": 11, "body": 13, "heading": 15, "title": 20, "display": 28}
TEXT_SCALE = {"small": 0.85, "normal": 1.0, "large": 1.2}
WEIGHT_REGULAR = 400
WEIGHT_STRONG = 600
WEIGHT_NUMBER = 700


def type_pt(role: str, scale: float | str = 1.0) -> float:
    """The size of `role` in points, at a Text knob's name or a scale, to the nearest half point."""
    factor = TEXT_SCALE[scale] if isinstance(scale, str) else scale
    return round(TYPE_PT[role] * factor * 2) / 2


def text_knob(body_pt: float) -> str | None:
    """The Text knob whose body size is `body_pt`, for a painter that knows only its widget's font;
    None for a size off the scale, as a design's own."""
    return next((knob for knob in TEXT_SCALE if type_pt("body", knob) == body_pt), None)


def _decode(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _encode(channel: float) -> float:
    return channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def linear_rgb(colour: str) -> tuple[float, float, float]:
    raw = colour.lstrip("#")
    red, green, blue = (_decode(int(raw[at : at + 2], 16) / 255) for at in (0, 2, 4))
    return red, green, blue


def hex_from_linear(red: float, green: float, blue: float) -> str:
    """A linear sRGB colour as hex, each channel clipped into the gamut, as browsers draw one outside it."""
    channels = (round(_encode(min(max(value, 0.0), 1.0)) * 255) for value in (red, green, blue))
    return "#{:02x}{:02x}{:02x}".format(*channels)


def oklab_from_linear(red: float, green: float, blue: float) -> tuple[float, float, float]:
    long = math.cbrt(0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue)
    medium = math.cbrt(0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue)
    short = math.cbrt(0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue)
    return (
        0.2104542553 * long + 0.7936177850 * medium - 0.0040720468 * short,
        1.9779984951 * long - 2.4285922050 * medium + 0.4505937099 * short,
        0.0259040371 * long + 0.7827717662 * medium - 0.8086757660 * short,
    )


def linear_from_oklab(light: float, a: float, b: float) -> tuple[float, float, float]:
    long = (light + 0.3963377774 * a + 0.2158037573 * b) ** 3
    medium = (light - 0.1055613458 * a - 0.0638541728 * b) ** 3
    short = (light - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        4.0767416621 * long - 3.3077115913 * medium + 0.2309699292 * short,
        -1.2684380046 * long + 2.6097574011 * medium - 0.3413193965 * short,
        -0.0041960863 * long - 0.7034186147 * medium + 1.7076147010 * short,
    )


def oklab(colour: str) -> tuple[float, float, float]:
    return oklab_from_linear(*linear_rgb(colour))


def oklch(light: float, chroma: float, hue: float) -> str:
    """An OKLCH colour as sRGB hex, clipped into the gamut."""
    angle = math.radians(hue)
    return hex_from_linear(*linear_from_oklab(light, chroma * math.cos(angle), chroma * math.sin(angle)))


def _channels(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def mix(top: str, bottom: str, alpha: float) -> str:
    """The solid colour of `top` laid over `bottom` at `alpha`.

    The web palette states its hairlines as translucent tints. Qt stylesheets
    disagree between versions about alpha syntax, so the tint is settled here.
    """
    pairs = zip(_channels(top), _channels(bottom), strict=True)
    blended = [round(over * alpha + under * (1 - alpha)) for over, under in pairs]
    return "#{:02x}{:02x}{:02x}".format(*blended)


def luminance(colour: str) -> float:
    red, green, blue = linear_rgb(colour)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def oklch_of(colour: str) -> tuple[float, float, float]:
    """A hex colour as OKLCH: lightness, chroma and hue in degrees."""
    light, a, b = oklab(colour)
    return light, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def fit_lightness(colour: str, grounds: tuple[str, ...], floor: float) -> str:
    """`colour` with its OKLCH lightness moved the least it takes to read at `floor` on every ground,
    darker or lighter, whichever needs the smaller move; its hue and chroma kept as the gamut allows.

    A colour that already reads is returned as it is. The search ends at black or white, which read
    at 4.58 to 1 or better on any one ground.
    """

    def reads(candidate: str) -> bool:
        return all(contrast(candidate, ground) >= floor for ground in grounds)

    if reads(colour):
        return colour
    light, chroma, hue = oklch_of(colour)
    found: list[tuple[float, str]] = []
    for end, extreme in ((0.0, "#000000"), (1.0, "#ffffff")):
        if not reads(oklch(end, chroma, hue)):
            if reads(extreme):
                found.append((abs(end - light) + 1, extreme))
            continue
        fails, passes = light, end
        for _step in range(40):
            middle = (fails + passes) / 2
            fails, passes = (fails, middle) if reads(oklch(middle, chroma, hue)) else (middle, passes)
        found.append((abs(passes - light), oklch(passes, chroma, hue)))
    if not found:
        return max(("#000000", "#ffffff"), key=lambda ink: min(contrast(ink, g) for g in grounds))
    return min(found)[1]


def mix_oklab(top: str, bottom: str, amount: float) -> str:
    """`amount` of `top` in `bottom`, mixed in OKLab as CSS's `color-mix(in oklab, …)` does."""
    over, under = oklab(top), oklab(bottom)
    mixed = (o * amount + u * (1 - amount) for o, u in zip(over, under, strict=True))
    return hex_from_linear(*linear_from_oklab(*mixed))


# Decision 9: one family of category colours, each category at its own hue. A light look fills a block
# with the pale colour and edges it with the mark; a dark look sinks the tone into its own card.
FILL = (0.92, 0.045)
MARK = {"light": (0.62, 0.14), "dark": (0.72, 0.14), "contrast": (0.78, 0.16)}
GREY_CHROMA = 0.01
SINK = 0.34
# At one lightness a deuteranope sees homework's red and sports' green as one colour, and the two lie
# side by side all week. Homework's mark alone is darker, which no colour filter takes away.
HOMEWORK_DARKER = 0.22


def family_colours(hue: float, *, grey: bool = False, homework: bool = False) -> dict[str, tuple[str, str]]:
    """A category's colours in each kind of look: (fill, mark) in light looks, (tone, mark) in dark
    and high-contrast ones."""
    fill = oklch(FILL[0], GREY_CHROMA if grey else FILL[1], hue)
    colours = {}
    for family, (light, chroma) in MARK.items():
        chroma = GREY_CHROMA if grey else chroma
        mark = oklch(light - (HOMEWORK_DARKER if homework else 0), chroma, hue)
        colours[family] = (fill if family == "light" else oklch(light, chroma, hue), mark)
    return colours
