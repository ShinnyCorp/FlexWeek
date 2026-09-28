"""The layouts a student can pick, and what each lets them change.

A layout is a whole way of showing the week, where a look is only paint. There are two roles. A main
view is where planning happens, so it has to offer the whole week, what has no time yet, Add, Plan and
opening a block by itself. A day screen is what you watch once planning is done, so it offers what is
on now, Done, Start focus, Running late and the way back.

Customising comes in three levels, and the dialog is built from this table rather than by hand:
  1. pick   which main view and which day screen
  2. style  each design's colourways, one of which always follows the student's own look
  3. detail what that design shows and how densely

This module is plain data with no Qt in it, so the choices can be checked without a screen.
"""

from __future__ import annotations

from dataclasses import dataclass

from desktop.native.layouts.colourways import BENTO, CLAY, DIAL, MISSION, ONE, RETRO, TIMELINE, Colourways
from desktop.native.look import AA_TEXT, contrast, mix, readable_ink
from desktop.native.tokens import fit_lightness

MATCH = "match"


@dataclass(frozen=True)
class Choice:
    value: str
    label: str


@dataclass(frozen=True)
class Option:
    key: str
    label: str
    level: str
    choices: tuple[Choice, ...]

    @property
    def default(self) -> str:
        return self.choices[0].value

    @property
    def values(self) -> tuple[str, ...]:
        return tuple(choice.value for choice in self.choices)


@dataclass(frozen=True)
class LayoutSpec:
    id: str
    role: str
    label: str
    summary: str
    options: tuple[Option, ...] = ()
    colourways: Colourways = ()
    # What the view is for, in a student's words. The style name alone ("Bento", "Today's app") did
    # not say that one is a dashboard and the other the plain calendar.
    purpose: str = ""
    # Offered after the standard designs, under EXPERIMENTAL. Kept, never deleted: a saved choice of
    # one still opens.
    experimental: bool = False


def _colour(spec_colourways: Colourways) -> Option:
    """Match my look first, so it is what a design wears until a student picks one of its own
    colourways (decision 3 of 0.17). A colourway saved before then still loads as saved."""
    named = tuple(Choice(value, label) for value, label, _ in spec_colourways)
    return Option("colour", "Colours", "style", (Choice(MATCH, "Match my look"), *named))


def _show(key: str, label: str, level: str = "detail") -> Option:
    return Option(key, label, level, (Choice("show", "Show"), Choice("hide", "Hide")))


LAYOUTS: dict[str, LayoutSpec] = {
    spec.id: spec
    for spec in (
        LayoutSpec(
            "classic",
            "plan",
            "Today's app",
            "The week grid with the sidebar. Its colours are the Look menu.",
            purpose="Calendar",
        ),
        LayoutSpec(
            "timeline",
            "plan",
            "Timeline",
            "The week as a paper planner opened flat, and a day as its page of hours beside its notes.",
            (
                _colour(TIMELINE),
                Option(
                    "density",
                    "Spacing",
                    "style",
                    (Choice("comfortable", "Comfortable"), Choice("compact", "Compact")),
                ),
                _show("finished", "Finished and past items"),
            ),
            TIMELINE,
            purpose="Agenda",
        ),
        LayoutSpec(
            "mission",
            "plan",
            "Mission control",
            "Today in numbers across the top, the days as lanes of hours, and deadlines by time left.",
            (_colour(MISSION), _show("figures", "Figures across the top")),
            MISSION,
            purpose="Dashboard",
            experimental=True,
        ),
        LayoutSpec(
            "bento",
            "plan",
            "Bento",
            "A live day or week in one big tile, with homework and deadlines beside it.",
            (
                _colour(BENTO),
                Option(
                    "corners", "Tile corners", "style", (Choice("soft", "Soft"), Choice("square", "Square"))
                ),
                Option(
                    "tiles", "Supporting tiles", "detail",
                    (Choice("all", "All"), Choice("essentials", "Hero and tray only")),
                ),
            ),
            BENTO,
            purpose="Dashboard",
            experimental=True,
        ),
        LayoutSpec(
            "retro",
            "plan",
            "Retro desktop",
            "Schedule.exe and Week.exe, a deadlines notepad, and a taskbar.",
            (
                _colour(RETRO),
                Option(
                    "windows",
                    "Windows open at start",
                    "detail",
                    (Choice("all", "All three"), Choice("week", "Main window only")),
                ),
            ),
            RETRO,
            purpose="Dashboard",
            experimental=True,
        ),
        LayoutSpec(
            "clay",
            "plan",
            "Clay deck",
            "One day at a time on a large card, the days either side peeking, moved with the arrows.",
            (_colour(CLAY), _show("peek", "Days either side")),
            CLAY,
            purpose="Agenda",
            experimental=True,
        ),
        LayoutSpec(
            "dial",
            "day",
            "Day dial",
            "The day as a clock face, read out hour by hour beside it.",
            (
                _colour(DIAL),
                _show("list", "Hour by hour list"),
                _show("week", "Small dials for the week"),
            ),
            DIAL,
            purpose="Clock",
        ),
        LayoutSpec(
            "one",
            "day",
            "One thing",
            "The whole window is the thing that is on now.",
            (
                _colour(ONE),
                Option(
                    "lead",
                    "Lead with",
                    "detail",
                    (Choice("now", "What is on now"), Choice("next", "What is next")),
                ),
                _show("actions", "Buttons"),
                _show("daybar", "Day bar"),
            ),
            ONE,
            purpose="Focus",
            experimental=True,
        ),
    )
}
MAIN_DEFAULT, DAY_DEFAULT = "classic", "dial"
LEVELS = (("style", "Style"), ("detail", "Fine-tune"))
EXPERIMENTAL = "Experimental styles"


