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
    SINK,
    contrast,
    fit_lightness,
    luminance,
    mix,
    mix_oklab,
    oklch,
    oklch_of,
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
    "blocks": "filled",
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
TEXT_PT = {"small": 10, "normal": 12, "large": 15}
# The shortest a field may be drawn. A layout under pressure squeezes its rows, and a combo box or a
# line edit has no minimum of its own worth the name, so the text inside gets sliced in half rather
# than the dialog refusing to shrink. Measured against the app's own font at each size.
FIELD_MIN_PX = {"small": 22, "normal": 26, "large": 34}
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
    "layoutMainHeading",
    "layoutDayHeading",
    "cardTitle",
    "setupChoiceName",
    "focusScreenTask",
)
AA_TEXT = 4.5
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


def pack_motion(pack: object) -> str:
    chosen = known_pack(pack)
    return "extra" if chosen in {"light-frost", "dark-frost"} else "normal"


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
# The four colours a student sets; muted text, the raised card and the strong line follow from them.
CUSTOM_COLOURS = ("page", "card", "text", "line")
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
        scales = {name: size / TEXT_PT["normal"] for name, size in TEXT_PT.items()}
        knobs["text"] = _nearest(custom["text_scale"], scales)
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
    scale = custom.get("text_scale", TEXT_PT[knobs["text"]] / TEXT_PT["normal"])
    return {
        "radius": radius,
        "card_radius": card_radius,
        "size": round(TEXT_PT["normal"] * scale, 1) if "text_scale" in custom else TEXT_PT[knobs["text"]],
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


def look_motion(pack: object, look: dict | None) -> str:
    """The motion level a look starts at when the student never chose one: a custom look's own, Reduce
    for Paper ("distinct page turns, sharp transitions"), else the pack's."""
    selected = sanitize_look(look)
    custom = selected.get("custom")
    if custom is not None:
        return custom.get("motion") or ("reduce" if LOOK_BASES[custom["base"]][1] == "paper" else "normal")
    return "reduce" if selected["preset"] == "paper" else pack_motion(pack)


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
        axis = "dark" if luminance(page) < 0.18 else "light"
        if axis != table["axis"] or table["family"] != "contrast":
            table["family"] = axis
        table["axis"] = axis
        sunk = card if axis == "light" else mix(card, page, 0.42)
        table.update(window=page, panel=card, field=sunk, grid=sunk, text=text, hairline=line)
        if {"page", "card", "text"} & colours.keys():
            raised = mix(text, card, 0.05)
            flex_reads = contrast(table["block_flex_ink"], table["block_flex"]) >= AA_TEXT
            table.update(
                muted=_derived_muted(text, card, page),
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
    readable = fit_lightness(palette["accent"], (palette["window"], palette["panel"]), AA_TEXT)
    if readable != palette["accent"]:
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
    or an edge is drawn with the mark.
    """
    flexible = kind == "flexible"
    neutral = palette["block_flex" if flexible else "block_locked"]
    neutral_ink = palette["block_flex_ink" if flexible else "block_locked_ink"]
    mark = mark or category_color or palette["block_edge"]
    mode = effective_look(look)["blocks"]
    if mode == "outline":
        return {"mode": mode, "fill": palette["grid"], "ink": palette["text"], "outline": mark, "edge": None}
    if mode == "edge":
        return {
            "mode": mode,
            "fill": palette["panel"],
            "ink": palette["text"],
            "outline": palette["hairline"],
            "edge": mark,
        }
    if category_color:
        text = palette["text"]
        ink = text if contrast(text, category_color) >= AA_TEXT else readable_ink(category_color)
        return {"mode": mode, "fill": category_color, "ink": ink, "outline": None, "edge": None}
    return {"mode": mode, "fill": neutral, "ink": neutral_ink, "outline": None, "edge": None}


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


def control_rules(palette: dict, radius: int, size: int, art: dict[str, str]) -> str:
    """Scrollbars, dropdowns, steppers, check marks, lists, menus and tooltips in the design's colours.

    Left to Fusion they kept its grey chrome in every design, and on a dark palette an unticked box, an
    unselected radio button and the spin arrows could not be seen at all. `art` holds the tick and
    chevron images, which `control_art` in widgets.py draws for the palette.
    """
    handle = mix(palette["muted"], palette["panel"], 0.55)
    corner = max(4, min(radius, 10))
    item = max(4, corner - 2)
    tick, down, up = art["tick"], art["down"], art["up"]
    return (
        "QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }"
        "QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }"
        f"QScrollBar::handle:vertical {{ background: {handle}; border-radius: 4px; min-height: 36px; "
        "margin: 0 2px; }"
        f"QScrollBar::handle:horizontal {{ background: {handle}; border-radius: 4px; min-width: 36px; "
        "margin: 2px 0; }"
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
        f"QComboBox QAbstractItemView::item {{ min-height: {size * 2 + 8}px; padding: 2px 10px; "
        f"border-radius: {item}px; }}"
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
        "border: none; padding: 4px 8px; font-weight: 600; }"
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
        f"QLabel#menuHeading {{ color: {palette['muted']}; font-weight: 600; "
        f"font-size: {max(size - 1, 8)}pt; padding: 6px 12px 2px 12px; }}"
        # A tooltip does not take the window's text size by itself, so at Large it stayed small.
        f"QToolTip {{ background: {palette['text']}; color: {palette['window']}; border: none; "
        f"padding: 5px 9px; border-radius: {item}px; font-size: {size}pt; }}"
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


def settings_rules(palette: dict, radius: int, size: int, pad: int, depth: str) -> str:
    """Settings as a page: a list of sections on the left, cards on the right, and segmented choices.
    Dialogs laid out in cards use the same card.

    A segmented control is a sunken track with the chosen segment raised on it, so two or three
    choices read as one control with one answer.
    """
    edges = _depth_rules(depth, palette)
    card_radius = max(radius, 10)
    track = mix(palette["text"], palette["panel"], 0.07)
    chosen_edge = "none" if depth == "none" else f"1px solid {palette['hairline_strong']}"
    selected = mix(palette["accent"], palette["panel"], 0.16)
    return (
        f"QWidget#settingsPage {{ background: {palette['window']}; }}"
        # Bare widgets inside a card, which the app-wide rule would paint as a band of page colour.
        "QWidget#settingsRow, QWidget#settingsBody, QWidget#settingsFooter, QWidget#prefFineHost, "
        "QWidget#prefReminderControls, QFrame[designs=\"true\"] { background: transparent; "
        "border: none; padding: 0; }"
        f"QWidget#settingsRail {{ background: {palette['panel']}; }}"
        "QScrollArea#settingsScroll { background: transparent; border: none; padding: 0; border-radius: 0; }"
        f"QListWidget#prefsNav {{ background: {palette['panel']}; border: none; border-radius: 0; "
        "padding: 16px 8px; }"
        f"QListWidget#prefsNav::item {{ color: {palette['muted']}; padding: {pad + 4}px 12px; "
        f"border-radius: {max(radius - 2, 4)}px; }}"
        f"QListWidget#prefsNav::item:hover {{ background: {palette['hairline']}; color: {palette['text']}; }}"
        f"QListWidget#prefsNav::item:selected {{ background: {selected}; color: {palette['text']}; }}"
        f"QLabel#settingsTitle {{ font-size: {size + 8}pt; font-weight: 700; }}"
        f"QFrame#settingsCard, QFrame#dialogCard {{ background: {palette['panel']}; "
        f"border-radius: {card_radius}px; padding: 0; {edges} }}"
        "QLabel#prefsHeading, QLabel#layoutMainHeading, QLabel#layoutDayHeading, QLabel#cardTitle { "
        f"font-size: {size + 1}pt; font-weight: 700; color: {palette['text']}; }}"
        "QLabel#settingsCardNote, QLabel#cardNote, QLabel#settingsExperimental, QLabel#prefPlanningNote, "
        "QLabel#prefDndNote, "
        "QLabel#prefTrayNote, QLabel#prefBlockSongNote, QLabel#prefToneNote, QLabel#reminderLimits { "
        f"color: {palette['muted']}; }}"
        "QLabel#settingsExperimental { font-weight: 700; margin-top: 6px; }"
        f'QFrame[segmented="true"] {{ background: {track}; border: none; '
        f"border-radius: {max(radius, 6) + 2}px; padding: 0; }}"
        f'QPushButton[segment="true"] {{ background: transparent; color: {palette["muted"]}; border: none; '
        # One weight whether chosen or not: a bolder chosen segment was wider than the room it was given.
        f"border-radius: {max(radius, 6)}px; padding: {max(pad - 2, 3)}px {pad + 8}px; font-weight: 600; "
        "min-height: 0; }"
        f'QPushButton[segment="true"]:hover {{ color: {palette["text"]}; }}'
        f'QPushButton[segment="true"]:checked {{ background: {palette["field"]}; color: {palette["text"]}; '
        f"border: {chosen_edge}; }}"
        'QPushButton[segment="true"]:disabled { background: transparent; '
        f'color: {palette["hairline_strong"]}; }}'
    )


def setup_rules(palette: dict, radius: int, size: int, pad: int, depth: str) -> str:
    """First-run setup: a rail of steps beside one question at a time, and cards to pick from.

    Groups, chips and Back take the depth's edges like every other control. A card keeps a ring of
    one width whether or not it is picked, so picking one never nudges its picture: the ring is the
    accent when picked and, except on a flat look, a soft line otherwise.
    """
    edges = _depth_rules(depth, palette)
    card_radius = max(radius, 10)
    ring = "transparent" if depth == "none" else mix(palette["hairline_strong"], palette["panel"], 0.6)
    # A card is larger than a control, so it is lifted with the text colour, never the accent.
    lift = mix(palette["text"], palette["panel"], 0.04)
    quiet = (
        "setupQuiet", "setupSkip", "setupSkipAll", "setupOwnLook", "setupAddActivity", "setupAddHomework",
        "setupSuggest", "setupPlay", "setupChange", "setupFineTune",
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
        f"QLabel#setupBrand {{ font-size: {size + 2}pt; font-weight: 700; color: {palette['accent']}; }}"
        f"QPushButton#setupRailItem {{ background: transparent; color: {palette['muted']}; border: none; "
        f"text-align: left; padding: {pad + 2}px {pad}px; font-weight: 500; min-height: 0; }}"
        f"QPushButton#setupRailItem:hover {{ color: {palette['text']}; }}"
        f"QPushButton#setupRailItem[done=\"true\"] {{ color: {palette['text']}; }}"
        f"QPushButton#setupRailItem[current=\"true\"] {{ color: {palette['text']}; font-weight: 700; }}"
        f"QPushButton#setupRailItem:disabled {{ background: transparent; "
        f"color: {mix(palette['muted'], palette['panel'], 0.55)}; }}"
        f"QFrame#setupRailMarker {{ background: {palette['accent']}; border: none; padding: 0; "
        f"border-radius: 1px; }}"
        f"QLabel#setupTitle {{ font-size: {size + 8}pt; font-weight: 700; }}"
        f"QLabel#setupNote {{ color: {palette['muted']}; font-size: {size + 1}pt; }}"
        f"QLabel#setupHint, QLabel#setupFieldLabel {{ color: {palette['muted']}; }}"
        f"QLabel#setupSection {{ font-size: {size + 1}pt; font-weight: 700; margin-top: 8px; }}"
        f"QLabel#setupError {{ color: {palette['error']}; font-weight: 600; }}"
        f"QLabel#setupSummaryName {{ font-weight: 700; }}"
        f"QFrame#setupChoice {{ background: {palette['panel']}; border: 2px solid {ring}; "
        f"border-radius: {card_radius}px; padding: 0; }}"
        f"QFrame#setupChoice:hover {{ background: {lift}; }}"
        f"QFrame#setupChoice:focus {{ border-color: {mix(palette['accent'], palette['panel'], 0.5)}; }}"
        f"QFrame#setupChoice[selected=\"true\"] {{ border-color: {palette['accent']}; background: {lift}; }}"
        f"QLabel#setupChoiceName {{ font-weight: 700; font-size: {size + 1}pt; }}"
        f"QLabel#setupChoiceNote {{ color: {palette['muted']}; }}"
        f"QFrame#setupGroup {{ background: {palette['panel']}; border-radius: {card_radius}px; {edges} }}"
        f"{pills} {{ background: {palette['field']}; color: {palette['text']}; {edges} "
        f"border-radius: 14px; padding: 4px 12px; font-weight: 500; min-height: 0; }}"
        f"QPushButton#setupDay {{ padding: 4px 9px; }}"
        f"{pills_hover} {{ background: {mix(palette['accent'], palette['field'], 0.14)}; }}"
        f"QPushButton#setupChip:checked, QPushButton#setupDay:checked {{ background: {palette['accent']}; "
        f"color: {palette['accent_ink']}; }}"
        f"{quiet_rule} {{ background: transparent; color: {palette['accent']}; border: none; "
        f"padding: {pad}px 2px; font-weight: 600; min-height: 0; }}"
        f"{quiet_hover} {{ color: {palette['text']}; text-decoration: underline; }}"
        f"QPushButton#setupAddActivity:disabled, QPushButton#setupAddHomework:disabled {{ "
        f"background: transparent; color: {palette['muted']}; }}"
        # Level with the name beside it, which a button's padding pushed a few pixels below.
        f"QPushButton#setupChange {{ padding: 0 2px; }}"
        f"QPushButton#setupBack {{ background: transparent; color: {palette['text']}; {edges} }}"
        f"QPushButton#setupBack:hover {{ background: {mix(palette['accent'], palette['window'], 0.1)}; }}"
        f"QPushButton#setupNext {{ padding: {pad}px {pad * 3}px; font-weight: 700; }}"
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
    size = measures["size"]
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
    # A flat look draws no lines at all, so its segments are told apart by the raised one alone.
    divider = "none" if knobs["depth"] == "none" else f"1px solid {palette['hairline_strong']}"
    return (
        f"QMainWindow, QDialog, QWidget {{ background: {palette['window']}; color: {palette['text']}; "
        f"font-family: {family}; font-size: {size}pt; }}"
        f"QFrame, QGroupBox, QTableWidget, QListWidget {{ background: {palette['panel']}; "
        f"color: {palette['text']}; padding: {card}px; border-radius: {card_radius}px; {edges} }}"
        # Lists, tables and scroll areas are frames too, but their padding is room around rows.
        f"QAbstractScrollArea {{ padding: {pad}px; }}"
        # A group's title sits in the space above its frame. Without the room it was drawn on the
        # frame line, over the first row of what it names.
        f"QGroupBox {{ margin-top: {round(size * 1.9) + 4}px; }}"
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
        # Today's app's Day: the day's hours, then what still needs a time and a summary beside them.
        f"QFrame#daySide {{ background: {palette['panel']}; border-radius: 0; {edges} }}"
        f"QLabel#dayWaitingLabel, QLabel#daySummaryLabel {{ color: {palette['accent']}; font-weight: 800; "
        f"font-size: {max(size - 1, 7)}pt; }}"
        f"QLabel#daySummaryLabel {{ margin-top: 10px; }}"
        f"QLabel#dayWaitingHint {{ color: {palette['muted']}; font-size: {max(size - 1, 7)}pt; }}"
        # What follows the pointer while something is carried: a pill, readable over any calendar.
        f"QLabel#heldChip {{ background: {palette['accent']}; color: {palette['accent_ink']}; "
        f"padding: 3px 10px; border-radius: 10px; }}"
        f'QLabel#heldChip[refused="true"] {{ background: {palette["panel"]}; color: {palette["error"]}; '
        f"{edges} }}"
        f"QHeaderView::section, QTableCornerButton::section {{ background: {palette['panel']}; "
        f"color: {palette['muted']}; padding: 2px 6px; border: none; }}"
        # QLabel is a QFrame in Qt, so without this every label, even an empty one, is drawn as a panel.
        f"QLabel {{ background: transparent; border: none; padding: 0; }}"
        f"QPushButton {{ background: {palette['accent']}; color: {palette['accent_ink']}; "
        f"padding: {pad}px {pad * 2}px; border-radius: {radius}px; {edges}{button_min} }}"
        f"QPushButton:disabled {{ background: {palette['hairline_strong']}; color: {palette['muted']}; }}"
        # The rule above that gives every widget the text colour also keeps it when the widget is off,
        # so reminder settings looked live while reminders were off.
        f"QWidget#prefReminderControls QWidget:disabled {{ color: {palette['muted']}; }}"
        # One filled button per dialog: the answer. Cancel and its kind are drawn plain beside it, and
        # a button that destroys something takes the error colour.
        f'QPushButton[quiet="true"] {{ color: {palette["text"]}; {quiet_edge} }}'
        f'QPushButton[quiet="true"]:hover {{ background: {palette["hairline"]}; }}'
        f'QPushButton[danger="true"] {{ background: {palette["error"]}; '
        f'color: {readable_ink(palette["error"])}; }}'
        f"QPushButton#deleteBlock, QPushButton#deleteHomework {{ background: transparent; "
        f"color: {palette['error']}; border: none; "
        f"padding: {pad}px 2px; font-weight: 600; min-height: 0; }}"
        f"QPushButton#deleteBlock:hover, QPushButton#deleteHomework:hover {{ text-decoration: underline; }}"
        # Homework that still needs a time, to be dragged onto the hours: it looks like homework, not
        # like a button that does something when pressed. Its edge is homework's own colour; red would
        # say something is wrong, and nothing is.
        f"QPushButton[tray=\"true\"] {{ background: {palette['panel']}; color: {palette['text']}; "
        f"{edges} border-left: 4px solid {category_paint('assignments', palette)[1]}; text-align: left; }}"
        f"QMenu::item {{ min-height: {item_h}px; padding: {pad}px {pad * 2}px; }}"
        f"QLabel#nowNext {{ font-weight: 600; }}"
        f"QLabel#focusTask {{ font-weight: 600; }}"
        f"QLabel#focusPhase {{ color: {palette['muted']}; }}"
        f"QLabel#focusTime {{ font-family: {MONO_FAMILY}; font-weight: 700; }}"
        f"QLabel#recoveryList {{ font-family: {MONO_FAMILY}; }}"
        f"QLabel#recoveryStatus {{ color: {palette['error']}; }}"
        # How many recovery codes are left is an ordinary fact until none are.
        f"QLabel#recoveryCount {{ color: {palette['muted']}; }}"
        f'QLabel#recoveryCount[problem="true"] {{ color: {palette["error"]}; font-weight: 600; }}'
        f"QWidget#authCard {{ background: {palette['panel']}; border-radius: {card_radius}px; {edges} }}"
        f"QLabel#authBrand {{ font-size: {size + 8}pt; font-weight: 700; color: {palette['accent']}; }}"
        f"QLabel#authHeading {{ font-weight: 600; font-size: {size + 3}pt; }}"
        f"QLabel#authNote, QLabel#passwordHint, QLabel#usernameHint {{ color: {palette['muted']}; }}"
        f"QLabel#validationError {{ color: {palette['error']}; font-weight: 600; }}"
        f"QLabel#homeworkEstimateHint {{ color: {palette['muted']}; }}"
        f"QLabel#homeworkEstimateHint[problem=\"true\"] {{ color: {palette['error']}; font-weight: 600; }}"
        f"QPushButton#todayWeek {{ background: transparent; color: {palette['text']}; "
        f"font-weight: 600; padding: {pad}px {pad * 2}px; {edges} }}"
        # The way in is a button; the way to a new account is small print, so it is drawn as a link.
        f"QLabel#updateHeading {{ font-size: {size + 4}pt; font-weight: 700; }}"
        f"QLabel#updateDetail, QLabel#updateStatus {{ color: {palette['muted']}; }}"
        # The first-week card sits on top of the week rather than in a layout, so it has to read as
        # something laid over the calendar rather than printed onto it.
        # The week you are on, said once and said large.
        f"QLabel#weekTitle {{ font-size: {size + 6}pt; font-weight: 700; color: {palette['text']}; }}"
        # Today's name above the week, in the accent over a 2 px line. The others keep a clear line,
        # so the row does not move when the day changes.
        f'QLabel[today="false"] {{ border-bottom: 2px solid transparent; border-radius: 0; }}'
        f'QLabel[today="true"] {{ color: {palette["accent"]}; font-weight: 700; '
        f'border-bottom: 2px solid {palette["accent"]}; border-radius: 0; }}'
        # Day / Week / Month / My day are one segmented control: a shared track, the chosen view
        # raised in the panel colour, the others muted, a hairline between them.
        f"QPushButton#viewDay, QPushButton#viewWeek, QPushButton#viewMonth, QPushButton#viewMyDay {{ "
        f"background: transparent; color: {palette['muted']}; font-weight: 500; "
        f"padding: {pad}px {round(pad * 1.5)}px; border: none; border-radius: {max(radius - 2, 0)}px; "
        f"border-left: {divider}; }}"
        f'QPushButton[segment="first"] {{ border-left: none; }}'
        f"QPushButton#viewDay:hover, QPushButton#viewWeek:hover, QPushButton#viewMonth:hover, "
        f"QPushButton#viewMyDay:hover {{ color: {palette['text']}; }}"
        f"QPushButton#viewDay:checked, QPushButton#viewWeek:checked, QPushButton#viewMonth:checked, "
        f"QPushButton#viewMyDay:checked {{ background: {palette['panel']}; color: {palette['text']}; "
        f"font-weight: 600; border-left: none; {edges} }}"
        # The arrows are navigation, not actions, so they carry no fill.
        f"QPushButton#prevWeek, QPushButton#nextWeek {{ background: transparent; "
        f"color: {palette['text']}; font-size: {size + 3}pt; font-weight: 700; "
        f"padding: 0; {edges} }}"
        f"QPushButton#prevWeek:hover, QPushButton#nextWeek:hover {{ color: {palette['text']}; }}"
        # Zoom is a view control like the arrows: no fill. The corner sizes it to the text.
        f"QPushButton[zoom=\"true\"] {{ background: transparent; color: {palette['text']}; "
        f"font-weight: 700; padding: 0; min-height: 0; {edges} }}"
        f"QPushButton[zoom=\"true\"]:disabled {{ background: transparent; "
        f"color: {palette['hairline_strong']}; }}"
        # One filled button on the page: the thing the app is for.
        f"QLabel#blockDurationLine {{ color: {palette['muted']}; }}"
        f"QLabel#blockDurationLine[problem=\"true\"] {{ color: {palette['error']}; font-weight: 600; }}"
        f"QLabel#aboutVersion {{ font-size: {size + 4}pt; font-weight: 700; }}"
        f"QLabel#helpKey {{ font-weight: 600; }}"
        f"QLabel#helpScreenName {{ font-weight: 700; }}"
        f"QPushButton#moreButton, QPushButton#settingsGear {{ background: transparent; "
        f"color: {palette['muted']}; {edges} }}"
        + setup_rules(palette, radius, size, pad, knobs["depth"])
        + settings_rules(palette, radius, size, pad, knobs["depth"])
        + f"QPushButton#authSwitch, QPushButton#forgotPassword, QPushButton#updateSkip {{ "
        f"background: transparent; "
        f"color: {palette['accent']}; border: none; padding: {pad}px 0; "
        f"font-size: {size - 1}pt; text-align: left; min-height: 0; }}"
        f"QPushButton#authSwitch:hover, QPushButton#forgotPassword:hover, "
        f"QPushButton#updateSkip:hover {{ "
        f"color: {palette['text']}; text-decoration: underline; }}"
        # A ringing alarm is the one thing in the app that has to be read from across a room.
        f"QLabel#alarmTitle {{ font-size: {size + 8}pt; font-weight: 700; }}"
        f"QLabel#alarmDetail {{ font-size: {size + 2}pt; color: {palette['muted']}; }}"
        f"QFrame#toast {{ background: {palette['panel']}; color: {palette['text']}; "
        f"{edges} padding: {pad * 2}px {pad * 3}px; border-radius: {card_radius}px; }}"
        # A new account's empty week, the focus screen and the command bar.
        f"QLabel#emptyWeekHeading {{ font-size: {size + 8}pt; font-weight: 700; }}"
        f"QLabel#emptyWeekLine {{ color: {palette['muted']}; font-size: {size + 1}pt; }}"
        f"QPushButton#emptyWeekAdd, QPushButton#focusScreenStart {{ font-weight: 600; "
        f"padding: {pad + 2}px {pad * 3}px; }}"
        f"QLabel#focusScreenPhase {{ color: {palette['accent']}; font-size: {size + 2}pt; "
        f"font-weight: 700; letter-spacing: 2px; }}"
        # The countdown is read from across a desk, in the look's own face at a size the text knob never sets.
        f"QLabel#focusScreenTime {{ font-size: 96pt; "
        f"font-weight: 700; color: {palette['text']}; }}"
        f"QLabel#focusScreenTask {{ font-size: {size + 6}pt; font-weight: 600; }}"
        f"QLabel#focusScreenHint {{ color: {palette['muted']}; }}"
        f"QProgressBar#focusScreenProgress {{ background: {palette['hairline']}; border: none; "
        f"border-radius: 3px; min-height: 6px; max-height: 6px; padding: 0; }}"
        f"QProgressBar#focusScreenProgress::chunk {{ background: {palette['accent']}; border-radius: 3px; }}"
        # Laid over the window, it dims what is behind so the box reads as the one thing to answer.
        f"QWidget#commandBar {{ background: rgba(0, 0, 0, 90); }}"
        f"QFrame#commandBox {{ background: {palette['panel']}; border-radius: {card_radius}px; "
        f"{edges} padding: {pad}px; }}"
        f"QLineEdit#commandInput {{ font-size: {size + 2}pt; }}"
        f"QListWidget#commandList {{ border: none; padding: 0; }}"
        f"QListWidget#commandList::item {{ padding: {pad}px; border-radius: {radius}px; }}"
        f"QLabel#commandNothing {{ color: {palette['muted']}; padding: {pad}px; }}"
        # The view control's track, which the chosen segment sits in.
        f"QFrame#segments {{ background: {palette['hairline']}; padding: 2px; border: none; "
        f"border-radius: {radius}px; }}"
        # Add and its arrow are one button split in two.
        f"QPushButton#addButton {{ font-weight: 600; border-top-right-radius: 0; "
        f"border-bottom-right-radius: 0; }}"
        f"QPushButton#addArrow {{ padding: {pad}px {pad}px; border-top-left-radius: 0; "
        f"border-bottom-left-radius: 0; margin-left: 1px; }}"
        f"QPushButton#addArrow::menu-indicator {{ image: none; width: 0; }}"
        # The toast's one button reads as part of its sentence.
        f"QPushButton#toastButton {{ background: transparent; color: {palette['accent']}; border: none; "
        f"font-weight: 700; padding: 2px {pad}px; min-height: 0; }}"
        f"QPushButton#toastButton:hover {{ text-decoration: underline; }}"
        # Week's side, as Day's: the panel colour, its headings in the accent, and folded, one line.
        # Narrower at the sides than a card, so "Math worksheet · 45 min" is whole in its 250 pixels.
        f"QFrame#weekSide {{ background: {palette['panel']}; border-radius: 0; "
        f"padding: {card}px {pad}px; {edges} }}"
        f'QFrame#weekSide[folded="true"] {{ padding: {pad // 2}px {pad}px; }}'
        f"QLabel#weekNext, QLabel#weekSideLine {{ font-weight: 600; }}"
        f"QLabel#focusTasksLabel, QLabel#classicWaitingLabel {{ color: {palette['accent']}; "
        f"font-weight: 800; font-size: {max(size - 1, 7)}pt; margin-top: 6px; }}"
        f"QLabel#weekNoneWaiting {{ color: {palette['muted']}; font-size: {max(size - 1, 7)}pt; }}"
        + (_contrast_rules(palette) if palette.get("family") == "contrast" else "")
        # Headings in the look's heading face: Newsreader in the Serif font, over Inter.
        + ", ".join(f"QLabel#{name}" for name in HEADING_NAMES)
        + f" {{ font-family: {measures['heading']}; }}"
    ) + (control_rules(palette, radius, size, art) if art is not None else "")


def _contrast_rules(palette: dict) -> str:
    """High contrast's segmented controls: a track outlined on the page, every choice in the text colour
    and the chosen one filled with the accent. Yellow on light grey could not be read."""
    views = ("viewDay", "viewWeek", "viewMonth", "viewMyDay")
    selectors = [*(f"QPushButton#{name}" for name in views), 'QPushButton[segment="true"]']
    segments = ", ".join(selectors)
    chosen = ", ".join(f"{selector}:checked" for selector in selectors)
    return (
        f'QFrame#segments, QFrame[segmented="true"] {{ background: {palette["window"]}; '
        f"border: 1px solid {palette['text']}; }}"
        f"{segments} {{ color: {palette['text']}; border: none; }}"
        f"{chosen} {{ background: {palette['accent']}; color: {palette['accent_ink']}; border: none; }}"
    )


def copy_look(choice: dict | None) -> dict:
    return deepcopy(sanitize_look(choice))
