"""What a student does with a look of their own: start one, check it reads, keep it by name, share it.
No Qt.

A custom look is one of the ten looks as a starting point and what was changed on it (look.py's
`sanitize_custom` says what may be changed, and `resolved_palette` and `pack_stylesheet` draw it as they
draw the built-in looks). It is worn as the device look's "custom" entry, and kept by name in the look
file's "saved_looks" (plan, "Customise"). Settings builds its screen on these functions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from backend.tests.engine_ref.calendar import CATEGORIES
from backend.tests.engine_ref.tokens import fit_lightness, luminance, mix

from desktop.native.look import (
    AA_GRAPHIC,
    AA_TEXT,
    BASE_LABELS,
    LOOK_BASES,
    LOOK_PRESET_LABELS,
    MID_GREY,
    NAME_MAX,
    PACK_LABELS,
    block_paint,
    category_paint,
    contrast,
    effective_look,
    known_pack,
    resolved_palette,
    sanitize_custom,
    sanitize_look,
)

# Shown when a student has not named the look yet.
UNNAMED = "My look"
# The export file: its kind, so any other JSON is told apart, and the version of its settings.
FILE_KIND = "FlexWeek look"
FILE_VERSION = 1
FILE_MAX_BYTES = 64 * 1024
# A knob of the look on screen and the custom setting that carries it on.
KNOB_FIELDS = {"density": "spacing", "depth": "shadows", "blocks": "blocks"}


class LookNameError(ValueError):
    """A name a saved look cannot have, or one no saved look has. Its message is for the student."""


def base_of(pack: object, look: dict | None) -> str:
    """The id of the look on screen, as a custom look's base: its preset, or else its pack."""
    selected = sanitize_look(look)
    if "custom" in selected:
        return selected["custom"]["base"]
    if selected["preset"] != "default":
        return selected["preset"]
    return {"light-frost": "light", "dark-frost": "dark"}.get(known_pack(pack), known_pack(pack))


def start_custom(pack: object, look: dict | None, accent: object = "default") -> dict:
    """A custom look that draws as the look on screen does, to be changed from there: its base, the
    student's accent, and the knobs they had moved."""
    selected = sanitize_look(look)
    if "custom" in selected:
        return dict(selected["custom"])
    custom: dict = {"name": UNNAMED, "base": base_of(pack, selected)}
    if accent != "default":
        custom["accent"] = accent
    knobs = effective_look(selected)
    base_knobs = effective_look({"preset": LOOK_BASES[custom["base"]][1], "knobs": {}})
    for knob, field in KNOB_FIELDS.items():
        if knobs[knob] != base_knobs[knob]:
            custom[field] = knobs[knob]
    return sanitize_custom(custom)[0] or custom


def wear(look: dict | None, custom: dict) -> dict:
    """The device look with `custom` worn, its preset and knobs kept for when it is taken off."""
    selected = sanitize_look(look)
    return sanitize_look({**selected, "custom": custom})


def reset_look(custom: dict) -> dict:
    """Back to its base, as it was before anything was changed; the name stays."""
    return {key: custom[key] for key in ("name", "base") if key in custom}


# Saved looks.


def _name(name: object) -> str:
    if not isinstance(name, str) or not name.strip():
        raise LookNameError("A look needs a name.")
    clean = " ".join(name.split())
    if len(clean) > NAME_MAX:
        raise LookNameError(f"A look's name can be {NAME_MAX} letters at most.")
    built_in = {label.casefold() for label in (*BASE_LABELS.values(), *PACK_LABELS.values())}
    built_in |= {label.casefold() for label in LOOK_PRESET_LABELS.values()}
    if clean.casefold() in built_in:
        raise LookNameError(f"{clean} is one of FlexWeek's own looks. Choose another name.")
    return clean


def _find(saved: list[dict], name: str) -> int:
    for index, look in enumerate(saved):
        if look["name"].casefold() == name.casefold():
            return index
    return -1


