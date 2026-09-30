"""Device-only look knobs and account theme packs. No Qt.

A look has two halves. The palette says what colours exist; the knobs say how
the interface is drawn with them. A pack (Light, Dark, System, Slate, Nocturne) is the account's;
a preset (High contrast, Paper, Ink, Terminal, Poster, Pastel) is a look of its own on this device,
its palette and the knobs it sets. A custom look is any of those ten with what the student changed
(custom_look.py keeps and checks them), drawn by the same functions. Every knob has to change
something a student can see: a control that stores a value nothing reads is the bug this module
exists to prevent, and desktop/tests/test_look.py proves each value moves the output.

The ten looks' colours are the 0.17 mock-up's (docs/mockups/look-017/looks.css).
"""

from __future__ import annotations

import math
import re
from copy import deepcopy
from functools import lru_cache

from desktop.native.calendar import CATEGORIES
from desktop.native.tokens import (
    FILL,
    GREY_CHROMA,
    HOMEWORK_DARKER,
    MARK,
    RADIUS_CARD,
    RADIUS_CONTROL,
    RADIUS_SHEET,
    SHADOW_SMALL,
    SINK,
    SPACING,
    TEXT_SCALE,
    TYPE_PT,
    WEIGHT_REGULAR,
    WEIGHT_STRONG,
    _channels,
    contrast,
    fit_lightness,
    luminance,
    mix,
    mix_oklab,
    oklch,
    oklch_of,
    type_pt,
)

# The knobs of 0.17 (plan, "The knobs"), each value in the order Settings offers them. Round's id is
# "rounded" because "round" was 0.16's name for what is now Soft; a look saved then still opens as it
# looked (LEGACY_KNOBS).
LOOK_KNOBS = {
    "surface": ("flat", "layered"),
    "corners": ("soft", "sharp", "rounded"),
    "depth": ("none", "soft", "bold"),
    "font": ("sans", "serif", "mono"),
    "blocks": ("edge", "filled", "outline"),
    "density": ("comfortable", "compact"),
    "text": ("small", "normal", "large"),
}
KNOB_LABELS = {
    "surface": "Surface",
    "corners": "Corners",
    "depth": "Shadows",
    "font": "Font",
    "blocks": "Blocks",
    "density": "Spacing",
    "text": "Text size",
}
KNOB_VALUE_LABELS = {
    "flat": "Flat",
    "layered": "Layered",
    "soft": "Soft",
    "sharp": "Sharp",
    "rounded": "Round",
    "none": "None",
    "bold": "Bold",
    "sans": "Sans",
    "serif": "Serif",
    "mono": "Mono",
    "edge": "Edge",
    "filled": "Filled",
    "outline": "Outline",
    "comfortable": "Comfortable",
    "compact": "Compact",
    "small": "Small",
    "normal": "Normal",
    "large": "Large",
}
# 0.16's names for the values that were renamed.
LEGACY_KNOBS = {
    "surface": {"frost": "layered"},
    "corners": {"round": "soft", "pill": "rounded"},
    "depth": {"flat": "none", "hard": "bold"},
    "blocks": {"outlined": "outline"},
}
LOOK_DEFAULTS = {
    "surface": "layered",
    "corners": "soft",
    "depth": "soft",
    "font": "sans",
    # Decision 14 of 0.17: the category's fill with a 3-pixel edge in its mark.
    "blocks": "edge",
    "density": "comfortable",
    "text": "normal",
}
# A preset is a look of its own, whatever the account's pack: its palette (PRESET_PALETTES) and the
# knobs it sets. Blocks follow the default in every look but High contrast, as the mock-up draws them.
LOOK_PRESETS = {
    "default": {},
    "high-contrast": {
        "surface": "flat",
        "corners": "sharp",
        "depth": "bold",
        "font": "sans",
        "blocks": "outline",
        "density": "comfortable",
        "text": "large",
    },
    # E-Ink / Paper: serif headings and hairline rules. Its depth draws those hairlines; Qt draws no
    # shadow under them.
    "paper": {"surface": "layered", "corners": "soft", "depth": "soft", "font": "serif"},
    "ink": {"surface": "layered", "corners": "soft", "depth": "soft", "font": "serif"},
    "terminal": {"surface": "layered", "corners": "sharp", "depth": "soft", "font": "mono"},
    # Neubrutalism: square corners and heavy black edges.
    "poster": {"surface": "layered", "corners": "sharp", "depth": "bold", "font": "sans"},
    "pastel": {"surface": "layered", "corners": "rounded", "depth": "soft", "font": "sans"},
}
LOOK_PRESET_LABELS = {
    "default": "Pack default",
    "terminal": "Terminal",
    "poster": "Poster",
    "ink": "Ink",
    "high-contrast": "High contrast",
    "paper": "Paper",
    "pastel": "Pastel",
}
PACK_LABELS = {
    "system": "System",
    "light-frost": "Light",
    "dark-frost": "Dark",
    "nocturne": "Nocturne",
    "slate": "Slate",
}
PACKS = ("system", "light-frost", "dark-frost", "nocturne", "slate")
ACCENTS = ("default", "sky", "gold", "sea", "sand")
MONO_FAMILY = "DejaVu Sans Mono, Noto Sans Mono, monospace"
# The shortest a field may be drawn. A layout under pressure squeezes its rows, and a combo box or a
# line edit has no minimum of its own worth the name, so the text inside gets sliced in half rather
# than the dialog refusing to shrink. Measured against the app's own font: 2.25 pixels a point.
FIELD_MIN_PX = {text: math.ceil(type_pt("body", text) * 2.25) for text in TEXT_SCALE}
# A card's padding, and the smaller one of a button, a field, a list or a menu, which keep their heights.
DENSITY_PAD = {"comfortable": 16, "compact": 8}
CONTROL_PAD = {"comfortable": 8, "compact": 4}
# (controls, cards) at each Corners setting. Soft is the system's own shape (decision 5 of 0.17).
CORNER_RADIUS = {
    "soft": (RADIUS_CONTROL, RADIUS_CARD),
    "sharp": (0, 2),
    "rounded": (RADIUS_CARD, RADIUS_SHEET),
}
# The bundled faces first (fonts.py), then the system's.
FONT_FAMILIES = {
    "sans": "Inter, Noto Sans, DejaVu Sans, sans-serif",
    "serif": "Newsreader, Noto Serif, DejaVu Serif, serif",
    "mono": "JetBrains Mono, Noto Sans Mono, DejaVu Sans Mono, monospace",
}
# The Font knob as (body, headings): Serif is Newsreader headings over Inter.
FONT_PAIRS = {"sans": ("sans", "sans"), "serif": ("sans", "serif"), "mono": ("mono", "mono")}
# The labels that are headings, which take the heading face.
HEADING_NAMES = (
    "weekTitle",
    "settingsTitle",
    "setupTitle",
    "authHeading",
    "emptyWeekHeading",
    "alarmTitle",
    "aboutVersion",
    "updateHeading",
    "prefsHeading",
    "lookEditorTitle",
    "lookGroupName",
    "layoutMainHeading",
    "layoutDayHeading",
    "cardTitle",
    "setupChoiceName",
    "focusScreenTask",
    "clayDayName",
    "timelineDayName",
    "timelineStat",
    "bentoHeroTitle",
    "bentoNextTitle",
    "bentoFigure",
)
AA_TEXT = 4.5
# A block's times and length, in its ink laid this much over its fill where that still reads.
MUTED_INK = 0.72
# The luminance under which a colour is dark: a custom page under it makes a dark look.
MID_GREY = 0.18
# Room round a drawn menu's panel for its shadow: its window is this much larger on every side.
MENU_EDGE = 24
# How far High contrast lays its text over a row under the pointer; OKLab mixes 6 % of white on black
# to a black no one can tell from the page, and more would dim Delete's red below 4.5 to 1.
HIGH_CONTRAST_HOVER = 0.3
DARK_INK = "#0b1224"
LIGHT_INK = "#ffffff"
# Each accent has a dark-axis and a light-axis colour with its own ink, so it reads on either. The
# default is FlexWeek's blue, the icon's, and every look but High contrast wears it (decision 1 of 0.17).
ACCENT_COLORS = {
    "default": {"dark": ("#7fa8ff", DARK_INK), "light": ("#3d6fc4", LIGHT_INK)},
    "sky": {"dark": ("#38bdf8", DARK_INK), "light": ("#0369a1", LIGHT_INK)},
    "gold": {"dark": ("#eab308", DARK_INK), "light": ("#a16207", LIGHT_INK)},
    "sea": {"dark": ("#2dd4bf", DARK_INK), "light": ("#0f766e", LIGHT_INK)},
    "sand": {"dark": ("#e7d5a3", DARK_INK), "light": ("#926a2a", LIGHT_INK)},
}
# Looks whose accent no swatch replaces: High contrast's yellow is part of its contrast.
OWN_ACCENT = ("high-contrast",)


def readable_ink(background: str) -> str:
    """Black or white, whichever reads better on a colour the palette does not own, such as a category.

    Pure black, not the palette's navy ink: on the violet Study colour navy reaches about 4.4 to 1 and
    white about 4.2, so neither passes, while black does.
    """
    return max(("#000000", LIGHT_INK), key=lambda ink: contrast(ink, background))


def _palette(
    axis: str, tint: str | None = None, soft: float = 0.12, strong: float = 0.24, **colors: object
) -> dict:
    """A colour table in the one accent. Hairlines are `tint` over the panel unless named outright.

    `family` says which of a category's colours the look draws (light, dark or contrast), and `rule`
    is the grid's hour rules, which take the stronger hairline on a dark look, where the plain one all
    but vanished on the page.
    """
    accent, accent_ink = ACCENT_COLORS["default"][axis]
    table = {"axis": axis, "family": axis, "accent": accent, "accent_ink": accent_ink}
    if tint is not None:
        panel = colors["panel"]
        table.update(hairline=mix(tint, panel, soft), hairline_strong=mix(tint, panel, strong))
    table.update(colors)
    table.setdefault("rule", table["hairline_strong" if axis == "dark" else "hairline"])
    return table


