"""Device-only look knobs and account theme packs. No Qt.

A look has two halves. The palette says what colours exist; the knobs say how
the interface is drawn with them. A preset is a bundle of knob values, and may
bring its own palette. Every knob has to change something a student can see:
a control that stores a value nothing reads is the bug this module exists to
prevent, and desktop/tests/test_look.py proves each value moves the output.

Colours began as the retired web client's CSS custom properties, where they already passed the
readability and accent-distance audits, so both clients show the same look.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache

from desktop.native.calendar import CATEGORIES
from desktop.native.tokens import RADIUS_CARD, RADIUS_CONTROL, SINK, WEIGHT_STRONG, mix_oklab, type_pt

LOOK_KNOBS = {
    "surface": ("frost", "flat"),
    "corners": ("round", "sharp", "pill"),
    "depth": ("soft", "flat", "hard"),
    "font": ("sans", "mono", "serif"),
    "blocks": ("filled", "outlined", "edge"),
    "density": ("comfortable", "compact"),
    "text": ("small", "normal", "large"),
}
LOOK_DEFAULTS = {
    "surface": "frost",
    "corners": "round",
    "depth": "soft",
    "font": "sans",
    # Decision 14 of 0.17: the category's fill with a 3-pixel edge in its mark.
    "blocks": "edge",
    "density": "comfortable",
    "text": "normal",
}
LOOK_PRESETS = {
    "default": {},
    "terminal": {
        "surface": "flat",
        "corners": "sharp",
        "depth": "flat",
        "font": "mono",
        "blocks": "outlined",
        "density": "compact",
        "text": "normal",
    },
    "poster": {
        "surface": "flat",
        "corners": "sharp",
        "depth": "hard",
        "font": "sans",
        "blocks": "filled",
        "density": "compact",
        "text": "large",
    },
    "ink": {
        "surface": "flat",
        "corners": "sharp",
        "depth": "flat",
        "font": "serif",
        "blocks": "edge",
        "density": "comfortable",
        "text": "normal",
    },
    "high-contrast": {
        "surface": "flat",
        "corners": "sharp",
        "depth": "hard",
        "font": "sans",
        "blocks": "outlined",
        "density": "comfortable",
        "text": "large",
    },
    # The two soft looks. Every preset above is flat and sharp; these keep rounded corners and depth.
    "paper": {
        "surface": "flat",
        "corners": "round",
        "depth": "soft",
        "font": "serif",
        "blocks": "filled",
        "density": "comfortable",
        "text": "normal",
    },
    "pastel": {
        "surface": "frost",
        "corners": "pill",
        "depth": "soft",
        "font": "sans",
        "blocks": "filled",
        "density": "comfortable",
        "text": "normal",
    },
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
# (controls, cards) at each Corners setting. Round is the system's own shape (decision 5 of 0.17).
CORNER_RADIUS = {"round": (RADIUS_CONTROL, RADIUS_CARD), "sharp": (0, 0), "pill": (16, 16)}
FONT_FAMILIES = {
    "sans": "Inter, Noto Sans, DejaVu Sans, sans-serif",
    "mono": "Noto Sans Mono, DejaVu Sans Mono, monospace",
    "serif": "Noto Serif, DejaVu Serif, serif",
}
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


def _channels(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def mix(top: str, bottom: str, alpha: float) -> str:
    """The solid colour of `top` laid over `bottom` at `alpha`.

    The web palette states its hairlines as translucent tints. Qt stylesheets
    disagree between versions about alpha syntax, so the tint is settled here.
    """
    pairs = zip(_channels(top), _channels(bottom), strict=True)
    blended = [round(over * alpha + under * (1 - alpha)) for over, under in pairs]
    return "#{:02x}{:02x}{:02x}".format(*blended)


def luminance(color: str) -> float:
    linear = []
    for channel in _channels(color):
        value = channel / 255
        linear.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def readable_ink(background: str) -> str:
    """Black or white, whichever reads better on a colour the palette does not own, such as a category.

    Pure black, not the palette's navy ink: on the violet Study colour navy reaches about 4.4 to 1 and
    white about 4.2, so neither passes, while black does.
    """
    return max(("#000000", LIGHT_INK), key=lambda ink: contrast(ink, background))


def _palette(
    axis: str, tint: str | None = None, soft: float = 0.12, strong: float = 0.24, **colors: str
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


# window is the page, panel the raised surface, field an input, grid the calendar cell.
PALETTES = {
    "nocturne": _palette(
        "dark",
        "#baccff",
        window="#0e1320",
        panel="#161d2b",
        field="#121827",
        grid="#131a27",
        text="#e6ebf5",
        muted="#9ba6ba",
        error="#ff9b9b",
        block_locked="#2b3a52",
        block_locked_ink="#eef2fa",
        block_flex="#4a3c1c",
        block_flex_ink="#fff4dc",
        block_edge="#7d93b8",
    ),
    "slate": _palette(
        "light",
        "#182c58",
        strong=0.22,
        window="#edf2fa",
        panel="#ffffff",
        field="#fbfcfe",
        grid="#fbfcff",
        text="#172033",
        muted="#536079",
        error="#b42318",
        block_locked="#dde6f3",
        block_locked_ink="#18233a",
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
# A preset may replace the pack's colours outright. Terminal is true black with phosphor text.
# Ink has a light map and a dark map so it follows the pack axis; the others are one look.
PRESET_PALETTES = {
    "terminal": _palette(
        "dark",
        "#78ff78",
        soft=0.25,
        strong=0.45,
        window="#000000",
        panel="#0a0a0a",
        field="#000000",
        grid="#050505",
        text="#d6ffd6",
        muted="#7fbf7f",
        error="#ff6b6b",
        block_locked="#0a0a0a",
        block_locked_ink="#d6ffd6",
        block_flex="#0a0a0a",
        block_flex_ink="#ffe9a8",
        block_edge="#7fbf7f",
    ),
    "poster": _palette(
        "light",
        "#0b132b",
        soft=0.75,
        strong=1.0,
        window="#ffd60a",
        panel="#ffd60a",
        field="#ffd60a",
        grid="#ffe14d",
        text="#0b132b",
        muted="#5c3d2e",
        error="#a3004f",
        block_locked="#0b132b",
        block_locked_ink="#ffd60a",
        block_flex="#8b0000",
        block_flex_ink="#ffd60a",
        block_edge="#0b132b",
    ),
    "high-contrast": _palette(
        "dark",
        "#ffffff",
        soft=0.4,
        strong=1.0,
        family="contrast",
        window="#000000",
        panel="#000000",
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
    # Light looks whatever pack sits underneath, as Poster is. Paper is warmer than Ink's light sheet
    # on purpose. Pastel's softness is in its surfaces; a pale lavender accent could not pass as text.
    "paper": _palette(
        "light",
        "#4a341e",
        soft=0.16,
        strong=0.30,
        window="#f7ecd2",
        panel="#fdf8ea",
        field="#fffcf2",
        grid="#fffcf2",
        text="#2f2418",
        muted="#6a5a45",
        error="#9b1b30",
        block_locked="#eadfc6",
        block_locked_ink="#2f2418",
        block_flex="#f3dca6",
        block_flex_ink="#3b2a05",
        block_edge="#a08a68",
    ),
    "pastel": _palette(
        "light",
        "#7a3e9d",
        soft=0.16,
        strong=0.30,
        window="#fdf2f8",
        panel="#ffffff",
        field="#fffafd",
        grid="#fffafd",
        text="#3b2a4a",
        muted="#6b5a7a",
        error="#b42318",
        block_locked="#ede4fb",
        block_locked_ink="#2e1f47",
        block_flex="#ffe4ef",
        block_flex_ink="#4a1230",
        block_edge="#a78bda",
    ),
    "ink": {
        "dark": _palette(
            "dark",
            "#eaeaea",
            soft=0.28,
            strong=0.50,
            window="#111111",
            panel="#111111",
            field="#111111",
            grid="#161616",
            text="#eaeaea",
            muted="#9a9a9a",
            error="#ff6b6b",
            block_locked="#111111",
            block_locked_ink="#eaeaea",
            block_flex="#111111",
            block_flex_ink="#eaeaea",
            block_edge="#9a9a9a",
        ),
        "light": _palette(
            "light",
            "#1a1a1a",
            strong=0.22,
            window="#f4f1ea",
            panel="#f4f1ea",
            field="#f4f1ea",
            grid="#efece4",
            text="#1a1a1a",
            muted="#5a5a5a",
            error="#9b1b30",
            block_locked="#f4f1ea",
            block_locked_ink="#1a1a1a",
            block_flex="#f4f1ea",
            block_flex_ink="#1a1a1a",
            block_edge="#1a1a1a",
        ),
    },
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
    is the pack with its own knobs; a preset is a bundle of knobs on the account's pack."""

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


