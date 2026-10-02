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

import flexweek_engine  # type: ignore[import-untyped]

from desktop.native.calendar import CATEGORIES
from desktop.native.look import (
    BASE_LABELS,
    LOOK_BASES,
    LOOK_PRESET_LABELS,
    NAME_MAX,
    PACK_LABELS,
    block_paint,
    category_paint,
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
    return json.loads(flexweek_engine.look_reset(json.dumps(custom)))


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
    try:
        return json.loads(
            flexweek_engine.look_save(
                json.dumps(saved),
                json.dumps(custom),
                name if isinstance(name, str) else "",
            )
        )
    except ValueError as err:
        raise LookNameError(str(err)) from err



def free_name(saved: list[dict], name: object) -> str:
    """`name` as a new saved look can have it: tidied, and numbered ("My look 2") past the saved looks
    that have it already, since `save_look` puts a look of the same name in their place."""
    try:
        return str(flexweek_engine.free_name(json.dumps(saved), name if isinstance(name, str) else ""))
    except ValueError as err:
        raise LookNameError(str(err)) from err



def rename_look(saved: list[dict], old: str, new: object) -> list[dict]:
    try:
        return json.loads(
            flexweek_engine.rename_look(json.dumps(saved), old, new if isinstance(new, str) else "")
        )
    except ValueError as err:
        raise LookNameError(str(err)) from err



def duplicate_look(saved: list[dict], name: str) -> tuple[list[dict], str]:
    """A copy of the saved look `name` after it, as "<name> copy" (then "copy 2" and on), and its name."""
    try:
        kept, copy = flexweek_engine.duplicate_look(json.dumps(saved), name)
    except ValueError as err:
        raise LookNameError(str(err)) from err
    return json.loads(kept), copy



def delete_look(saved: list[dict], name: str) -> list[dict]:
    try:
        return json.loads(flexweek_engine.delete_look(json.dumps(saved), name))
    except ValueError as err:
        raise LookNameError(str(err)) from err



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
    """Every pair that reads under 4.5 to 1, named as the Customise mock-up names them."""
    look = {"preset": "default", "knobs": {}, "custom": custom}
    palette = resolved_palette("system", system_dark, look)
    blocks = []
    for key, info in CATEGORIES.items():
        fill, mark = category_paint(key, palette)
        drawn = block_paint(look, palette, fill, info["kind"], mark)
        if drawn["fill"] == fill:
            blocks.append({"key": key, "label": info["label"], "fill": fill, "ink": drawn["ink"]})
    found = json.loads(
        flexweek_engine.look_readability(
            json.dumps(custom),
            json.dumps(
                {
                    name: palette[name]
                    for name in ("window", "panel", "grid", "text", "muted", "accent", "accent_ink")
                }
            ),
            json.dumps(blocks),
        )
    )
    return [
        Problem(
            item["words"],
            item["ink"],
            item["ground"],
            item["ratio"],
            tuple(item["field"]),
            item["fixed"],
        )
        for item in found
    ]



def apply_fix(custom: dict, problem: Problem) -> dict:
    """`custom` with the problem's colour moved. A category given as a hue becomes the exact colour."""
    return json.loads(
        flexweek_engine.look_apply_fix(
            json.dumps(custom),
            json.dumps(
                {
                    "words": problem.words,
                    "ink": problem.ink,
                    "ground": problem.ground,
                    "ratio": problem.ratio,
                    "field": list(problem.field),
                    "fixed": problem.fixed,
                }
            ),
        )
    )