# window is the page, panel the raised surface (a card), card_2 a raised one on a card, field an input,
# grid the calendar cell. The seven looks after Light, Dark and High contrast are looks.css's
# (docs/mockups/look-017), page, card, raised, text, muted and both hairlines as drawn there; the rest
# is worked out the way Light's and Dark's are.
PALETTES = {
    # Dark Mode (OLED): midnight, low emission.
    "nocturne": _palette(
        "dark",
        window="#0a0e27",
        panel="#121633",
        card_2="#1a1f42",
        field="#0d112c",
        grid="#0d112c",
        text="#e0e4f0",
        muted="#9aa3c0",
        hairline="#262b4d",
        hairline_strong="#343a63",
        rule=mix("#e0e4f0", "#0a0e27", 0.08),
        error="#ff8a7a",
        block_locked="#1f2449",
        block_locked_ink="#e0e4f0",
        block_flex="#4a3c1c",
        block_flex_ink="#fff4dc",
        block_edge="#7d86a6",
    ),
    # Swiss Modernism 2.0: cool and professional.
    "slate": _palette(
        "light",
        window="#eef1f5",
        panel="#ffffff",
        card_2="#e7ebf1",
        field="#ffffff",
        grid="#ffffff",
        text="#0f172a",
        muted="#475569",
        hairline="#dbe1ea",
        hairline_strong="#c3ccd9",
        error="#b42318",
        block_locked="#e7ebf1",
        block_locked_ink="#0f172a",
        block_flex="#f5e6c3",
        block_flex_ink="#3b2a05",
        block_edge="#8a9bb8",
    ),
    # Dark and Light (decision 2 of 0.17): neutral surfaces, so the categories are the only colour on the
    # page. They keep the frost ids, so a look saved before 0.17 opens as these.
    "dark-frost": _palette(
        "dark",
        window="#111315",
        panel="#1a1d21",
        card_2="#22262b",
        field="#15171a",
        grid="#15171a",
        text="#e8eaed",
        muted="#9aa1ab",
        hairline="#2a2e34",
        hairline_strong="#3a3f46",
        error="#ff8a7a",
        block_locked="#2c3137",
        block_locked_ink="#eceef1",
        block_flex="#4a3c1c",
        block_flex_ink="#fff4dc",
        block_edge="#7c8591",
    ),
    "light-frost": _palette(
        "light",
        window="#f7f8fa",
        panel="#ffffff",
        card_2="#f1f3f6",
        field="#ffffff",
        grid="#ffffff",
        text="#111827",
        muted="#5b6474",
        hairline="#e4e7ec",
        hairline_strong="#d0d5dd",
        error="#c42b1c",
        block_locked="#eceff3",
        block_locked_ink="#111827",
        block_flex="#f5e6c3",
        block_flex_ink="#3b2a05",
        block_edge="#8a93a3",
    ),
}
# A preset brings its own colours, the same on any pack. `fill` moves the category family's pale fills
# (decision 9) for a look that draws them paler or bolder.
PRESET_PALETTES = {
    # Developer Mono on GitHub-dark surfaces; no glow, no phosphor green.
    "terminal": _palette(
        "dark",
        window="#0d1117",
        panel="#161b22",
        card_2="#1c2129",
        field="#11151c",
        grid="#11151c",
        text="#c9d1d9",
        muted="#8b949e",
        hairline="#30363d",
        hairline_strong="#484f58",
        rule=mix("#c9d1d9", "#0d1117", 0.08),
        error="#f85149",
        block_locked="#21262d",
        block_locked_ink="#c9d1d9",
        block_flex="#4a3c1c",
        block_flex_ink="#fff4dc",
        block_edge="#6e7681",
    ),
    # Neubrutalism: black lines on cream, bolder fills. Its hour rules are the ink at 14 %, not black.
    "poster": _palette(
        "light",
        window="#fff8e7",
        panel="#ffffff",
        card_2="#fff1cc",
        field="#ffffff",
        grid="#ffffff",
        text="#111111",
        muted="#3d3d3d",
        hairline="#111111",
        hairline_strong="#111111",
        rule=mix("#111111", "#fff8e7", 0.14),
        error="#b42318",
        block_locked="#fff1cc",
        block_locked_ink="#111111",
        block_flex="#f5e6c3",
        block_flex_ink="#3b2a05",
        block_edge="#111111",
        fill=(0.88, 0.09),
    ),
    "high-contrast": _palette(
        "dark",
        "#ffffff",
        soft=0.4,
        strong=1.0,
        family="contrast",
        window="#000000",
        panel="#000000",
        card_2="#0d0d0d",
        field="#000000",
        grid="#000000",
        text="#ffffff",
        muted="#e6e6e6",
        accent="#ffd400",
        accent_ink="#000000",
        error="#ff6b6b",
        # Text at 7 to 1, not every line at full white: the hour rules are 40 % white, as the hairlines.
        rule="#666666",
        block_locked="#000000",
        block_locked_ink="#ffffff",
        block_flex="#000000",
        block_flex_ink="#ffd400",
        block_edge="#ffd400",
    ),
    # E-Ink / Paper: ink on off-white, matte, the category fills a little quieter.
    "paper": _palette(
        "light",
        window="#fdfbf7",
        panel="#fffdf9",
        card_2="#f6f1e8",
        field="#fffdf9",
        grid="#fffdf9",
        text="#1a1a1a",
        muted="#5c5750",
        hairline="#e6e0d6",
        hairline_strong="#cfc7b9",
        error="#9b1b30",
        block_locked="#f6f1e8",
        block_locked_ink="#1a1a1a",
        block_flex="#f3dca6",
        block_flex_ink="#3b2a05",
        block_edge="#a08a68",
        fill=(0.92, 0.035),
    ),
    # Paper's night counterpart: charcoal and warm ivory.
    "ink": _palette(
        "dark",
        window="#1c1b19",
        panel="#242320",
        card_2="#2c2a26",
        field="#1f1e1c",
        grid="#1f1e1c",
        text="#f3eee3",
        muted="#b3ab9c",
        hairline="#3a3833",
        hairline_strong="#4a4740",
        rule=mix("#f3eee3", "#1c1b19", 0.08),
        error="#ff8a7a",
        block_locked="#2c2a26",
        block_locked_ink="#f3eee3",
        block_flex="#4a3c1c",
        block_flex_ink="#fff4dc",
        block_edge="#8a8375",
    ),
    # Soft UI Evolution: improved-contrast pastels on lavender, text at slate-900's depth.
    "pastel": _palette(
        "light",
        window="#f3f0ff",
        panel="#ffffff",
        card_2="#ece7ff",
        field="#ffffff",
        grid="#ffffff",
        text="#1e1b2e",
        muted="#4b4763",
        hairline="#e4ddfb",
        hairline_strong="#cfc5f5",
        error="#b42318",
        block_locked="#ece7ff",
        block_locked_ink="#1e1b2e",
        block_flex="#ffe4ef",
        block_flex_ink="#4a1230",
        block_edge="#a78bda",
    ),
}


def known_pack(pack: object) -> str:
    return pack if pack in PACKS else "system"


def pack_axis(pack: object) -> str:
    chosen = known_pack(pack)
    if chosen in {"light-frost", "slate"}:
        return "slate"
    if chosen in {"dark-frost", "nocturne"}:
        return "nocturne"
    return "system"


def resolved_pack_theme(pack: object, system_dark: bool) -> str:
    chosen = known_pack(pack)
    if chosen == "system":
        return "dark-frost" if system_dark else "light-frost"
    return chosen


# The looks offered first, as (kind, name); every other pack and preset is experimental.
STANDARD_LOOKS = (
    ("pack", "system"),
    ("pack", "light-frost"),
    ("pack", "dark-frost"),
    ("preset", "high-contrast"),
)
EXPERIMENTAL_LOOKS = (
    ("pack", "nocturne"),
    ("pack", "slate"),
    ("preset", "poster"),
    ("preset", "terminal"),
    ("preset", "paper"),
    ("preset", "ink"),
    ("preset", "pastel"),
)


def look_menu_items() -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """The Look list in two groups, standard then experimental, each item (name, label, kind). A pack
    is the pack with its own knobs; a preset is a look of its own on any pack."""

    def item(kind: str, name: str) -> tuple[str, str, str]:
        return name, (PACK_LABELS if kind == "pack" else LOOK_PRESET_LABELS)[name], kind

    return [item(*entry) for entry in STANDARD_LOOKS], [item(*entry) for entry in EXPERIMENTAL_LOOKS]


def look_menu_token(kind: str, name: str) -> str:
    return f"{kind}:{name}"


def parse_look_menu_token(token: object) -> tuple[str, str] | None:
    if not isinstance(token, str) or ":" not in token:
        return None
    kind, name = token.split(":", 1)
    if kind == "pack" and name in PACKS:
        return kind, name
    if kind == "preset" and name in LOOK_PRESETS and name != "default":
        return kind, name
    return None


def look_menu_value(pack: object, look: dict | None) -> str:
    preset = sanitize_look(look)["preset"]
    if preset != "default":
        return look_menu_token("preset", preset)
    return look_menu_token("pack", known_pack(pack))


# Customise (plan, 27 September): one of the ten looks as a starting point and what the student changed
# on it. Each base is the (pack, preset) it stands for; a custom look ignores the account's pack.
LOOK_BASES = {
    "light": ("light-frost", "default"),
    "dark": ("dark-frost", "default"),
    "system": ("system", "default"),
    "high-contrast": ("system", "high-contrast"),
    "slate": ("slate", "default"),
    "nocturne": ("nocturne", "default"),
    "paper": ("system", "paper"),
    "ink": ("system", "ink"),
    "terminal": ("system", "terminal"),
    "poster": ("system", "poster"),
    "pastel": ("system", "pastel"),
}
BASE_LABELS = {
    "light": "Light",
    "dark": "Dark",
    "system": "System",
    "high-contrast": "High contrast",
    "slate": "Slate",
    "nocturne": "Nocturne",
    "paper": "Paper",
    "ink": "Ink",
    "terminal": "Terminal",
    "poster": "Poster",
    "pastel": "Pastel",
}
# The colours a student sets. Muted text follows from the text and the card unless set too; the
# raised card and the strong line always follow.
CUSTOM_COLOURS = ("page", "card", "text", "line", "muted")
HOUR_LINES = ("none", "faint", "clear")
NOW_LINES = ("accent", "text")
# The motion levels of decision 33; Lane F's motion.py runs them.
MOTION_LEVELS = ("normal", "extra", "reduce", "off")
CUSTOM_CHOICES = {
    "spacing": LOOK_KNOBS["density"],
    "shadows": LOOK_KNOBS["depth"],
    "body_font": tuple(FONT_FAMILIES),
    "heading_font": tuple(FONT_FAMILIES),
    "blocks": LOOK_KNOBS["blocks"],
    "hour_lines": HOUR_LINES,
    "now_line": NOW_LINES,
    "motion": MOTION_LEVELS,
}
CUSTOM_SWITCHES = ("show_times", "show_lengths", "today_highlight")
# The least and the most of each measure, and whether it is whole pixels.
CUSTOM_RANGES = {"corners": (0, 16, True), "text_scale": (0.9, 1.3, False), "edge_width": (2, 6, True)}
NAME_MAX = 40
HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _hex(value: object) -> str | None:
    return value.lower() if isinstance(value, str) and HEX.fullmatch(value) else None


def _category_spec(value: object) -> tuple[str, float | str] | None:
    """A category's colour as the student set it: ("hue", degrees) on the family, or ("colour", hex)."""
    if not isinstance(value, dict):
        return None
    hue = value.get("hue")
    if isinstance(hue, int | float) and not isinstance(hue, bool) and math.isfinite(hue):
        return "hue", float(hue) % 360
    colour = _hex(value.get("colour"))
    return ("colour", colour) if colour else None


def _said(key: str) -> str:
    return key.replace("_", " ").capitalize()


def sanitize_custom(raw: object) -> tuple[dict | None, list[str]]:
    """A custom look with every unknown key and bad value dropped, and a plain sentence for each one
    dropped. None when there is no look to keep: no base, or one this FlexWeek does not have."""
    if not isinstance(raw, dict):
        return None, ["A look has to be a set of named settings."]
    if not isinstance(raw.get("base"), str) or raw["base"] not in LOOK_BASES:
        return None, [f"It starts from a look FlexWeek does not have: {str(raw.get('base'))[:40]!r}."]
    clean: dict = {"base": raw["base"]}
    problems: list[str] = []
    known = {"name", "base", "accent", "colours", "categories", *CUSTOM_CHOICES, *CUSTOM_SWITCHES}
    known |= set(CUSTOM_RANGES)
    for key in raw:
        if key not in known:
            problems.append(f"{str(key)[:40]!r} is not a look setting, so it was left out.")
    name = raw.get("name")
    if isinstance(name, str) and name.strip():
        clean["name"] = " ".join(name.split())[:NAME_MAX]
    elif "name" in raw:
        problems.append("The name was not text, so it was left out.")
    if "accent" in raw:
        accent = raw["accent"]
        if (isinstance(accent, str) and accent in ACCENTS) or _hex(accent):
            clean["accent"] = _hex(accent) or accent
        else:
            problems.append("The accent was not a swatch or a colour like #3d6fc4, so it was left out.")
    colours = raw.get("colours", {})
    if not isinstance(colours, dict):
        colours = {}
        problems.append("The colours were not a set of named colours, so they were left out.")
    kept = {key: _hex(colours.get(key)) for key in CUSTOM_COLOURS if _hex(colours.get(key))}
    problems += [
        f"The {key} colour was not a colour like #3d6fc4, so it was left out."
        for key in colours
        if key not in kept
    ]
    if kept:
        clean["colours"] = kept
    categories = raw.get("categories", {})
    if not isinstance(categories, dict):
        categories = {}
        problems.append("The category colours were not a set, so they were left out.")
    specs = {key: _category_spec(value) for key, value in categories.items() if key in CATEGORIES}
    for key in categories:
        if specs.get(key) is None:
            problems.append(f"The colour for {str(key)[:40]!r} was left out: no such category or no colour.")
    specs = {key: spec for key, spec in specs.items() if spec is not None}
    if specs:
        clean["categories"] = {key: {spec[0]: spec[1]} for key, spec in specs.items()}
    for key, values in CUSTOM_CHOICES.items():
        if key in raw:
            if raw[key] in values:
                clean[key] = raw[key]
            else:
                problems.append(f"{_said(key)} was not one of {', '.join(values)}.")
    for key in CUSTOM_SWITCHES:
        if key in raw:
            if isinstance(raw[key], bool):
                clean[key] = raw[key]
            else:
                problems.append(f"{_said(key)} was not on or off, so it was left out.")
    for key, (low, high, whole) in CUSTOM_RANGES.items():
        if key in raw:
            value = raw[key]
            if isinstance(value, int | float) and not isinstance(value, bool) and low <= value <= high:
                clean[key] = round(value) if whole else round(float(value), 2)
            else:
                problems.append(f"{_said(key)} was not between {low} and {high}.")
    return clean, problems