def sanitize_saved(raw: object) -> list[dict]:
    """The saved looks from the look file: each a custom look with a name of its own. One that is
    broken or named twice is left out; the rest load."""
    kept: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        custom, _problems = sanitize_custom(item)
        if custom is None:
            continue
        try:
            custom["name"] = _name(custom.get("name"))
        except LookNameError:
            continue
        if _find(kept, custom["name"]) < 0:
            kept.append(custom)
    return kept


def save_look(saved: list[dict], custom: dict, name: object) -> list[dict]:
    """`custom` kept as `name`, in place of a saved look of that name or after the others."""
    clean = _name(name)
    kept = [dict(look) for look in saved]
    look = {**custom, "name": clean}
    at = _find(kept, clean)
    if at >= 0:
        kept[at] = look
    else:
        kept.append(look)
    return kept


def free_name(saved: list[dict], name: object) -> str:
    """`name` as a new saved look can have it: tidied, and numbered ("My look 2") past the saved looks
    that have it already, since `save_look` puts a look of the same name in their place."""
    clean = _name(name)
    stem = clean[: NAME_MAX - 3]
    free, count = clean, 2
    while _find(saved, free) >= 0:
        free, count = f"{stem} {count}", count + 1
    return free


def rename_look(saved: list[dict], old: str, new: object) -> list[dict]:
    at = _find(saved, old)
    if at < 0:
        raise LookNameError(f"No saved look is called {old}.")
    clean = _name(new)
    other = _find(saved, clean)
    if other >= 0 and other != at:
        raise LookNameError(f"There is already a look called {clean}.")
    kept = [dict(look) for look in saved]
    kept[at]["name"] = clean
    return kept


def duplicate_look(saved: list[dict], name: str) -> tuple[list[dict], str]:
    """A copy of the saved look `name` after it, as "<name> copy" (then "copy 2" and on), and its name."""
    at = _find(saved, name)
    if at < 0:
        raise LookNameError(f"No saved look is called {name}.")
    original = saved[at]["name"]
    stem = f"{original[: NAME_MAX - 8]} copy"
    copy, count = stem, 2
    while _find(saved, copy) >= 0:
        copy, count = f"{stem} {count}", count + 1
    kept = [dict(look) for look in saved]
    kept.insert(at + 1, {**saved[at], "name": copy})
    return kept, copy


def delete_look(saved: list[dict], name: str) -> list[dict]:
    if _find(saved, name) < 0:
        raise LookNameError(f"No saved look is called {name}.")
    return [dict(look) for look in saved if look["name"].casefold() != name.casefold()]


# Export and import.


def export_look(custom: dict) -> str:
    """A small file to share a look: what kind of file it is, its version, and the look."""
    clean = sanitize_custom(custom)[0] or {}
    return json.dumps({"kind": FILE_KIND, "version": FILE_VERSION, **clean}, indent=2) + "\n"


@dataclass(frozen=True)
class Imported:
    """A look read from a file: the look, or None when there is none to use, and what was wrong, in
    words a student can read. A look can come with notes about settings that were left out."""

    look: dict | None
    problems: tuple[str, ...]


def import_look(text: str | bytes) -> Imported:
    if len(text) > FILE_MAX_BYTES:
        return Imported(None, ("This file is too large to be a FlexWeek look.",))
    try:
        raw = json.loads(text)
    except ValueError:
        return Imported(None, ("This file is not a FlexWeek look: it could not be read as one.",))
    if not isinstance(raw, dict) or raw.get("kind") != FILE_KIND:
        return Imported(None, ("This file is not a FlexWeek look.",))
    version = raw.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        return Imported(None, ("This look file has no version FlexWeek can read.",))
    if version > FILE_VERSION:
        return Imported(None, ("This look was made by a newer FlexWeek. Update FlexWeek to open it.",))
    body = {key: value for key, value in raw.items() if key not in {"kind", "version"}}
    custom, problems = sanitize_custom(body)
    if custom is not None:
        custom.setdefault("name", UNNAMED)
    return Imported(custom, tuple(problems))


# The readability check.


@dataclass(frozen=True)
class Problem:
    """A pair of colours that reads under 4.5 to 1, and the fix: `field` set to `fixed`, the colour the
    student chose with its OKLCH lightness moved the least it takes for the pair to pass."""

    words: str
    ink: str
    ground: str
    ratio: float
    field: tuple[str, ...]
    fixed: str


