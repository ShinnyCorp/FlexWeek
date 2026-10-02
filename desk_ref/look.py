"""The look functions as they were at 6e86802, before `desktop/native/look.py` called the engine for
them: `sanitize_custom`, `sanitize_look`, `effective_look` and `known_pack`, with the helpers only they
use. `desk_ref/custom_look.py` reads these, so the comparison with the engine's own is not the engine
against itself. The tables they read are look.py's, which the engine's are held equal to by
`test_the_look_tables_in_the_engine_are_the_ones_in_look_py`.
"""

from __future__ import annotations

import math

from desk_ref.calendar import CATEGORIES
from desk_ref.tokens import TEXT_SCALE
from desktop.native.look import (
    ACCENTS,
    CORNER_RADIUS,
    CUSTOM_CHOICES,
    CUSTOM_COLOURS,
    CUSTOM_RANGES,
    CUSTOM_SWITCHES,
    FONT_PAIRS,
    HEX,
    LEGACY_KNOBS,
    LOOK_BASES,
    LOOK_DEFAULTS,
    LOOK_KNOBS,
    LOOK_PRESETS,
    NAME_MAX,
    PACKS,
)


def known_pack(pack: object) -> str:
    return pack if pack in PACKS else "system"


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
    if selected["preset"] == "paper" and knobs["font"] == "serif":
        body = "serif"
    body, heading = custom.get("body_font", body), custom.get("heading_font", heading)
    if (body, heading) != FONT_PAIRS[knobs["font"]]:
        knobs["font"] = "mono" if body == "mono" else "serif" if "serif" in (body, heading) else "sans"
    if "text_scale" in custom:
        knobs["text"] = _nearest(custom["text_scale"], TEXT_SCALE)
    if "corners" in custom:
        cards = {name: card for name, (_control, card) in CORNER_RADIUS.items()}
        knobs["corners"] = _nearest(custom["corners"], cards)
    return knobs