def sanitize_look(raw: object) -> dict:
    """The device's look: a preset and the knobs moved on it, 0.16's knob names read as today's, and a
    custom look when the student made one."""
    clean: dict = {"preset": "default", "knobs": {}}
    if not isinstance(raw, dict):
        return clean
    if isinstance(raw.get("preset"), str) and raw["preset"] in LOOK_PRESETS:
        clean["preset"] = raw["preset"]
    stored = raw.get("knobs")
    knobs = stored if isinstance(stored, dict) else {}
    for knob, values in LOOK_KNOBS.items():
        value = knobs.get(knob)
        if not isinstance(value, str):
            continue
        value = LEGACY_KNOBS.get(knob, {}).get(value, value)
        if value in values:
            clean["knobs"][knob] = value
    if "custom" in raw:
        custom, _problems = sanitize_custom(raw["custom"])
        if custom is not None:
            clean["custom"] = custom
    return clean


def _nearest(value: float, choices: dict[str, float]) -> str:
    return min(choices, key=lambda name: abs(choices[name] - value))


def effective_look(choice: dict | None) -> dict:
    """Every knob as it is drawn. A custom look's measures answer as the nearest knob, so what reads a
    knob, such as setup's chips, still reads something true."""
    selected = sanitize_look(choice)
    custom = selected.get("custom")
    if custom is None:
        return {**LOOK_DEFAULTS, **LOOK_PRESETS[selected["preset"]], **selected["knobs"]}
    knobs = {**LOOK_DEFAULTS, **LOOK_PRESETS[LOOK_BASES[custom["base"]][1]]}
    for field, knob in (("spacing", "density"), ("shadows", "depth"), ("blocks", "blocks")):
        knobs[knob] = custom.get(field, knobs[knob])
    body, heading = FONT_PAIRS[knobs["font"]]
    body, heading = custom.get("body_font", body), custom.get("heading_font", heading)
    if (body, heading) != FONT_PAIRS[knobs["font"]]:
        knobs["font"] = "mono" if body == "mono" else "serif" if "serif" in (body, heading) else "sans"
    if "text_scale" in custom:
        knobs["text"] = _nearest(custom["text_scale"], TEXT_SCALE)
    if "corners" in custom:
        cards = {name: card for name, (_control, card) in CORNER_RADIUS.items()}
        knobs["corners"] = _nearest(custom["corners"], cards)
    return knobs


def look_measures(choice: dict | None) -> dict:
    """What a look draws that is not a colour, worked out from its knobs and any custom measures: the
    corners of controls and cards, the text size in points, the body and heading faces, and how blocks
    and the grid are drawn. `edge_width` None is the painter's own."""
    selected = sanitize_look(choice)
    custom = selected.get("custom") or {}
    knobs = effective_look(selected)
    radius, card_radius = CORNER_RADIUS[knobs["corners"]]
    if "corners" in custom:
        # A card's corner as set, and a control's in the ratio Soft and Round keep, 6 to 10.
        card_radius = custom["corners"]
        radius = round(card_radius * RADIUS_CONTROL / RADIUS_CARD)
    body, heading = FONT_PAIRS[knobs["font"]]
    if custom:
        base_font = {**LOOK_DEFAULTS, **LOOK_PRESETS[LOOK_BASES[custom["base"]][1]]}["font"]
        body, heading = FONT_PAIRS[base_font]
        body, heading = custom.get("body_font", body), custom.get("heading_font", heading)
    scale = custom.get("text_scale", TEXT_SCALE[knobs["text"]])
    return {
        "radius": radius,
        "card_radius": card_radius,
        "size": type_pt("body", scale),
        "scale": scale,
        "body": FONT_FAMILIES[body],
        "heading": FONT_FAMILIES[heading],
        "edge_width": custom.get("edge_width"),
        "show_times": custom.get("show_times", True),
        "show_lengths": custom.get("show_lengths", True),
        "today_highlight": custom.get("today_highlight", True),
    }


def text_scale(choice: dict | None) -> float:
    """How much larger than Normal the look's text is drawn."""
    return look_measures(choice)["scale"]


def look_motion(look: dict | None) -> str:
    """The motion level a look starts at when the student never chose one: a custom look's own, Reduce
    for Paper ("distinct page turns, sharp transitions"), else Normal. Light and Dark once started at
    More, 0.16's leftover, so choosing Light moved more than System did."""
    selected = sanitize_look(look)
    custom = selected.get("custom")
    if custom is not None:
        return custom.get("motion") or ("reduce" if LOOK_BASES[custom["base"]][1] == "paper" else "normal")
    return "reduce" if selected["preset"] == "paper" else "normal"


def preset_knobs(preset: object) -> dict:
    """Every knob as the preset alone sets it, which is what choosing that preset means."""
    return effective_look({"preset": preset, "knobs": {}})


def look_overrides(preset: object, shown: dict) -> dict:
    """Only the knobs a student moved away from the preset, so the preset keeps governing the rest."""
    bundle = preset_knobs(preset)
    return {knob: value for knob, value in shown.items() if knob in bundle and value != bundle[knob]}


def known_accent(name: object) -> str:
    return name if name in ACCENTS else "default"


def _derived_muted(text: str, card: str, page: str) -> str:
    """The quietest mix of the text into the card that still reads at 4.5 to 1 on the card and the page."""
    for step in range(60, 101, 2):
        muted = mix(text, card, step / 100)
        if min(contrast(muted, card), contrast(muted, page)) >= AA_TEXT + 0.1:
            return muted
    return text


def _customised(palette: dict, custom: dict) -> dict:
    """The base look's colours with the student's in their place, and what follows from them: a dark
    page makes a dark look, muted text is the quietest mix of the text that still reads, the raised
    card and the strong line are the text laid faintly over the card and the line."""
    colours = custom.get("colours", {})
    table = dict(palette)
    if colours:
        page = colours.get("page", table["window"])
        card = colours.get("card", table["panel"])
        text = colours.get("text", table["text"])
        line = colours.get("line", table["hairline"])
        axis = "dark" if luminance(page) < MID_GREY else "light"
        if axis != table["axis"] or table["family"] != "contrast":
            table["family"] = axis
        table["axis"] = axis
        sunk = card if axis == "light" else mix(card, page, 0.42)
        table.update(window=page, panel=card, field=sunk, grid=sunk, text=text, hairline=line)
        if "muted" in colours:
            table["muted"] = colours["muted"]
        if {"page", "card", "text"} & colours.keys():
            raised = mix(text, card, 0.05)
            flex_reads = contrast(table["block_flex_ink"], table["block_flex"]) >= AA_TEXT
            table.update(
                muted=colours.get("muted") or _derived_muted(text, card, page),
                card_2=raised,
                block_locked=raised if contrast(text, raised) >= AA_TEXT else card,
                block_locked_ink=text,
                block_flex=table["block_flex"] if flex_reads else card,
                block_flex_ink=table["block_flex_ink"] if flex_reads else text,
                error=fit_lightness(table["error"], (page, card), AA_TEXT),
            )
            table["block_edge"] = mix(table["muted"], card, 0.75)
        if {"text", "line"} & colours.keys():
            table["hairline_strong"] = mix(text, line, 0.09)
        table["rule"] = table["hairline_strong"] if axis == "dark" else line
    lines = custom.get("hour_lines")
    if lines == "none":
        table["rule"] = table["window"]
    elif lines == "faint":
        table["rule"] = mix(table["text"], table["window"], 0.08)
    elif lines == "clear":
        table["rule"] = table["hairline_strong"]
    if "categories" in custom:
        table["categories"] = {key: next(iter(spec.items())) for key, spec in custom["categories"].items()}
    return table


def _accent(palette: dict, accent: object) -> tuple[str, str]:
    """The accent and its ink on this palette: a swatch in the palette's axis, or a colour of the
    student's with black or white ink, whichever reads."""
    colour = _hex(accent)
    if colour:
        return colour, readable_ink(colour)
    return ACCENT_COLORS[known_accent(accent)][palette["axis"]]


def _preset_palette(preset: str) -> dict | None:
    return PRESET_PALETTES.get(preset)


def resolved_palette(pack: object, system_dark: bool, look: dict | None, accent: object = "default") -> dict:
    """The colours on screen: the preset's palette or the pack's, then a custom look's colours, then the
    accent, then the surface knob.

    The accent is one colour everywhere, but a page may need its darker shade (or on a dark page its
    lighter one) for accent words to read at 4.5 to 1; its lightness moves the least it takes, and its
    hue stays. No built-in look needs it; a custom page might."""
    choice = sanitize_look(look)
    custom = choice.get("custom")
    preset = choice["preset"]
    if custom is not None:
        pack, preset = LOOK_BASES[custom["base"]]
    base = _preset_palette(preset) or PALETTES[resolved_pack_theme(pack, system_dark)]
    palette = dict(base)
    if custom is not None:
        palette = _customised(palette, custom)
        accent = custom.get("accent", accent)
    if preset not in OWN_ACCENT or (custom is not None and "accent" in custom):
        palette["accent"], palette["accent_ink"] = _accent(palette, accent)
    if effective_look(choice)["surface"] == "flat":
        # Flat has no raised surfaces: panels and inputs sit in the page and only hairlines divide them.
        palette["panel"] = palette["window"]
        palette["field"] = palette["window"]
    # A colour the student typed stays as typed; the readability check offers its fix instead.
    own = custom is not None and _hex(custom.get("accent")) is not None
    readable = fit_lightness(palette["accent"], (palette["window"], palette["panel"]), AA_TEXT)
    if readable != palette["accent"] and not own:
        palette["accent"] = readable
        palette["accent_ink"] = readable_ink(readable)
    if custom is not None and custom.get("now_line") == "text":
        palette["now"] = palette["text"]
    return palette


def category_paint(category: str | None, palette: dict) -> tuple[str | None, str | None]:
    """A category's fill and mark in this look, or (None, None) for none.

    A light look fills with the pale colour. On a dark one a pale fill glared off the page, so the fill
    there is the category's tone sunk into the look's own panel. A look may draw the family's fills
    paler or bolder (`fill`), and a custom look may give a category a hue of its own on the family, or
    an exact colour, which is its fill in any look.
    """
    info = CATEGORIES.get(category or "")
    if info is None:
        return None, None
    family = palette.get("family", "light")
    spec = (palette.get("categories") or {}).get(category)
    fill = palette.get("fill")
    if spec is None and (fill is None or family != "light"):
        if family == "light":
            return info["color"], info["mark"]
        tone, mark = info[family]
        return _sunk(tone, palette["panel"]), mark
    return _own_paint(category, family, spec, fill, palette["panel"])