def sanitize_look(raw: object) -> dict:
    clean: dict = {"preset": "default", "knobs": {}}
    if not isinstance(raw, dict):
        return clean
    if raw.get("preset") in LOOK_PRESETS:
        clean["preset"] = raw["preset"]
    stored = raw.get("knobs")
    knobs = stored if isinstance(stored, dict) else {}
    for knob, values in LOOK_KNOBS.items():
        value = knobs.get(knob)
        if value in values:
            clean["knobs"][knob] = value
    return clean


def effective_look(choice: dict | None) -> dict:
    selected = sanitize_look(choice)
    layered = {**LOOK_DEFAULTS, **LOOK_PRESETS[selected["preset"]], **selected["knobs"]}
    return layered


def preset_knobs(preset: object) -> dict:
    """Every knob as the preset alone sets it, which is what choosing that preset means."""
    return effective_look({"preset": preset, "knobs": {}})


def look_overrides(preset: object, shown: dict) -> dict:
    """Only the knobs a student moved away from the preset, so the preset keeps governing the rest."""
    bundle = preset_knobs(preset)
    return {knob: value for knob, value in shown.items() if knob in bundle and value != bundle[knob]}


def known_accent(name: object) -> str:
    return name if name in ACCENTS else "default"


def _preset_palette(preset: str, pack: object, system_dark: bool) -> dict | None:
    table = PRESET_PALETTES.get(preset)
    if table is None:
        return None
    if "axis" in table:
        return table
    theme = resolved_pack_theme(pack, system_dark)
    return table["dark" if theme in {"nocturne", "dark-frost"} else "light"]


