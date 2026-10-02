"""What crosses to the engine as JSON when Python's own JSON reader made the value.

`json.loads` reads NaN, Infinity and lone surrogates, which JSON text for the engine cannot hold.
`plain` writes them in a form the engine reads back as the same things: a non-finite float as the
one-key dict `{"\\u0000float": "nan"}`, a lone surrogate as a private-use character that `restore`
turns back. Everything else is `json.dumps` as it was.
"""

from __future__ import annotations

import json
import math

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


def plain(value: object) -> str:
    return json.dumps(_clean(value))


def restore(value: object) -> object:
    """`value` as the engine sent it, with the private-use characters turned back to surrogates."""
    if isinstance(value, str):
        return value.translate(str.maketrans(_BACK)) if any(ch in _BACK for ch in value) else value
    if isinstance(value, dict):
        return {restore(key) if isinstance(key, str) else key: restore(item) for key, item in value.items()}
    if isinstance(value, list):
        return [restore(item) for item in value]
    return value