@lru_cache(maxsize=512)
def _own_paint(
    category: str,
    family: str,
    spec: tuple[str, float | str] | None,
    fill: tuple[float, float] | None,
    panel: str,
) -> tuple[str, str]:
    info = CATEGORIES[category]
    homework = HOMEWORK_DARKER if category == "assignments" else 0.0
    mark_light, mark_chroma = MARK[family]
    if spec is not None and spec[0] == "colour":
        colour = str(spec[1])
        _light, chroma, hue = oklch_of(colour)
        return colour, oklch(mark_light - homework, min(chroma, mark_chroma), hue)
    hue = float(spec[1]) if spec is not None else info["hue"]
    grey = spec is None and category == "free"
    chroma = GREY_CHROMA if grey else mark_chroma
    mark = oklch(mark_light - homework, chroma, hue)
    if family != "light":
        return _sunk(oklch(mark_light, chroma, hue), panel), mark
    light, fill_chroma = fill or FILL
    return oklch(light, GREY_CHROMA if grey else fill_chroma, hue), mark


@lru_cache(maxsize=256)
def _sunk(tone: str, panel: str) -> str:
    return mix_oklab(tone, panel, SINK)


def block_paint(
    look: dict | None,
    palette: dict,
    category_color: str | None,
    kind: str = "locked",
    mark: str | None = None,
) -> dict:
    """How one calendar block is drawn: its fill, its ink, and where the category colour goes.

    `category_color` is the fill and `mark` the strong colour of the same category, both as
    `category_paint` gives them for the look. A pale outline vanishes on a light pack, so an outline
    or an edge is drawn with the mark. Edge is Filled with the mark down the block's left side.
    """
    flexible = kind == "flexible"
    neutral = palette["block_flex" if flexible else "block_locked"]
    neutral_ink = palette["block_flex_ink" if flexible else "block_locked_ink"]
    mark = mark or category_color or palette["block_edge"]
    selected = sanitize_look(look)
    mode = effective_look(selected)["blocks"]
    if mode == "outline":
        return {"mode": mode, "fill": palette["grid"], "ink": palette["text"], "outline": mark, "edge": None}
    edge = mark if mode == "edge" else None
    if category_color:
        text = palette["text"]
        # A look of the student's own writes its text as chosen, as the mock-up does, so a colour it does
        # not read on shows on the week, and Readability names it with its Fix.
        own = "custom" in selected
        ink = text if own or contrast(text, category_color) >= AA_TEXT else readable_ink(category_color)
        return {"mode": mode, "fill": category_color, "ink": ink, "outline": None, "edge": edge}
    return {"mode": mode, "fill": neutral, "ink": neutral_ink, "outline": None, "edge": edge}


def block_time_colour(ink: str, fill: str) -> str:
    """A block's times and length: its ink laid `MUTED_INK` over its fill, quieter than the title, or
    as much more of the ink as it takes to read at 4.5 to 1 on the fill."""
    for step in range(round(MUTED_INK * 100), 101, 2):
        muted = mix(ink, fill, step / 100)
        if contrast(muted, fill) >= AA_TEXT:
            return muted
    return ink


def _depth_rules(depth: str, palette: dict) -> str:
    # Qt stylesheets have no shadows. Depth is drawn with edges instead: a hairline for Soft, nothing
    # for None, and for Bold a heavy bottom and right edge, which reads as Poster's offset shadow.
    if depth == "none":
        return "border: none;"
    if depth == "bold":
        strong = palette["hairline_strong"]
        heavy = f"4px solid {strong}"
        return f"border: 2px solid {strong}; border-bottom: {heavy}; border-right: {heavy};"
    return f"border: 1px solid {palette['hairline']};"


def palette_from_tokens(tokens: dict[str, str], base: dict) -> dict:
    """Read a layout's colourway back into a palette, for the design's own page.

    The chrome wears the student's look (decision 3 of 0.17); what sits on a design's page, its
    panels, buttons and scroll bars, wears the design's colourway, so the page is one design and
    not a light rail inside a dark one. A category keeps its hue in every design, in the family the
    design's cards call for.

    The page writes one text colour on the window, its panels and its fields. Where the page's ink
    cannot be read on the design's cards, as Retro's white desktop ink on its grey windows (1.82 to 1),
    the window takes the cards' colour and ink, as Retro's own windows do.
    """
    line = tokens["line"]
    if contrast(tokens["bg_ink"], tokens["surface"]) >= AA_TEXT:
        window, text, muted = tokens["bg"], tokens["bg_ink"], tokens["bg_muted"]
    else:
        window, text, muted = tokens["surface"], tokens["text"], tokens["muted"]
    return {
        **base,
        "family": "dark" if luminance(tokens["surface"]) < 0.2 else "light",
        "window": window,
        "panel": tokens["surface"],
        "field": tokens["surface"],
        "grid": line,
        "text": text,
        "muted": muted,
        "accent": tokens["accent"],
        "accent_ink": tokens["accent_ink"],
        "error": tokens["danger"],
        "hairline": line,
        "hairline_strong": mix(text, tokens["surface"], 0.30),
        "rule": line,
    }


def type_sizes(text: float | str) -> dict[str, str]:
    """Each role of the type scale (decision 4) as a stylesheet writes its size, at the Text knob."""
    return {role: f"{type_pt(role, text):g}pt" for role in TYPE_PT}


def control_rules(palette: dict, radius: int, text: float | str, art: dict[str, str]) -> str:
    """Scrollbars, dropdowns, steppers, check marks, lists, menus and tooltips in the design's colours.

    Left to Fusion they kept its grey chrome in every design, and on a dark palette an unticked box, an
    unselected radio button and the spin arrows could not be seen at all. `art` holds the tick and
    chevron images, which `control_art` in widgets.py draws for the palette.
    """
    pt = type_sizes(text)
    handle = mix(palette["muted"], palette["panel"], 0.55)
    corner = max(4, min(radius, 10))
    item = max(4, corner - 2)
    tick, down, up = art["tick"], art["down"], art["up"]
    return (
        # No margin on the bar itself: a bar with one cannot be laid over its content (below).
        "QScrollBar:vertical { background: transparent; width: 12px; }"
        "QScrollBar:horizontal { background: transparent; height: 12px; }"
        f"QScrollBar::handle:vertical {{ background: {handle}; border-radius: 4px; min-height: 36px; "
        "margin: 2px 4px; }"
        f"QScrollBar::handle:horizontal {{ background: {handle}; border-radius: 4px; min-width: 36px; "
        "margin: 4px 2px; }"
        # Decision 12's overlay bars, which widgets.OverlayBar draws. Given a background here, Qt
        # would draw them itself and give them a strip of their own beside the content.
        'QScrollBar[overlay="true"]:vertical, QScrollBar[overlay="true"]:horizontal { background: none; }'
        f"QScrollBar::handle:hover {{ background: {palette['muted']}; }}"
        f"QScrollBar::handle:pressed {{ background: {palette['accent']}; }}"
        "QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; "
        "background: none; }"
        "QScrollBar::add-page, QScrollBar::sub-page { background: none; }"
        "QAbstractScrollArea::corner { background: transparent; border: none; }"
        "QComboBox { padding-right: 30px; combobox-popup: 0; }"
        "QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; "
        "width: 28px; border: none; background: transparent; }"
        f"QComboBox::down-arrow {{ image: url({down}); width: 14px; height: 14px; }}"
        f"QComboBox::down-arrow:on {{ image: url({up}); }}"
        f"QComboBox QAbstractItemView {{ background: {palette['panel']}; color: {palette['text']}; "
        f"border: 1px solid {palette['hairline_strong']}; padding: 4px; outline: 0; }}"
        f"QComboBox QAbstractItemView::item {{ min-height: {round(type_pt('body', text) * 2) + 8}px; "
        f"padding: 2px 10px; border-radius: {item}px; }}"
        f"QComboBox QAbstractItemView::item:hover {{ background: {palette['hairline']}; }}"
        "QAbstractSpinBox { padding-right: 26px; }"
        "QAbstractSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; "
        "width: 24px; border: none; background: transparent; }"
        "QAbstractSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; "
        "width: 24px; border: none; background: transparent; }"
        f"QAbstractSpinBox::up-arrow {{ image: url({up}); width: 12px; height: 12px; }}"
        f"QAbstractSpinBox::down-arrow {{ image: url({down}); width: 12px; height: 12px; }}"
        "QDateTimeEdit::drop-down { subcontrol-origin: padding; subcontrol-position: center right; "
        "width: 26px; border: none; background: transparent; }"
        f"QDateTimeEdit::down-arrow {{ image: url({down}); width: 14px; height: 14px; }}"
        f"QCalendarWidget QWidget {{ background: {palette['panel']}; color: {palette['text']}; "
        f"alternate-background-color: {palette['panel']}; }}"
        f"QCalendarWidget QToolButton {{ background: transparent; color: {palette['text']}; "
        f"border: none; padding: 4px 8px; font-weight: {WEIGHT_STRONG}; }}"
        # The month's grid is a QFrame too. Padded like a panel, it lost its last column and week: the
        # calendar sizes its columns to the whole view, not to what the padding leaves.
        f"QCalendarWidget QAbstractItemView {{ selection-background-color: {palette['accent']}; "
        f"selection-color: {palette['accent_ink']}; outline: 0; padding: 0; border: none; "
        "border-radius: 0; }"
        f"QCalendarWidget QAbstractItemView:disabled {{ color: {palette['muted']}; }}"
        "QCheckBox, QRadioButton { background: transparent; spacing: 8px; }"
        f"QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; "
        f"border: 1px solid {palette['muted']}; background: {palette['field']}; }}"
        "QCheckBox::indicator { border-radius: 4px; }"
        "QRadioButton::indicator { border-radius: 9px; }"
        f"QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ "
        f"border-color: {palette['accent']}; }}"
        f"QCheckBox::indicator:checked {{ background: {palette['accent']}; "
        f"border-color: {palette['accent']}; image: url({tick}); }}"
        f"QRadioButton::indicator:checked {{ background: {palette['field']}; "
        f"border: 5px solid {palette['accent']}; width: 8px; height: 8px; }}"
        f"QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ "
        f"background: {palette['hairline']}; border-color: {palette['hairline_strong']}; }}"
        # A list's ticks are the same box as a check box's, not Qt's own (decision 23 of 0.17).
        f"QAbstractItemView::indicator {{ width: 16px; height: 16px; border-radius: 4px; "
        f"border: 1px solid {palette['muted']}; background: {palette['field']}; }}"
        f"QAbstractItemView::indicator:checked {{ background: {palette['accent']}; "
        f"border-color: {palette['accent']}; image: url({tick}); }}"
        "QListWidget, QListView { outline: 0; }"
        f"QListWidget::item:hover, QListView::item:hover {{ background: {palette['hairline']}; }}"
        f"QListWidget::item:selected, QListView::item:selected {{ background: {palette['accent']}; "
        f"color: {palette['accent_ink']}; }}"
        f"QMenu {{ background: {palette['panel']}; color: {palette['text']}; "
        f"border: 1px solid {palette['hairline_strong']}; border-radius: {corner}px; padding: 6px; }}"
        f"QMenu::item {{ border-radius: {item}px; }}"
        f"QMenu::item:selected {{ background: {palette['accent']}; color: {palette['accent_ink']}; }}"
        f"QMenu::item:disabled {{ color: {palette['muted']}; }}"
        f"QMenu::separator {{ height: 1px; background: {palette['hairline']}; margin: 6px 8px; }}"
        f"QLabel#menuHeading {{ color: {palette['muted']}; font-weight: {WEIGHT_STRONG}; "
        f"font-size: {pt['caption']}; padding: 6px 12px 2px 12px; }}"
        # A tooltip does not take the window's text size by itself, so at Large it stayed small.
        f"QToolTip {{ background: {palette['text']}; color: {palette['window']}; border: none; "
        f"padding: 5px 9px; border-radius: {item}px; font-size: {pt['body']}; }}"
        f"QProgressBar {{ background: {palette['hairline']}; border: none; border-radius: 4px; "
        f"max-height: 8px; text-align: center; color: transparent; }}"
        f"QProgressBar::chunk {{ background: {palette['accent']}; border-radius: 4px; }}"
        f"QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus, QPlainTextEdit:focus {{ "
        f"border: 1px solid {palette['accent']}; }}"
        # A switch is a check box whose box is a pill with a knob, drawn whole by `control_art`.
        'QCheckBox[switch="true"] { spacing: 10px; }'
        'QCheckBox[switch="true"]::indicator { width: 34px; height: 20px; border: none; '
        f"background: transparent; border-radius: 10px; image: url({art['switch_off']}); }}"
        f'QCheckBox[switch="true"]::indicator:checked {{ image: url({art["switch_on"]}); }}'
        f'QCheckBox[switch="true"]::indicator:disabled {{ image: url({art["switch_off_off"]}); }}'
        f'QCheckBox[switch="true"]::indicator:checked:disabled {{ image: url({art["switch_on_off"]}); }}'
    )


