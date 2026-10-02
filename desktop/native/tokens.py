"""The shared system's measures and its colour maths. No Qt.

Spacing, radii and shadows are 0.17's decisions 5 and 6 as data. The colour functions turn OKLCH, the
space the category family is chosen in (decision 9), into the sRGB hex a stylesheet takes, and back
into OKLab to measure how far apart two colours look.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import flexweek_engine  # type: ignore[import-untyped]

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
    return float(flexweek_engine.tokens_type_pt(role, scale))


def text_knob(body_pt: float) -> str | None:
    """The Text knob whose body size is `body_pt`, for a painter that knows only its widget's font."""
    return flexweek_engine.tokens_text_knob(body_pt)


def linear_rgb(colour: str) -> tuple[float, float, float]:
    red, green, blue = flexweek_engine.tokens_linear_rgb(colour)
    return float(red), float(green), float(blue)


def hex_from_linear(red: float, green: float, blue: float) -> str:
    """A linear sRGB colour as hex, each channel clipped into the gamut."""
    return str(flexweek_engine.tokens_hex_from_linear(red, green, blue))


def oklab_from_linear(red: float, green: float, blue: float) -> tuple[float, float, float]:
    light, a, b = flexweek_engine.tokens_oklab_from_linear(red, green, blue)
    return float(light), float(a), float(b)


def linear_from_oklab(light: float, a: float, b: float) -> tuple[float, float, float]:
    red, green, blue = flexweek_engine.tokens_linear_from_oklab(light, a, b)
    return float(red), float(green), float(blue)


def oklab(colour: str) -> tuple[float, float, float]:
    light, a, b = flexweek_engine.tokens_oklab(colour)
    return float(light), float(a), float(b)


def oklch(light: float, chroma: float, hue: float) -> str:
    """An OKLCH colour as sRGB hex, clipped into the gamut."""
    return str(flexweek_engine.tokens_oklch(light, chroma, hue))


def _channels(colour: str) -> tuple[int, int, int]:
    red, green, blue = flexweek_engine.tokens_channels(colour)
    return int(red), int(green), int(blue)


def mix(top: str, bottom: str, alpha: float) -> str:
    """The solid colour of `top` laid over `bottom` at `alpha`."""
    return str(flexweek_engine.tokens_mix(top, bottom, alpha))


def luminance(colour: str) -> float:
    return float(flexweek_engine.tokens_luminance(colour))


def contrast(first: str, second: str) -> float:
    return float(flexweek_engine.tokens_contrast(first, second))


def oklch_of(colour: str) -> tuple[float, float, float]:
    """A hex colour as OKLCH: lightness, chroma and hue in degrees."""
    light, chroma, hue = flexweek_engine.tokens_oklch_of(colour)
    return float(light), float(chroma), float(hue)


def fit_lightness(colour: str, grounds: tuple[str, ...], floor: float) -> str:
    """`colour` with its OKLCH lightness moved the least it takes to read at `floor` on every ground."""
    return str(flexweek_engine.tokens_fit_lightness(colour, list(grounds), floor))


def mix_oklab(top: str, bottom: str, amount: float) -> str:
    """`amount` of `top` in `bottom`, mixed in OKLab."""
    return str(flexweek_engine.tokens_mix_oklab(top, bottom, amount))


# Decision 9: one family of category colours, each category at its own hue. A light look fills a block
# with the pale colour and edges it with the mark; a dark look sinks the tone into its own card.
FILL = (0.92, 0.045)
MARK = {"light": (0.62, 0.14), "dark": (0.72, 0.14), "contrast": (0.78, 0.16)}
GREY_CHROMA = 0.01
SINK = 0.34
# At one lightness a deuteranope sees homework's red and sports' green as one colour, and the two lie
# side by side all week. Homework's mark alone is darker, which no colour filter takes away.
HOMEWORK_DARKER = 0.22
SLEEP_FILL_DARKER = 0.08
SLEEP_MARK_DARKER = 0.12


def family_colours(
    hue: float, *, grey: bool = False, homework: bool = False, sleep: bool = False,
) -> dict[str, tuple[str, str]]:
    """A category's colours in each kind of look: (fill, mark) in light looks, (tone, mark) in dark ones."""
    raw = json.loads(flexweek_engine.tokens_family_colours(hue, grey, homework, sleep))
    return {key: (value[0], value[1]) for key, value in raw.items()}
