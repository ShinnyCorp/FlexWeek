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

from desktop.native.calendar import CATEGORIES
from desktop.native.look import (
    AA_TEXT,
    BASE_LABELS,
    LOOK_BASES,
    LOOK_PRESET_LABELS,
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
from desktop.native.tokens import fit_lightness

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
    """Every pair that reads under 4.5 to 1: text on the page, a card and the calendar, muted text on a
    card, and each block's words on its category's fill. Muted text follows from the text, so its fix
    moves the text; a block drawn on the card (Edge, Outline) is the text on the card or calendar."""
    look = {"preset": "default", "knobs": {}, "custom": custom}
    palette = resolved_palette("system", system_dark, look)
    text = palette["text"]
    found: list[Problem] = []
    for words, ink, ground in (
        ("Text on the page", text, palette["window"]),
        ("Text on a card", text, palette["panel"]),
        ("Text on the calendar", text, palette["grid"]),
        ("Muted text on a card", palette["muted"], palette["panel"]),
    ):
        ratio = contrast(ink, ground)
        if ratio < AA_TEXT:
            fixed = fit_lightness(text, (ground,), AA_TEXT)
            found.append(Problem(words, ink, ground, ratio, ("colours", "text"), fixed))
    for key, info in CATEGORIES.items():
        fill, mark = category_paint(key, palette)
        drawn = block_paint(look, palette, fill, info["kind"], mark)
        ratio = contrast(drawn["ink"], drawn["fill"])
        if drawn["fill"] == fill and ratio < AA_TEXT:
            fixed = fit_lightness(fill, (drawn["ink"],), AA_TEXT)
            words = f"{info['label']} blocks"
            found.append(Problem(words, drawn["ink"], fill, ratio, ("categories", key), fixed))
    return found


def apply_fix(custom: dict, problem: Problem) -> dict:
    """`custom` with the problem's colour moved. A category given as a hue becomes the exact colour."""
    fixed = dict(custom)
    group, key = problem.field
    if group == "colours":
        fixed["colours"] = {**custom.get("colours", {}), key: problem.fixed}
    else:
        fixed["categories"] = {**custom.get("categories", {}), key: {"colour": problem.fixed}}
    return fixed