def settings_rules(palette: dict, radius: int, text: float | str, pad: int, depth: str) -> str:
    """Settings as a page: a list of sections on the left, cards on the right, and segmented choices.
    Dialogs laid out in cards use the same card.

    A segmented control is a sunken track with the chosen segment raised on it, so two or three
    choices read as one control with one answer.
    """
    pt = type_sizes(text)
    edges = _depth_rules(depth, palette)
    card_radius = max(radius, 10)
    track = mix(palette["text"], palette["panel"], 0.07)
    chosen_edge = "none" if depth == "none" else f"1px solid {palette['hairline_strong']}"
    # The chosen section is marked by a bar in the accent; its row takes only a little of the text.
    selected = mix(palette["text"], palette["panel"], 0.06)
    # Nothing runs under the footer: a hairline above it ends the page, but on a look with no
    # lines at all.
    footer_line = "none" if depth == "none" else f"1px solid {palette['hairline']}"
    return (
        f"QWidget#settingsPage {{ background: {palette['window']}; }}"
        # Bare widgets inside a card, which the app-wide rule would paint as a band of page colour.
        "QWidget#settingsRow, QWidget#settingsBody, QWidget#settingsFooter, QWidget#prefFineHost, "
        "QWidget#prefReminderControls, QFrame[designs=\"true\"] { background: transparent; "
        "border: none; padding: 0; }"
        f"QWidget#settingsRail {{ background: {palette['panel']}; }}"
        "QScrollArea#settingsScroll { background: transparent; border: none; padding: 0; border-radius: 0; }"
        f"QListWidget#prefsNav {{ background: {palette['panel']}; border: none; border-radius: 0; "
        "padding: 16px 4px; }"
        f"QListWidget#prefsNav::item {{ color: {palette['muted']}; "
        f"padding: {pad + 4}px 8px {pad + 4}px 7px; border-left: 3px solid transparent; border-radius: 0; }}"
        f"QListWidget#prefsNav::item:hover {{ background: {palette['hairline']}; color: {palette['text']}; }}"
        f"QListWidget#prefsNav::item:selected {{ background: {selected}; color: {palette['text']}; "
        f"border-left: 3px solid {palette['accent']}; font-weight: {WEIGHT_STRONG}; }}"
        f"QWidget#settingsFooter {{ border-top: {footer_line}; }}"
        f"QLabel#settingsTitle {{ font-size: {pt['title']}; font-weight: {WEIGHT_STRONG}; }}"
        f"QFrame#settingsCard, QFrame#dialogCard {{ background: {palette['panel']}; "
        f"border-radius: {card_radius}px; padding: 0; {edges} }}"
        "QLabel#prefsHeading, QLabel#layoutMainHeading, QLabel#layoutDayHeading, QLabel#cardTitle, "
        "QLabel#lookEditorTitle, QLabel#lookGroupName { "
        f"font-size: {pt['heading']}; font-weight: {WEIGHT_STRONG}; color: {palette['text']}; }}"
        # The look editor, a page of Settings: its notes, values, tag and small buttons are captions;
        # the names of its settings, its sample blocks and its colour pairs are strong.
        "QLabel#lookNote, QLabel#lookOut, QLabel#lookEditorState, QLabel#lookMessageText, QLabel#lookTag, "
        f'QCheckBox[exact="true"], QPushButton[small="true"] {{ font-size: {pt["caption"]}; }}'
        "QLabel#lookFieldLabel, QLabel#lookCategoryName, QLabel#lookTag, QLabel#lookChip, QLabel#lookPair { "
        f"font-weight: {WEIGHT_STRONG}; }}"
        "QLabel#settingsCardNote, QLabel#cardNote, QLabel#settingsExperimental, QLabel#prefPlanningNote, "
        "QLabel#prefDndNote, "
        "QLabel#prefTrayNote, QLabel#prefBlockSongNote, QLabel#prefToneNote, QLabel#reminderLimits { "
        f"color: {palette['muted']}; }}"
        f"QLabel#settingsExperimental {{ font-weight: {WEIGHT_STRONG}; margin-top: 6px; }}"
        f'QFrame[segmented="true"] {{ background: {track}; border: none; '
        f"border-radius: {max(radius, 6) + 2}px; padding: 0; }}"
        f'QPushButton[segment="true"] {{ background: transparent; color: {palette["muted"]}; border: none; '
        # One weight whether chosen or not: a bolder chosen segment was wider than the room it was given.
        f"border-radius: {max(radius, 6)}px; padding: {max(pad - 2, 3)}px {pad + 8}px; "
        f"font-weight: {WEIGHT_STRONG}; min-height: 0; }}"
        f'QPushButton[segment="true"]:hover {{ color: {palette["text"]}; }}'
        f'QPushButton[segment="true"]:checked {{ background: {palette["field"]}; color: {palette["text"]}; '
        f"border: {chosen_edge}; }}"
        'QPushButton[segment="true"]:disabled { background: transparent; '
        f'color: {palette["hairline_strong"]}; }}'
        # Still raised, so a choice that cannot be changed here says which it is.
        f'QPushButton[segment="true"]:checked:disabled {{ background: {palette["field"]}; '
        f'color: {palette["muted"]}; border: {chosen_edge}; }}'
    )


def _rgba(colour: str, alpha: float) -> str:
    red, green, blue = _channels(colour)
    return f"rgba({red}, {green}, {blue}, {round(alpha * 255)})"


DISABLED = 0.4


def dialog_rules(palette: dict, card_radius: int, depth: str, quiet_edge: str) -> str:
    """Dialogs (decision 23 of 0.17): the body is the card, a sheet's card is rounded as a sheet, and a
    button that cannot be pressed yet keeps its shape at 40 %, not a grey slab that looked broken."""
    edges = _depth_rules(depth, palette)
    sheet = RADIUS_SHEET if card_radius else 0
    return (
        # A sheet's window is only room for its shadow; the card is what is seen.
        'QDialog[sheet="true"] { background: transparent; }'
        f"QFrame#sheetCard {{ background: {palette['panel']}; border-radius: {sheet}px; padding: 0; "
        f"{edges} }}"
        'QWidget[bare="true"], QScrollArea[bare="true"] { background: transparent; border: none; '
        "padding: 0; border-radius: 0; }"
        'QScrollArea[bare="true"] > QWidget#qt_scrollarea_viewport { background: transparent; }'
        f"QDialog QPushButton:disabled {{ background: {_rgba(palette['accent'], DISABLED)}; "
        f"color: {_rgba(palette['accent_ink'], DISABLED)}; }}"
        'QDialog QPushButton[quiet="true"]:disabled, '
        'QWidget#settingsPage QPushButton[quiet="true"]:disabled '
        f"{{ {quiet_edge} color: {_rgba(palette['text'], DISABLED)}; }}"
    )


def setup_rules(palette: dict, radius: int, text: float | str, pad: int, depth: str) -> str:
    """First-run setup: a rail of steps beside one question at a time, and cards to pick from.

    Groups, chips and Back take the depth's edges like every other control. A card keeps a ring of
    one width whether or not it is picked, so picking one never nudges its picture: the ring is the
    accent when picked and, except on a look with no shadows, a soft line otherwise. Sizes and weights are the
    type scale's (decision 4 of 0.17).
    """
    edges = _depth_rules(depth, palette)
    strong = f"font-weight: {WEIGHT_STRONG};"
    heading = f"font-size: {type_pt('heading', text)}pt; {strong}"
    card_radius = max(radius, 10)
    ring = "transparent" if depth == "none" else mix(palette["hairline_strong"], palette["panel"], 0.6)
    # A card is larger than a control, so it is lifted with the text colour, never the accent.
    lift = mix(palette["text"], palette["panel"], 0.04)
    quiet = (
        "setupQuiet", "setupSkip", "setupSkipAll", "setupOwnLook", "setupAddActivity", "setupAddHomework",
        "setupSuggest", "setupChange", "setupFineTune",
    )
    quiet_rule = ", ".join(f"QPushButton#{name}" for name in quiet)
    quiet_hover = ", ".join(f"QPushButton#{name}:hover" for name in quiet)
    pills = "QPushButton#setupChip, QPushButton#setupDay, QPushButton#setupStudyChip"
    pills_hover = "QPushButton#setupChip:hover, QPushButton#setupDay:hover, QPushButton#setupStudyChip:hover"
    return (
        f"QWidget#setupRail {{ background: {palette['panel']}; }}"
        f"QWidget#setupNav {{ background: {palette['window']}; }}"
        # The rows inside the pages are bare QWidgets, which the app-wide rule paints in the page
        # colour. On a card that is a band of background across the middle of it.
        f"QWidget#setupRow, QWidget#setupBody {{ background: transparent; border: none; padding: 0; }}"
        f"QScrollArea#setupScroll {{ background: transparent; border: none; padding: 0; }}"
        f"QLabel#setupBrand {{ {heading} color: {palette['text']}; }}"
        f"QPushButton#setupRailItem {{ background: transparent; color: {palette['muted']}; border: none; "
        f"text-align: left; padding: {pad + 2}px {pad}px; font-weight: {WEIGHT_REGULAR}; min-height: 0; }}"
        f"QPushButton#setupRailItem:hover {{ color: {palette['text']}; }}"
        f"QPushButton#setupRailItem[done=\"true\"] {{ color: {palette['text']}; }}"
        f"QPushButton#setupRailItem[current=\"true\"] {{ color: {palette['text']}; {strong} }}"
        f"QPushButton#setupRailItem:disabled {{ background: transparent; "
        f"color: {mix(palette['muted'], palette['panel'], 0.55)}; }}"
        f"QFrame#setupRailMarker {{ background: {palette['accent']}; border: none; padding: 0; "
        f"border-radius: 1px; }}"
        f"QLabel#setupTitle {{ font-size: {type_pt('title', text)}pt; {strong} }}"
        f"QLabel#setupNote {{ color: {palette['muted']}; font-size: {type_pt('body', text)}pt; }}"
        f"QLabel#setupHint, QLabel#setupFieldLabel {{ color: {palette['muted']}; }}"
        # A margin on a label turns on its indent, which set each section 5 pixels right of the title.
        f"QLabel#setupSection {{ {heading} margin-top: {SPACING[1]}px; qproperty-indent: 0; }}"
        f"QLabel#setupError {{ color: {palette['error']}; {strong} }}"
        f"QLabel#setupSummaryName {{ {strong} }}"
        f"QFrame#setupChoice {{ background: {palette['panel']}; border: 2px solid {ring}; "
        f"border-radius: {card_radius}px; padding: 0; }}"
        f"QFrame#setupChoice:hover {{ background: {lift}; }}"
        f"QFrame#setupChoice:focus {{ border-color: {mix(palette['accent'], palette['panel'], 0.5)}; }}"
        f"QFrame#setupChoice[selected=\"true\"] {{ border-color: {palette['accent']}; background: {lift}; }}"
        f"QLabel#setupChoiceName {{ {heading} }}"
        f"QLabel#setupChoiceNote {{ color: {palette['muted']}; }}"
        f"QFrame#setupGroup {{ background: {palette['panel']}; border-radius: {card_radius}px; {edges} }}"
        f"{pills} {{ background: {palette['field']}; color: {palette['text']}; {edges} "
        f"border-radius: 14px; padding: 4px 12px; font-weight: {WEIGHT_REGULAR}; min-height: 0; }}"
        f"QPushButton#setupDay {{ padding: 4px 9px; }}"
        f"{pills_hover} {{ background: {mix(palette['accent'], palette['field'], 0.14)}; }}"
        f"QPushButton#setupChip:checked, QPushButton#setupDay:checked {{ background: {palette['accent']}; "
        f"color: {palette['accent_ink']}; }}"
        f"{quiet_rule} {{ background: transparent; color: {palette['accent']}; border: none; "
        f"padding: {pad}px 2px; font-weight: {WEIGHT_STRONG}; min-height: 0; }}"
        f"{quiet_hover} {{ color: {palette['text']}; text-decoration: underline; }}"
        f"QPushButton#setupAddActivity:disabled, QPushButton#setupAddHomework:disabled {{ "
        f"background: transparent; color: {palette['muted']}; }}"
        # Level with the name beside it, which a button's padding pushed a few pixels below.
        f"QPushButton#setupChange {{ padding: 0 2px; }}"
        f"QPushButton#setupBack {{ background: transparent; color: {palette['text']}; {edges} }}"
        f"QPushButton#setupBack:hover {{ background: {mix(palette['accent'], palette['window'], 0.1)}; }}"
        f"QPushButton#setupNext {{ padding: {pad}px {pad * 3}px; {strong} }}"
        # Play is an icon on its own, with a quiet ground under the pointer instead of an underline.
        f"QPushButton#setupPlay {{ background: transparent; border: none; padding: {SPACING[0]}px; "
        f"border-radius: {radius}px; min-height: 0; }}"
        f"QPushButton#setupPlay:hover {{ background: {palette['hairline']}; }}"
    )