def readability(custom: dict, system_dark: bool = False) -> list[Problem]:
    """Every pair that reads under 4.5 to 1, named as the Customise mock-up names them: text and muted
    text on the page, cards and the calendar, accent text on cards, text on accent buttons, and each
    block's words on its category's fill; the now line is held to 3 to 1, as a line. Text and muted text
    are moved to read on every surface at once, and the text on the blocks too, but for a block on the
    other side of mid-grey from the page: no one text reads on both, so that block keeps its own Fix.
    An outlined block is the text on the calendar."""
    look = {"preset": "default", "knobs": {}, "custom": custom}
    palette = resolved_palette("system", system_dark, look)
    surfaces = (palette["window"], palette["panel"], palette["grid"])
    text, muted, accent = palette["text"], palette["muted"], palette["accent"]
    own_accent = str(custom.get("accent", "")).startswith("#")
    tint = mix(accent, palette["window"], 0.10)
    blocks = []
    for key, info in CATEGORIES.items():
        fill, mark = category_paint(key, palette)
        drawn = block_paint(look, palette, fill, info["kind"], mark)
        if drawn["fill"] == fill:
            blocks.append((key, info["label"], fill, drawn["ink"]))
    dark_page = luminance(palette["window"]) < MID_GREY
    alike = tuple(fill for _key, _label, fill, _ink in blocks if (luminance(fill) < MID_GREY) == dark_page)
    under = surfaces + alike
    text_fixed = fit_lightness(text, under, AA_TEXT)
    if min(contrast(text_fixed, ground) for ground in under) < AA_TEXT:
        text_fixed = fit_lightness(text, surfaces, AA_TEXT)
    found: list[Problem] = []
    for words, ink, ground, field in (
        ("Text on the page", text, palette["window"], "text"),
        ("Text on cards", text, palette["panel"], "text"),
        ("Text on the calendar", text, palette["grid"], "text"),
        ("Muted text on the page", muted, palette["window"], "muted"),
        ("Muted text on cards", muted, palette["panel"], "muted"),
        ("Accent text on cards", accent, palette["panel"], "accent"),
        ("Plan button words", accent, tint, "accent"),
        ("Today's day name", accent, palette["grid"], "accent"),
        ("Now line", palette["text"] if custom.get("now_line") == "text" else accent,
         palette["grid"], "accent"),
        ("Text on accent buttons", palette["accent_ink"], accent, "accent"),
    ):
        if field == "accent" and not own_accent:
            continue
        # The now line is a line, fitted to 3 to 1 as the look draws it; the rest is text.
        need = AA_GRAPHIC if words == "Now line" else AA_TEXT
        ratio = contrast(ink, ground)
        if ratio < need:
            if field == "accent":
                # Its words on the page and cards, and white or black on it, which any colour reads.
                fixed = fit_lightness(accent, surfaces + (tint,), need)
                found.append(Problem(words, ink, ground, ratio, ("accent",), fixed))
                continue
            fixed = text_fixed if field == "text" else fit_lightness(ink, surfaces, AA_TEXT)
            found.append(Problem(words, ink, ground, ratio, ("colours", field), fixed))
    for key, label, fill, ink in blocks:
        ratio = contrast(ink, fill)
        if ratio < AA_TEXT:
            fixed = fit_lightness(fill, (ink,), AA_TEXT)
            found.append(Problem(f"Text on {label} blocks", ink, fill, ratio, ("categories", key), fixed))
    return found


def apply_fix(custom: dict, problem: Problem) -> dict:
    """`custom` with the problem's colour moved. A category given as a hue becomes the exact colour."""
    fixed = dict(custom)
    group, key = (*problem.field, "")[:2]
    if group == "accent":
        fixed["accent"] = problem.fixed
    elif group == "colours":
        fixed["colours"] = {**custom.get("colours", {}), key: problem.fixed}
    else:
        fixed["categories"] = {**custom.get("categories", {}), key: {"colour": problem.fixed}}
    return fixed