def layouts_for(role: str, experimental: bool | None = None) -> tuple[LayoutSpec, ...]:
    """The designs for `role`, the standard ones first; only one kind when `experimental` is given."""
    chosen = [spec for spec in LAYOUTS.values() if spec.role == role]
    if experimental is not None:
        chosen = [spec for spec in chosen if spec.experimental == experimental]
    return tuple(sorted(chosen, key=lambda spec: spec.experimental))


def sanitize_layout(raw: object) -> dict:
    """Whatever the file on disk says, hand back a choice this build can show."""
    clean: dict = {"main": MAIN_DEFAULT, "day": DAY_DEFAULT, "options": {}}
    if not isinstance(raw, dict):
        return clean
    for slot, role in (("main", "plan"), ("day", "day")):
        spec = LAYOUTS.get(raw.get(slot)) if isinstance(raw.get(slot), str) else None
        if spec is not None and spec.role == role:
            clean[slot] = spec.id
    stored = raw.get("options")
    for layout_id, values in (stored if isinstance(stored, dict) else {}).items():
        spec = LAYOUTS.get(layout_id) if isinstance(layout_id, str) else None
        if spec is None or not isinstance(values, dict):
            continue
        kept = {
            option.key: values[option.key]
            for option in spec.options
            if values.get(option.key) in option.values
        }
        if kept:
            clean["options"][layout_id] = kept
    return clean


def options_for(choice: dict | None, layout_id: str) -> dict[str, str]:
    """Every option of a layout, as the student set it or as the design ships."""
    stored = sanitize_layout(choice)["options"].get(layout_id, {})
    return {option.key: stored.get(option.key, option.default) for option in LAYOUTS[layout_id].options}


def _tint(accent: str, surface: str, share: float, inks: tuple[str, ...], bg: str, floor: float = 4.5) -> str:
    """As much of the accent as the text on it can take, without vanishing into the page.

    The four cards keep their relative shares. If the strongest would disappear into `bg`, the
    whole set is scaled up to the last mix the inks can still read.
    """

    def readable(colour: str) -> bool:
        return all(contrast(ink, colour) >= floor for ink in inks)

    def paint(amount: float) -> str:
        return mix(accent, surface, amount)

    max_ok = 0.0
    for step in range(1, 99):
        amount = step / 100
        if readable(paint(amount)):
            max_ok = amount
    if max_ok == 0:
        return surface
    strongest = 0.22
    peak = min(strongest, max_ok)
    amount = min(share, max_ok)
    if max_ok > strongest and contrast(paint(peak), bg) < 3.0:
        amount = min(share * max_ok / strongest, max_ok)
    colour = paint(amount)
    return colour if readable(colour) else surface