def auth_rules(palette: dict, knobs: dict, radius: int, card_radius: int) -> str:
    """Sign in and the recovery codes (decision 25 of 0.17): the wordmark on the page above one card
    rounded as a sheet, one heading, the small print as links, and the codes set as code.

    A stylesheet has no shadows; window.py lifts the card with the large one.
    """
    text = knobs["text"]
    edges = _depth_rules(knobs["depth"], palette)
    inset = SPACING[5] if knobs["density"] == "comfortable" else SPACING[4]
    title = f"font-size: {type_pt('title', text)}pt; font-weight: {WEIGHT_STRONG};"
    sheet = RADIUS_SHEET if card_radius else 0
    ring = mix(palette["accent"], palette["field"], 0.4)
    links = "QPushButton#authSwitch, QPushButton#forgotPassword"
    return (
        f"QWidget#authCard {{ background: {palette['panel']}; border-radius: {sheet}px; "
        f"padding: {inset}px; {edges} }}"
        f"QLabel#authBrand {{ {title} color: {palette['text']}; }}"
        f"QLabel#authHeading {{ {title} }}"
        f"QLabel#authNote {{ color: {palette['muted']}; }}"
        f"QLabel#passwordHint, QLabel#usernameHint {{ color: {palette['muted']}; "
        f"font-size: {type_pt('caption', text)}pt; }}"
        # Inter with figures of one width and a little air between letters reads as code.
        f"QLabel#recoveryList {{ background: {mix(palette['text'], palette['panel'], 0.05)}; "
        f"border-radius: {radius}px; padding: {SPACING[2]}px {SPACING[3]}px; letter-spacing: 0.5px; }}"
        f"QToolButton#passwordReveal {{ background: transparent; border: none; padding: 0; "
        f"border-radius: {radius}px; }}"
        f"QToolButton#passwordReveal:hover {{ background: {palette['hairline']}; }}"
        f"QToolButton#passwordReveal:focus {{ border: 2px solid {ring}; }}"
        f"{links} {{ background: transparent; color: {palette['accent']}; border: none; "
        f"padding: {SPACING[0]}px 0; min-height: 0; }}"
        f"QPushButton#authSwitch:hover, QPushButton#forgotPassword:hover {{ color: {palette['text']}; "
        "text-decoration: underline; }"
    )


def help_rules(palette: dict, text: float | str, radius: int, depth: str) -> str:
    """Help's shortcuts as keycaps, a key's bottom edge a little heavier, and About's name beside the
    logo (decision 27 of 0.17). A look with no shadows draws no lines, so there a key is a tinted
    tile."""
    caption = f"font-size: {type_pt('caption', text)}pt;"
    line = palette["hairline_strong"]
    if depth == "none":
        cap = f"background: {mix(palette['text'], palette['window'], 0.08)}; border: none;"
    else:
        cap = f"background: {palette['panel']}; border: 1px solid {line}; border-bottom: 2px solid {line};"
    return (
        f"QLabel#aboutVersion {{ font-size: {type_pt('title', text)}pt; font-weight: {WEIGHT_STRONG}; }}"
        f"QLabel#helpScreenName {{ font-weight: {WEIGHT_STRONG}; }}"
        "QWidget#helpKey { background: transparent; }"
        f"QLabel#helpKeycap {{ {cap} color: {palette['text']}; {caption} font-weight: {WEIGHT_STRONG}; "
        f"border-radius: {radius}px; padding: 1px 6px; min-width: 8px; }}"
        # Level with the letters on the caps beside them, which sit below a border and a pixel of padding.
        f"QLabel#helpKeyJoin {{ color: {palette['muted']}; {caption} padding-top: 2px; }}"
    )


def _veil(colour: str, amount: float) -> str:
    """`colour` at `amount` opacity, laid over whatever the control sits on."""
    red, green, blue = _channels(colour)
    return f"rgba({red}, {green}, {blue}, {round(amount * 255)})"


def button_rules(palette: dict, pad: int, radius: int, depth: str, button_min: str) -> str:
    """Decision 11: one set of states dresses every button in the app. Primary is filled in the accent,
    secondary is accent words on a tenth of the accent, quiet is words in the text colour. Each takes
    6 % of the text colour on hover and 10 % when pressed; a disabled one shows at 40 %; the key that
    reached it draws a 2-pixel ring at 40 % of the accent (the whole accent in High contrast), which
    a click does not (see `widgets.KeyFocus`).

    The ring is the button's own edge, kept clear at rest, so focusing a button moves nothing. A
    stylesheet has no opacity, so the 40 % is each colour mixed 40 % into the page.
    """
    text, accent, ink, page = palette["text"], palette["accent"], palette["accent_ink"], palette["window"]
    danger = palette["error"]
    contrast_look = palette.get("family") == "contrast"
    tint = "transparent" if contrast_look else mix(accent, page, 0.10)
    ring = accent if contrast_look else mix(accent, page, 0.4)
    # Poster's heavy edges are its own look; every other button is its fill and its words.
    hard = depth == "hard" and not contrast_look
    rest = _depth_rules(depth, palette) if hard else "border: 2px solid transparent;"
    kinds = (
        ("QPushButton", accent, ink, WEIGHT_STRONG),
        ('QPushButton[secondary="true"]', tint, accent, WEIGHT_STRONG),
        ('QPushButton[danger="true"]', danger, readable_ink(danger), WEIGHT_STRONG),
    )
    rules = [f"QPushButton {{ padding: {pad}px {pad * 2}px; border-radius: {radius}px; {rest}{button_min} }}"]
    for selector, fill, words, weight in kinds:
        solid = page if fill == "transparent" else fill
        rules += [
            f"{selector} {{ background: {fill}; color: {words}; font-weight: {weight}; }}",
            f"{selector}:hover {{ background: {mix(text, solid, 0.06)}; }}",
            f"{selector}:pressed {{ background: {mix(text, solid, 0.10)}; }}",
            f"{selector}:disabled {{ background: {mix(solid, page, 0.4)}; color: {mix(words, page, 0.4)}; }}",
        ]
    if contrast_look:
        # A tint of yellow on black is mud, so High contrast outlines a secondary button instead.
        rules.append(f'QPushButton[secondary="true"] {{ border-color: {accent}; }}')
    rules += [
        f'QPushButton[quiet="true"] {{ background: transparent; color: {text}; '
        f"font-weight: {WEIGHT_REGULAR}; }}",
        f'QPushButton[quiet="true"]:hover {{ background: {_veil(text, 0.06)}; }}',
        f'QPushButton[quiet="true"]:pressed {{ background: {_veil(text, 0.10)}; }}',
        f'QPushButton[quiet="true"]:disabled {{ background: transparent; color: {mix(text, page, 0.4)}; }}',
        f'QPushButton[keyfocus="true"]:focus {{ border-color: {ring}; }}',
    ]
    return "".join(rules)


VIEW_BUTTONS = ("viewDay", "viewWeek", "viewMonth", "viewMyDay")
BAR_BUTTONS = ", ".join(
    f"QPushButton#{name}"
    for name in (
        "prevWeek", "nextWeek", "todayWeek", "addButton", "addArrow", "solveButton", "retrySave",
        "moreButton", "settingsGear",
    )
)
ZOOM_PILL_PX = 24