def resolved_palette(pack: object, system_dark: bool, look: dict | None, accent: object = "default") -> dict:
    """The colours on screen: the preset's palette or the pack's, then the accent, then the surface knob."""
    choice = sanitize_look(look)
    pack_colours = PALETTES[resolved_pack_theme(pack, system_dark)]
    base = _preset_palette(choice["preset"], pack, system_dark) or pack_colours
    palette = dict(base)
    if choice["preset"] not in OWN_ACCENT:
        palette["accent"], palette["accent_ink"] = ACCENT_COLORS[known_accent(accent)][palette["axis"]]
    if effective_look(choice)["surface"] == "flat":
        # Flat has no raised surfaces: panels and inputs sit in the page and only hairlines divide them.
        palette["panel"] = palette["window"]
        palette["field"] = palette["window"]
    return palette


def category_paint(category: str | None, palette: dict) -> tuple[str | None, str | None]:
    """A category's fill and mark in this look, or (None, None) for none.

    A light look fills with the pale colour. On a dark one a pale fill glared off the page, so the fill
    there is the category's tone sunk into the look's own panel.
    """
    info = CATEGORIES.get(category or "")
    if info is None:
        return None, None
    family = palette.get("family", "light")
    if family == "light":
        return info["color"], info["mark"]
    tone, mark = info[family]
    return _sunk(tone, palette["panel"]), mark


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
    mode = effective_look(look)["blocks"]
    if mode == "outlined":
        return {"mode": mode, "fill": palette["grid"], "ink": palette["text"], "outline": mark, "edge": None}
    edge = mark if mode == "edge" else None
    if category_color:
        text = palette["text"]
        ink = text if contrast(text, category_color) >= AA_TEXT else readable_ink(category_color)
        return {"mode": mode, "fill": category_color, "ink": ink, "outline": None, "edge": edge}
    return {"mode": mode, "fill": neutral, "ink": neutral_ink, "outline": None, "edge": edge}


def _depth_rules(depth: str, palette: dict) -> str:
    # Qt stylesheets have no shadows. Depth is drawn with edges instead: a hairline for soft, nothing
    # for flat, and a heavy bottom and right edge for hard, which reads as a hard offset shadow.
    if depth == "flat":
        return "border: none;"
    if depth == "hard":
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
    chosen_edge = "none" if depth == "flat" else f"1px solid {palette['hairline_strong']}"
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
    ring = "transparent" if depth == "flat" else mix(palette["hairline_strong"], palette["panel"], 0.6)
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
    size = TEXT_PT[knobs["text"]]
    family = FONT_FAMILIES[knobs["font"]]
    radius, card_radius = CORNER_RADIUS[knobs["corners"]]
    edges = _depth_rules(knobs["depth"], palette)
    item_h = 36 if knobs["text"] == "large" else 22
    button_min = f" min-height: {item_h}px;" if knobs["text"] == "large" else ""
    field_min = FIELD_MIN_PX[knobs["text"]]
    # A flat look has no edges, so a plain button is told from its words by a faint fill instead.
    if knobs["depth"] == "flat":
        quiet_edge = f"background: {palette['hairline']}; border: none;"
    else:
        quiet_edge = f"background: transparent; border: 1px solid {palette['hairline_strong']};"
    # A flat look draws no lines at all, so its segments are told apart by the raised one alone.
    divider = "none" if knobs["depth"] == "flat" else f"1px solid {palette['hairline_strong']}"
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
        + planner_rules(palette, knobs["text"], pad, card_radius, edges)
    ) + (control_rules(palette, radius, size, art) if art is not None else "")


def planner_rules(palette: dict, text: str, pad: int, card_radius: int, edges: str) -> str:
    """Today's app around its hours: the plan bar, the rail, Day's agenda (decisions 13 to 18 of 0.17).
    Sizes from the type scale; section labels in the muted colour, never the accent, which read as
    links."""
    caption, body, heading = (f"{type_pt(role, text)}pt" for role in ("caption", "body", "heading"))
    link = (
        f"background: transparent; color: {palette['accent']}; border: none; "
        f"padding: 2px {pad // 2}px; min-height: 0; font-weight: {WEIGHT_STRONG};"
    )
    return (
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