def _fill(accent: str, surface: str, floor: float = 1.8) -> str:
    """A block of colour that carries no text, only has to be seen.

    The card tints are held down by the text that sits on them, which left Bento's load bars at
    1.27 to 1 against their tile in the median look and 1.01 at worst. A bar has no text on it, so
    it is free to be as strong as it needs to be.
    """
    for step in range(20, 101, 5):
        colour = mix(accent, surface, step / 100)
        if contrast(colour, surface) >= floor:
            return colour
    return accent


def complete(tokens: dict[str, str]) -> dict[str, str]:
    """Fill in what a colourway leaves out from its own colours, never from another palette: white text
    from one over a pale card from another measured 1.15 to 1."""
    inks = (tokens["text"], tokens["muted"])
    cards = {
        f"card_{name}": _tint(tokens["accent"], tokens["surface"], share, inks, tokens["bg"])
        for name, share in zip("abcd", (0.10, 0.16, 0.22, 0.13), strict=True)
    }
    return {
        "cta": tokens["accent"],
        "cta_ink": tokens["accent_ink"],
        "fill": _fill(tokens["accent"], tokens["surface"]),
        **cards,
        **tokens,
    }


def match_tokens(palette: dict) -> dict[str, str]:
    """A design in the student's own look: the colours the rest of the app is already wearing. Its
    cards are the look's cards, never tinted with the accent, which is not spread over anything larger
    than a control (decision 1 of 0.17). On a flat look, where cards sit in the page, a little of the
    text colour tells them from it."""
    surface, page = palette["panel"], palette["window"]
    card = surface if contrast(surface, page) >= 1.02 else mix(palette["text"], page, 0.05)
    return complete(
        {
            **{f"card_{name}": card for name in "abcd"},
            "bg": palette["window"],
            "bg_ink": palette["text"],
            "bg_muted": palette["muted"],
            "surface": palette["panel"],
            "text": palette["text"],
            "muted": palette["muted"],
            "accent": palette["accent"],
            "accent_ink": palette["accent_ink"],
            "line": mix(palette["text"], palette["panel"], 0.22),
            "danger": palette["error"],
            "danger_ink": readable_ink(palette["error"]),
        }
    )


def tokens_for(layout_id: str, colour: str, palette: dict) -> dict[str, str]:
    """The colours a layout paints with. Every design can ask for every token, so a view never has to
    guard a missing key."""
    chosen = next((tokens for value, _, tokens in LAYOUTS[layout_id].colourways if value == colour), None)
    if chosen is None:
        return match_tokens(palette)
    if "accent" in chosen:
        return complete(chosen)
    # A colourway that names no accent, as One thing's Poster and Day dial's Night, wears the
    # student's own. Its lightness moves as little as it takes to read on the colourway's page, as
    # the look moves it for the look's: a light look's blue on Poster's black read at 4.2 to 1.
    accent = fit_lightness(palette["accent"], (chosen["bg"], chosen["surface"]), AA_TEXT)
    ink = palette["accent_ink"] if accent == palette["accent"] else readable_ink(accent)
    return complete({"accent": accent, "accent_ink": ink, **chosen})


def contrast_failures(tokens: dict[str, str], floor: float = 4.5) -> list[str]:
    """Every pair of colours a layout puts text on, held to AA, and every card tint against the page.

    The pairs come from the token names: `x_ink` is text on `x`, `text` and `muted` sit on `surface`
    and on every `card_`, `bg_muted` on `bg`. A `card_` that is the same colour as `bg` is a load bar
    that disappears.
    """
    pairs = [(f"{key}", tokens[key], tokens[key[:-4]]) for key in tokens if key.endswith("_ink")]
    pairs += [(name, tokens[name], tokens["surface"]) for name in ("text", "muted")]
    pairs += [("bg_muted", tokens["bg_muted"], tokens["bg"])]
    pairs += [
        (f"{name} on {key}", tokens[name], tokens[key])
        for key in tokens
        if key.startswith("card_")
        for name in ("text", "muted")
    ]
    pairs += [(f"{key} on bg", tokens[key], tokens["bg"]) for key in tokens if key.startswith("card_")]
    pairs += [("fill on surface", tokens["fill"], tokens["surface"])]
    failed = []
    for label, ink, paper in pairs:
        ratio = contrast(ink, paper)
        if label == "fill on surface":
            need = 1.8
        elif label.endswith(" on bg"):
            need = 1.01
        else:
            need = floor
        if ratio < need:
            failed.append(f"{label} {ratio:.2f}")
    return failed