def top_bar_rules(palette: dict, pad: int, depth: str, art: dict[str, str] | None) -> str:
    """Decision 11's top bar, as the mock-up draws it. The arrows, Today, More and the gear are quiet
    buttons in the text colour. Add and its chevron are one pill split by a line of the accent's ink.
    The view control is a pill track with the chosen view raised on it by the small shadow, painted by
    `widgets.SegmentTrack` from the colours given here; High contrast keeps its readable control, the
    track outlined in white and the chosen view filled yellow. The zoom is a small "− +" pill in the
    hours' corner (decision 12)."""
    text, muted, page = palette["text"], palette["muted"], palette["window"]
    contrast_look = palette.get("family") == "contrast"
    ring = palette["accent"] if contrast_look else mix(palette["accent"], page, 0.4)
    track = page if contrast_look else mix(text, page, 0.06)
    chosen = palette["accent"] if contrast_look else palette["panel"]
    chosen_words = palette["accent_ink"] if contrast_look else text
    outline = text if contrast_look else track
    lifted = depth == "soft" and not contrast_look
    dark = palette.get("axis") == "dark"
    shade = round(255 * (SHADOW_SMALL.dark_opacity if dark else SHADOW_SMALL.opacity)) if lifted else 0
    divider = mix(palette["accent_ink"], palette["accent"], 0.3)
    more = art.get("more") if art else None
    pill_edge = palette["hairline_strong"] if contrast_look else palette["hairline"]
    quiet_ink = text if contrast_look else muted

    def views(state: str = "") -> str:
        return ", ".join(f"QPushButton#{name}{state}" for name in VIEW_BUTTONS)

    focused = views('[keyfocus="true"]:focus')
    menu = (
        # The chevron's room is added to the width by Qt; the padding only keeps it off the word.
        f"QPushButton#moreButton {{ padding-right: {pad + 14}px; }}"
        f"QPushButton#moreButton::menu-indicator {{ image: url({more}); subcontrol-origin: padding; "
        f"subcontrol-position: center right; width: 14px; height: 14px; right: {pad}px; }}"
        if more
        else ""
    )
    return (
        f"QFrame#segments {{ background: transparent; border: none; border-radius: 0; padding: 3px; "
        f"alternate-background-color: {track}; selection-background-color: {chosen}; color: {outline}; "
        f"qproperty-shade: {shade}; }}"
        f"{views()} {{ background: transparent; color: {quiet_ink}; font-weight: {WEIGHT_REGULAR}; "
        # Inside a track 3 pixels in from the bar's other controls: a view's own padding is that much
        # less, or the track squeezed it and cut the tails off "Day" and "My day".
        f"border: 2px solid transparent; padding: {max(pad - 7, 0)}px {pad + 2}px; min-height: 0; }}"
        f"{views(':hover')} {{ background: transparent; color: {text}; }}"
        f"{views(':checked')} {{ background: transparent; color: {chosen_words}; "
        f"font-weight: {WEIGHT_STRONG}; }}"
        f"{focused} {{ border-color: {ring}; }}"
        # The bar's controls are 32 pixels tall at Normal, as the mock-up's, not a dialog's 40.
        f"{BAR_BUTTONS} {{ padding-top: {max(pad - 4, 1)}px; padding-bottom: {max(pad - 4, 1)}px; }}"
        "QPushButton#prevWeek, QPushButton#nextWeek, QPushButton#settingsGear { "
        f"padding-left: {max(pad - 2, 2)}px; padding-right: {max(pad - 2, 2)}px; }}"
        # Words-only controls sit as close to their words as the mock-up's: a filled button's
        # padding made More 108 pixels wide and pushed a two-month title into its short form.
        f"QPushButton#todayWeek, QPushButton#moreButton {{ padding-left: {pad}px; }}"
        f"QPushButton#todayWeek {{ padding-right: {pad}px; }}"
        "QPushButton#addButton { border-top-right-radius: 0; border-bottom-right-radius: 0; "
        f"padding-right: {pad + 2}px; }}"
        f"QPushButton#addArrow {{ padding: {pad}px {pad // 2 + 2}px; border-top-left-radius: 0; "
        f"border-bottom-left-radius: 0; border-left-width: 1px; border-left-color: {divider}; }}"
        "QPushButton#addArrow::menu-indicator { image: none; width: 0; }"
        f"{menu}"
        f'QWidget[zoomPill="true"] {{ background: {palette["panel"]}; border-width: 1px; '
        f"border-style: solid; border-color: {pill_edge}; border-radius: {ZOOM_PILL_PX // 2}px; }}"
        f"QWidget#zoomDivider {{ background: {pill_edge}; }}"
        f'QPushButton[zoom="true"] {{ background: transparent; color: {quiet_ink}; border: none; '
        f"border-radius: {ZOOM_PILL_PX // 2 - 1}px; padding: 0; min-height: 0; }}"
        f'QPushButton[zoom="true"]:hover {{ background: {_veil(text, 0.06)}; }}'
        f'QPushButton[zoom="true"]:pressed {{ background: {_veil(text, 0.10)}; }}'
        f'QPushButton[zoom="true"]:disabled {{ background: transparent; '
        f'color: {palette["hairline_strong"]}; }}'
        f'QPushButton[zoom="true"][keyfocus="true"]:focus {{ border: 2px solid {ring}; }}'
    )


def pack_stylesheet(
    pack: object,
    system_dark: bool,
    look: dict | None,
    accent: object = "default",
    palette: dict | None = None,
    art: dict[str, str] | None = None,
) -> str:
    palette = palette if palette is not None else resolved_palette(pack, system_dark, look, accent)
    knobs = effective_look(look)
    card = DENSITY_PAD[knobs["density"]]
    pad = CONTROL_PAD[knobs["density"]]
    measures = look_measures(look)
    # The Text knob's step, or a custom look's own scale, which the type scale takes either way.
    scale = measures["scale"]
    pt = type_sizes(scale)
    family = measures["body"]
    radius, card_radius = measures["radius"], measures["card_radius"]
    edges = _depth_rules(knobs["depth"], palette)
    item_h = 36 if knobs["text"] == "large" else 22
    button_min = f" min-height: {item_h}px;" if knobs["text"] == "large" else ""
    field_min = FIELD_MIN_PX[knobs["text"]]
    # A flat look has no edges, so a plain button is told from its words by a faint fill instead.
    if knobs["depth"] == "none":
        quiet_edge = f"background: {palette['hairline']}; border: none;"
    else:
        quiet_edge = f"background: transparent; border: 1px solid {palette['hairline_strong']};"
    return (
        f"QMainWindow, QDialog, QWidget {{ background: {palette['window']}; color: {palette['text']}; "
        f"font-family: {family}; font-size: {pt['body']}; }}"
        f"QFrame, QGroupBox, QTableWidget, QListWidget {{ background: {palette['panel']}; "
        f"color: {palette['text']}; padding: {card}px; border-radius: {card_radius}px; {edges} }}"
        # Lists, tables and scroll areas are frames too, but their padding is room around rows.
        f"QAbstractScrollArea {{ padding: {pad}px; }}"
        # A group's title sits in the space above its frame. Without the room it was drawn on the
        # frame line, over the first row of what it names.
        f"QGroupBox {{ margin-top: {round(type_pt('body', knobs['text']) * 1.9) + 4}px; }}"
        f"QGroupBox::title {{ subcontrol-origin: margin; left: {card + 4}px; padding: 0 4px; }}"
        f"QLineEdit, QComboBox, QSpinBox, QTimeEdit, QDateTimeEdit {{ background: {palette['field']}; "
        f"color: {palette['text']}; padding: {pad}px; border-radius: {radius}px; "
        f"min-height: {field_min}px; {edges} }}"
        f"QPlainTextEdit {{ background: {palette['field']}; color: {palette['text']}; "
        f"padding: {pad}px; border-radius: {radius}px; {edges} }}"
        f"QTableWidget {{ gridline-color: {palette['hairline']}; "
        f"selection-background-color: {palette['accent']}; selection-color: {palette['accent_ink']}; }}"
        # Headers and the view stack are QFrames too. Left to the panel rule, each header is padded and
        # rounded inside a fixed height, which slices its text in half, and the calendar sits in two boxes.
        f"QHeaderView, QStackedWidget {{ background: transparent; border: none; "
        f"padding: 0; border-radius: 0; }}"
        # The week's hours paint their own background; as a frame the scroll area boxed them twice.
        f"QScrollArea#weekScroll, QScrollArea#dayScroll, QScrollArea#helpScroll {{ background: transparent; "
        f"border: none; padding: 0; border-radius: 0; }}"
        # What follows the pointer while something is carried: a pill, readable over any calendar.
        f"QLabel#heldChip {{ background: {palette['accent']}; color: {palette['accent_ink']}; "
        f"padding: 3px 10px; border-radius: 10px; }}"
        f'QLabel#heldChip[refused="true"] {{ background: {palette["panel"]}; color: {palette["error"]}; '
        f"{edges} }}"
        f"QHeaderView::section, QTableCornerButton::section {{ background: {palette['panel']}; "
        f"color: {palette['muted']}; padding: 2px 6px; border: none; }}"
        # QLabel is a QFrame in Qt, so without this every label, even an empty one, is drawn as a panel.
        f"QLabel {{ background: transparent; border: none; padding: 0; }}"
        # One filled button per dialog: the answer. Cancel and its kind are drawn plain beside it, and
        # a button that destroys something takes the error colour.
        + button_rules(palette, pad, radius, knobs["depth"], button_min)
        # The rule above that gives every widget the text colour also keeps it when the widget is off,
        # so reminder settings looked live while reminders were off.
        + f"QWidget#prefReminderControls QWidget:disabled {{ color: {palette['muted']}; }}"
        f"QPushButton#deleteBlock, QPushButton#deleteHomework, QPushButton#deleteAccount {{ "
        f"background: transparent; "
        f"color: {palette['error']}; border: none; "
        f"padding: {pad}px 2px; font-weight: {WEIGHT_STRONG}; min-height: 0; }}"
        f"QPushButton#deleteBlock:hover, QPushButton#deleteHomework:hover, "
        f"QPushButton#deleteAccount:hover {{ text-decoration: underline; }}"
        # Homework that still needs a time, to be dragged onto the hours: it looks like homework, not
        # like a button that does something when pressed. Its edge is homework's own colour; red would
        # say something is wrong, and nothing is.
        f"QPushButton[tray=\"true\"] {{ background: {palette['panel']}; color: {palette['text']}; "
        f"{edges} border-left: 4px solid {category_paint('assignments', palette)[1]}; text-align: left; }}"
        f"QMenu::item {{ min-height: {item_h}px; padding: {pad}px {pad * 2}px; }}"
        f"QLabel#nowNext {{ font-weight: {WEIGHT_STRONG}; }}"
        f"QLabel#focusTask {{ font-weight: {WEIGHT_STRONG}; }}"
        f"QLabel#focusPhase {{ color: {palette['muted']}; }}"
        f"QLabel#focusTime {{ font-family: {MONO_FAMILY}; font-weight: {WEIGHT_STRONG}; }}"
        f"QLabel#recoveryStatus {{ color: {palette['error']}; }}"
        # How many recovery codes are left is an ordinary fact until none are.
        f"QLabel#recoveryCount {{ color: {palette['muted']}; }}"
        f'QLabel#recoveryCount[problem="true"] {{ color: {palette["error"]}; font-weight: {WEIGHT_STRONG}; }}'
        f"QLabel#validationError {{ color: {palette['error']}; font-weight: {WEIGHT_STRONG}; }}"
        f"QLabel#homeworkEstimateHint {{ color: {palette['muted']}; }}"
        f"QLabel#homeworkEstimateHint[problem=\"true\"] {{ color: {palette['error']}; "
        f"font-weight: {WEIGHT_STRONG}; }}"
        # The way in is a button; the way to a new account is small print, so it is drawn as a link.
        f"QLabel#updateHeading {{ font-size: {pt['heading']}; font-weight: {WEIGHT_STRONG}; }}"
        f"QLabel#updateDetail, QLabel#updateStatus {{ color: {palette['muted']}; }}"
        # The first-week card sits on top of the week rather than in a layout, so it has to read as
        # something laid over the calendar rather than printed onto it.
        # The week you are on, said once and said large.
        f"QLabel#weekTitle {{ font-size: {pt['title']}; font-weight: {WEIGHT_STRONG}; "
        f"color: {palette['text']}; }}"
        # One filled button on the page: the thing the app is for.
        f"QLabel#blockDurationLine {{ color: {palette['muted']}; }}"
        f"QLabel#blockDurationLine[problem=\"true\"] {{ color: {palette['error']}; "
        f"font-weight: {WEIGHT_STRONG}; }}"
        + help_rules(palette, scale, radius, knobs["depth"])
        + top_bar_rules(palette, pad, knobs["depth"], art)
        + setup_rules(palette, radius, scale, pad, knobs["depth"])
        + settings_rules(palette, radius, scale, pad, knobs["depth"])
        + auth_rules(palette, knobs, radius, card_radius)
        + dialog_rules(palette, card_radius, knobs["depth"], quiet_edge)
        + f"QPushButton#updateSkip {{ background: transparent; "
        f"color: {palette['accent']}; border: none; padding: {pad}px 0; "
        f"font-size: {pt['caption']}; text-align: left; min-height: 0; }}"
        f"QPushButton#updateSkip:hover {{ color: {palette['text']}; text-decoration: underline; }}"
        # A ringing alarm is the one thing in the app that has to be read from across a room.
        f"QLabel#alarmTitle {{ font-size: {pt['title']}; font-weight: {WEIGHT_STRONG}; }}"
        f"QLabel#alarmDetail {{ font-size: {pt['heading']}; color: {palette['muted']}; }}"
        # A new account's empty week.
        f"QLabel#emptyWeekHeading {{ font-size: {pt['title']}; font-weight: {WEIGHT_STRONG}; }}"
        f"QLabel#emptyWeekLine {{ color: {palette['muted']}; font-size: {pt['body']}; }}"
        f"QPushButton#emptyWeekAdd {{ font-weight: {WEIGHT_STRONG}; "
        f"padding: {pad + 2}px {pad * 3}px; }}"
        f"QLabel#weekSideLine {{ font-weight: {WEIGHT_STRONG}; }}"
        + (_contrast_rules(palette) if palette.get("family") == "contrast" else "")
        + planner_rules(palette, scale, pad, radius, card_radius, edges)
        # Headings in the look's heading face: Newsreader in the Serif font, over Inter.
        + ", ".join(f"QLabel#{name}" for name in HEADING_NAMES)
        + f" {{ font-family: {measures['heading']}; }}"
    ) + (control_rules(palette, radius, scale, art) if art is not None else "") + overlay_rules(
        palette, knobs, pad, card_radius
    )


