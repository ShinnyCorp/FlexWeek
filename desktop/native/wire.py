"""What crosses to the engine as JSON when Python's own JSON reader made the value.

`json.loads` reads NaN, Infinity and lone surrogates, which JSON text for the engine cannot hold.
`plain` writes them in a form the engine reads back as the same things: a non-finite float as the
one-key dict `{"\\u0000float": "nan"}`, a lone surrogate as a private-use character that `restore`
turns back. Everything else is `json.dumps` as it was.
"""

from __future__ import annotations

import json
import math
import re

NONFINITE = "\u0000float"
# U+D800..U+DFFF as U+10F800..U+10FFFF: the last planes' private-use block, which no real text uses.
_SURROGATE_BASE = 0x10F800
_PAIRS = {chr(code): chr(_SURROGATE_BASE + code - 0xD800) for code in range(0xD800, 0xE000)}
_BACK = {mapped: original for original, mapped in _PAIRS.items()}


def _mapped(text: str) -> str:
    return text.translate(str.maketrans(_PAIRS)) if any("\ud800" <= ch <= "\udfff" for ch in text) else text


def _clean(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return {NONFINITE: repr(value)}
    if isinstance(value, str):
        return _mapped(value)
    if isinstance(value, dict):
        return {_mapped(key) if isinstance(key, str) else key: _clean(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(item) for item in value]
    return value


# Text json.dumps made holds a lone surrogate as an escape, `\ud8xx` to `\udfxx`. A real emoji is a
# pair of them, so it takes the walk too, which only costs time.
_SURROGATE_ESCAPE = re.compile(r"\\u[dD][89a-fA-F]")
# What the engine sent back that `restore` has work for: the marker (as serde_json writes the NUL, or as
# the character itself), a mapped character raw, or either written as an escape.
_NEEDS_RESTORE = re.compile(
    r"\\u0000float|\x00float|[\U0010f800-\U0010ffff]|\\u[dD][89a-fA-F]", re.IGNORECASE
)


def plain(value: object) -> str:
    """Most values hold none of the three, and are written as they are; json.dumps itself refuses NaN
    and infinity, and the text shows a lone surrogate, so the walk runs only for those."""
    try:
        text = json.dumps(value, allow_nan=False)
    except ValueError:
        return json.dumps(_clean(value))
    if _SURROGATE_ESCAPE.search(text):
        return json.dumps(_clean(value))
    return text


def restore(value: object) -> object:
    """`value` as the engine sent it, with the private-use characters turned back to surrogates."""
    if isinstance(value, str):
        return value.translate(str.maketrans(_BACK)) if any(ch in _BACK for ch in value) else value
    if isinstance(value, dict):
        if list(value) == [NONFINITE]:
            return float(value[NONFINITE])
        return {restore(key) if isinstance(key, str) else key: restore(item) for key, item in value.items()}
    if isinstance(value, list):
        return [restore(item) for item in value]
    return value


def restored(text: str) -> object:
    """`restore(json.loads(text))`, without the walk when the text holds nothing to turn back."""
    value = json.loads(text)
    return restore(value) if _NEEDS_RESTORE.search(text) else value