def hover_tint(palette: dict, share: float = 0.06) -> str:
    """A row or a text button under the pointer: the text laid thinly over the card. High contrast
    takes more, as 6 % of white on black could not be seen."""
    amount = max(share, HIGH_CONTRAST_HOVER) if palette.get("family") == "contrast" else share
    return mix_oklab(palette["text"], palette["panel"], amount)


def toast_colours(palette: dict) -> dict[str, str]:
    """Decision 20: the toast is dark with light words. On a light look it is the text colour with the
    page's words, and Undo the accent's light shade; on a dark look it is raised a step off the cards,
    edged, with Undo in the dark look's accent, which is already a light shade."""
    if palette.get("family", "light") == "light":
        return {
            "background": palette["text"],
            "text": palette["window"],
            "action": mix_oklab(palette["accent"], palette["window"], 0.45),
            "edge": palette["text"],
        }
    return {
        "background": mix_oklab(palette["text"], palette["panel"], 0.05),
        "text": palette["text"],
        "action": palette["accent"],
        "edge": palette["hairline_strong"],
    }


# The focus screen's words-only buttons, beside its one filled button.
FOCUS_TEXT_BUTTONS = ("focusScreenBack", "focusScreenSkip", "focusScreenFinish", "focusScreenBreak")


def overlay_rules(palette: dict, knobs: dict, pad: int, card_radius: int) -> str:
    """The toast, the focus screen, Ctrl+K and the menus (decisions 19 to 22 of 0.17).

    The toast and Ctrl+K take the sheet's 16 corners, square only when the look's cards are. A menu
    drawn by `menus.Menu` paints its own panel and rows; the sheet gives only its size, with room on
    every side for its shadow.
    """
    text = knobs["text"]
    sheet_radius = RADIUS_SHEET if card_radius else 0
    toast = toast_colours(palette)
    hover, pressed = hover_tint(palette), hover_tint(palette, 0.10)
    words = ", ".join(f"QPushButton#{name}" for name in FOCUS_TEXT_BUTTONS)
    words_hover = ", ".join(f"QPushButton#{name}:hover" for name in FOCUS_TEXT_BUTTONS)
    words_pressed = ", ".join(f"QPushButton#{name}:pressed" for name in FOCUS_TEXT_BUTTONS)
    row = 30 if text == "large" else 24
    # A look with no shadows draws no lines: its toast and Ctrl+K's box are told from the page by
    # colour alone.
    flat = knobs["depth"] == "none"
    toast_edge = "none" if flat else f"1px solid {toast['edge']}"
    box_edge = "none" if flat else f"1px solid {palette['hairline']}"
    return (
        f"QFrame#toast {{ background: {toast['background']}; color: {toast['text']}; "
        f"border: {toast_edge}; border-radius: {sheet_radius}px; padding: 8px 12px 8px 16px; }}"
        f"QLabel#toastText {{ color: {toast['text']}; }}"
        # The toast's one button reads as part of its sentence.
        f"QPushButton#toastButton {{ background: transparent; color: {toast['action']}; border: none; "
        f"font-weight: {WEIGHT_STRONG}; padding: 4px 8px; min-height: 0; "
        f"border-radius: {RADIUS_CONTROL}px; }}"
        f"QPushButton#toastButton:hover {{ "
        f"background: {mix_oklab(toast['text'], toast['background'], 0.12)}; }}"
        # The focus screen: the look's page, a muted phase over the ring and the homework under it.
        f"QLabel#focusScreenPhase {{ color: {palette['muted']}; font-size: {type_pt('heading', text)}pt; "
        f"font-weight: {WEIGHT_STRONG}; }}"
        f"QLabel#focusScreenTask {{ color: {palette['text']}; font-size: {type_pt('title', text)}pt; "
        f"font-weight: {WEIGHT_STRONG}; }}"
        f"QLabel#focusScreenHint {{ color: {palette['muted']}; }}"
        "QPushButton#focusScreenStart, QPushButton#focusScreenPause, QPushButton#focusScreenFinished { "
        f"font-weight: {WEIGHT_STRONG}; padding: {pad + 2}px {pad * 3}px; }}"
        f"{words} {{ background: transparent; color: {palette['text']}; border: none; "
        f"font-weight: {WEIGHT_STRONG}; padding: {pad + 2}px {pad * 2}px; }}"
        f"{words_hover} {{ background: {hover}; }}"
        f"{words_pressed} {{ background: {pressed}; }}"
        # Ctrl+K: the window dimmed 40 %, the box a sheet, its field borderless on the box.
        "QWidget#commandBar { background: rgba(0, 0, 0, 102); }"
        f"QFrame#commandBox {{ background: {palette['panel']}; border: {box_edge}; "
        f"border-radius: {sheet_radius}px; padding: 8px; }}"
        f"QLineEdit#commandInput, QLineEdit#commandInput:focus {{ background: transparent; border: none; "
        f"font-size: {type_pt('heading', text)}pt; padding: 8px 4px; }}"
        f"QFrame#commandRule {{ background: {palette['hairline']}; border: none; padding: 0; "
        "border-radius: 0; min-height: 1px; max-height: 1px; }"
        "QListWidget#commandList { background: transparent; border: none; padding: 0; }"
        f"QListWidget#commandList::item {{ color: {palette['text']}; padding: 0 8px; "
        f"border-radius: {RADIUS_CONTROL if card_radius else 0}px; }}"
        f"QListWidget#commandList::item:hover, QListWidget#commandList::item:selected {{ "
        f"background: {hover}; color: {palette['text']}; }}"
        f"QLabel#commandNothing {{ color: {palette['muted']}; padding: 8px; }}"
        # A drawn menu: transparent round its panel, which it paints itself, with the shadow's room.
        f'QMenu[drawn="true"] {{ background: transparent; border: none; padding: {MENU_EDGE + 4}px; }}'
        f'QMenu[drawn="true"]::item {{ padding: 4px 8px; min-height: {row}px; }}'
        'QMenu[drawn="true"]::separator { height: 1px; margin: 4px 8px; }'
    )


def planner_rules(
    palette: dict, text: float | str, pad: int, radius: int, card_radius: int, edges: str
) -> str:
    """Today's app around its hours: the plan bar, the rail, Day's agenda (decisions 13 to 18 of 0.17).
    Sizes from the type scale; section labels in the muted colour, never the accent, which read as
    links."""
    caption, body, heading = (f"{type_pt(role, text)}pt" for role in ("caption", "body", "heading"))
    link = (
        f"background: transparent; color: {palette['accent']}; border: none; "
        f"padding: 2px {pad // 2}px; min-height: 0; font-weight: {WEIGHT_STRONG};"
    )
    bare = "background: transparent; border: none; padding: 0; border-radius: 0;"
    line = palette["hairline_strong"] if palette.get("family") == "contrast" else palette["hairline"]

    def rule(side: str) -> str:
        # A flat look draws no lines, here as everywhere.
        return "" if edges == "border: none;" else f"border-{side}: 1px solid {line};"

    hover = mix(palette["text"], palette["window"], 0.06)
    ring = mix(palette["accent"], palette["window"], 0.4)
    return (
        # The rail sits on the page; Day and Week on a sheet in the card colour, its corner rounded.
        f"QFrame#rail, QScrollArea#railScroll, QWidget#railBody, QWidget#railStrip, QWidget#railMonth, "
        f"QWidget#railNext, QWidget#railWaiting, QWidget#railFocus, QFrame#railNextCard {{ {bare} }}"
        f'QFrame#rail[folded="true"] {{ padding: {pad // 2}px {pad}px; }}'
        f"QListWidget#focusTasks {{ {bare} }}"
        f"QLabel[railMonthTitle=\"true\"], QLabel#railNextTitle {{ font-size: {body}; "
        f"font-weight: {WEIGHT_STRONG}; }}"
        f"QLabel#railNextWhen, QLabel#railNextThen, QLabel#classicAgendaSub, QLabel#weekNoneWaiting {{ "
        f"color: {palette['muted']}; font-size: {caption}; }}"
        f"QLabel#railWaitingCount {{ background: {mix(palette['text'], palette['window'], 0.07)}; "
        f"color: {palette['muted']}; border-radius: 9px; padding: 1px 6px; font-size: {caption}; "
        f"font-weight: {WEIGHT_STRONG}; }}"
        f'QPushButton[railIcon="true"] {{ background: transparent; border: none; padding: 0; '
        f"min-height: 0; border-radius: {radius}px; }}"
        f'QPushButton[railIcon="true"]:hover {{ background: {hover}; }}'
        # A rail chip paints itself; the tray's border and a large-text button's height are not its.
        f'QPushButton[railChip="true"] {{ {bare} min-height: 0; }}'
        f'QPushButton[railIcon="true"]:focus {{ border: 2px solid {ring}; }}'
        f"QFrame#weekTable, QFrame#dayView {{ background: {palette['panel']}; padding: 0; border: none; "
        f"{rule("top")} {rule("left")} border-radius: 0; "
        f"border-top-left-radius: 16px; }}"
        f"QWidget#weekHeader, QWidget#dayHeader, QWidget#weekDayNames, QWidget#dayNames, "
        f"QWidget#weekZoom, QWidget#dayZoom, QScrollArea#classicAgendaScroll, "
        f"QWidget#classicAgendaList, QWidget#daySummary {{ {bare} }}"
        f"QFrame#classicAgenda {{ {bare} {rule("right")} }}"
        f"QFrame#classicAgendaFoot {{ {bare} {rule("top")} }}"

        # One slim bar: its count, Details, Replan as text and Got it filled.
        f"QFrame#planReview {{ background: {palette['panel']}; padding: {pad // 2}px {pad}px; "
        f"border-radius: {card_radius}px; {edges} }}"
        f"QLabel#planReviewHeading {{ font-weight: {WEIGHT_STRONG}; font-size: {body}; }}"
        f"QPushButton#planReviewDetails, QPushButton#planReviewReplan {{ {link} }}"
        f"QPushButton#planReviewDetails:hover, QPushButton#planReviewReplan:hover {{ "
        f"text-decoration: underline; }}"
        f"QListWidget#planReviewList {{ border: none; padding: 0; font-size: {caption}; }}"
        f"QLabel[railLabel=\"true\"] {{ color: {palette['muted']}; font-size: {caption}; "
        f"font-weight: {WEIGHT_STRONG}; }}"
        f"QLabel[railHeading=\"true\"] {{ font-size: {heading}; font-weight: {WEIGHT_STRONG}; }}"
    )


def _contrast_rules(palette: dict) -> str:
    """High contrast's segmented choices in Settings: a track outlined on the page, every choice in the
    text colour and the chosen one filled with the accent. Yellow on light grey could not be read. The
    top bar's view control takes the same colours from `top_bar_rules`."""
    return (
        f'QFrame[segmented="true"] {{ background: {palette["window"]}; '
        f"border: 1px solid {palette['text']}; }}"
        f'QPushButton[segment="true"] {{ color: {palette["text"]}; border: none; }}'
        f'QPushButton[segment="true"]:checked {{ background: {palette["accent"]}; '
        f"color: {palette['accent_ink']}; border: none; }}"
    )


def copy_look(choice: dict | None) -> dict:
    return deepcopy(sanitize_look(choice))
